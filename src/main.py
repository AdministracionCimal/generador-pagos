import sys
from pathlib import Path

from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtWidgets import QApplication

from src.ui import theme
from src.ui.main_window import MainWindow


def _app_icon() -> QIcon:
    """Devuelve el icono embebido (PyInstaller) o desde assets/."""
    # sys._MEIPASS existe cuando corre como .exe de PyInstaller
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent.parent))
    ico = base / "assets" / "icon.ico"
    if ico.exists():
        return QIcon(str(ico))
    return QIcon()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Generador de Pagos")
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI Variable Display", 9))
    app.setStyleSheet(theme.STYLESHEET)
    icon = _app_icon()
    app.setWindowIcon(icon)
    window = MainWindow()
    window.setWindowIcon(icon)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
