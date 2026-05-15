from src.ui.result_dialog import _comparacion_numero


def test_comparacion_numero_ok_coincide():
    assert _comparacion_numero({
        "estado": "OK",
        "numero_previsto": "OP-0004-00022002",
        "numero_real": "OP-0004-00022002",
    }) == ("Coincide", "success")


def test_comparacion_numero_ok_no_coincide():
    assert _comparacion_numero({
        "estado": "OK",
        "numero_previsto": "OP-0004-00022002",
        "numero_real": "OP-0004-00022003",
    }) == ("No coincide", "warning")


def test_comparacion_numero_no_ok_queda_neutral():
    assert _comparacion_numero({
        "estado": "ERROR",
        "numero_previsto": "OP-0004-00022002",
        "numero_real": "",
    }) == ("—", "neutral")
