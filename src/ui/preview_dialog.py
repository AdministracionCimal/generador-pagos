"""Diálogo de verificación previo al envío a Finnegans."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout,
)

from src.domain.models import Modalidad, OpPago, ProveedorTanda
from src.ui import theme


def _fmt(importe: float) -> str:
    return f"$ {importe:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _item(cols: list[str], color: QColor | None = None,
          bold: bool = False) -> QTreeWidgetItem:
    it = QTreeWidgetItem(cols)
    if color:
        for c in range(len(cols)):
            it.setForeground(c, color)
    if bold:
        f = QFont(); f.setBold(True)
        it.setFont(0, f)
    return it


class PreviewDialog(QDialog):
    def __init__(
        self,
        ops: list[OpPago],
        manuales: list[ProveedorTanda],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Verificación previa al envío")
        self.resize(900, 580)

        total_ops     = len(ops)
        total_importe = sum(float(op.proveedor.importe_total) for op in ops)

        # ── Colores del tema ─────────────────────────────────────────────
        _GRAY  = QColor(theme.TEXT_MUTED)
        _BLUE  = QColor(theme.BRAND)
        _GREEN = QColor(theme.SUCCESS)
        _RED   = QColor(theme.DANGER)

        bold_font = QFont(); bold_font.setBold(True)
        semi_font = QFont(); semi_font.setWeight(QFont.Weight.Medium)

        # ── Encabezado ───────────────────────────────────────────────────
        title = QLabel("Revisar antes de enviar")
        title.setObjectName("PageTitle")

        lbl_resumen = QLabel(
            f"<b>{total_ops} órdenes de pago</b> por un total de "
            f"<b>{_fmt(total_importe)}</b> listas para enviar."
        )
        lbl_resumen.setObjectName("PageSubtitle")

        lbl_manual = None
        if manuales:
            lbl_manual = QLabel(
                f"⚠ {len(manuales)} proveedor(es) requieren carga manual y no se enviarán: "
                + ", ".join(p.nombre for p in manuales[:5])
                + ("…" if len(manuales) > 5 else "")
            )
            lbl_manual.setObjectName("Muted")
            lbl_manual.setWordWrap(True)

        # ── Separador ────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {theme.BORDER};")

        # ── Árbol ────────────────────────────────────────────────────────
        self._tree = QTreeWidget()
        self._tree.setColumnCount(4)
        self._tree.setHeaderLabels(["Concepto", "Detalle", "Fecha", "Importe"])
        self._tree.setAlternatingRowColors(False)
        self._tree.setAnimated(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setIndentation(20)
        self._tree.header().setStretchLastSection(False)
        self._tree.setColumnWidth(0, 290)
        self._tree.setColumnWidth(1, 190)
        self._tree.setColumnWidth(2, 105)
        self._tree.setColumnWidth(3, 130)
        self._tree.header().setMinimumSectionSize(80)

        # Estilo adicional inline para que el header quede igual que QTableWidget
        self._tree.setStyleSheet(
            f"QHeaderView::section {{"
            f"  background-color: {theme.BG_SURFACE};"
            f"  color: {theme.TEXT_MUTED};"
            f"  padding: 10px 12px;"
            f"  border: none;"
            f"  border-bottom: 1px solid {theme.BORDER};"
            f"  font-weight: 600;"
            f"  font-size: 11px;"
            f"  letter-spacing: 0.4px;"
            f"}}"
        )

        for op in ops:
            p = op.proveedor
            modalidad_txt = (
                "Cheque propio" if p.modalidad == Modalidad.CHEQUE_PROPIO
                else "Transferencia"
            )
            root = QTreeWidgetItem([
                p.nombre,
                p.cuit or "—",
                modalidad_txt,
                _fmt(float(p.importe_total)),
            ])
            root.setFont(0, bold_font)
            for c in range(4):
                root.setForeground(c, _BLUE)

            # — Ítems a cancelar ─────────────────────────────────────────
            nodo_items = _item(["Ítems a cancelar", "", "", ""], _GRAY, bold=True)
            for item in p.items:
                nodo_items.addChild(_item([
                    item.documento,
                    item.comprobante,
                    item.fecha_vto.strftime("%d/%m/%Y") if item.fecha_vto else "",
                    _fmt(float(item.importe)),
                ]))
            root.addChild(nodo_items)

            # — Cheques a emitir ─────────────────────────────────────────
            if op.cheques:
                nodo_cheq = _item(
                    [f"Cheques a emitir ({len(op.cheques)})", "", "", ""],
                    _GRAY, bold=True,
                )
                for ch in op.cheques:
                    nodo_cheq.addChild(_item([
                        f"Nº {ch.numero}",
                        "",
                        ch.fecha_vencimiento.strftime("%d/%m/%Y"),
                        _fmt(float(ch.importe)),
                    ], _GREEN))
                root.addChild(nodo_cheq)
            elif p.modalidad == Modalidad.TRANSFERENCIA:
                total_ret = sum(r.get("Importe", 0) for r in op.retenciones)
                neto_transf = float(p.importe_total) - total_ret
                nodo_transf = _item(
                    ["Transferencia por lote", "", "", _fmt(neto_transf)],
                    _GREEN,
                )
                root.addChild(nodo_transf)

            # — Retenciones ──────────────────────────────────────────────
            if op.retenciones:
                nodo_ret = _item(
                    [f"Retenciones ({len(op.retenciones)})", "", "", ""],
                    _GRAY, bold=True,
                )
                for ret in op.retenciones:
                    codigo   = ret.get("RetencionCodigo", "")
                    nombre   = ret.get("_nombre", codigo)
                    isar_act = ret.get("ISAR", 0)
                    isar_his = ret.get("_isar_historico")
                    isar_acc = ret.get("_isar_acumulado")
                    ya_ret   = ret.get("_ya_retenido")
                    importe  = ret.get("Importe", 0)

                    # Fila principal: nombre + importe
                    nodo_cod = _item([nombre, "", "", _fmt(importe)], _RED, bold=True)

                    # Sub-filas de detalle si tenemos datos de acumulado
                    nodo_cod.addChild(_item(
                        ["Base actual", _fmt(isar_act), "", ""],
                    ))
                    if isar_his is not None:
                        nodo_cod.addChild(_item(
                            ["Acumulado anterior (mes)", _fmt(isar_his), "", ""],
                        ))
                    if isar_acc is not None:
                        nodo_cod.addChild(_item(
                            ["Total acumulado al confirmar", _fmt(isar_acc), "", ""],
                        ))
                    if ya_ret is not None and ya_ret > 0:
                        nodo_cod.addChild(_item(
                            ["Ya retenido este mes", _fmt(ya_ret), "", ""],
                        ))

                    nodo_ret.addChild(nodo_cod)
                root.addChild(nodo_ret)

            self._tree.addTopLevelItem(root)
            root.setExpanded(True)
            nodo_items.setExpanded(True)

        self._tree.resizeColumnToContents(2)

        # ── Botones ──────────────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        btn_ok.setText("Confirmar y enviar")
        btn_ok.setObjectName("Primary")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        # ── Layout ───────────────────────────────────────────────────────
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(lbl_resumen)
        if lbl_manual:
            layout.addWidget(lbl_manual)
        layout.addWidget(sep)
        layout.addWidget(self._tree, stretch=1)
        layout.addWidget(buttons)
