from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QCompleter, QDialog, QDialogButtonBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QVBoxLayout,
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


class SettingsDialog(QDialog):
    def __init__(self, cfg: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configuración")
        self.setMinimumWidth(620)
        self._cfg    = cfg
        self._loader = None

        primera_vez = not config.is_configured(cfg)

        # ── Encabezado ───────────────────────────────────────────────────
        title    = QLabel("Configuración"); title.setObjectName("PageTitle")
        subtitle = QLabel(
            "Credenciales de la API Finnegans y cuentas por defecto. "
            "Se guardan cifradas en este equipo."
        )
        subtitle.setObjectName("PageSubtitle"); subtitle.setWordWrap(True)

        # ── Campos ───────────────────────────────────────────────────────
        _DEFAULT_URL = "https://api.finneg.com/api"
        self._base_url      = QLineEdit(cfg.get("base_url") or _DEFAULT_URL)
        self._base_url.setPlaceholderText(_DEFAULT_URL)
        self._client_id     = QLineEdit(cfg.get("client_id", ""))
        self._client_secret = QLineEdit(cfg.get("client_secret", ""))
        self._client_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self._banco_codigo  = QLineEdit(cfg.get("banco_codigo", "00285"))

        # — Empresa ——————————————————————————————————————————————————————
        self._combo_empresa = self._make_combo()
        self._combo_empresa.setMinimumWidth(320)
        _saved_emp_cod = cfg.get("empresa_codigo", "EMPRE01")
        _saved_emp_nom = cfg.get("empresa_nombre", _saved_emp_cod)
        self._combo_empresa.addItem(_saved_emp_nom, _saved_emp_cod)

        # — Cuentas bancarias ————————————————————————————————————————————
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

        # — Operaciones bancarias ————————————————————————————————————————
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

        btn_cargar = QPushButton("Cargar desde API")
        btn_cargar.clicked.connect(self._cargar_manual)

        def _col(label_text, combo):
            col = QVBoxLayout(); col.setSpacing(4)
            lbl = QLabel(label_text); lbl.setObjectName("CardHint")
            col.addWidget(lbl); col.addWidget(combo)
            return col

        combo_row = QHBoxLayout(); combo_row.setSpacing(12)
        combo_row.addLayout(_col("CHEQUES PROPIOS", self._combo_cheque))
        combo_row.addLayout(_col("TRANSFERENCIAS",  self._combo_transf))
        combo_row.addWidget(btn_cargar)
        combo_row.setAlignment(btn_cargar, Qt.AlignmentFlag.AlignBottom)

        self._lbl_ops_estado = QLabel(""); self._lbl_ops_estado.setObjectName("Muted")

        # ── Progress ─────────────────────────────────────────────────────
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(4)
        self._progress.setVisible(False)

        self._lbl_cargando = QLabel("Cargando información desde Finnegans…")
        self._lbl_cargando.setObjectName("Muted")
        self._lbl_cargando.setVisible(False)

        # ── Sección CONEXIÓN ──────────────────────────────────────────────
        grp_cred = QGroupBox("CONEXIÓN")
        form_cred = QFormLayout(grp_cred)
        form_cred.setHorizontalSpacing(18); form_cred.setVerticalSpacing(10)
        form_cred.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form_cred.addRow("URL base Finnegans", self._base_url)
        form_cred.addRow("Client ID",          self._client_id)
        form_cred.addRow("Client Secret",      self._client_secret)

        # ── Sección CUENTAS BANCARIAS ─────────────────────────────────────
        grp_banco = QGroupBox("CUENTAS BANCARIAS")
        form_banco = QFormLayout(grp_banco)
        form_banco.setHorizontalSpacing(18); form_banco.setVerticalSpacing(10)
        form_banco.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form_banco.addRow("Empresa",                      self._combo_empresa)
        form_banco.addRow("Cuenta cheques propios",       self._combo_cuenta_cheque)
        form_banco.addRow("Cuenta transferencias",        self._combo_cuenta_transf)
        form_banco.addRow("Código de banco",              self._banco_codigo)

        # ── Sección OPERACIONES ───────────────────────────────────────────
        grp_ops = QGroupBox("OPERACIONES BANCARIAS")
        form_ops = QFormLayout(grp_ops)
        form_ops.setHorizontalSpacing(18); form_ops.setVerticalSpacing(10)
        form_ops.addRow("", combo_row)
        form_ops.addRow("", self._lbl_ops_estado)

        # ── Botones ───────────────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("Primary")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Guardar")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        # ── Layout ────────────────────────────────────────────────────────
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18); layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        if primera_vez:
            banner = self._make_banner(
                "Primera vez: completá las credenciales y guardá para empezar."
            )
            layout.addWidget(banner)

        layout.addWidget(self._progress)
        layout.addWidget(self._lbl_cargando)
        layout.addWidget(grp_cred)
        layout.addWidget(grp_banco)
        layout.addWidget(grp_ops)
        layout.addSpacing(4)
        layout.addWidget(buttons)

        if config.is_configured(cfg):
            QTimer.singleShot(200, self._auto_cargar)

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _make_banner(text: str):
        """Info banner — full border, no side-stripe."""
        from PyQt6.QtWidgets import QFrame, QHBoxLayout
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background-color: {theme.INFO_BG}; border: 1px solid #BFDBFE;"
            f" border-radius: 8px; }}"
        )
        h = QHBoxLayout(frame); h.setContentsMargins(14, 10, 14, 10)
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {theme.INFO}; font-size: 13px; background: transparent; border: none;"
        )
        lbl.setWordWrap(True)
        h.addWidget(lbl)
        return frame

    def _make_combo(self) -> QComboBox:
        combo = QComboBox()
        combo.setMinimumWidth(260)
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        completer = QCompleter()
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        combo.setCompleter(completer)
        return combo

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
        self._progress.setVisible(True)
        self._lbl_cargando.setVisible(True)
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
        self._progress.setVisible(True)
        self._lbl_cargando.setVisible(True)
        self._loader = self._make_loader(url, cid, secret)
        self._loader.start()

    # ── Slots ─────────────────────────────────────────────────────────────

    def _on_ops_listas(self, activos: list) -> None:
        cur_cheque = self._combo_cheque.currentData()
        cur_transf = self._combo_transf.currentData()
        self._combo_cheque.clear(); self._combo_transf.clear()
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
        self._combo_empresa.clear()
        for e in sorted(empresas, key=lambda x: x.get("nombre", x.get("Nombre", ""))):
            cod = e.get("codigo") or e.get("Codigo", "")
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
        self._progress.setVisible(False)
        self._lbl_cargando.setVisible(False)

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
            "op_bancaria_cheque_codigo":         self._combo_cheque.currentData() or "EMCHPROP",
            "op_bancaria_cheque_nombre":         self._combo_cheque.currentText(),
            "op_bancaria_transferencia_codigo":  self._combo_transf.currentData() or "TLote",
            "op_bancaria_transferencia_nombre":  self._combo_transf.currentText(),
        })
        config.save(self._cfg)
        self.accept()
