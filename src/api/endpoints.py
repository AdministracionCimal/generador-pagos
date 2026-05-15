class Endpoints:
    def __init__(self, base_url: str) -> None:
        self.base = base_url.rstrip("/")

    def token(self) -> str:
        return f"{self.base}/oauth/token"

    def operacion_tesoreria_save(self) -> str:
        return f"{self.base}/ordenPago"

    def organizacion_get(self, codigo: str) -> str:
        return f"{self.base}/Organizacion/get?codigo={codigo}"

    def proveedor(self, cuit: str, token: str) -> str:
        return f"{self.base}/proveedor/{cuit}?ACCESS_TOKEN={token}"

    def retencion(self, codigo: str, token: str) -> str:
        return f"{self.base}/retencion/{codigo}?ACCESS_TOKEN={token}"

    def factura_compra(self, codigo: str, token: str) -> str:
        from urllib.parse import quote
        return f"{self.base}/facturaCompra/{quote(codigo, safe='')}?ACCESS_TOKEN={token}"

    def talonario(self, codigo: str, token: str) -> str:
        from urllib.parse import quote
        return f"{self.base}/Talonario/{quote(codigo, safe='')}?ACCESS_TOKEN={token}"

    def cuenta(self, codigo: str, token: str) -> str:
        from urllib.parse import quote
        return f"{self.base}/cuenta/{quote(codigo, safe='')}?ACCESS_TOKEN={token}"

    def talonario_list(self, token: str) -> str:
        return f"{self.base}/Talonario/list?ACCESS_TOKEN={token}"

    def tipo_operacion_bancaria_list(self, token: str) -> str:
        return f"{self.base}/tipoOperacionBancaria/list?ACCESS_TOKEN={token}"

    def empresa_list(self, token: str) -> str:
        return f"{self.base}/empresa/list?ACCESS_TOKEN={token}"

    def cuenta_list(self, token: str) -> str:
        return f"{self.base}/cuenta/list?ACCESS_TOKEN={token}"

    def analisis_retencion(
        self,
        token: str,
        cuit: str,
        fecha_desde: str,
        fecha_hasta: str,
        empresa: str = "",
        modo_emision: int = 2,
    ) -> str:
        from urllib.parse import quote
        return (
            f"{self.base}/reports/analisisRetencion"
            f"?ACCESS_TOKEN={token}"
            f"&PARAMWEBREPORT_FechaDesde={fecha_desde}"
            f"&PARAMWEBREPORT_FechaHasta={fecha_hasta}"
            f"&PARAMWEBREPORT_ModoEmision={modo_emision}"
            f"&PARAMWEBREPORT_Organizacion={quote(cuit, safe='')}"
            f"&PARAMWEBREPORT_Empresa={quote(empresa, safe='')}"
        )

    def cotizacion(self, token: str, fecha: str, moneda: str = "DOL") -> str:
        return (
            f"{self.base}/reports/MONEDACOTIZACION"
            f"?ACCESS_TOKEN={token}"
            f"&PARAMWEBREPORT_FechaDesde={fecha}"
            f"&PARAMWEBREPORT_FechaHasta={fecha}"
            f"&PARAMWEBREPORT_Moneda={moneda}"
        )

    def aplicacion_factura_compra(self, comprobante: str, token: str) -> str:
        from urllib.parse import quote
        return (
            f"{self.base}/reports/aplicacionFacturaCompra"
            f"?ACCESS_TOKEN={token}"
            f"&NumeroDocumento={quote(comprobante, safe='')}"
        )

    def composicion_saldo_proveedor(self, cuit: str, fecha: str, token: str) -> str:
        from urllib.parse import quote
        return (
            f"{self.base}/reports/composicionSaldoProveedor"
            f"?ACCESS_TOKEN={token}"
            f"&PARAMWEBREPORT_fecha={fecha}"
            f"&PARAMWEBREPORT_organizacion={quote(cuit, safe='')}"
            f"&PARAMWEBREPORT_cuenta=02.01.01.01.0001"
        )
