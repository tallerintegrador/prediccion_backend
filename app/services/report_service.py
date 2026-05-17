from io import BytesIO

from app.db.models import EstimacionPredictiva


class ReportService:
    @staticmethod
    def generate_pdf(estimacion: EstimacionPredictiva) -> BytesIO:
        try:
            from weasyprint import HTML
        except ImportError as exc:
            raise RuntimeError("weasyprint no esta instalado.") from exc

        html = ReportService._build_html(estimacion)
        buffer = BytesIO()
        HTML(string=html).write_pdf(buffer)
        buffer.seek(0)
        return buffer

    @staticmethod
    def generate_excel(estimacion: EstimacionPredictiva) -> BytesIO:
        try:
            from openpyxl import Workbook
        except ImportError as exc:
            raise RuntimeError("openpyxl no esta instalado.") from exc

        wb = Workbook()
        ws = wb.active
        ws.title = "Preliquidacion"
        ws.append(["Campo", "Valor"])
        rows = [
            ("ID", estimacion.id),
            ("Categoria", estimacion.categoria),
            ("Producto", estimacion.producto),
            ("Pais de origen", estimacion.pais_origen),
            ("Proveedor", estimacion.proveedor),
            ("Incoterm", estimacion.incoterm),
            ("Cantidad", estimacion.cantidad),
            ("Tipo de cambio", estimacion.tipo_cambio),
            ("Costo predicho USD", estimacion.costo_predicho_usd),
        ]
        for key, value in rows:
            ws.append([key, value])

        ws.append([])
        ws.append(["Concepto", "Monto USD"])
        for key, value in estimacion.desglose.items():
            ws.append([key, value])

        buffer = BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return buffer

    @staticmethod
    def _build_html(estimacion: EstimacionPredictiva) -> str:
        desglose_rows = "".join(
            f"<tr><td>{key}</td><td>{value:.2f}</td></tr>"
            for key, value in estimacion.desglose.items()
        )
        return f"""
        <!doctype html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; color: #1f2937; }}
                h1 {{ font-size: 22px; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
                th, td {{ border: 1px solid #d1d5db; padding: 8px; text-align: left; }}
                th {{ background: #f3f4f6; }}
            </style>
        </head>
        <body>
            <h1>Preliquidacion de Importacion #{estimacion.id}</h1>
            <p><strong>Producto:</strong> {estimacion.producto}</p>
            <p><strong>Categoria:</strong> {estimacion.categoria}</p>
            <p><strong>Origen:</strong> {estimacion.pais_origen}</p>
            <p><strong>Proveedor:</strong> {estimacion.proveedor}</p>
            <p><strong>Costo predicho USD:</strong> {estimacion.costo_predicho_usd:.2f}</p>
            <table>
                <thead><tr><th>Concepto</th><th>Monto USD</th></tr></thead>
                <tbody>{desglose_rows}</tbody>
            </table>
        </body>
        </html>
        """
