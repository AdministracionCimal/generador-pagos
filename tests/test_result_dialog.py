from src.ui.result_dialog import _fmt


def test_fmt_formatea_miles_correctamente():
    assert _fmt(27242454.17) == "$ 27.242.454,17"


def test_fmt_cero():
    assert _fmt(0.0) == "$ 0,00"
