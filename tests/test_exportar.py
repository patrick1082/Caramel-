from io import BytesIO

from openpyxl import load_workbook

from predictor.exportar import COLUMNAS_APUESTAS, COLUMNAS_MOVIMIENTOS, exportar_excel
from predictor.modelos import Estado, Movimiento, TipoMovimiento


def _abrir(bitacora):
    contenido = exportar_excel(bitacora.apuestas(), bitacora.movimientos(), bitacora.resumen())
    return load_workbook(BytesIO(contenido))


def _filas(hoja):
    return list(hoja.iter_rows(values_only=True))


def test_exporta_tres_hojas(bitacora):
    libro = _abrir(bitacora)

    assert libro.sheetnames == ["Apuestas", "Movimientos", "Resumen"]


def test_exporta_vacio_con_encabezados(bitacora):
    libro = _abrir(bitacora)

    assert _filas(libro["Apuestas"]) == [tuple(COLUMNAS_APUESTAS.values())]
    assert _filas(libro["Movimientos"]) == [tuple(COLUMNAS_MOVIMIENTOS.values())]


def test_exporta_apuestas_y_movimientos(bitacora, crear_apuesta):
    apuesta = bitacora.registrar_apuesta(crear_apuesta(monto=1000))
    bitacora.registrar_apuesta(crear_apuesta(monto=500, colocada=False))
    bitacora.liquidar(apuesta.id, Estado.GANADA)
    bitacora.registrar_movimiento(Movimiento(tipo=TipoMovimiento.DEPOSITO, monto=3_000))

    libro = _abrir(bitacora)
    apuestas = _filas(libro["Apuestas"])
    encabezados = apuestas[0]
    primera = dict(zip(encabezados, apuestas[1], strict=True))

    assert len(apuestas) == 3
    assert primera["Partido"] == "Lakers vs Celtics"
    assert primera["Cuota"] == 1.85
    assert primera["Monto (CLP)"] == 1000
    assert primera["Estado"] == "ganada"
    assert primera["Resultado neto (CLP)"] == 850
    assert primera["Colocada"] == "Sí"
    assert len(_filas(libro["Movimientos"])) == 2


def test_resumen_incluye_saldo_y_desglose(bitacora, crear_apuesta):
    apuesta = bitacora.registrar_apuesta(crear_apuesta(monto=1000))
    bitacora.liquidar(apuesta.id, Estado.PERDIDA)

    filas = _filas(_abrir(bitacora)["Resumen"])
    valores = {fila[0]: fila[1] for fila in filas if fila[0]}

    assert valores["Saldo actual (CLP)"] == 9_000
    assert valores["ROI (%)"] == -100
    assert any(fila[0] == "NBA" for fila in filas)
