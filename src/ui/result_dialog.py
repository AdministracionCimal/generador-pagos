import csv

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QFrame, QHBoxLayout, QHeaderView,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from src.ui import theme

_ESTADO_VARIANT = {"OK": "success", "ERROR": "danger", "MANUAL": "warning"}
_ROW_ERROR_BG   = QColor("#FEF2F2")


def _fmt(importe: float) -> str:
    return f"$ {importe:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


class ResultDialog(QDialog):
    def __init__(self, resultados: list[dict], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Resultado del procesamiento")
        self.resize(860, 560)
        self._resultados = resultados

        ok_items  = [r for r in resultados if r["estado"] == "OK"]
        err_items = [r for r in resultados if r["estado"] == "ERROR"]

        ok  = len(ok_items)
        err = len(err_items)

        total_ok  = sum(float(r.get("importe", 0) or 0) for r in ok_items)
        total_err = sum(float(r.get("importe", 0) or 0) for r in err_items)

        # — Header ————————————————————————————————————————————————————————
        title    = QLabel("Resultado del procesamiento")
        title.setObjectName("PageTitle")
        subtitle = QLabel(f"Se procesaron {len(resultados)} órdenes.")
        subtitle.setObjectName("PageSubtitle")

        # — Stats bar (3 KPIs) ——————————————————————————————————————————
        stats_bar = self._build_stats_bar([
            ("PROCESADAS OK",    ok,   _fmt(total_ok),                  "success"),
            ("CON ERROR",        err,  _fmt(total_err) if err else "—", "danger"),
            ("TOTAL CONFIRMADO", None, _fmt(total_ok),                  "neutral"),
        ])

        # — Tabla ————————————————————————————————————————————————————————
        self._tabla = QTableWidget(len(resultados), 5)
        self._tabla.setHorizontalHeaderLabels(
            ["Proveedor", "Estado", "OP prevista", "OP real / detalle", "Importe"]
        )
        self._tabla.setAlternatingRowColors(True)
        self._tabla.setShowGrid(False)
        self._tabla.verticalHeader().setVisible(False)
        self._tabla.verticalHeader().setDefaultSectionSize(34)
        self._tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        hh = self._tabla.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        _LEFT  = Qt.AlignmentFlag.AlignLeft  | Qt.AlignmentFlag.AlignVCenter
        _RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter

        for row, r in enumerate(resultados):
            is_error = r["estado"] == "ERROR"
            row_bg   = _ROW_ERROR_BG if is_error else None

            def _mk(text: str, align=_LEFT, bg=row_bg) -> QTableWidgetItem:
                it = QTableWidgetItem(text)
                it.setTextAlignment(align)
                if bg is not None:
                    it.setBackground(QBrush(bg))
                return it

            self._tabla.setItem(row, 0, _mk(r.get("nombre", "")))
            variant = _ESTADO_VARIANT.get(r["estado"], "neutral")
            self._tabla.setCellWidget(row, 1, theme.make_badge(r["estado"].title(), variant))
            self._tabla.setItem(row, 2, _mk(r.get("numero_previsto", "") or "—"))
            self._tabla.setItem(row, 3, _mk(r.get("numero_real") or r.get("detalle", "")))
            importe  = r.get("importe", "")
            imp_text = _fmt(float(importe)) if isinstance(importe, (int, float)) else str(importe)
            self._tabla.setItem(row, 4, _mk(imp_text, _RIGHT))

        # — Footer label ——————————————————————————————————————————————————
        parts = []
        if ok:  parts.append(f"✓  {ok} confirmada{'s' if ok != 1 else ''}")
        if err: parts.append(f"✗  {err} con error")
        footer_lbl = QLabel("  ·  ".join(parts) if parts else "")
        footer_lbl.setObjectName("Muted")

        # — Bottom bar ———————————————————————————————————————————————————
        btn_csv = QPushButton("Exportar CSV")
        btn_csv.clicked.connect(self._exportar_csv)
        btn_ok = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btn_ok.button(QDialogButtonBox.StandardButton.Ok).setObjectName("Primary")
        btn_ok.button(QDialogButtonBox.StandardButton.Ok).setText("Cerrar")
        btn_ok.accepted.connect(self.accept)

        bar = QHBoxLayout()
        bar.setSpacing(10)
        bar.addWidget(btn_csv)
        bar.addStretch()
        bar.addWidget(btn_ok)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 18)
        root.setSpacing(12)
        head = QVBoxLayout()
        head.setSpacing(2)
        head.addWidget(title)
        head.addWidget(subtitle)
        root.addLayout(head)
        root.addWidget(stats_bar)
        root.addWidget(self._tabla, stretch=1)
        root.addWidget(footer_lbl)
        root.addLayout(bar)

    def _build_stats_bar(self, stats: list[tuple]) -> QFrame:
        bar = QFrame()
        bar.setObjectName("Card")
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        for i, (label, value, sub, variant) in enumerate(stats):
            cell = QWidget()
            v = QVBoxLayout(cell)
            v.setContentsMargins(24, 14, 24, 14)
            v.setSpacing(3)

            lbl = QLabel(label)
            lbl.setObjectName("KpiLabel")
            fg = theme._BADGE_VARIANTS[variant][0]

            v.addWidget(lbl)

            if value is not None:
                num = QLabel(str(value))
                num.setObjectName("KpiNumber")
                num.setStyleSheet(f"color: {fg};")
                v.addWidget(num)
                sub_lbl = QLabel(sub)
                sub_lbl.setStyleSheet(f"font-size: 11px; color: {theme.TEXT_MUTED};")
                v.addWidget(sub_lbl)
            else:
                # TOTAL CONFIRMADO: only the formatted amount, big
                num = QLabel(sub)
                num.setObjectName("KpiNumber")
                num.setStyleSheet(f"color: {theme.TEXT_PRIMARY};")
                v.addWidget(num)

            row.addWidget(cell, stretch=1)

            if i < len(stats) - 1:
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.VLine)
                sep.setStyleSheet(
                    f"color: {theme.BORDER}; background: {theme.BORDER};"
                    f"max-width: 1px; margin: 14px 0;"
                )
                row.addWidget(sep)

        return bar

    def _exportar_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar reporte", "resultado_pagos.csv", "CSV (*.csv)"
        )
        if not path:
            return

        headers = ["Proveedor", "Estado", "OP Prevista", "OP Real / Detalle", "Importe"]
        total_ok = 0.0

        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(headers)
            for r in self._resultados:
                importe = r.get("importe", "")
                imp_val = float(importe) if isinstance(importe, (int, float)) else ""
                if r["estado"] == "OK" and isinstance(imp_val, float):
                    total_ok += imp_val
                w.writerow([
                    r.get("nombre", ""),
                    r.get("estado", ""),
                    r.get("numero_previsto", "") or "",
                    r.get("numero_real") or r.get("detalle", "") or "",
                    imp_val,
                ])
            w.writerow(["TOTALES", "", "", "", total_ok])
