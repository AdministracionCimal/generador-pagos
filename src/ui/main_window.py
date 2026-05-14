from datetime import date
from decimal import Decimal
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QCompleter, QDialog, QDialogButtonBox, QFileDialog, QFrame,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMenu, QMenuBar,
    QMessageBox, QProgressBar, QPushButton, QStatusBar, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

import src.config as config
from src.api.client import ApiError, AuthError, FinnegansClient
from src.domain.clasificador import clasificar
from src.domain.fraccionador import fraccionar_proveedor
from src.domain.mapper import armar_post
from src.domain.models import Modalidad, OpPago, ProveedorTanda
from src.excel.dm_reader import leer_dm
from src.ui import theme
from src.ui.preview_dialog import PreviewDialog
from src.ui.result_dialog import ResultDialog
from src.ui.settings_dialog import SettingsDialog

# Estado interno → (label, variante visual)
def _hint(text: str) -> QLabel:
    lbl = QLabel(text); lbl.setObjectName("CardHint")
    return lbl


_ESTADOS = {
    "LISTO":     ("Listo",           "success"),
    "MANUAL":    ("Carga manual",    "warning"),
    "EXCEDE":    ("Excede chequera", "danger"),
    "SIN_ITEMS": ("Sin ítems",       "danger"),
}

_COLS = ["Proveedor", "CUIT", "Importe", "Modalidad", "Cheques", "Estado"]


class _PrecargarWorker(QThread):
    progreso = pyqtSignal(str)
    listo    = pyqtSignal(object, object, object, object, object)  # cotizacion_dolar, ret_cache, ratios_fc, docs_pendientes, cotizacion_fallback
    error    = pyqtSignal(str)

    def __init__(self, proveedores: list, cfg: dict) -> None:
        super().__init__()
        self._proveedores = proveedores
        self._cfg = cfg

    def run(self) -> None:
        cfg = self._cfg
        client = FinnegansClient(cfg["base_url"], cfg["client_id"], cfg["client_secret"])

        cotizacion_fallback = False
        try:
            cotiz = client.get_cotizacion_dolar(date.today().strftime("%Y-%m-%d"))
            cotizacion_dolar = Decimal(str(cotiz))
            if cotizacion_dolar <= Decimal("1"):
                cotizacion_fallback = True
        except Exception:
            cotizacion_dolar = Decimal("1")
            cotizacion_fallback = True

        cache: dict = {}
        codigos_ret_cargados: dict = {}
        ratios_fc: dict = {}

        empresa    = cfg.get("empresa_codigo", "")
        mes_inicio = date.today().replace(day=1).strftime("%Y-%m-%d")
        mes_hoy    = date.today().strftime("%Y-%m-%d")

        provs = [
            p for p in self._proveedores
            if p.modalidad != Modalidad.MANUAL and p.items and p.cuit
        ]
        total = len(provs)

        for i, p in enumerate(provs):
            self.progreso.emit(f"Consultando proveedor {i + 1} de {total}: {p.nombre}")
            try:
                prov_data    = client.get_proveedor(p.cuit)
                percepciones = prov_data.get("Percepciones", [])
                maestros: dict = {}
                for perc in percepciones:
                    cod = perc.get("RetencionCodigo")
                    if not cod:
                        continue
                    if cod not in codigos_ret_cargados:
                        try:
                            codigos_ret_cargados[cod] = client.get_retencion(cod)
                        except Exception:
                            codigos_ret_cargados[cod] = {}
                    maestros[cod] = codigos_ret_cargados[cod]

                historico: dict = {}
                tiene_retencion = any(m.get("RetencionItems") for m in maestros.values())
                if tiene_retencion:
                    try:
                        cuit_limpio = p.cuit.replace("-", "").replace(".", "")
                        rows_all = client.get_analisis_retencion(
                            cuit_limpio, mes_inicio, mes_hoy, ""
                        )
                        rows = [
                            r for r in rows_all
                            if not empresa
                            or r.get("EMPRESAPADRECODIGO", "") == empresa
                            or r.get("EMPRESAPADRECODIGO", "").removeprefix("EMPRESA_") == empresa.removeprefix("EMPRESA_")
                        ]
                        for row in rows:
                            cod_tipo = row.get("RETENCIONTIPOCODIGO", "")
                            cod_esp  = row.get("RETENCIONCODIGO", "")
                            nombre   = row.get("RETENCIONTIPO", cod_tipo or cod_esp).strip()
                            isar_inc = Decimal(str(row.get("ISAR", 0)))
                            imp_inc  = Decimal(str(row.get("IMPORTE", 0)))
                            for key in {k for k in (cod_tipo, cod_esp) if k}:
                                if key not in historico:
                                    historico[key] = {
                                        "isar_historico": Decimal("0"),
                                        "ya_retenido":    Decimal("0"),
                                        "nombre":         nombre,
                                    }
                                historico[key]["isar_historico"] += isar_inc
                                historico[key]["ya_retenido"]    += imp_inc
                    except Exception:
                        pass

                cache[p.cuit] = (percepciones, maestros, historico)

                if tiene_retencion:
                    for item in p.items:
                        doc = item.documento
                        if not doc.lower().startswith("fc -") or doc in ratios_fc:
                            continue
                        try:
                            fc       = client.get_factura_compra(doc)
                            gravado  = sum(
                                Decimal(str(c.get("ConceptoImporteGravado", 0)))
                                for c in fc.get("Conceptos", [])
                            )
                            total_fc = Decimal(str(fc.get("ImporteTotalControl", 0)))
                            if total_fc > 0:
                                ratios_fc[doc] = gravado / total_fc
                        except Exception:
                            pass
            except Exception:
                pass

        # Verificar saldos pendientes por proveedor (composicionSaldoProveedor)
        # Una llamada por CUIT en vez de una por comprobante.
        # docs_pendientes[cuit] = set de IDENTIFICACIONEXTERNA con saldo abierto.
        # None = consulta falló → fail-open (no bloquear).
        docs_pendientes: dict[str, set | None] = {}
        cuits_a_verificar = sorted({
            p.cuit for p in self._proveedores
            if p.cuit and p.modalidad != Modalidad.MANUAL
        })
        fecha_hoy = date.today().strftime("%Y-%m-%d")
        n_cuits = len(cuits_a_verificar)
        for i, cuit in enumerate(cuits_a_verificar):
            self.progreso.emit(f"Verificando saldo {i + 1}/{n_cuits}: {cuit}")
            try:
                rows = client.get_composicion_saldo_proveedor(cuit, fecha_hoy)
                docs_pendientes[cuit] = {
                    r["IDENTIFICACIONEXTERNA"]
                    for r in rows
                    if r.get("IDENTIFICACIONEXTERNA")
                    and float(r.get("IMPORTEMONTRAN", 0) or 0) != 0
                }
            except Exception:
                docs_pendientes[cuit] = None  # fail-open: incluir todos

        self.listo.emit(cotizacion_dolar, cache, ratios_fc, docs_pendientes, cotizacion_fallback)


class _ChiquerasLoader(QThread):
    listo = pyqtSignal(list, object)   # (talonarios activos, detalle talonario seleccionado | None)
    error = pyqtSignal(str)

    def __init__(self, base_url, client_id, secret, selected_code: str = ""):
        super().__init__()
        self._url, self._id, self._secret = base_url, client_id, secret
        self._selected_code = selected_code

    def run(self):
        try:
            from src.api.client import FinnegansClient
            c = FinnegansClient(self._url, self._id, self._secret)
            talonarios = c.get_talonario_list()
            activos = sorted(
                [t for t in talonarios if t.get("Activo", t.get("activo", True))],
                key=lambda t: t.get("Nombre", t.get("nombre", "")),
            )
            # Traer detalle del talonario actualmente seleccionado
            detail = None
            if self._selected_code:
                try:
                    detail = c.get_talonario(self._selected_code)
                except Exception:
                    pass
            self.listo.emit(activos, detail)
        except Exception as e:
            self.error.emit(str(e))


class _ProcesarWorker(QThread):
    progreso = pyqtSignal(int, str)       # (fila_tabla, mensaje)
    terminado = pyqtSignal(list)          # lista de resultados

    def __init__(self, ops: list[OpPago], client: FinnegansClient) -> None:
        super().__init__()
        self._ops = ops
        self._client = client

    def run(self) -> None:
        resultados = []
        for i, op in enumerate(self._ops):
            nombre = op.proveedor.nombre
            try:
                payload = armar_post(op)
                resp = self._client.crear_op(payload)
                numero = resp.get("documento") or resp.get("NumeroComprobante") or resp.get("numeroComprobante") or "OK"
                self.progreso.emit(i, f"OK → {numero}")
                resultados.append({
                    "nombre": nombre,
                    "estado": "OK",
                    "detalle": numero,
                    "importe": float(op.proveedor.importe_total),
                })
            except (ApiError, AuthError) as e:
                self.progreso.emit(i, f"ERROR: {e}")
                resultados.append({
                    "nombre": nombre,
                    "estado": "ERROR",
                    "detalle": str(e),
                    "importe": float(op.proveedor.importe_total),
                })
            except Exception as e:
                self.progreso.emit(i, f"ERROR: {e}")
                resultados.append({
                    "nombre": nombre,
                    "estado": "ERROR",
                    "detalle": str(e),
                    "importe": float(op.proveedor.importe_total),
                })
        self.terminado.emit(resultados)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Generador de Pagos — Finnegans")
        self.resize(1080, 680)
        self.setMinimumSize(880, 560)
        self._cfg = config.load()
        self._proveedores: list[ProveedorTanda] = []
        self._ops_a_procesar: list[OpPago] = []
        self._worker: _ProcesarWorker | None = None
        self._precarga_worker: _PrecargarWorker | None = None
        self._ultimo_cheque: int = 0
        self._build_ui()
        self._build_menu()
        if not config.is_configured(self._cfg):
            QTimer.singleShot(0, self._abrir_settings)
        else:
            QTimer.singleShot(500, lambda: self._cargar_chequeras(silent=True))

    # ── construcción ──────────────────────────────────────────────────────

    def _build_menu(self) -> None:
        mb = QMenuBar(self)
        menu = mb.addMenu("Archivo")
        menu.addAction("Configuración", self._abrir_settings)
        menu.addSeparator()
        menu.addAction("Salir", self.close)
        self.setMenuBar(mb)

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(28, 22, 28, 16)
        root.setSpacing(16)

        # — Header ——————————————————————————————————————————————————————
        header = QVBoxLayout(); header.setSpacing(2)
        title = QLabel("Generador de Pagos"); title.setObjectName("PageTitle")
        subtitle = QLabel("Cargá la planilla autorizada y enviá las órdenes a Finnegans.")
        subtitle.setObjectName("PageSubtitle")
        header.addWidget(title)
        header.addWidget(subtitle)
        root.addLayout(header)

        # — Card: archivo ————————————————————————————————————————————————
        self._lbl_archivo = QLabel("Sin archivo cargado")
        self._lbl_archivo.setObjectName("Muted")
        btn_cargar = QPushButton("Cargar Excel…")
        btn_cargar.clicked.connect(self._cargar_excel)
        root.addWidget(self._card_archivo(btn_cargar))

        # — Card: chequera ———————————————————————————————————————————————
        saved_cod = self._cfg.get("chequera_codigo", "")
        self._combo_cheq = QComboBox()
        self._combo_cheq.setEditable(True)
        self._combo_cheq.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._combo_cheq.setMinimumWidth(220)
        self._combo_cheq.setPlaceholderText("ej. MACRO CPDProv 03")
        completer = QCompleter()
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._combo_cheq.setCompleter(completer)
        if saved_cod:
            self._combo_cheq.addItem(saved_cod, saved_cod)
            self._combo_cheq.setCurrentIndex(0)
        self._combo_cheq.activated.connect(self._on_chequera_seleccionada)

        self._btn_cargar_cheq = QPushButton("Cargar chequeras")
        self._btn_cargar_cheq.clicked.connect(self._cargar_chequeras)

        self._inp_cheq_ultimo = QLineEdit(self._cfg.get("chequera_ultimo", ""))
        self._inp_cheq_ultimo.setPlaceholderText("ej. 73189914")
        self._inp_cheq_limite = QLineEdit(self._cfg.get("chequera_limite", ""))
        self._inp_cheq_limite.setPlaceholderText("ej. 73190500")
        self._lbl_disponibles = QLabel("")
        self._lbl_disponibles.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for w in (self._inp_cheq_ultimo, self._inp_cheq_limite):
            w.textChanged.connect(self._actualizar_disponibles)
        root.addWidget(self._card_chequera())

        # — Tabla ————————————————————————————————————————————————————————
        self._tabla = QTableWidget(0, len(_COLS))
        self._tabla.setHorizontalHeaderLabels(_COLS)
        self._tabla.setAlternatingRowColors(True)
        self._tabla.setShowGrid(False)
        self._tabla.verticalHeader().setVisible(False)
        self._tabla.verticalHeader().setDefaultSectionSize(42)
        hh = self._tabla.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in range(1, len(_COLS)):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self._tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._tabla.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tabla.customContextMenuRequested.connect(self._on_tabla_context_menu)
        root.addWidget(self._tabla, stretch=1)

        # — Action bar ———————————————————————————————————————————————————
        self._btn_procesar = QPushButton("Procesar pagos")
        self._btn_procesar.setObjectName("Primary")
        self._btn_procesar.setEnabled(False)
        self._btn_procesar.clicked.connect(self._procesar)
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setTextVisible(False)
        self._progress.setFixedWidth(140)
        self._lbl_progreso = QLabel("")
        self._lbl_progreso.setObjectName("Muted")
        self._lbl_progreso.setVisible(False)

        action_bar = QHBoxLayout(); action_bar.setSpacing(12)
        action_bar.addWidget(self._lbl_progreso, stretch=1)
        action_bar.addWidget(self._progress)
        action_bar.addWidget(self._btn_procesar)
        root.addLayout(action_bar)

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        # Calcular disponibles con los valores iniciales del config
        self._actualizar_disponibles()

    def _card_archivo(self, btn_cargar: QPushButton) -> QFrame:
        card = QFrame(); card.setObjectName("Card")
        v = QVBoxLayout(card); v.setContentsMargins(18, 14, 18, 14); v.setSpacing(8)
        t = QLabel("Planilla autorizada"); t.setObjectName("CardTitle")
        v.addWidget(t)
        row = QHBoxLayout(); row.setSpacing(12)
        row.addWidget(self._lbl_archivo, stretch=1)
        row.addWidget(btn_cargar)
        v.addLayout(row)
        return card

    def _card_chequera(self) -> QFrame:
        card = QFrame(); card.setObjectName("Card")
        v = QVBoxLayout(card); v.setContentsMargins(18, 14, 18, 14); v.setSpacing(10)
        t = QLabel("Chequera"); t.setObjectName("CardTitle")
        v.addWidget(t)

        row = QHBoxLayout(); row.setSpacing(14)

        col_cod = QVBoxLayout(); col_cod.setSpacing(4)
        col_cod.addWidget(_hint("CHEQUERA"))
        cheq_row = QHBoxLayout(); cheq_row.setSpacing(8)
        cheq_row.addWidget(self._combo_cheq, stretch=1)
        cheq_row.addWidget(self._btn_cargar_cheq)
        col_cod.addLayout(cheq_row)
        row.addLayout(col_cod, stretch=3)

        for label_text, widget in [("ÚLTIMO Nº", self._inp_cheq_ultimo),
                                    ("LÍMITE",    self._inp_cheq_limite)]:
            col = QVBoxLayout(); col.setSpacing(4)
            col.addWidget(_hint(label_text)); col.addWidget(widget)
            row.addLayout(col, stretch=1)

        col_disp = QVBoxLayout(); col_disp.setSpacing(4)
        col_disp.addWidget(_hint("DISPONIBLES")); col_disp.addWidget(self._lbl_disponibles)
        row.addLayout(col_disp)
        v.addLayout(row)
        return card

    # ── acciones ──────────────────────────────────────────────────────────

    def _cargar_chequeras(self, silent: bool = False) -> None:
        if not config.is_configured(self._cfg):
            if not silent:
                QMessageBox.warning(self, "Sin configuración",
                                    "Completá las credenciales en Archivo → Configuración.")
            return
        self._progress.setRange(0, 0)
        self._progress.setVisible(True)
        self.statusBar().showMessage("Cargando chequeras, aguardá…")
        self._btn_cargar_cheq.setEnabled(False)

        selected = self._combo_cheq.currentData() or self._combo_cheq.currentText().strip()
        self._cheq_loader = _ChiquerasLoader(
            self._cfg["base_url"], self._cfg["client_id"], self._cfg["client_secret"],
            selected_code=selected,
        )
        self._cheq_loader.listo.connect(lambda activos, det: self._on_chequeras_listas(activos, det))
        self._cheq_loader.error.connect(lambda e: self._on_chequeras_error(e, silent))
        self._cheq_loader.finished.connect(self._on_chequeras_done)
        self._cheq_loader.start()

    def _on_chequeras_listas(self, activos: list, detail: dict | None) -> None:
        cur = self._combo_cheq.currentData() or self._combo_cheq.currentText()
        self._combo_cheq.clear()
        for t in activos:
            cod = t.get("Codigo") or t.get("codigo", "")
            nom = t.get("Nombre") or t.get("nombre") or cod
            self._combo_cheq.addItem(nom, cod)
        self._combo_cheq.completer().setModel(self._combo_cheq.model())
        theme.style_combo_popup(self._combo_cheq)
        idx = self._combo_cheq.findData(cur)
        if idx >= 0:
            self._combo_cheq.setCurrentIndex(idx)
        # Auto-poblar número y límite desde el detalle obtenido en background
        if detail:
            if detail.get("NumeroActual"):
                self._inp_cheq_ultimo.setText(str(detail["NumeroActual"]))
            if detail.get("LimiteHasta"):
                self._inp_cheq_limite.setText(str(detail["LimiteHasta"]))
        self.statusBar().showMessage(f"{len(activos)} chequeras cargadas.", 3000)

    def _on_chequeras_error(self, msg: str, silent: bool) -> None:
        if not silent:
            QMessageBox.critical(self, "Error", f"No se pudo cargar chequeras:\n{msg}")
        self.statusBar().showMessage("", 0)

    def _on_chequeras_done(self) -> None:
        self._progress.setRange(0, 100)
        self._progress.setVisible(False)
        self._btn_cargar_cheq.setEnabled(True)

    def _on_chequera_seleccionada(self, index: int) -> None:
        codigo = self._combo_cheq.itemData(index) or self._combo_cheq.itemText(index)
        if not codigo:
            return
        try:
            client = FinnegansClient(self._cfg["base_url"],
                                     self._cfg["client_id"],
                                     self._cfg["client_secret"])
            t = client.get_talonario(codigo)
            if t.get("NumeroActual"):
                self._inp_cheq_ultimo.setText(str(t["NumeroActual"]))
            if t.get("LimiteHasta"):
                self._inp_cheq_limite.setText(str(t["LimiteHasta"]))
            self.statusBar().showMessage(
                f"Chequera {codigo}: último {t.get('NumeroActual','?')}, "
                f"límite {t.get('LimiteHasta','?')}.", 4000)
        except Exception as e:
            self.statusBar().showMessage(f"No se pudo cargar datos de chequera: {e}", 4000)

    def _abrir_settings(self) -> None:
        dlg = SettingsDialog(self._cfg, self)
        theme.show_animated(dlg)
        if dlg.exec():
            self.statusBar().showMessage("Configuración guardada.", 3000)

    def _cargar_excel(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar planilla", "", "Excel (*.xlsx *.xls)"
        )
        if not path:
            return
        try:
            self._proveedores = leer_dm(Path(path))
            self._lbl_archivo.setText(Path(path).name)
            self._lbl_archivo.setObjectName("Filename")
            self._lbl_archivo.style().unpolish(self._lbl_archivo)
            self._lbl_archivo.style().polish(self._lbl_archivo)
            self._poblar_tabla()
            self._guardar_datos_chequera()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo leer el Excel:\n{e}")

    def _poblar_tabla(self) -> None:
        ultimo, limite = self._numero_desde(), self._limite()
        cheques_usados = 0

        filas = []
        for p in self._proveedores:
            n_cheques = 0
            if p.modalidad == Modalidad.CHEQUE_PROPIO and ultimo is not None:
                from src.domain.fraccionador import fraccionar_proveedor
                chs, _ = fraccionar_proveedor(p.items, numero_desde=ultimo + cheques_usados,
                                               fecha_emision=date.today())
                n_cheques = len(chs)
                cheques_usados += n_cheques

            estado = self._calcular_estado(p, n_cheques, ultimo, limite, cheques_usados - n_cheques)
            filas.append((p, n_cheques, estado))

        self._tabla.setRowCount(len(filas))
        self._ops_a_procesar = []

        for row, (p, n_cheques, estado) in enumerate(filas):
            self._tabla.setItem(row, 0, QTableWidgetItem(p.nombre))
            self._tabla.setItem(row, 1, QTableWidgetItem(p.cuit or "—"))
            importe_fmt = f"$ {float(p.importe_total):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            item_imp = QTableWidgetItem(importe_fmt)
            item_imp.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._tabla.setItem(row, 2, item_imp)
            self._tabla.setItem(row, 3, QTableWidgetItem(p.modalidad.name.replace("_", " ").title()))
            item_ch = QTableWidgetItem(str(n_cheques) if n_cheques else "—")
            item_ch.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._tabla.setItem(row, 4, item_ch)
            label, variant = _ESTADOS[estado]
            self._tabla.setCellWidget(row, 5, theme.make_badge(label, variant))

        listos = sum(1 for _, _, e in filas if e == "LISTO")
        self._btn_procesar.setEnabled(listos > 0)
        self.statusBar().showMessage(
            f"{len(self._proveedores)} proveedores cargados. {listos} listos para procesar."
        )

    def _calcular_estado(self, p, n_cheques, ultimo, limite, cheques_ya_usados):
        if not p.items:
            return "SIN_ITEMS"
        if p.modalidad == Modalidad.MANUAL:
            return "MANUAL"
        if p.modalidad == Modalidad.CHEQUE_PROPIO:
            if ultimo is None or limite is None:
                return "EXCEDE"
            if (ultimo + cheques_ya_usados + n_cheques) > limite:
                return "EXCEDE"
        return "LISTO"

    def _actualizar_disponibles(self) -> None:
        ultimo = self._numero_desde()
        limite = self._limite()
        if ultimo is not None and limite is not None:
            disp = limite - ultimo
            variant = "success" if disp > 0 else "danger"
            self._lbl_disponibles.setText(str(disp))
            self._lbl_disponibles.setStyleSheet(theme.badge_qss(variant))
        else:
            self._lbl_disponibles.setText("—")
            self._lbl_disponibles.setStyleSheet(theme.badge_qss("neutral"))
        if self._proveedores:
            self._poblar_tabla()

    def _numero_desde(self) -> int | None:
        try:
            return int(self._inp_cheq_ultimo.text().strip())
        except ValueError:
            return None

    def _limite(self) -> int | None:
        try:
            return int(self._inp_cheq_limite.text().strip())
        except ValueError:
            return None

    def _guardar_datos_chequera(self) -> None:
        self._cfg["chequera_codigo"] = (
            self._combo_cheq.currentData() or self._combo_cheq.currentText().strip()
        )
        self._cfg["chequera_ultimo"] = self._inp_cheq_ultimo.text().strip()
        self._cfg["chequera_limite"] = self._inp_cheq_limite.text().strip()
        config.save(self._cfg)

    def _procesar(self) -> None:
        faltantes = config.missing_fields(self._cfg)
        if faltantes:
            QMessageBox.warning(
                self, "Configuración incompleta",
                "Completá en Archivo → Configuración:\n"
                + "\n".join(f"  • {f}" for f in faltantes),
            )
            return

        ultimo = self._numero_desde()
        if ultimo is None:
            QMessageBox.warning(self, "Chequera", "Ingresá el último número de cheque emitido.")
            return

        self._guardar_datos_chequera()
        self._ultimo_cheque = ultimo

        self._progress.setRange(0, 0)
        self._progress.setVisible(True)
        self._lbl_progreso.setText("Iniciando consulta…")
        self._lbl_progreso.setVisible(True)
        self._btn_procesar.setEnabled(False)

        self._precarga_worker = _PrecargarWorker(list(self._proveedores), self._cfg)
        self._precarga_worker.progreso.connect(self._on_precarga_progreso)
        self._precarga_worker.listo.connect(self._on_precarga_lista)
        self._precarga_worker.error.connect(self._on_precarga_error)
        self._precarga_worker.start()

    def _on_precarga_progreso(self, msg: str) -> None:
        self._lbl_progreso.setText(msg)
        self.statusBar().showMessage(msg)

    def _on_precarga_error(self, msg: str) -> None:
        self._progress.setRange(0, 100)
        self._progress.setVisible(False)
        self._lbl_progreso.setVisible(False)
        self._btn_procesar.setEnabled(True)
        QMessageBox.critical(self, "Error", f"Error al consultar proveedores:\n{msg}")

    def _on_precarga_lista(self, cotizacion_dolar, ret_cache, ratios_fc, docs_pendientes, cotizacion_fallback) -> None:
        self._progress.setRange(0, 100)
        self._progress.setVisible(False)
        self._lbl_progreso.setVisible(False)

        if cotizacion_fallback:
            reply = QMessageBox.question(
                self,
                "Cotización del dólar no disponible",
                f"No se pudo obtener la cotización del dólar para hoy "
                f"(se usaría $1).\n\n"
                f"Esto puede afectar el cálculo de retenciones y la "
                f"cotización registrada en Finnegans.\n\n"
                f"¿Querés continuar de todas formas?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                self._btn_procesar.setEnabled(True)
                return

        self._construir_ops(self._ultimo_cheque, cotizacion_dolar, ret_cache, ratios_fc, docs_pendientes)

        # Si hubo overflow, ofrecer chequera alternativa antes de continuar
        self._manejar_overflow(cotizacion_dolar, ret_cache, ratios_fc)

        if getattr(self, "_ops_advertencias", []):
            cuerpo = "\n".join(self._ops_advertencias)
            QMessageBox.warning(self, "Proveedores omitidos", cuerpo)

        if not self._ops_a_procesar:
            QMessageBox.information(self, "Nada que procesar",
                                    "No hay pagos en estado ✅ Listo.")
            self._btn_procesar.setEnabled(True)
            return

        manuales = [p for p in self._proveedores if p.modalidad == Modalidad.MANUAL]
        preview = PreviewDialog(self._ops_a_procesar, manuales, self)
        theme.show_animated(preview)
        if not preview.exec():
            self._btn_procesar.setEnabled(True)
            return

        total = len(self._ops_a_procesar)
        self._progress.setRange(0, total)
        self._progress.setValue(0)
        self._progress.setVisible(True)
        self._lbl_progreso.setText(f"Pagos procesados 0 de {total}")
        self._lbl_progreso.setVisible(True)

        client = FinnegansClient(
            self._cfg["base_url"],
            self._cfg["client_id"],
            self._cfg["client_secret"],
        )
        self._worker = _ProcesarWorker(self._ops_a_procesar, client)
        self._worker.progreso.connect(self._on_progreso)
        self._worker.terminado.connect(self._on_terminado)
        self._worker.start()

    def _on_tabla_context_menu(self, pos) -> None:
        row = self._tabla.rowAt(pos.y())
        if row < 0 or row >= len(self._proveedores):
            return
        menu = QMenu(self)
        act_del = menu.addAction("Eliminar de la lista")
        if menu.exec(self._tabla.viewport().mapToGlobal(pos)) == act_del:
            self._proveedores.pop(row)
            self._poblar_tabla()

    def _construir_ops(self, ultimo: int, cotizacion_dolar: "Decimal | None" = None,
                       ret_cache: dict | None = None,
                       ratios_fc: dict | None = None,
                       docs_pendientes: dict | None = None) -> None:
        from dataclasses import replace as _dc_replace
        from decimal import Decimal as _D
        from src.domain.retenciones import calcular_retenciones
        cotizacion_dolar = cotizacion_dolar or _D("1")
        ret_cache = ret_cache or {}
        ratios_fc = ratios_fc or {}
        docs_pendientes = docs_pendientes or {}
        self._ops_a_procesar = []
        self._ops_advertencias: list[str] = []
        self._proveedores_overflow: list = []   # proveedores que exceden el límite
        numero_desde = ultimo + 1
        chequera = self._combo_cheq.currentData() or self._combo_cheq.currentText().strip()
        cuenta_banco_cheque = self._cfg.get("cuenta_banco_codigo", "02.01.04.01.0009")
        cuenta_banco_transf = self._cfg.get("cuenta_banco_transferencia_codigo", "01.01.01.02.0006")
        banco_codigo = self._cfg.get("banco_codigo", "00285")
        op_cheque = self._cfg.get("op_bancaria_cheque_codigo", "EMCHPROP")
        op_transf = self._cfg.get("op_bancaria_transferencia_codigo", "TLote")

        for p in self._proveedores:
            if p.modalidad == Modalidad.MANUAL or not p.items:
                continue

            # Filtrar ítems sin saldo pendiente según composicionSaldoProveedor
            pendientes = docs_pendientes.get(p.cuit) if p.cuit else None
            if pendientes is not None:
                # pendientes = set de documentos con saldo abierto en Finnegans
                items_sin_saldo = [i for i in p.items if i.documento not in pendientes]
                items_base = [i for i in p.items if i.documento in pendientes]
                for item in items_sin_saldo:
                    self._ops_advertencias.append(
                        f"• {p.nombre}: {item.documento} — sin saldo pendiente, omitido."
                    )
                if not items_base:
                    continue
                if len(items_base) < len(p.items):
                    p = _dc_replace(p, items=items_base)

            # A1: CUIT debe ser 11 dígitos numéricos
            if not p.cuit or not (p.cuit.isdigit() and len(p.cuit) == 11):
                self._ops_advertencias.append(
                    f"• {p.nombre}: CUIT inválido «{p.cuit or '—'}» — se omite."
                )
                continue

            # A3: importe total no puede ser cero
            if p.importe_total <= 0:
                self._ops_advertencias.append(
                    f"• {p.nombre}: importe total es $0 — se omite."
                )
                continue

            # Calcular retenciones y ajustar importes FC a neto
            retenciones_post: list[dict] = []
            items_a_usar = p.items
            if p.cuit and p.cuit in ret_cache:
                percepciones, maestros, historico = ret_cache[p.cuit]
                retenciones_post, items_a_usar = calcular_retenciones(
                    percepciones, maestros, p.items, ratios_fc, historico
                )

            limite = self._limite()
            cheques = []
            if p.modalidad == Modalidad.CHEQUE_PROPIO:
                cheques, numero_desde = fraccionar_proveedor(
                    items_a_usar, numero_desde=numero_desde, fecha_emision=date.today()
                )
                if limite and (numero_desde - 1) > limite:
                    self._proveedores_overflow.append(p)
                    numero_desde -= len(cheques)  # liberar los números reservados
                    continue
            cuenta_banco = (
                cuenta_banco_transf if p.modalidad == Modalidad.TRANSFERENCIA
                else cuenta_banco_cheque
            )
            op = OpPago(
                proveedor=p,
                cheques=cheques,
                chequera_codigo=chequera,
                banco_codigo=banco_codigo,
                cuenta_banco_codigo=cuenta_banco,
                op_bancaria_cheque_codigo=op_cheque,
                op_bancaria_transferencia_codigo=op_transf,
                cotizacion_dolar=cotizacion_dolar,
                retenciones=retenciones_post,
                fecha=date.today(),
            )
            self._ops_a_procesar.append(op)

    def _manejar_overflow(self, cotizacion_dolar, ret_cache: dict, ratios_fc: dict) -> None:
        """
        Si hay proveedores que excedieron la chequera principal, muestra un diálogo
        para asignarlos a una chequera alternativa y genera sus OPs con ella.
        """
        from src.domain.retenciones import calcular_retenciones

        overflow = self._proveedores_overflow
        if not overflow:
            return

        # ── Construir diálogo ─────────────────────────────────────────────
        dlg = QDialog(self)
        dlg.setWindowTitle("Chequera insuficiente")
        dlg.setMinimumWidth(460)
        v = QVBoxLayout(dlg)
        v.setSpacing(14)
        v.setContentsMargins(22, 18, 22, 18)

        chequera_actual = self._combo_cheq.currentText()
        lbl_info = QLabel(
            f"La chequera <b>{chequera_actual}</b> no tiene suficientes números "
            f"para todos los pagos.<br><br>"
            f"<b>Proveedores que no entraron:</b>"
        )
        lbl_info.setWordWrap(True)
        v.addWidget(lbl_info)

        lbl_lista = QLabel("\n".join(f"  • {p.nombre}" for p in overflow))
        lbl_lista.setObjectName("Muted")
        v.addWidget(lbl_lista)

        lbl_sel = QLabel("Asignar a otra chequera:")
        v.addWidget(lbl_sel)

        combo_alt = QComboBox()
        current_cod = self._combo_cheq.currentData() or self._combo_cheq.currentText().strip()
        for i in range(self._combo_cheq.count()):
            cod = self._combo_cheq.itemData(i)
            nom = self._combo_cheq.itemText(i)
            if cod != current_cod:
                combo_alt.addItem(nom, cod)
        v.addWidget(combo_alt)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Asignar")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("Omitir proveedores")
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)

        if combo_alt.count() == 0:
            QMessageBox.warning(self, "Sin chequeras disponibles",
                                "No hay otras chequeras cargadas. "
                                "Los proveedores serán omitidos.")
            for p in overflow:
                self._ops_advertencias.append(
                    f"• {p.nombre}: sin chequera alternativa disponible — omitido."
                )
            return

        if dlg.exec() != QDialog.DialogCode.Accepted:
            for p in overflow:
                self._ops_advertencias.append(
                    f"• {p.nombre}: excede la chequera, descartado por el usuario."
                )
            return

        # ── Obtener datos de la chequera alternativa ──────────────────────
        nueva_cod = combo_alt.currentData() or combo_alt.currentText().strip()
        try:
            client = FinnegansClient(
                self._cfg["base_url"], self._cfg["client_id"], self._cfg["client_secret"]
            )
            t = client.get_talonario(nueva_cod)
            nuevo_ultimo = int(t.get("NumeroActual", 0))
            nuevo_limite = int(t["LimiteHasta"]) if t.get("LimiteHasta") else None
        except Exception as e:
            QMessageBox.warning(self, "Error al cargar chequera",
                                f"No se pudieron obtener los datos de {nueva_cod}:\n{e}")
            for p in overflow:
                self._ops_advertencias.append(
                    f"• {p.nombre}: error al cargar chequera alternativa — omitido."
                )
            return

        # ── Construir OPs con la chequera alternativa ─────────────────────
        cuenta_banco  = self._cfg.get("cuenta_banco_codigo", "02.01.04.01.0009")
        banco_codigo  = self._cfg.get("banco_codigo", "00285")
        op_cheque_cod = self._cfg.get("op_bancaria_cheque_codigo", "EMCHPROP")
        numero_desde  = nuevo_ultimo + 1

        for p in overflow:
            retenciones_post: list[dict] = []
            items_a_usar = p.items
            if p.cuit and p.cuit in ret_cache:
                percepciones, maestros, historico = ret_cache[p.cuit]
                retenciones_post, items_a_usar = calcular_retenciones(
                    percepciones, maestros, p.items, ratios_fc, historico
                )

            cheques, numero_desde = fraccionar_proveedor(
                items_a_usar, numero_desde=numero_desde, fecha_emision=date.today()
            )

            if nuevo_limite and (numero_desde - 1) > nuevo_limite:
                self._ops_advertencias.append(
                    f"• {p.nombre}: también excede {nueva_cod} — omitido."
                )
                numero_desde -= len(cheques)
                continue

            self._ops_a_procesar.append(OpPago(
                proveedor=p,
                cheques=cheques,
                chequera_codigo=nueva_cod,
                banco_codigo=banco_codigo,
                cuenta_banco_codigo=cuenta_banco,
                op_bancaria_cheque_codigo=op_cheque_cod,
                cotizacion_dolar=cotizacion_dolar,
                retenciones=retenciones_post,
                fecha=date.today(),
            ))

    def _on_progreso(self, fila: int, msg: str) -> None:
        total = len(self._ops_a_procesar)
        self._progress.setValue(fila + 1)
        self._lbl_progreso.setText(f"Pagos procesados {fila + 1} de {total}")
        self.statusBar().showMessage(f"Procesando {fila+1}/{total}: {msg}")

    def _on_terminado(self, resultados: list) -> None:
        self._progress.setVisible(False)
        self._lbl_progreso.setVisible(False)
        self._btn_procesar.setEnabled(True)

        # Auto-actualizar "Último Nº" solo con cheques de la chequera principal
        chequera_principal = self._combo_cheq.currentData() or self._combo_cheq.currentText().strip()
        ultimo_exitoso = self._ultimo_cheque
        for op, res in zip(self._ops_a_procesar, resultados):
            if (res.get("estado") == "OK"
                    and op.cheques
                    and op.chequera_codigo == chequera_principal):
                ultimo_exitoso = max(ultimo_exitoso, max(int(ch.numero) for ch in op.cheques))
        if ultimo_exitoso > self._ultimo_cheque:
            self._inp_cheq_ultimo.setText(str(ultimo_exitoso))
            self._guardar_datos_chequera()

        manuales = [{"nombre": p.nombre, "estado": "MANUAL",
                     "detalle": p.motivo_manual or "Modalidad no soportada",
                     "importe": float(p.importe_total)}
                    for p in self._proveedores if p.modalidad == Modalidad.MANUAL]
        dlg = ResultDialog(resultados + manuales, self)
        theme.show_animated(dlg)
        dlg.exec()
        self.statusBar().showMessage("Procesamiento terminado.")
