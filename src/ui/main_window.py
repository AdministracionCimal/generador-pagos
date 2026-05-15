import functools
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from decimal import Decimal
from pathlib import Path

_LOG = logging.getLogger(__name__)

from PyQt6.QtCore import QRect, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QCompleter, QDialog, QDialogButtonBox, QFileDialog, QFrame,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMenuBar,
    QMessageBox, QProgressBar, QPushButton, QStatusBar, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

import src.config as config
from src.api.client import ApiError, AuthError, FinnegansClient
from src.domain.clasificador import clasificar
from src.domain.fraccionador import fraccionar_proveedor
from src.domain.mapper import armar_post
from src.domain.models import Modalidad, OpPago, ProveedorTanda
from src.domain.numeracion import secuencia_comprobantes
from src.excel.dm_reader import leer_dm
from src.ui import theme
from src.ui.preview_dialog import PreviewDialog
from src.ui.result_dialog import ResultDialog
from src.ui.settings_dialog import SettingsDialog

# Estado interno → (label, variante visual)
def _hint(text: str) -> QLabel:
    lbl = QLabel(text); lbl.setObjectName("CardHint")
    return lbl


@functools.lru_cache(maxsize=512)
def _fmt_money(value: Decimal | float | int) -> str:
    return f"$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


_ESTADOS = {
    "LISTO":     ("Listo",           "success"),
    "MANUAL":    ("Carga manual",    "warning"),
    "EXCEDE":    ("Excede chequera", "danger"),
    "SIN_ITEMS": ("Sin ítems",       "danger"),
    "YA_PAGADA": ("Sin saldo",       "neutral"),
}

_COLS = ["", "Proveedor", "CUIT", "Importe", "Modalidad", "Cheques", "Estado"]


def _draw_round_check(painter: QPainter, rect: QRect, state: Qt.CheckState) -> None:
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    circle = rect.adjusted(2, 2, -2, -2)
    if state == Qt.CheckState.Checked:
        painter.setPen(QPen(QColor(theme.BRAND_HOVER), 1.5))
        painter.setBrush(QColor(theme.BRAND))
        painter.drawEllipse(circle)
        dot = circle.adjusted(5, 5, -5, -5)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.BG_SURFACE))
        painter.drawEllipse(dot)
    else:
        painter.setPen(QPen(QColor(theme.BRAND_HOVER if state == Qt.CheckState.PartiallyChecked else theme.TEXT_MUTED), 1.8))
        painter.setBrush(QColor(theme.BRAND_SUBTLE if state == Qt.CheckState.PartiallyChecked else theme.BG_SURFACE))
        painter.drawEllipse(circle)
        if state == Qt.CheckState.PartiallyChecked:
            line_y = circle.center().y()
            painter.setPen(QPen(QColor(theme.BRAND_HOVER), 2.0))
            painter.drawLine(circle.left() + 4, line_y, circle.right() - 4, line_y)
    painter.restore()


class _RoundCheckBox(QCheckBox):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setText("")
        self.setTristate(False)
        self.setFixedSize(20, 20)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        _draw_round_check(
            painter,
            self.rect().adjusted(1, 1, -1, -1),
            Qt.CheckState.Checked if self.isChecked() else Qt.CheckState.Unchecked,
        )


class _CheckHeader(QHeaderView):
    toggled = pyqtSignal(bool)

    def __init__(self, orientation, parent=None) -> None:
        super().__init__(orientation, parent)
        self._check_state = Qt.CheckState.Unchecked
        self.setSectionsClickable(True)

    def set_check_state(self, state: Qt.CheckState) -> None:
        if self._check_state == state:
            return
        self._check_state = state
        self.viewport().update()

    def paintSection(self, painter, rect, logical_index) -> None:
        super().paintSection(painter, rect, logical_index)
        if logical_index != 0:
            return
        _draw_round_check(painter, self._checkbox_rect(rect), self._check_state)

    def mousePressEvent(self, event) -> None:
        index = self.logicalIndexAt(event.pos())
        if index == 0:
            checked = self._check_state != Qt.CheckState.Checked
            self.toggled.emit(checked)
            event.accept()
            return
        super().mousePressEvent(event)

    def _checkbox_rect(self, rect: QRect) -> QRect:
        size = 20
        x = rect.x() + (rect.width() - size) // 2
        y = rect.y() + (rect.height() - size) // 2
        return QRect(x, y, size, size)


class _PrecargarWorker(QThread):
    progreso = pyqtSignal(str)
    listo    = pyqtSignal(object, object, object, object, object, object)  # cotizacion_dolar, ret_cache, ratios_fc, docs_pendientes, cotizacion_fallback, ultimo_op
    error    = pyqtSignal(str)

    def __init__(self, proveedores: list, cfg: dict, cache_docs: dict | None = None) -> None:
        super().__init__()
        self._proveedores = proveedores
        self._cfg = cfg
        self._cache_docs = cache_docs

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

        ultimo_op = ""
        talonario_op = str(cfg.get("talonario_op_codigo", "TE-OP") or "").strip()
        if talonario_op:
            try:
                detalle_op = client.get_talonario(talonario_op)
                ultimo_op = str(detalle_op.get("NumeroActual", "") or "").strip()
            except Exception:
                ultimo_op = ""

        cache: dict = {}
        codigos_ret_cargados: dict = {}
        ratios_fc: dict = {}
        lock = threading.Lock()

        empresa    = cfg.get("empresa_codigo", "")
        mes_inicio = date.today().replace(day=1).strftime("%Y-%m-%d")
        mes_hoy    = date.today().strftime("%Y-%m-%d")

        provs = [
            p for p in self._proveedores
            if p.modalidad != Modalidad.MANUAL and p.items and p.cuit
        ]
        total = len(provs)

        def _precargar_proveedor(p) -> tuple:
            avisos: list[str] = []
            try:
                prov_data    = client.get_proveedor(p.cuit)
                percepciones = prov_data.get("Percepciones", [])
                maestros: dict = {}
                for perc in percepciones:
                    cod = perc.get("RetencionCodigo")
                    if not cod:
                        continue
                    with lock:
                        already = cod in codigos_ret_cargados
                    if not already:
                        try:
                            ret_data = client.get_retencion(cod)
                        except Exception:
                            ret_data = {}
                        with lock:
                            codigos_ret_cargados.setdefault(cod, ret_data)
                    with lock:
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
                            nombre_tipo = str(row.get("RETENCIONTIPO", "") or "").strip()
                            nombre_esp = str(row.get("RETENCION", "") or "").strip()
                            isar_inc = Decimal(str(row.get("ISAR", 0)))
                            imp_inc  = Decimal(str(row.get("IMPORTE", 0)))
                            for key in {k for k in (cod_tipo, cod_esp) if k}:
                                if key not in historico:
                                    historico[key] = {
                                        "isar_historico": Decimal("0"),
                                        "ya_retenido":    Decimal("0"),
                                        "nombre":         nombre_esp,
                                        "nombre_tipo":    nombre_tipo,
                                    }
                                if nombre_esp and not historico[key].get("nombre"):
                                    historico[key]["nombre"] = nombre_esp
                                if nombre_tipo and not historico[key].get("nombre_tipo"):
                                    historico[key]["nombre_tipo"] = nombre_tipo
                                historico[key]["isar_historico"] += isar_inc
                                historico[key]["ya_retenido"]    += imp_inc
                    except Exception as exc:
                        _LOG.warning("analisisRetencion falló para %s: %s", p.cuit, exc)
                        avisos.append(
                            f"⚠ {p.nombre}: no se pudo cargar histórico de retenciones ({exc})"
                        )

                with lock:
                    cache[p.cuit] = (percepciones, maestros, historico)

                if tiene_retencion:
                    docs_to_fetch = []
                    for item in p.items:
                        doc = item.documento
                        if not doc.lower().startswith("fc -"):
                            continue
                        with lock:
                            already_ratio = doc in ratios_fc
                        if not already_ratio:
                            docs_to_fetch.append(doc)
                    for doc in docs_to_fetch:
                        try:
                            fc      = client.get_factura_compra(doc)
                            gravado = sum(
                                Decimal(str(c.get("ConceptoImporteGravado", 0)))
                                for c in fc.get("Conceptos", [])
                            )
                            total_fc = Decimal(str(fc.get("ImporteTotalControl", 0)))
                            if total_fc > 0:
                                with lock:
                                    ratios_fc.setdefault(doc, gravado / total_fc)
                        except Exception:
                            pass
            except Exception as exc:
                _LOG.warning("Precarga falló para %s: %s", p.cuit, exc)
                avisos.append(f"⚠ {p.nombre}: error al precargar datos ({exc})")
            return p, avisos

        with ThreadPoolExecutor(max_workers=8) as pool:
            futs = {pool.submit(_precargar_proveedor, p): p for p in provs}
            for i, fut in enumerate(as_completed(futs), 1):
                p_orig = futs[fut]
                try:
                    _, avisos = fut.result()
                except Exception:
                    avisos = []
                for aviso in avisos:
                    self.progreso.emit(aviso)
                self.progreso.emit(f"Consultando proveedor {i} de {total}: {p_orig.nombre}")

        # Verificar saldos pendientes por proveedor (composicionSaldoProveedor).
        # Si hay cache fresco del _SaldoCheckerWorker, reutilizarlo para ahorrar ~1-2 s.
        if self._cache_docs is not None:
            docs_pendientes: dict[str, set | None] = self._cache_docs
        else:
            docs_pendientes = {}
            cuits_a_verificar = sorted({p.cuit for p in self._proveedores if p.cuit})
            fecha_hoy = date.today().strftime("%Y-%m-%d")
            n_cuits = len(cuits_a_verificar)

            def _fetch_saldo(cuit: str) -> tuple[str, "set | None"]:
                try:
                    rows = client.get_composicion_saldo_proveedor(cuit, fecha_hoy)
                    return cuit, {
                        r["IDENTIFICACIONEXTERNA"]
                        for r in rows
                        if r.get("IDENTIFICACIONEXTERNA")
                        and float(r.get("IMPORTEMONTRAN", 0) or 0) != 0
                    }
                except Exception:
                    return cuit, None

            with ThreadPoolExecutor(max_workers=8) as pool:
                futs_saldo = {pool.submit(_fetch_saldo, c): c for c in cuits_a_verificar}
                for i, fut in enumerate(as_completed(futs_saldo), 1):
                    cuit, resultado = fut.result()
                    docs_pendientes[cuit] = resultado
                    self.progreso.emit(f"Verificando saldo {i}/{n_cuits}: {cuit}")

        self.listo.emit(
            cotizacion_dolar,
            cache,
            ratios_fc,
            docs_pendientes,
            cotizacion_fallback,
            ultimo_op,
        )


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


class _SaldoCheckerWorker(QThread):
    """
    Worker liviano: solo consulta composicionSaldoProveedor por cada CUIT
    y emite el dict docs_pendientes. Se lanza al cargar el Excel para que
    los badges 'Sin saldo' aparezcan sin esperar a 'Procesar pagos'.
    """
    listo    = pyqtSignal(dict)   # docs_pendientes: {cuit: set | None}
    progreso = pyqtSignal(str)

    def __init__(self, proveedores: list, cfg: dict) -> None:
        super().__init__()
        self._proveedores = proveedores
        self._cfg = cfg

    def run(self) -> None:
        try:
            client = FinnegansClient(
                self._cfg["base_url"], self._cfg["client_id"], self._cfg["client_secret"]
            )
            cuits = sorted({p.cuit for p in self._proveedores if p.cuit})
            fecha_hoy = date.today().strftime("%Y-%m-%d")
            docs_pendientes: dict = {}
            total = len(cuits)

            def _fetch(cuit: str) -> tuple[str, "set | None"]:
                try:
                    rows = client.get_composicion_saldo_proveedor(cuit, fecha_hoy)
                    return cuit, {
                        r["IDENTIFICACIONEXTERNA"]
                        for r in rows
                        if r.get("IDENTIFICACIONEXTERNA")
                        and float(r.get("IMPORTEMONTRAN", 0) or 0) != 0
                    }
                except Exception:
                    return cuit, None

            with ThreadPoolExecutor(max_workers=8) as pool:
                futs = {pool.submit(_fetch, c): c for c in cuits}
                for i, fut in enumerate(as_completed(futs), 1):
                    cuit, resultado = fut.result()
                    docs_pendientes[cuit] = resultado
                    self.progreso.emit(f"Verificando saldo {i}/{total}: {cuit}")

            self.listo.emit(docs_pendientes)
        except Exception:
            self.listo.emit({})  # fail-open: no bloquear


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
                numero = (
                    resp.get("NumeroComprobante")
                    or resp.get("numeroComprobante")
                    or resp.get("documento")
                    or "OK"
                )
                self.progreso.emit(i, f"OK → {numero}")
                resultados.append({
                    "nombre": nombre,
                    "estado": "OK",
                    "detalle": numero,
                    "numero_previsto": op.numero_comprobante_estimado,
                    "numero_real": numero,
                    "importe": float(op.proveedor.importe_total),
                })
            except (ApiError, AuthError) as e:
                self.progreso.emit(i, f"ERROR: {e}")
                resultados.append({
                    "nombre": nombre,
                    "estado": "ERROR",
                    "detalle": str(e),
                    "numero_previsto": op.numero_comprobante_estimado,
                    "numero_real": "",
                    "importe": float(op.proveedor.importe_total),
                })
            except Exception as e:
                self.progreso.emit(i, f"ERROR: {e}")
                resultados.append({
                    "nombre": nombre,
                    "estado": "ERROR",
                    "detalle": str(e),
                    "numero_previsto": op.numero_comprobante_estimado,
                    "numero_real": "",
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
        self._actualizando_tabla = False
        self._ultimo_cheque: int = 0
        self._docs_pendientes_cache: dict | None = None
        self._docs_pendientes_ts: float = 0.0
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
        root.setContentsMargins(28, 16, 28, 16)
        root.setSpacing(10)

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
        self._combo_cheq = theme.NoScrollComboBox()
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
        self._debounce_tabla = QTimer(self)
        self._debounce_tabla.setSingleShot(True)
        self._debounce_tabla.timeout.connect(self._poblar_tabla_si_proveedores)
        for w in (self._inp_cheq_ultimo, self._inp_cheq_limite):
            w.textChanged.connect(self._actualizar_disponibles)
        root.addWidget(self._card_chequera())

        self._summary_values: dict[str, QLabel] = {}
        self._summary_hints: dict[str, QLabel] = {}
        root.addWidget(self._build_resumen_operativo())

        # — Tabla ————————————————————————————————————————————————————————
        self._tabla = QTableWidget(0, len(_COLS))
        self._tabla_header = _CheckHeader(Qt.Orientation.Horizontal, self._tabla)
        self._tabla_header.toggled.connect(self._marcar_todos)
        self._tabla.setHorizontalHeader(self._tabla_header)
        self._tabla.setHorizontalHeaderLabels(_COLS)
        self._tabla.setAlternatingRowColors(True)
        self._tabla.setShowGrid(False)
        self._tabla.verticalHeader().setVisible(False)
        self._tabla.verticalHeader().setDefaultSectionSize(42)
        hh = self._tabla.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for c in range(2, 5):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        self._tabla.setColumnWidth(0, 52)
        self._tabla.setColumnWidth(5, 72)
        self._tabla.setColumnWidth(6, 110)
        self._tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        root.addWidget(self._tabla, stretch=1)

        # — Action bar ———————————————————————————————————————————————————
        self._btn_eliminar = QPushButton("Eliminar seleccionados")
        self._btn_eliminar.setEnabled(False)
        self._btn_eliminar.clicked.connect(self._eliminar_seleccionados)
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
        action_bar.addWidget(self._btn_eliminar)
        action_bar.addWidget(self._lbl_progreso, stretch=1)
        action_bar.addWidget(self._progress)
        action_bar.addWidget(self._btn_procesar)
        root.addLayout(action_bar)

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        # Calcular disponibles con los valores iniciales del config
        self._actualizar_disponibles()

    def _build_resumen_operativo(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        row = QHBoxLayout(card)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        items = [
            ("listos", "PAGOS LISTOS", "0"),
            ("total", "TOTAL LISTO", _fmt_money(0)),
            ("cheques", "CHEQUES PREVISTOS", "0"),
            ("manuales", "CARGA MANUAL", "0"),
            ("disponibles", "DISPONIBLES", "—"),
        ]

        for index, (key, label, value) in enumerate(items):
            cell = QWidget()
            col = QVBoxLayout(cell)
            col.setContentsMargins(20, 13, 20, 13)
            col.setSpacing(3)

            hint = QLabel(label)
            hint.setObjectName("KpiLabel")

            number = QLabel(value)
            number.setStyleSheet(
                f"color: {theme.TEXT_PRIMARY}; font-size: 18px; font-weight: 700;"
            )

            col.addWidget(hint)
            col.addWidget(number)
            row.addWidget(cell, stretch=1)
            self._summary_hints[key] = hint
            self._summary_values[key] = number

            if index < len(items) - 1:
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.VLine)
                sep.setStyleSheet(
                    f"color: {theme.BORDER}; background: {theme.BORDER};"
                    f"max-width: 1px; margin: 12px 0;"
                )
                row.addWidget(sep)

        return card

    def _card_archivo(self, btn_cargar: QPushButton) -> QFrame:
        card = QFrame(); card.setObjectName("Card")
        row = QHBoxLayout(card); row.setContentsMargins(16, 10, 16, 10); row.setSpacing(14)
        lbl_t = QLabel("PLANILLA AUTORIZADA"); lbl_t.setObjectName("CardHint")
        row.addWidget(lbl_t)
        row.addWidget(self._lbl_archivo, stretch=1)
        row.addWidget(btn_cargar)
        return card

    def _card_chequera(self) -> QFrame:
        card = QFrame(); card.setObjectName("Card")
        row = QHBoxLayout(card); row.setContentsMargins(16, 8, 16, 8); row.setSpacing(14)

        col_cod = QVBoxLayout(); col_cod.setSpacing(3)
        col_cod.addWidget(_hint("CHEQUERA"))
        cheq_row = QHBoxLayout(); cheq_row.setSpacing(8)
        cheq_row.addWidget(self._combo_cheq, stretch=1)
        cheq_row.addWidget(self._btn_cargar_cheq)
        col_cod.addLayout(cheq_row)
        row.addLayout(col_cod, stretch=3)

        for label_text, widget in [("ÚLTIMO Nº", self._inp_cheq_ultimo),
                                    ("LÍMITE",    self._inp_cheq_limite)]:
            col = QVBoxLayout(); col.setSpacing(3)
            col.addWidget(_hint(label_text)); col.addWidget(widget)
            row.addLayout(col, stretch=1)

        col_disp = QVBoxLayout(); col_disp.setSpacing(3)
        col_disp.addWidget(_hint("DISPONIBLES")); col_disp.addWidget(self._lbl_disponibles)
        row.addLayout(col_disp)
        return card

    # ── acciones ──────────────────────────────────────────────────────────

    def _iniciar_saldo_checker(self) -> None:
        """
        Lanza _SaldoCheckerWorker con un mini diálogo modal bloqueante.
        El usuario no puede pulsar 'Procesar pagos' hasta que termine la consulta.
        """
        if hasattr(self, "_saldo_checker") and self._saldo_checker.isRunning():
            self._saldo_checker.quit()
            self._saldo_checker.wait(5000)  # máx 5 s; evita freeze si la API no responde

        # ── Mini diálogo de carga ──────────────────────────────────────────
        self._saldo_dlg = QDialog(self)
        self._saldo_dlg.setWindowTitle("Verificando saldos")
        self._saldo_dlg.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
        )
        self._saldo_dlg.setMinimumWidth(380)
        v = QVBoxLayout(self._saldo_dlg)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(10)
        lbl_titulo = QLabel("Consultando saldos en Finnegans…")
        lbl_titulo.setObjectName("CardTitle")
        v.addWidget(lbl_titulo)
        self._saldo_dlg_msg = QLabel("Iniciando…")
        self._saldo_dlg_msg.setObjectName("Muted")
        v.addWidget(self._saldo_dlg_msg)
        pb = QProgressBar()
        pb.setRange(0, 0)        # indeterminado (spinner)
        pb.setTextVisible(False)
        pb.setFixedHeight(6)
        v.addWidget(pb)

        self._saldo_checker = _SaldoCheckerWorker(list(self._proveedores), self._cfg)
        self._saldo_checker.progreso.connect(self._saldo_dlg_msg.setText)
        self._saldo_checker.listo.connect(self._on_saldo_checker_listo)
        self._saldo_checker.start()
        self._saldo_dlg.exec()   # bloquea UI en loop propio hasta accept()

    def _on_saldo_checker_listo(self, docs_pendientes: dict) -> None:
        # Cerrar el diálogo de carga
        if hasattr(self, "_saldo_dlg") and self._saldo_dlg.isVisible():
            self._saldo_dlg.accept()

        self._docs_pendientes_cache = docs_pendientes
        self._docs_pendientes_ts = time.monotonic()

        # Auto-eliminar proveedores cuyos ítems ya no tienen saldo pendiente
        removidos: list[str] = []
        nuevos: list = []
        for p in self._proveedores:
            if (p.cuit
                    and docs_pendientes.get(p.cuit) is not None
                    and p.items
                    and all(i.documento not in docs_pendientes[p.cuit] for i in p.items)):
                removidos.append(p.nombre)
            else:
                nuevos.append(p)

        if removidos:
            self._proveedores = nuevos
            self._poblar_tabla()
            self.statusBar().showMessage(
                f"Eliminados {len(removidos)} sin saldo pendiente: {', '.join(removidos)}.",
                7000,
            )
        else:
            self.statusBar().showMessage("Saldos verificados — todos con saldo pendiente.", 3000)

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
            if config.is_configured(self._cfg):
                self._iniciar_saldo_checker()
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

        self._actualizando_tabla = True
        self._tabla.setUpdatesEnabled(False)
        self._tabla.setRowCount(len(filas))
        self._ops_a_procesar = []

        for row, (p, n_cheques, estado) in enumerate(filas):
            chk = _RoundCheckBox()
            chk.toggled.connect(self._on_checkbox_toggled)
            chk_wrap = QWidget()
            chk_wrap.setMinimumSize(20, 20)
            chk_layout = QHBoxLayout(chk_wrap)
            chk_layout.setContentsMargins(0, 0, 0, 0)
            chk_layout.setSpacing(0)
            chk_layout.addWidget(chk, alignment=Qt.AlignmentFlag.AlignCenter)
            self._tabla.setCellWidget(row, 0, chk_wrap)

            self._tabla.setItem(row, 1, QTableWidgetItem(p.nombre))
            self._tabla.setItem(row, 2, QTableWidgetItem(p.cuit or "—"))
            importe_fmt = _fmt_money(p.importe_total)
            item_imp = QTableWidgetItem(importe_fmt)
            item_imp.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._tabla.setItem(row, 3, item_imp)
            self._tabla.setItem(row, 4, QTableWidgetItem(p.modalidad.name.replace("_", " ").title()))
            item_ch = QTableWidgetItem(str(n_cheques) if n_cheques else "—")
            item_ch.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._tabla.setItem(row, 5, item_ch)
            label, variant = _ESTADOS[estado]
            self._tabla.setCellWidget(row, 6, theme.make_badge(label, variant))

        self._tabla.setUpdatesEnabled(True)
        self._actualizando_tabla = False

        listos = sum(1 for _, _, e in filas if e == "LISTO")
        self._actualizar_resumen_operativo(filas)
        self._btn_procesar.setEnabled(listos > 0)
        self._actualizar_btn_eliminar()
        self._actualizar_checkbox_header()
        self.statusBar().showMessage(
            f"{len(self._proveedores)} proveedores cargados. {listos} listos para procesar."
        )

    def _actualizar_resumen_operativo(self, filas: list[tuple]) -> None:
        if not hasattr(self, "_summary_values"):
            return

        listos = [(p, n) for p, n, estado in filas if estado == "LISTO"]
        manuales = sum(1 for _, _, estado in filas if estado == "MANUAL")
        total_listo = sum((p.importe_total for p, _ in listos), Decimal("0"))
        cheques_previstos = sum(n for _, n in listos)

        ultimo = self._numero_desde()
        limite = self._limite()
        disponibles = limite - ultimo if ultimo is not None and limite is not None else None

        values = {
            "listos": str(len(listos)),
            "total": _fmt_money(total_listo),
            "cheques": str(cheques_previstos),
            "manuales": str(manuales),
            "disponibles": str(disponibles) if disponibles is not None else "—",
        }
        colors = {
            "listos": theme.SUCCESS if listos else theme.TEXT_PRIMARY,
            "total": theme.TEXT_PRIMARY,
            "cheques": theme.TEXT_PRIMARY,
            "manuales": theme.WARNING if manuales else theme.TEXT_PRIMARY,
            "disponibles": (
                theme.SUCCESS if disponibles is not None and disponibles >= cheques_previstos
                else theme.DANGER if disponibles is not None
                else theme.TEXT_PRIMARY
            ),
        }

        for key, value in values.items():
            label = self._summary_values[key]
            label.setText(value)
            label.setStyleSheet(
                f"color: {colors[key]}; font-size: 18px; font-weight: 700;"
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
            self._debounce_tabla.start(150)

    def _poblar_tabla_si_proveedores(self) -> None:
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

        _CACHE_TTL = 900  # 15 minutos
        cache_docs = (
            self._docs_pendientes_cache
            if self._docs_pendientes_cache is not None
            and time.monotonic() - self._docs_pendientes_ts < _CACHE_TTL
            else None
        )
        self._precarga_worker = _PrecargarWorker(list(self._proveedores), self._cfg, cache_docs=cache_docs)
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

    def _on_precarga_lista(
        self,
        cotizacion_dolar,
        ret_cache,
        ratios_fc,
        docs_pendientes,
        cotizacion_fallback,
        ultimo_op,
    ) -> None:
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
        self._actualizar_estados_post_precarga(docs_pendientes)

        # Si hubo overflow, ofrecer chequera alternativa antes de continuar
        self._manejar_overflow(cotizacion_dolar, ret_cache, ratios_fc)
        self._asignar_numeros_op(ultimo_op)

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

    def _on_checkbox_toggled(self, _checked: bool) -> None:
        if self._actualizando_tabla:
            return
        self._actualizar_btn_eliminar()
        self._actualizar_checkbox_header()

    def _checkbox_en_fila(self, row: int) -> _RoundCheckBox | None:
        wrapper = self._tabla.cellWidget(row, 0)
        if wrapper is None:
            return None
        return wrapper.findChild(_RoundCheckBox)

    def _filas_marcadas(self) -> list[int]:
        filas = []
        for row in range(self._tabla.rowCount()):
            chk = self._checkbox_en_fila(row)
            if chk and chk.isChecked():
                filas.append(row)
        return filas

    def _actualizar_btn_eliminar(self) -> None:
        self._btn_eliminar.setEnabled(bool(self._filas_marcadas()))

    def _actualizar_checkbox_header(self) -> None:
        total = self._tabla.rowCount()
        marcadas = len(self._filas_marcadas())
        if total == 0 or marcadas == 0:
            state = Qt.CheckState.Unchecked
        elif marcadas == total:
            state = Qt.CheckState.Checked
        else:
            state = Qt.CheckState.PartiallyChecked
        self._tabla_header.set_check_state(state)

    def _marcar_todos(self, checked: bool) -> None:
        self._actualizando_tabla = True
        for row in range(self._tabla.rowCount()):
            chk = self._checkbox_en_fila(row)
            if chk is not None:
                chk.setChecked(checked)
        self._actualizando_tabla = False
        self._actualizar_btn_eliminar()
        self._actualizar_checkbox_header()

    def _eliminar_seleccionados(self) -> None:
        filas = self._filas_marcadas()
        if not filas:
            return
        if len(filas) > 1:
            reply = QMessageBox.question(
                self,
                "Eliminar pagos",
                f"Se van a eliminar {len(filas)} pagos de la lista.\n\n¿Querés continuar?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        for row in reversed(filas):
            if 0 <= row < len(self._proveedores):
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

            # Filtrar ítems sin saldo pendiente según composicionSaldoProveedor.
            # Los créditos (PAGO -) siempre se incluyen: no figuran en composición
            # de saldo porque ya están aplicados en Finnegans, pero deben estar
            # en el POST para descontar del total.
            pendientes = docs_pendientes.get(p.cuit) if p.cuit else None
            if pendientes is not None:
                items_sin_saldo = [
                    i for i in p.items
                    if i.documento not in pendientes
                    and not i.documento.lower().startswith("pago -")
                ]
                items_base = [
                    i for i in p.items
                    if i.documento in pendientes
                    or i.documento.lower().startswith("pago -")
                ]
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
                empresa_codigo=self._cfg.get("empresa_codigo", "EMPRE01"),
                cotizacion_dolar=cotizacion_dolar,
                retenciones=retenciones_post,
                fecha=date.today(),
            )
            self._ops_a_procesar.append(op)

    def _asignar_numeros_op(self, ultimo_op: str) -> None:
        ultimo_op = str(ultimo_op or "").strip()
        if not ultimo_op or not self._ops_a_procesar:
            return
        try:
            numeros = secuencia_comprobantes(ultimo_op, len(self._ops_a_procesar))
        except ValueError:
            self.statusBar().showMessage(
                f"No se pudo interpretar el último número de OP: {ultimo_op}",
                5000,
            )
            return
        for op, numero in zip(self._ops_a_procesar, numeros):
            op.numero_comprobante_estimado = numero

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

        combo_alt = theme.NoScrollComboBox()
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
                empresa_codigo=self._cfg.get("empresa_codigo", "EMPRE01"),
                cotizacion_dolar=cotizacion_dolar,
                retenciones=retenciones_post,
                fecha=date.today(),
            ))

    def _actualizar_estados_post_precarga(self, docs_pendientes: dict) -> None:
        """
        Tras la precarga, recorre la tabla y marca como 'Sin saldo' los proveedores
        cuyos ítems ya no tienen balance pendiente en Finnegans.
        Aplica también a proveedores MANUAL (incluidos en la consulta de saldo).
        """
        for row in range(self._tabla.rowCount()):
            item_cuit = self._tabla.item(row, 2)
            if item_cuit is None:
                continue
            cuit = item_cuit.text().strip()
            prov = next((p for p in self._proveedores if p.cuit == cuit), None)
            if prov is None or not prov.cuit:
                continue
            pendientes = docs_pendientes.get(prov.cuit)
            if pendientes is None:
                continue  # fail-open: no cambiar estado
            sin_saldo = [i for i in prov.items if i.documento not in pendientes]
            if sin_saldo and len(sin_saldo) == len(prov.items):
                label, variant = _ESTADOS["YA_PAGADA"]
                self._tabla.setCellWidget(row, 6, theme.make_badge(label, variant))

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
                     "numero_previsto": "",
                     "numero_real": "",
                     "importe": float(p.importe_total)}
                    for p in self._proveedores if p.modalidad == Modalidad.MANUAL]
        dlg = ResultDialog(resultados + manuales, self)
        theme.show_animated(dlg)
        dlg.exec()
        self.statusBar().showMessage("Procesamiento terminado.")
