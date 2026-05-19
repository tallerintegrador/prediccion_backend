from io import BytesIO

from app.db.models import EstimacionPredictiva


class ReportService:
    @staticmethod
    def generate_pdf(estimacion: EstimacionPredictiva) -> BytesIO:
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import cm
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        except ImportError as exc:
            raise RuntimeError("reportlab no esta instalado.") from exc

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=1.6 * cm,
            leftMargin=1.6 * cm,
            topMargin=1.5 * cm,
            bottomMargin=1.5 * cm,
            title=f"Pre-liquidacion {estimacion.id}",
        )
        styles = getSampleStyleSheet()
        story = [
            Paragraph("Hortifrut Peru S.A.C.", styles["Normal"]),
            Spacer(1, 6),
            Paragraph("Pre-liquidacion estimada de importacion", styles["Title"]),
            Paragraph("Documento generado por Sistema Predictivo de Costos", styles["Normal"]),
            Spacer(1, 18),
        ]

        numero = f"PREL-{estimacion.created_at.year}-{estimacion.id:04d}"
        fecha_arribo = (
            estimacion.fecha_estimada_arribo.strftime("%d/%m/%Y")
            if estimacion.fecha_estimada_arribo
            else "Pendiente"
        )
        fecha_emision = estimacion.created_at.strftime("%d/%m/%Y")
        tipo_cambio = float(estimacion.tipo_cambio)
        total_usd = float(estimacion.costo_predicho_usd)
        total_pen = total_usd * tipo_cambio

        resumen = Table(
            [
                ["N pre-liquidacion", numero, "Estado", "ESTIMADA"],
                ["Fecha de emision", fecha_emision, "Arribo estimado", fecha_arribo],
                ["Producto", estimacion.producto, "Categoria", estimacion.categoria],
                ["Proveedor", estimacion.proveedor, "Origen", estimacion.pais_origen],
                ["Incoterm", estimacion.incoterm, "Tipo de cambio", f"{tipo_cambio:.2f}"],
            ],
            colWidths=[3.2 * cm, 5.0 * cm, 3.2 * cm, 5.0 * cm],
        )
        resumen.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#0F172A")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.extend([resumen, Spacer(1, 18)])

        desglose_rows = [["Componente", "Estimado USD", "Estimado PEN", "% del total"]]
        for key, value in estimacion.desglose.items():
            monto_usd = float(value)
            porcentaje = (monto_usd / total_usd) * 100 if total_usd else 0
            desglose_rows.append(
                [
                    key.replace("_", " ").title(),
                    f"$ {monto_usd:,.2f}",
                    f"S/ {monto_usd * tipo_cambio:,.2f}",
                    f"{porcentaje:.1f}%",
                ]
            )

        desglose = Table(desglose_rows, colWidths=[6.0 * cm, 3.6 * cm, 4.0 * cm, 3.0 * cm])
        desglose.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#334155")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
                    ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        story.extend([desglose, Spacer(1, 18)])

        totales = Table(
            [
                ["Total estimado USD", f"$ {total_usd:,.2f}"],
                ["Total estimado PEN", f"S/ {total_pen:,.2f}"],
            ],
            colWidths=[6.0 * cm, 4.0 * cm],
            hAlign="RIGHT",
        )
        totales.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        story.append(totales)

        doc.build(story)
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
