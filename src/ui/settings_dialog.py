from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QCompleter, QDialog, QDialogButtonBox, QFormLayout, QFrame,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

import src.config as config
from src.ui import theme


class _SettingsLoader(QThread):
    """Carga operaciones bancarias, empresas y cuentas en background."""
    operaciones_listas = pyqtSignal(list)
    empresas_listas    = pyqtSignal(list)
    cuentas_listas     = pyqtSignal(list)
    terminado          = pyqtSignal()

    def __init__(self, base_url, client_id, secret):
        super().__init__()
        self._url    = base_url
        self._id     = client_id
        self._secret = secret

    def run(self):
        try:
            from src.api.client import FinnegansClient
            c = FinnegansClient(self._url, self._id, self._secret)

            try:
                ops = c.get_tipo_operacion_bancaria_list()
                activos = sorted(
                    [o for o in ops if o.get("activo", o.get("Activo", True))],
                    key=lambda o: o.get("nombre", o.get("Nombre", "")),
                )
                self.operaciones_listas.emit(activos)
            except Exception:
                pass

            try:
                self.empresas_listas.emit(c.get_empresa_list())
            except Exception:
                pass

            try:
                self.cuentas_listas.emit(c.get_cuenta_list())
            except Exception:
                pass

        except Exception:
            pass
        finally:
            self.terminado.emit()


class _TestConnectionWorker(QThread):
    """Prueba la autenticación con Finnegans (GET /oauth/token)."""
    resultado = pyqtSignal(bool, str)   # (ok, mensaje)

    def __init__(self, base_url, client_id, secret):
        super().__init__()
        self._url    = base_url
        self._id     = client_id
        self._secret = secret

    def run(self):
        try:
            from src.api.client import FinnegansClient
            c = FinnegansClient(self._url, self._id, self._secret)
            c._fetch_token()
            self.resultado.emit(True, "Conexión exitosa")
        except Exception as e:
            msg = str(e)
            if len(msg) > 90:
                msg = msg[:87] + "…"
            self.resultado.emit(False, msg)


class SettingsDialog(QDialog):
    def __init__(self, cfg: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configuración")
        self.setMinimumWidth(640)
        self.resize(640, 700)
        self._cfg    = cfg
        self._loader = None
        self._tester = None

        primera_vez = not config.is_configured(cfg)

        # ── Encabezado ───────────────────────────────────────────────────
        title    = QLabel("Configuración")
        title.setObjectName("PageTitle")
        subtitle = QLabel(
            "Credenciales de la API Finnegans y cuentas por defecto. "
            "Se guardan cifradas en este equipo."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)

        # ── Acción global ────────────────────────────────────────────────
        self._btn_cargar = QPushButton("Cargar desde API")
        self._btn_cargar.setToolTip(
            "Conecta con Finnegans y rellena los combos de empresa, "
            "cuentas y operaciones bancarias."
        )
        self._btn_cargar.clicked.connect(self._cargar_manual)

        action_bar = QHBoxLayout()
        action_bar.addStretch()
        action_bar.addWidget(self._btn_cargar)

        # ── Progress ─────────────────────────────────────────────────────
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(4)
        self._progress.setVisible(False)

        self._lbl_cargando = QLabel("Cargando información desde Finnegans…")
        self._lbl_cargando.setObjectName("Muted")
        self._lbl_cargando.setVisible(False)

        # ── Campos ───────────────────────────────────────────────────────
        _DEFAULT_URL = "https://api.finneg.com/api"
        self._base_url = QLineEdit(cfg.get("base_url") or _DEFAULT_URL)
        self._base_url.setPlaceholderText(_DEFAULT_URL)
        self._base_url.setToolTip("URL base de la API Finnegans (ej. https://api.finneg.com/api)")

        self._client_id = QLineEdit(cfg.get("client_id", ""))
        self._client_id.setToolTip("ID de aplicación registrada en Finnegans.")

        self._client_secret = QLineEdit(cfg.get("client_secret", ""))
        self._client_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self._client_secret.setToolTip(
            "Contraseña de la aplicación. No se muestra y se guarda cifrada con Fernet."
        )

        self._banco_codigo = QLineEdit(cfg.get("banco_codigo", "00285"))
        self._banco_codigo.setToolTip("Código interno del banco en Finnegans (ej. 00285)")
        self._banco_codigo.setMaximumWidth(120)

        self._talonario_op_codigo = QLineEdit(cfg.get("talonario_op_codigo", "TE-OP"))
        self._talonario_op_codigo.setPlaceholderText("TE-OP")
        self._talonario_op_codigo.setMaximumWidth(160)
        self._talonario_op_codigo.setToolTip(
            "Código del talonario para Órdenes de Pago en Finnegans (ej. TE-OP)"
        )

        # — Empresa ——————————————————————————————————————————————————————
        self._combo_empresa = self._make_combo()
        self._combo_empresa.setMinimumWidth(320)
        _saved_emp_cod = cfg.get("empresa_codigo", "EMPRE01")
        _saved_emp_nom = cfg.get("empresa_nombre", _saved_emp_cod)
        self._combo_empresa.addItem(_saved_emp_nom, _saved_emp_cod)

        # — Cuentas contables ────────────────────────────────────────────
        self._combo_cuenta_cheque = self._make_combo()
        self._combo_cuenta_transf = self._make_combo()
        for combo in (self._combo_cuenta_cheque, self._combo_cuenta_transf):
            combo.setMinimumWidth(320)

        _saved_ch_cod = cfg.get("cuenta_banco_codigo", "02.01.04.01.0009")
        _saved_ch_nom = cfg.get("cuenta_banco_nombre", _saved_ch_cod)
        self._combo_cuenta_cheque.addItem(_saved_ch_nom, _saved_ch_cod)

        _saved_tr_cod = cfg.get("cuenta_banco_transferencia_codigo", "01.01.01.02.0006")
        _saved_tr_nom = cfg.get("cuenta_banco_transferencia_nombre", _saved_tr_cod)
        self._combo_cuenta_transf.addItem(_saved_tr_nom, _saved_tr_cod)

        # — Operaciones bancarias ────────────────────────────────────────
        self._combo_cheque = self._make_combo()
        self._combo_transf = self._make_combo()
        self._combo_cheque.addItem(
            cfg.get("op_bancaria_cheque_nombre", "Emisión de cheque propio"),
            cfg.get("op_bancaria_cheque_codigo", "EMCHPROP"),
        )
        self._combo_transf.addItem(
            cfg.get("op_bancaria_transferencia_nombre", "Transferencia por Lote"),
            cfg.get("op_bancaria_transferencia_codigo", "TLote"),
        )
        self._lbl_ops_estado = QLabel("")
        self._lbl_ops_estado.setObjectName("Muted")

        # ── Sección CONEXIÓN ──────────────────────────────────────────────
        grp_cred = QGroupBox("CONEXIÓN")
        vbox_cred = QVBoxLayout(grp_cred)
        vbox_cred.setSpacing(10)

        form_cred = QFormLayout()
        form_cred.setHorizontalSpacing(18)
        form_cred.setVerticalSpacing(10)
        form_cred.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form_cred.addRow("URL base Finnegans", self._base_url)
        form_cred.addRow("Client ID",          self._client_id)
        form_cred.addRow("Client Secret",      self._client_secret)
        vbox_cred.addLayout(form_cred)

        self._btn_probar = QPushButton("Probar conexión")
        self._btn_probar.setFixedWidth(148)
        self._btn_probar.setToolTip("Verifica las credenciales contra la API Finnegans.")
        self._btn_probar.clicked.connect(self._probar_conexion)
        self._lbl_test = QLabel("")
        self._lbl_test.setObjectName("Muted")

        test_row = QHBoxLayout()
        test_row.setSpacing(12)
        test_row.addWidget(self._btn_probar)
        test_row.addWidget(self._lbl_test)
        test_row.addStretch()
        vbox_cred.addLayout(test_row)

        # ── Sección EMPRESA Y BANCO ───────────────────────────────────────
        grp_empresa = QGroupBox("EMPRESA Y BANCO")
        form_empresa = QFormLayout(grp_empresa)
        form_empresa.setHorizontalSpacing(18)
        form_empresa.setVerticalSpacing(10)
        form_empresa.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form_empresa.addRow("Empresa",       self._combo_empresa)
        form_empresa.addRow("Código banco",  self._banco_codigo)

        # ── Sección TALONARIOS ────────────────────────────────────────────
        grp_talonarios = QGroupBox("TALONARIOS")
        form_tal = QFormLayout(grp_talonarios)
        form_tal.setHorizontalSpacing(18)
        form_tal.setVerticalSpacing(10)
        form_tal.addRow("Talonario orden de pago", self._talonario_op_codigo)

        # ── Sección CUENTAS CONTABLES ─────────────────────────────────────
        grp_cuentas = QGroupBox("CUENTAS CONTABLES")
        form_cuentas = QFormLayout(grp_cuentas)
        form_cuentas.setHorizontalSpacing(18)
        form_cuentas.setVerticalSpacing(10)
        form_cuentas.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form_cuentas.addRow("Cheques propios",  self._combo_cuenta_cheque)
        form_cuentas.addRow("Transferencias",   self._combo_cuenta_transf)

        # ── Sección OPERACIONES BANCARIAS ─────────────────────────────────
        grp_ops = QGroupBox("OPERACIONES BANCARIAS")
        vbox_ops = QVBoxLayout(grp_ops)
        vbox_ops.setSpacing(10)

        def _col(label_text, combo):
            col = QVBoxLayout()
            col.setSpacing(4)
            lbl = QLabel(label_text)
            lbl.setObjectName("CardHint")
            col.addWidget(lbl)
            col.addWidget(combo)
            return col

        combo_row = QHBoxLayout()
        combo_row.setSpacing(16)
        combo_row.addLayout(_col("CHEQUES PROPIOS", self._combo_cheque))
        combo_row.addLayout(_col("TRANSFERENCIAS",  self._combo_transf))
        combo_row.addStretch()
        vbox_ops.addLayout(combo_row)
        vbox_ops.addWidget(self._lbl_ops_estado)

        # ── Scroll area con las secciones ─────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setStyleSheet(f"background-color: {theme.BG_APP};")
        sections = QVBoxLayout(content)
        sections.setContentsMargins(0, 0, 6, 0)
        sections.setSpacing(8)
        sections.addWidget(grp_cred)
        sections.addWidget(grp_empresa)
        sections.addWidget(grp_talonarios)
        sections.addWidget(grp_cuentas)
        sections.addWidget(grp_ops)
        sections.addStretch()
        scroll.setWidget(content)

        # ── Botones ───────────────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("Primary")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Guardar")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        # ── Layout raíz ──────────────────────────────────────────────────
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        if primera_vez:
            layout.addWidget(self._make_banner(
                "Primera vez: completá las credenciales y guardá para empezar."
            ))

        layout.addLayout(action_bar)
        layout.addWidget(self._progress)
        layout.addWidget(self._lbl_cargando)
        layout.addWidget(scroll, stretch=1)
        layout.addSpacing(4)
        layout.addWidget(buttons)

        if config.is_configured(cfg):
            QTimer.singleShot(200, self._auto_cargar)

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _make_banner(text: str) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background-color: {theme.INFO_BG}; border: 1px solid #BFDBFE;"
            f" border-radius: 8px; }}"
        )
        h = QHBoxLayout(frame)
        h.setContentsMargins(14, 10, 14, 10)
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {theme.INFO}; font-size: 13px; background: transparent; border: none;"
        )
        lbl.setWordWrap(True)
        h.addWidget(lbl)
        return frame

    def _make_combo(self) -> theme.NoScrollComboBox:
        combo = theme.NoScrollComboBox()
        combo.setMinimumWidth(260)
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        completer = QCompleter()
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        combo.setCompleter(completer)
        return combo

    # ── Probar conexión ───────────────────────────────────────────────────

    def _probar_conexion(self) -> None:
        url = self._base_url.text().strip()
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url
        cid    = self._client_id.text().strip()
        secret = self._client_secret.text().strip()
        if not (url and cid and secret):
            self._lbl_test.setText("Completá URL, Client ID y Client Secret.")
            self._lbl_test.setStyleSheet(f"color: {theme.DANGER};")
            return
        self._btn_probar.setEnabled(False)
        self._lbl_test.setText("Probando…")
        self._lbl_test.setStyleSheet(f"color: {theme.TEXT_MUTED};")
        self._tester = _TestConnectionWorker(url, cid, secret)
        self._tester.resultado.connect(self._on_test_resultado)
        self._tester.start()

    def _on_test_resultado(self, ok: bool, msg: str) -> None:
        self._btn_probar.setEnabled(True)
        if ok:
            self._lbl_test.setText(f"✓  {msg}")
            self._lbl_test.setStyleSheet(f"color: {theme.SUCCESS}; font-weight: 600;")
        else:
            self._lbl_test.setText(f"✗  {msg}")
            self._lbl_test.setStyleSheet(f"color: {theme.DANGER};")

    # ── Carga en background ───────────────────────────────────────────────

    def _make_loader(self, url, cid, secret):
        loader = _SettingsLoader(url, cid, secret)
        loader.operaciones_listas.connect(self._on_ops_listas)
        loader.empresas_listas.connect(self._on_empresas_listas)
        loader.cuentas_listas.connect(self._on_cuentas_listas)
        loader.terminado.connect(self._on_carga_terminada)
        return loader

    def _auto_cargar(self) -> None:
        url    = self._cfg.get("base_url", "")
        cid    = self._cfg.get("client_id", "")
        secret = self._cfg.get("client_secret", "")
        if not (url and cid and secret):
            return
        self._set_loading(True)
        self._loader = self._make_loader(url, cid, secret)
        self._loader.start()

    def _cargar_manual(self) -> None:
        url = self._base_url.text().strip()
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url
        cid    = self._client_id.text().strip()
        secret = self._client_secret.text().strip()
        if not (url and cid and secret):
            self._lbl_ops_estado.setText("Completá URL, Client ID y Client Secret primero.")
            return
        self._set_loading(True)
        self._loader = self._make_loader(url, cid, secret)
        self._loader.start()

    def _set_loading(self, loading: bool) -> None:
        self._btn_cargar.setEnabled(not loading)
        self._progress.setVisible(loading)
        self._lbl_cargando.setVisible(loading)

    # ── Slots ─────────────────────────────────────────────────────────────

    def _on_ops_listas(self, activos: list) -> None:
        cur_cheque = self._combo_cheque.currentData()
        cur_transf = self._combo_transf.currentData()
        self._combo_cheque.clear()
        self._combo_transf.clear()
        for o in activos:
            cod = o.get("codigo") or o.get("Codigo", "")
            nom = o.get("nombre") or o.get("Nombre") or cod
            self._combo_cheque.addItem(nom, cod)
            self._combo_transf.addItem(nom, cod)
        for combo, saved in [(self._combo_cheque, cur_cheque),
                              (self._combo_transf, cur_transf)]:
            combo.completer().setModel(combo.model())
            theme.style_combo_popup(combo)
            idx = combo.findData(saved)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        self._lbl_ops_estado.setText(f"{len(activos)} operaciones cargadas.")

    def _on_empresas_listas(self, empresas: list) -> None:
        saved_cod = self._combo_empresa.currentData() or self._cfg.get("empresa_codigo", "EMPRE01")
        # Compatibilidad con configs viejas que guardaron el ID interno con prefijo.
        if isinstance(saved_cod, str) and saved_cod.startswith("EMPRESA_"):
            saved_cod = saved_cod.removeprefix("EMPRESA_")
        self._combo_empresa.clear()
        for e in sorted(empresas, key=lambda x: x.get("nombre", x.get("Nombre", ""))):
            cod = e.get("codigo") or e.get("Codigo", "")
            # /empresa/list devuelve el ID interno "EMPRESA_EMPRE01"; el POST de OPs
            # espera el código de negocio "EMPRE01" sin prefijo.
            if cod.startswith("EMPRESA_"):
                cod = cod.removeprefix("EMPRESA_")
            nom = e.get("nombre") or e.get("Nombre") or cod
            self._combo_empresa.addItem(nom, cod)
        self._combo_empresa.completer().setModel(self._combo_empresa.model())
        theme.style_combo_popup(self._combo_empresa)
        idx = self._combo_empresa.findData(saved_cod)
        if idx >= 0:
            self._combo_empresa.setCurrentIndex(idx)
        elif self._combo_empresa.count() > 0:
            self._combo_empresa.setCurrentIndex(0)

    def _on_cuentas_listas(self, cuentas: list) -> None:
        saved_ch = self._combo_cuenta_cheque.currentData() or self._cfg.get("cuenta_banco_codigo", "")
        saved_tr = self._combo_cuenta_transf.currentData() or self._cfg.get("cuenta_banco_transferencia_codigo", "")
        sorted_cuentas = sorted(cuentas, key=lambda x: x.get("nombre", x.get("Nombre", "")))
        for combo, saved in [
            (self._combo_cuenta_cheque, saved_ch),
            (self._combo_cuenta_transf, saved_tr),
        ]:
            combo.clear()
            for c in sorted_cuentas:
                cod = c.get("codigo") or c.get("Codigo", "")
                nom = c.get("nombre") or c.get("Nombre") or cod
                combo.addItem(f"{nom}  ({cod})", cod)
            combo.completer().setModel(combo.model())
            theme.style_combo_popup(combo)
            idx = combo.findData(saved)
            if idx >= 0:
                combo.setCurrentIndex(idx)

    def _on_carga_terminada(self) -> None:
        self._set_loading(False)

    def _accept(self) -> None:
        url = self._base_url.text().strip()
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url

        emp_cod = self._combo_empresa.currentData() or self._combo_empresa.currentText().strip()
        emp_nom = self._combo_empresa.currentText().strip()
        ch_cod  = self._combo_cuenta_cheque.currentData() or ""
        tr_cod  = self._combo_cuenta_transf.currentData() or ""

        def _strip_codigo(text: str, cod: str) -> str:
            suffix = f"  ({cod})"
            return text[: -len(suffix)] if text.endswith(suffix) else text

        ch_nom = _strip_codigo(self._combo_cuenta_cheque.currentText(), ch_cod)
        tr_nom = _strip_codigo(self._combo_cuenta_transf.currentText(), tr_cod)

        self._cfg.update({
            "base_url":                          url,
            "client_id":                         self._client_id.text().strip(),
            "client_secret":                     self._client_secret.text().strip(),
            "empresa_codigo":                    emp_cod,
            "empresa_nombre":                    emp_nom,
            "cuenta_banco_codigo":               ch_cod,
            "cuenta_banco_nombre":               ch_nom,
            "cuenta_banco_transferencia_codigo": tr_cod,
            "cuenta_banco_transferencia_nombre": tr_nom,
            "banco_codigo":                      self._banco_codigo.text().strip(),
            "talonario_op_codigo":               self._talonario_op_codigo.text().strip() or "TE-OP",
            "op_bancaria_cheque_codigo":          self._combo_cheque.currentData() or "EMCHPROP",
            "op_bancaria_cheque_nombre":          self._combo_cheque.currentText(),
            "op_bancaria_transferencia_codigo":   self._combo_transf.currentData() or "TLote",
            "op_bancaria_transferencia_nombre":   self._combo_transf.currentText(),
        })
        config.save(self._cfg)
        self.accept()
