import csv

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QFrame, QHBoxLayout, QHeaderView,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from src.ui import theme

_ESTADO_VARIANT = {"OK": "success", "ERROR": "danger", "MANUAL": "warning"}


class ResultDialog(QDialog):
    def __init__(self, resultados: list[dict], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Resultado del procesamiento")
        self.resize(900, 560)
        self._resultados = resultados

        ok     = sum(1 for r in resultados if r["estado"] == "OK")
        err    = sum(1 for r in resultados if r["estado"] == "ERROR")
        manual = sum(1 for r in resultados if r["estado"] == "MANUAL")

        # — Header ————————————————————————————————————————————————————————
        title    = QLabel("Resultado del procesamiento"); title.setObjectName("PageTitle")
        subtitle = QLabel(f"Se procesaron {len(resultados)} órdenes.")
        subtitle.setObjectName("PageSubtitle")

        # — Stats bar (un solo card, 3 celdas separadas) ——————————————————
        stats_bar = self._build_stats_bar([
            ("PROCESADAS OK",  ok,     "success"),
            ("CON ERROR",      err,    "danger"),
            ("CARGA MANUAL",   manual, "warning"),
        ])

        # — Tabla ————————————————————————————————————————————————————————
        self._tabla = QTableWidget(len(resultados), 4)
        self._tabla.setHorizontalHeaderLabels(
            ["Proveedor", "Estado", "Nº Comprobante / Detalle", "Importe"]
        )
        self._tabla.setAlternatingRowColors(True)
        self._tabla.setShowGrid(False)
        self._tabla.verticalHeader().setVisible(False)
        self._tabla.verticalHeader().setDefaultSectionSize(42)
        self._tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        hh = self._tabla.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        for row, r in enumerate(resultados):
            self._tabla.setItem(row, 0, QTableWidgetItem(r.get("nombre", "")))
            variant = _ESTADO_VARIANT.get(r["estado"], "neutral")
            self._tabla.setCellWidget(row, 1, theme.make_badge(r["estado"].title(), variant))
            self._tabla.setItem(row, 2, QTableWidgetItem(r.get("detalle", "")))
            importe = r.get("importe", "")
            imp_text = (
                f"$ {importe:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                if isinstance(importe, (int, float)) else str(importe)
            )
            item_imp = QTableWidgetItem(imp_text)
            item_imp.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._tabla.setItem(row, 3, item_imp)

        # — Bottom bar ———————————————————————————————————————————————————
        btn_csv = QPushButton("Exportar CSV")
        btn_csv.clicked.connect(self._exportar_csv)
        btn_ok = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btn_ok.button(QDialogButtonBox.StandardButton.Ok).setObjectName("Primary")
        btn_ok.button(QDialogButtonBox.StandardButton.Ok).setText("Cerrar")
        btn_ok.accepted.connect(self.accept)

        bar = QHBoxLayout(); bar.setSpacing(10)
        bar.addWidget(btn_csv); bar.addStretch(); bar.addWidget(btn_ok)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 18); root.setSpacing(14)
        head = QVBoxLayout(); head.setSpacing(2)
        head.addWidget(title); head.addWidget(subtitle)
        root.addLayout(head)
        root.addWidget(stats_bar)
        root.addWidget(self._tabla, stretch=1)
        root.addLayout(bar)

    def _build_stats_bar(self, stats: list[tuple]) -> QFrame:
        """Horizontal stat bar inside a single card — avoids identical card grid."""
        bar = QFrame(); bar.setObjectName("Card")
        row = QHBoxLayout(bar); row.setContentsMargins(0, 0, 0, 0); row.setSpacing(0)

        for i, (label, value, variant) in enumerate(stats):
            cell = QWidget()
            v = QVBoxLayout(cell); v.setContentsMargins(28, 18, 28, 18); v.setSpacing(5)

            lbl = QLabel(label); lbl.setObjectName("KpiLabel")
            num = QLabel(str(value)); num.setObjectName("KpiNumber")
            fg  = theme._BADGE_VARIANTS[variant][0]
            num.setStyleSheet(f"color: {fg};")

            v.addWidget(lbl)
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
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["nombre", "estado", "detalle", "importe"])
            w.writeheader()
            w.writerows(self._resultados)
