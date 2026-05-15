"""Dialogo de verificacion previo al envio a Finnegans."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.domain.models import Modalidad, OpPago, ProveedorTanda
from src.ui import theme


def _fmt(importe: float) -> str:
    return f"$ {importe:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _retencion_label(ret: dict) -> str:
    nombre = str(ret.get("_nombre", "") or "").strip()
    nombre_tipo = str(ret.get("_nombre_tipo", "") or "").strip()
    principal = ""
    if nombre_tipo and nombre and nombre_tipo.casefold() != nombre.casefold():
        principal = f"{nombre_tipo} - {nombre}"
    else:
        principal = nombre or nombre_tipo
    return principal or "—"


class PreviewDialog(QDialog):
    def __init__(
        self,
        ops: list[OpPago],
        manuales: list[ProveedorTanda],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Verificacion previa al envio")
        self.resize(980, 680)

        total_ops   = len(ops)
        total_bruto = sum(float(op.proveedor.importe_total) for op in ops)
        total_ret   = sum(
            sum(float(r.get("Importe", 0) or 0) for r in op.retenciones)
            for op in ops
        )
        total_neto  = total_bruto - total_ret

        title = QLabel("Revisar antes de enviar")
        title.setObjectName("PageTitle")

        subtitle = QLabel(
            "Chequea importes, forma de pago y retenciones antes de confirmar el envío."
        )
        subtitle.setObjectName("PageSubtitle")

        stats_bar = self._build_stats_bar([
            ("ÓRDENES",      str(total_ops),   theme.BRAND),
            ("BRUTO",        _fmt(total_bruto), theme.TEXT_PRIMARY),
            ("RETENCIONES",
             _fmt(total_ret) if total_ret > 0 else "—",
             theme.DANGER if total_ret > 0 else theme.TEXT_MUTED),
            ("NETO A PAGAR", _fmt(total_neto),  theme.SUCCESS),
        ])

        manual_card = None
        if manuales:
            manual_card = self._build_manual_card(manuales)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        stack = QVBoxLayout(content)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.setSpacing(12)

        for op in ops:
            stack.addWidget(self._build_provider_card(op))
        stack.addStretch()

        scroll.setWidget(content)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        btn_ok.setText("Confirmar y enviar")
        btn_ok.setObjectName("Primary")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 16)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(stats_bar)
        if manual_card is not None:
            layout.addWidget(manual_card)
        layout.addWidget(scroll, stretch=1)
        layout.addWidget(buttons)

    def _build_stats_bar(self, stats: list[tuple[str, str, str]]) -> QFrame:
        bar = QFrame()
        bar.setObjectName("Card")
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        for index, (label, value, color) in enumerate(stats):
            cell = QWidget()
            col = QVBoxLayout(cell)
            col.setContentsMargins(24, 14, 24, 14)
            col.setSpacing(4)

            lbl = QLabel(label)
            lbl.setObjectName("KpiLabel")
            num = QLabel(value)
            num.setObjectName("KpiNumber")
            num.setStyleSheet(f"color: {color};")

            col.addWidget(lbl)
            col.addWidget(num)
            row.addWidget(cell, stretch=1)

            if index < len(stats) - 1:
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.VLine)
                sep.setStyleSheet(
                    f"color: {theme.BORDER}; background: {theme.BORDER};"
                    f"max-width: 1px; margin: 14px 0;"
                )
                row.addWidget(sep)

        return bar

    def _build_manual_card(self, manuales: list[ProveedorTanda]) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        row = QHBoxLayout(card)
        row.setContentsMargins(18, 14, 18, 14)
        row.setSpacing(12)

        row.addWidget(theme.make_badge("Carga manual", "warning"))

        text = QLabel(
            f"{len(manuales)} proveedor(es) no se enviaran automaticamente: "
            + ", ".join(p.nombre for p in manuales[:5])
            + ("..." if len(manuales) > 5 else "")
        )
        text.setWordWrap(True)
        row.addWidget(text, stretch=1)
        return card

    def _build_provider_card(self, op: OpPago) -> QFrame:
        p = op.proveedor
        card = QFrame()
        card.setObjectName("Card")
        root = QVBoxLayout(card)
        root.setContentsMargins(16, 12, 16, 14)
        root.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(16)

        left = QVBoxLayout()
        left.setSpacing(6)

        name = QLabel(p.nombre)
        name.setStyleSheet(
            f"color: {theme.TEXT_PRIMARY}; font-size: 16px; font-weight: 700;"
        )
        left.addWidget(name)

        meta = QHBoxLayout()
        meta.setSpacing(8)
        modalidad = "Cheque propio" if p.modalidad == Modalidad.CHEQUE_PROPIO else "Transferencia"
        modalidad_variant = "info" if p.modalidad == Modalidad.TRANSFERENCIA else "success"
        meta.addWidget(theme.make_badge(modalidad, modalidad_variant))

        cuit = QLabel(f"CUIT {p.cuit or '—'}")
        cuit.setObjectName("Muted")
        meta.addWidget(cuit)

        if op.retenciones:
            meta.addWidget(theme.make_badge(f"{len(op.retenciones)} retenciones", "warning"))

        if op.numero_comprobante_estimado:
            meta.addWidget(theme.make_badge(op.numero_comprobante_estimado, "neutral"))

        meta.addStretch()
        left.addLayout(meta)
        header.addLayout(left, stretch=1)

        total_col = QVBoxLayout()
        total_col.setSpacing(2)
        total_col.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        bruto   = float(p.importe_total)
        neto_op = self._payment_total(op)
        ret_op  = bruto - neto_op

        if op.retenciones:
            for hint_txt, val_txt, color, fsize in [
                ("BRUTO",        _fmt(bruto),          theme.TEXT_MUTED,    "13px"),
                ("RETENCIONES",  f"−{_fmt(ret_op)}",   theme.DANGER,        "13px"),
                ("NETO A PAGAR", _fmt(neto_op),         theme.TEXT_PRIMARY,  "22px"),
            ]:
                h = QLabel(hint_txt); h.setObjectName("KpiLabel")
                total_col.addWidget(h, alignment=Qt.AlignmentFlag.AlignRight)
                lbl_v = QLabel(val_txt)
                lbl_v.setStyleSheet(
                    f"color: {color}; font-size: {fsize}; font-weight: 700;"
                )
                total_col.addWidget(lbl_v, alignment=Qt.AlignmentFlag.AlignRight)
                if hint_txt != "NETO A PAGAR":
                    total_col.addSpacing(6)
        else:
            total_lbl = QLabel("TOTAL A ENVIAR")
            total_lbl.setObjectName("KpiLabel")
            total_val = QLabel(_fmt(bruto))
            total_val.setStyleSheet(
                f"color: {theme.TEXT_PRIMARY}; font-size: 22px; font-weight: 700;"
            )
            total_col.addWidget(total_lbl, alignment=Qt.AlignmentFlag.AlignRight)
            total_col.addWidget(total_val, alignment=Qt.AlignmentFlag.AlignRight)

        header.addLayout(total_col)
        root.addLayout(header)

        body = QGridLayout()
        body.setHorizontalSpacing(14)
        body.setVerticalSpacing(10)

        items_table = self._build_table(
            ["Documento", "Comprobante", "Vencimiento", "Importe"],
            [
                [
                    item.documento,
                    item.comprobante,
                    item.fecha_vto.strftime("%d/%m/%Y") if item.fecha_vto else "—",
                    _fmt(float(item.importe)),
                ]
                for item in p.items
            ],
            right_align_cols={3},
        )
        body.addWidget(
            self._build_section("Items a cancelar", items_table),
            0,
            0,
            alignment=Qt.AlignmentFlag.AlignTop,
        )

        pago_total = self._payment_total(op)
        pago_table = self._build_payment_table(op)
        body.addWidget(
            self._build_section("Pago", pago_table, meta_text=f"Total {_fmt(pago_total)}"),
            0,
            1,
            alignment=Qt.AlignmentFlag.AlignTop,
        )

        if op.retenciones:
            ret_table = self._build_retenciones_table(op)
            body.addWidget(
                self._build_section("Retenciones", ret_table),
                1,
                0,
                1,
                2,
                alignment=Qt.AlignmentFlag.AlignTop,
            )

        body.setColumnStretch(0, 3)
        body.setColumnStretch(1, 2)
        root.addLayout(body)
        return card

    def _build_section(self, title: str, content: QWidget, meta_text: str = "") -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        title_lbl = QLabel(title.upper())
        title_lbl.setObjectName("CardHint")
        header.addWidget(title_lbl)
        header.addStretch()

        if meta_text:
            meta_lbl = QLabel(meta_text.upper())
            meta_lbl.setObjectName("CardHint")
            meta_lbl.setStyleSheet(f"color: {theme.TEXT_PRIMARY}; font-weight: 700;")
            header.addWidget(meta_lbl)

        layout.addLayout(header)
        layout.addWidget(content)
        return wrapper

    def _build_payment_table(self, op: OpPago) -> QTableWidget:
        if op.cheques:
            headers = ["Numero", "Vencimiento", "Importe"]
            rows = [
                [ch.numero, ch.fecha_vencimiento.strftime("%d/%m/%Y"), _fmt(float(ch.importe))]
                for ch in op.cheques
            ]
            return self._build_table(headers, rows, right_align_cols={2})

        return self._build_table(
            ["Operacion", "Importe"],
            [["Transferencia por lote", _fmt(self._payment_total(op))]],
            right_align_cols={1},
        )

    def _payment_total(self, op: OpPago) -> float:
        total_ret = sum(float(r.get("Importe", 0) or 0) for r in op.retenciones)
        return float(op.proveedor.importe_total) - total_ret

    def _build_retenciones_table(self, op: OpPago) -> QTableWidget:
        rows = []
        for ret in op.retenciones:
            acumulado = ret.get("_isar_acumulado")
            if acumulado is None:
                acumulado = ret.get("ISARAcumulado")
            rows.append([
                _retencion_label(ret),
                _fmt(ret.get("ISAR", 0)),
                _fmt(acumulado) if acumulado is not None else "—",
                _fmt(ret.get("Importe", 0)),
            ])
        return self._build_table(
            ["Concepto", "Base actual", "Acumulado", "Importe"],
            rows,
            right_align_cols={1, 2, 3},
        )

    def _build_table(
        self,
        headers: list[str],
        rows: list[list[str]],
        right_align_cols: set[int] | None = None,
    ) -> QTableWidget:
        right_align_cols = right_align_cols or set()
        table = QTableWidget(len(rows), len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(30)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.setFrameShape(QFrame.Shape.NoFrame)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        hh = table.horizontalHeader()
        for col in range(len(headers)):
            mode = QHeaderView.ResizeMode.ResizeToContents if col != 0 else QHeaderView.ResizeMode.Stretch
            hh.setSectionResizeMode(col, mode)

        for row_idx, row in enumerate(rows):
            for col_idx, value in enumerate(row):
                item = QTableWidgetItem(value)
                if col_idx in right_align_cols:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(row_idx, col_idx, item)

        table.setStyleSheet(
            f"QTableWidget {{"
            f"  background-color: {theme.BG_SURFACE};"
            f"  border: 1px solid {theme.BORDER};"
            f"  border-radius: 8px;"
            f"  alternate-background-color: {theme.BG_SUBTLE};"
            f"}}"
            f"QTableWidget::item {{ padding: 4px 10px; }}"
            f"QHeaderView::section {{"
            f"  background-color: {theme.BG_SUBTLE};"
            f"  color: {theme.TEXT_MUTED};"
            f"  padding: 6px 10px;"
            f"  border: none;"
            f"  border-bottom: 1px solid {theme.BORDER};"
            f"  font-size: 10px;"
            f"  font-weight: 600;"
            f"}}"
        )

        self._fit_table_height(table)
        return table

    def _fit_table_height(self, table: QTableWidget) -> None:
        header_height = table.horizontalHeader().height()
        rows_height = sum(table.rowHeight(row) for row in range(table.rowCount()))
        frame = table.frameWidth() * 2
        table.setFixedHeight(header_height + rows_height + frame + 2)
