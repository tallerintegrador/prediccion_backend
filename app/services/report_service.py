from io import BytesIO

from app.db.models import EstimacionPredictiva


class ReportService:
    @staticmethod
    def generate_pdf(estimacion: EstimacionPredictiva) -> BytesIO:
        try:
            from reportlab.lib import colors
            from reportlab.lib.enums import TA_RIGHT
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle
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
        company_style = ParagraphStyle(
            "Company",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#64748B"),
            uppercase=True,
        )
        title_style = ParagraphStyle(
            "DocumentTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=19,
            textColor=colors.HexColor("#020617"),
            spaceAfter=4,
        )
        muted_style = ParagraphStyle(
            "Muted",
            parent=styles["Normal"],
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#475569"),
        )
        label_style = ParagraphStyle(
            "Label",
            parent=styles["Normal"],
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#475569"),
        )
        value_style = ParagraphStyle(
            "Value",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#020617"),
        )
        right_label_style = ParagraphStyle("RightLabel", parent=label_style, alignment=TA_RIGHT)
        right_value_style = ParagraphStyle("RightValue", parent=value_style, alignment=TA_RIGHT, fontSize=10)
        note_style = ParagraphStyle(
            "Note",
            parent=styles["Normal"],
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#1E3A8A"),
        )

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

        estado = Table(
            [
                [
                    Paragraph(
                        "Estado: ESTIMADA",
                        ParagraphStyle(
                            "Status",
                            parent=value_style,
                            fontSize=7.5,
                            textColor=colors.HexColor("#92400E"),
                        ),
                    )
                ]
            ],
            colWidths=[2.7 * cm],
            hAlign="RIGHT",
        )
        estado.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FEF3C7")),
                    ("BOX", (0, 0), (-1, -1), 0.25, colors.HexColor("#FDE68A")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )

        encabezado = Table(
            [
                [
                    Paragraph("Hortifrut Peru S.A.C.", company_style),
                    Paragraph("N pre-liquidacion", right_label_style),
                ],
                [
                    Paragraph("Pre-liquidacion estimada de importacion", title_style),
                    Paragraph(numero, right_value_style),
                ],
                [
                    Paragraph("Documento generado por Sistema Predictivo de Costos", muted_style),
                    Paragraph(f"Fecha de emision: {fecha_emision}", right_label_style),
                ],
                ["", estado],
            ],
            colWidths=[11.0 * cm, 5.6 * cm],
        )
        encabezado.setStyle(
            TableStyle(
                [
                    ("LINEBELOW", (0, -1), (-1, -1), 0.75, colors.HexColor("#0F172A")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story = [encabezado, Spacer(1, 18)]

        datos = Table(
            [
                [
                    Paragraph("Producto:", label_style),
                    Paragraph(str(estimacion.producto), value_style),
                    Paragraph("Categoria:", label_style),
                    Paragraph(str(estimacion.categoria), value_style),
                ],
                [
                    Paragraph("Proveedor:", label_style),
                    Paragraph(str(estimacion.proveedor), value_style),
                    Paragraph("Origen:", label_style),
                    Paragraph(str(estimacion.pais_origen), value_style),
                ],
                [
                    Paragraph("Incoterm:", label_style),
                    Paragraph(str(estimacion.incoterm), value_style),
                    Paragraph("Arribo estimado:", label_style),
                    Paragraph(fecha_arribo, value_style),
                ],
            ],
            colWidths=[2.0 * cm, 6.0 * cm, 2.5 * cm, 6.1 * cm],
        )
        datos.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.extend([datos, Spacer(1, 14)])

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

        desglose = Table(desglose_rows, colWidths=[6.2 * cm, 3.6 * cm, 4.0 * cm, 2.8 * cm], repeatRows=1)
        desglose.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#334155")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#CBD5E1")),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
                    ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                    ("ALIGN", (1, 0), (-1, 0), "RIGHT"),
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
        story.extend(
            [
                totales,
                Spacer(1, 16),
                Table(
                    [
                        [
                            Paragraph(
                                "<b>Notas para Contabilidad:</b> Esta pre-liquidacion usa una estimacion predictiva real "
                                "registrada en FastAPI. El gasto definitivo se confirma al reconciliar las facturas reales.",
                                note_style,
                            )
                        ]
                    ],
                    colWidths=[16.6 * cm],
                    style=TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EFF6FF")),
                            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#BFDBFE")),
                            ("LEFTPADDING", (0, 0), (-1, -1), 8),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                            ("TOPPADDING", (0, 0), (-1, -1), 8),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                        ]
                    ),
                ),
            ]
        )

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
