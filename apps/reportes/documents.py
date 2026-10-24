"""Documentos imprimibles: el mismo contenido se entrega como PDF o como página lista para imprimir.

Un documento es un título, líneas de subtítulo (filtros aplicados) y bloques:
secciones, tablas (con fila de subtotal opcional) y notas.
"""

import datetime
from dataclasses import dataclass, field
from io import BytesIO

from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.text import slugify


@dataclass
class Link:
    """Celda con enlace en la versión web; en PDF/impresión se muestra solo el texto."""

    text: str
    url: str

    def __str__(self):
        return self.text


@dataclass
class Section:
    title: str
    kind: str = "section"


@dataclass
class Table:
    headers: list
    rows: list
    footer: list | None = None
    empty_text: str = "Sin registros."
    kind: str = "table"


@dataclass
class Note:
    text: str
    kind: str = "note"


@dataclass
class Document:
    title: str
    subtitle: list = field(default_factory=list)
    blocks: list = field(default_factory=list)
    landscape: bool = True

    def add(self, *blocks):
        self.blocks.extend(blocks)
        return self


def cell_text(value):
    from apps.core.crud import format_cell

    if isinstance(value, Link):
        return value.text
    if isinstance(value, str):
        return value
    return format_cell(value)


def wants_document(request):
    return request.GET.get("formato") in ("pdf", "imprimir")


def document_response(request, doc, filename):
    """Devuelve PDF (?formato=pdf) o la vista de impresión (?formato=imprimir)."""
    if request.GET.get("formato") == "pdf":
        return pdf_response(doc, filename, request.user)
    return render(request, "reportes/print.html", {
        "doc": doc, "generated": timezone.localtime(), "generated_by": request.user,
        "pdf_url": request.get_full_path().replace("formato=imprimir", "formato=pdf"),
    })


# ---------------------------------------------------------------- PDF


def pdf_response(doc, filename, user=None):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, TableStyle
    from reportlab.platypus import Table as RLTable

    from apps.core.models import CompanySettings

    company = str(CompanySettings.get())
    pagesize = landscape(A4) if doc.landscape else A4
    buf = BytesIO()
    margin = 1.2 * cm
    pdf = SimpleDocTemplate(buf, pagesize=pagesize, leftMargin=margin, rightMargin=margin, topMargin=margin,
                            bottomMargin=1.5 * cm, title=doc.title, author=company)
    styles = getSampleStyleSheet()
    s_title = ParagraphStyle("t", parent=styles["Title"], fontSize=15, leading=18, alignment=0, spaceAfter=2)
    s_company = ParagraphStyle("c", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#555555"))
    s_sub = ParagraphStyle("s", parent=styles["Normal"], fontSize=8.5, textColor=colors.HexColor("#444444"))
    s_section = ParagraphStyle("h", parent=styles["Heading2"], fontSize=11.5, spaceBefore=10, spaceAfter=4,
                               textColor=colors.HexColor("#1F4E79"), keepWithNext=1)
    s_cell = ParagraphStyle("cell", parent=styles["Normal"], fontSize=7.8, leading=9.5)
    s_head = ParagraphStyle("head", parent=s_cell, textColor=colors.white, fontName="Helvetica-Bold")
    s_foot = ParagraphStyle("foot", parent=s_cell, fontName="Helvetica-Bold")
    s_note = ParagraphStyle("n", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#555555"))
    s_right = ParagraphStyle("r", parent=s_cell, alignment=TA_RIGHT)

    def esc(v):
        return (cell_text(v) or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    story = [Paragraph(esc(company), s_company), Paragraph(esc(doc.title), s_title)]
    for line in doc.subtitle:
        story.append(Paragraph(esc(line), s_sub))
    story.append(Spacer(1, 6))

    width = pagesize[0] - 2 * margin
    for block in doc.blocks:
        if block.kind == "section":
            story.append(Paragraph(esc(block.title), s_section))
        elif block.kind == "note":
            story.append(Paragraph(esc(block.text), s_note))
        elif block.kind == "table":
            if not block.rows:
                story.append(Paragraph(esc(block.empty_text), s_note))
                continue
            texts = [[cell_text(c) for c in row] for row in block.rows]
            # Ancho de columnas proporcional al contenido (con mínimo y máximo).
            ncols = len(block.headers)
            weights = []
            for i in range(ncols):
                footer_len = len(cell_text(block.footer[i])) * 0.8 if block.footer and i < len(block.footer) else 0
                longest = max([len(str(block.headers[i])), footer_len] + [len(r[i]) for r in texts if i < len(r)])
                weights.append(min(max(longest, 8), 45))
            total = sum(weights)
            col_widths = [width * w / total for w in weights]

            def para(text, style, i):
                if style is s_cell and _looks_numeric(text):
                    style = s_right
                return Paragraph(esc(text), style)

            data = [[Paragraph(esc(h), s_head) for h in block.headers]]
            data += [[para(t, s_cell, i) for i, t in enumerate(r)] for r in texts]
            style = [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C8CED6")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F6F9")]),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ]
            if block.footer:
                data.append([Paragraph(esc(cell_text(c)), s_foot) for c in block.footer])
                style.append(("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#DCE6F0")))
            table = RLTable(data, colWidths=col_widths, repeatRows=1)
            table.setStyle(TableStyle(style))
            story.append(table if len(data) > 25 else KeepTogether(table))
            story.append(Spacer(1, 4))

    generated = timezone.localtime().strftime("%d/%m/%Y %H:%M")
    who = f" por {user}" if user and getattr(user, "is_authenticated", False) else ""

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(margin, 0.8 * cm, f"{company} · {doc.title} · Generado el {generated}{who}")
        canvas.drawRightString(pagesize[0] - margin, 0.8 * cm, f"Página {document.page}")
        canvas.restoreState()

    pdf.build(story, onFirstPage=footer, onLaterPages=footer)
    resp = HttpResponse(buf.getvalue(), content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{slugify(filename)}_{datetime.date.today():%Y%m%d}.pdf"'
    return resp


def _looks_numeric(text):
    t = text.replace("$", "").replace(".", "").replace(",", "").replace("%", "").replace("-", "").replace(" ", "")
    return bool(t) and t.isdigit()
