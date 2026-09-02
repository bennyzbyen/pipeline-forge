#!/usr/bin/env python3
"""Paginated, searchable waterline PDFs with embedded CJK fonts and vector flows."""
from __future__ import annotations

import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import tempfile
import xml.etree.ElementTree as ET

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, A3, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import BaseDocTemplate, Flowable, Frame, Image, KeepTogether, LongTable, NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer, TableStyle
from reportlab.platypus.tableofcontents import TableOfContents

from render_waterline_svg import validate_svg, validate_svg_safety

INK, MUTED, BLUE, LINE = "#203148", "#51627a", "#2563eb", "#dce4ed"


def content_digest(markdown, flow):
    return hashlib.sha256(json.dumps({"markdown": markdown, "flow": flow}, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def register_fonts():
    """Embed a real CJK TrueType font; do not depend on the recipient's font setup."""
    windows = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    candidates = [os.environ.get("PIPELINE_PDF_FONT", ""), str(windows / "msyh.ttc"),
                  "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", "/usr/share/fonts/truetype/arphic/uming.ttc"]
    path = next((Path(p) for p in candidates if p and Path(p).is_file()), None)
    if path is None:
        raise RuntimeError("PDF output requires an embeddable CJK TrueType font. Set PIPELINE_PDF_FONT to a .ttf or TrueType .ttc file.")
    pdfmetrics.registerFont(TTFont("Waterline", str(path)))
    bold = Path(os.environ.get("PIPELINE_PDF_BOLD_FONT") or str(path.with_name("msyhbd.ttc")))
    pdfmetrics.registerFont(TTFont("WaterlineBold", str(bold if bold.is_file() else path)))
    pdfmetrics.registerFontFamily("Waterline", normal="Waterline", bold="WaterlineBold", italic="Waterline", boldItalic="WaterlineBold")


def check_font_coverage(text):
    for name in ("Waterline", "WaterlineBold"):
        supported = pdfmetrics.getFont(name).face.charToGlyph
        missing = sorted({character for character in text if not character.isspace() and ord(character) not in supported})
        if missing:
            raise ValueError(f"PDF font {name} lacks glyphs: {''.join(missing[:20])!r}. Choose a CJK TrueType font using PIPELINE_PDF_FONT / PIPELINE_PDF_BOLD_FONT.")


def inline(value):
    # Escape original HTML. Only controlled Markdown formatting becomes PDF markup.
    value = html.escape(str(value), quote=True).replace("&lt;br&gt;", "<br/>")
    value = re.sub(r"`([^`]+)`", r'<font name="Waterline">\1</font>', value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", value)
    value = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<link href="\2" color="#2563eb">\1</link>', value)
    return value


def plain(value):
    return re.sub(r"`([^`]+)`|\*\*([^*]+)\*\*", lambda m: m[1] or m[2], value).replace("<br>", " ")


def parse_markdown(markdown):
    lines, blocks, i = markdown.splitlines(), [], 0
    while i < len(lines):
        value = lines[i]
        if not value.strip():
            i += 1; continue
        if value.startswith("```"):
            i += 1; code = []
            while i < len(lines) and not lines[i].startswith("```"):
                code.append(lines[i]); i += 1
            blocks.append(("code", "\n".join(code))); i += 1; continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", value)
        if heading:
            blocks.append(("heading", (len(heading[1]), heading[2]))); i += 1; continue
        image = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", value.strip())
        if image:
            blocks.append(("image", (image[1], image[2]))); i += 1; continue
        if value.lstrip().startswith("|") and i+1 < len(lines) and re.match(r"^\s*\|?\s*:?-{3,}", lines[i+1]):
            split = lambda row: [cell.strip().replace("\\|", "|") for cell in re.split(r"(?<!\\)\|", row.strip().strip("|"))]
            headers, rows = split(value), []; i += 2
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                row = split(lines[i])
                if len(row) != len(headers):
                    raise ValueError("PDF table column count differs from the canonical Markdown")
                rows.append(row); i += 1
            blocks.append(("table", (headers, rows))); continue
        bullet = re.match(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)(.+)$", value)
        if bullet:
            blocks.append(("bullet", bullet[1])); i += 1; continue
        paragraph = [value.strip()]; i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^#{1,6}\s|^\s*[-*+]\s|^\s*\d+[.)]\s|^\s*\||^!\[|^```", lines[i]):
            paragraph.append(lines[i].strip()); i += 1
        blocks.append(("paragraph", " ".join(paragraph)))
    return blocks


def text_units(blocks):
    """Stable, render-local IDs for checking actual glyphs, including split cells."""
    units, keys = {}, {}
    for block_index, (kind, value) in enumerate(blocks):
        values = []
        if kind == "table":
            values = [(row_index, col_index, cell) for row_index, row in enumerate([value[0], *value[1]]) for col_index, cell in enumerate(row)]
        elif kind == "heading":
            values = [(None, None, value[1])]
        elif kind in {"paragraph", "bullet", "code"}:
            values = [(None, None, value)]
        for row, col, text in values:
            unit_id = len(units)+1
            units[unit_id] = {"text": text, "header": kind == "table" and row == 0, "bullet": kind == "bullet"}
            keys[block_index, row, col] = unit_id
    return units, keys


class AuditedParagraph(Paragraph):
    """Mark visible PDF text, carrying the same ID across page-split fragments."""
    audit_id = None

    def split(self, availWidth, availHeight):
        parts = super().split(availWidth, availHeight)
        for part in parts:
            part.audit_id = self.audit_id
        return parts

    def draw(self):
        if self.audit_id is not None:
            self.canv.addLiteral(f"/P <</MCID {self.audit_id}>> BDC")
        super().draw()
        if self.audit_id is not None:
            self.canv.addLiteral("EMC")


class PageTable(LongTable):
    """Start each continuation on a new page, not under a second header nearby."""
    def split(self, availWidth, availHeight):
        parts = super().split(availWidth, availHeight)
        return [parts[0], PageBreak(), *parts[1:]] if len(parts) > 1 else parts


class HeadingGroup(KeepTogether):
    """Keep a heading with the table opening, not an entire multi-page table."""
    def wrap(self, availWidth, availHeight):
        result = super().wrap(availWidth, availHeight)
        for item in self._content:
            if isinstance(item, PageTable):
                opening = sum(item._rowHeights[:2])
                self._H -= max(0, item._height - min(opening, 150))
        return result


class VectorFlow(Flowable):
    """Draw this skill's safe SVG subset as PDF vectors, retaining searchable labels."""
    def __init__(self, path, width, max_height, anchor="", target=""):
        super().__init__()
        self.root = ET.parse(path).getroot()
        validate_svg_safety(self.root)
        x, y, w, h = map(float, self.root.get("viewBox").split())
        if x or y:
            raise ValueError("Waterline SVG must have a zero-origin viewBox")
        self.scale = min(width/w, max_height/h)
        self.width, self.height = w*self.scale, h*self.scale
        self.anchor, self.target = anchor, target
        self.hAlign = "CENTER"
        self.spaceAfter = 6

    def draw(self):
        canvas = self.canv
        if self.anchor:
            canvas.bookmarkHorizontalAbsolute(self.anchor, canvas.absolutePosition(0, self.height)[1])
        if self.target:
            canvas.linkRect("查看流程图", self.target, (0, 0, self.width, self.height), relative=1, thickness=0)
        canvas.saveState()
        canvas.translate(0, self.height); canvas.scale(self.scale, -self.scale)
        for child in self.root:
            self.draw_element(child)
        canvas.restoreState()

    def draw_element(self, element):
        name = element.tag.rsplit("}", 1)[-1]
        if name in {"defs", "title", "desc", "metadata"}:
            return
        canvas, a = self.canv, element.attrib
        if name == "g":
            for child in element:
                self.draw_element(child)
            return
        canvas.saveState()
        fill, stroke = a.get("fill", "none"), a.get("stroke", "none")
        if fill != "none":
            canvas.setFillColor(colors.HexColor(fill))
        if stroke != "none":
            canvas.setStrokeColor(colors.HexColor(stroke))
        canvas.setLineWidth(float(a.get("stroke-width", 1)))
        dash = a.get("stroke-dasharray", "none")
        if dash != "none":
            canvas.setDash([float(n) for n in re.split(r"[ ,]+", dash)])
        if name == "rect":
            x, y, w, h = [float(a.get(k, 0)) for k in ("x", "y", "width", "height")]
            radius = float(a.get("rx", 0))
            if a.get("class") == "node-band":
                # Match the clipped rounded header band without a raster conversion.
                radius = 11
                clip = canvas.beginPath(); clip.roundRect(x, y, w, h+radius, radius)
                canvas.clipPath(clip, stroke=0, fill=0)
            canvas.roundRect(x, y, w, h, radius, stroke=stroke != "none", fill=fill != "none") if radius and a.get("class") != "node-band" else canvas.rect(x, y, w, h, stroke=stroke != "none", fill=fill != "none")
        elif name == "line":
            canvas.line(*[float(a[k]) for k in ("x1", "y1", "x2", "y2")])
        elif name == "path":
            tokens = re.findall(r"[A-Za-z]|[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?", a["d"])
            path, index, points = canvas.beginPath(), 0, []
            while index < len(tokens):
                command = tokens[index]; index += 1
                count = {"M": 2, "L": 2, "C": 6, "Z": 0, "z": 0}.get(command)
                if count is None:
                    raise ValueError(f"Unsupported generated SVG command: {command}")
                values = list(map(float, tokens[index:index+count])); index += count
                if command == "M": path.moveTo(*values)
                elif command == "L": path.lineTo(*values)
                elif command == "C": path.curveTo(*values)
                else: path.close()
                if count:
                    points.extend(zip(values[::2], values[1::2]))
            canvas.drawPath(path, fill=fill != "none", stroke=stroke != "none")
            if a.get("marker-end") and len(points) > 1:
                end = points[-1]
                before = next((p for p in reversed(points[:-1]) if p != end), points[0])
                angle = math.atan2(end[1]-before[1], end[0]-before[0])
                tip = (end[0]+math.cos(angle), end[1]+math.sin(angle))
                sides = [(end[0]-8*math.cos(angle)+side*4.5*math.sin(angle), end[1]-8*math.sin(angle)-side*4.5*math.cos(angle)) for side in (-1, 1)]
                arrow = canvas.beginPath(); arrow.moveTo(*tip); arrow.lineTo(*sides[0]); arrow.lineTo(*sides[1]); arrow.close()
                canvas.setFillColor(colors.HexColor(stroke)); canvas.setDash([]); canvas.drawPath(arrow, fill=1, stroke=0)
        elif name == "text":
            x, y, size = float(a["x"]), float(a["y"]), float(a.get("font-size", 13))
            value = "".join(element.itertext())
            canvas.translate(x, y); canvas.scale(1, -1)
            canvas.setFont("WaterlineBold" if a.get("font-weight") in {"bold", "600", "650", "700", "750", "800"} else "Waterline", size)
            canvas.setFillColor(colors.HexColor(a.get("fill", INK)))
            if a.get("text-anchor") == "middle": canvas.drawCentredString(0, 0, value)
            elif a.get("text-anchor") == "end": canvas.drawRightString(0, 0, value)
            else: canvas.drawString(0, 0, value)
        else:
            raise ValueError(f"Unsupported generated SVG element: {name}")
        canvas.restoreState()


class WaterlineDoc(BaseDocTemplate):
    def __init__(self, filename, title, pagesize, **kwargs):
        super().__init__(filename, pagesize=pagesize, leftMargin=36, rightMargin=36, topMargin=44, bottomMargin=40, title=title, author="", pageCompression=1, keepTogetherClass=HeadingGroup, **kwargs)
        self.document_title = title
        self.addPageTemplates([self.template("body", pagesize), self.template("diagram", landscape(A3))])

    def template(self, name, size):
        frame = Frame(36, 40, size[0]-72, size[1]-84, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id=name+"-frame")
        return PageTemplate(id=name, pagesize=size, frames=[frame], onPage=self.page_chrome)

    def page_chrome(self, canvas, doc):
        w, h = canvas._pagesize
        canvas.saveState()
        canvas.setFont("Waterline", 8); canvas.setFillColor(colors.HexColor(MUTED))
        header = self.document_title
        while pdfmetrics.stringWidth(header, "Waterline", 8) > w-100:
            header = header[:-2] + "…"
        canvas.drawString(36, h-24, header)
        canvas.setStrokeColor(colors.HexColor(LINE)); canvas.setLineWidth(.5)
        canvas.line(36, 30, w-36, 30)
        canvas.drawString(36, 18, "DataEngine / DataHub")
        canvas.drawRightString(w-36, 18, f"第 {doc.page} 页")
        canvas.restoreState()

    def afterFlowable(self, flowable):
        if not hasattr(flowable, "heading_key"):
            return
        self.canv.bookmarkPage(flowable.heading_key)
        self.canv.addOutlineEntry(flowable.heading_text, flowable.heading_key, flowable.heading_level, closed=False)
        if flowable.heading_level <= 2 and not flowable.heading_key.startswith("document-title"):
            self.notify("TOCEntry", (flowable.heading_level, html.escape(flowable.heading_text), self.page, flowable.heading_key))


def column_widths(headers, width):
    weights = []
    for header in headers:
        h = header.lower()
        if h in {"序号", "no", "no."}: weight = .35
        elif h == "变更摘要": weight = 5.5
        elif h in {"作者", "发布日期", "文档修订版本"}: weight = .85
        elif h == "字段": weight = 4.2
        elif "逻辑" in h: weight = 3.4
        elif any(k in h for k in ("description", "业务描述", "过滤", "field&type")): weight = 2.0
        elif any(k in h for k in ("类型", "type", "类别", "版本")): weight = .9
        elif any(k in h for k in ("字段", "表名", "source", "name", "title", "数据项", "时间", "范围")): weight = 1.4
        else: weight = 1.1
        weights.append(weight)
    return [width*w/sum(weights) for w in weights]


def render_pdf(markdown, markdown_path, output, facts):
    register_fonts()
    blocks = parse_markdown(markdown)
    units, unit_keys = text_units(blocks)
    check_font_coverage("".join(plain(unit["text"]) for unit in units.values()))
    prefs = facts.get("render_preferences") or {}
    orientation = prefs.get("pdf_orientation", "auto")
    if orientation not in {"auto", "portrait", "landscape"}:
        raise ValueError("pdf_orientation must be auto, portrait, or landscape")
    wide = orientation == "landscape" or orientation == "auto" and any(kind=="table" and len(value[0])>=7 for kind, value in blocks)
    size = landscape(A4) if wide else A4
    width = size[0]-72
    base = dict(fontName="Waterline", fontSize=10, leading=15, textColor=colors.HexColor(INK), wordWrap="CJK", splitLongWords=1, spaceAfter=7)
    styles = {"body": ParagraphStyle("body", **base), "cell": ParagraphStyle("cell", **{**base, "fontSize": 9, "leading": 13, "spaceAfter": 0}),
              "headcell": ParagraphStyle("headcell", **{**base, "fontName": "WaterlineBold", "fontSize": 9, "leading": 13, "spaceAfter": 0}),
              "caption": ParagraphStyle("caption", **{**base, "fontSize": 9, "leading": 13, "alignment": TA_CENTER, "textColor": colors.HexColor(MUTED)}),
              "title": ParagraphStyle("title", **{**base, "fontName": "WaterlineBold", "fontSize": 23, "leading": 33, "alignment": TA_CENTER, "spaceBefore": 24, "spaceAfter": 26})}
    for level in range(1, 7):
        font_size = {1: 17, 2: 13, 3: 11}.get(level, 10)
        styles[f"h{level}"] = ParagraphStyle(f"h{level}", **{**base, "fontName": "WaterlineBold", "fontSize": font_size, "leading": font_size*1.5, "spaceBefore": 16 if level==1 else 10, "spaceAfter": 9, "keepWithNext": True, "textColor": colors.HexColor(BLUE if level==2 else INK)})
    story, figures, heading_index, toc_added = [], [], 0, False
    for block_index, (kind, value) in enumerate(blocks):
        if kind == "heading":
            level, label = value
            if level == 1 and re.match(r"1[.、]\s*", label) and not toc_added:
                story.append(PageBreak())
                story.append(Paragraph("目录", styles["h1"]))
                toc = TableOfContents()
                toc.tableStyle = TableStyle([("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 0), ("RIGHTPADDING", (0,0), (-1,-1), 0), ("TOPPADDING", (0,0), (-1,-1), 1), ("BOTTOMPADDING", (0,0), (-1,-1), 1)])
                toc.levelStyles = [ParagraphStyle(f"toc{i}", fontName="Waterline", fontSize=10 if i==0 else 9, leading=13, leftIndent=i*14, firstLineIndent=0, spaceBefore=4 if i==0 else 0, wordWrap="CJK") for i in range(3)]
                story.extend([toc, PageBreak()]); toc_added = True
            heading_index += 1
            is_title = heading_index==1 and level==1
            paragraph = AuditedParagraph(inline(label), styles["title" if is_title else f"h{level}"])
            paragraph.audit_id = unit_keys[block_index, None, None]
            paragraph.heading_key = "document-title" if is_title else f"section-{heading_index}"
            paragraph.heading_text = plain(label)
            paragraph.heading_level = level-1
            story.append(paragraph)
        elif kind == "table":
            headers, rows = value
            cells = []
            for row_index, row in enumerate([headers, *rows]):
                cells.append([])
                for col_index, cell in enumerate(row):
                    paragraph = AuditedParagraph(inline(cell), styles["headcell" if row_index==0 else "cell"])
                    paragraph.audit_id = unit_keys[block_index, row_index, col_index]
                    cells[-1].append(paragraph)
            table = PageTable(cells, colWidths=column_widths(headers, width), repeatRows=1, splitByRow=1, splitInRow=1, hAlign="LEFT")
            table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#eaf2ff")), ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f8fafc")]), ("GRID", (0,0), (-1,-1), .4, colors.HexColor(LINE)), ("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 6), ("RIGHTPADDING", (0,0), (-1,-1), 6), ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6)]))
            story.extend([table, Spacer(1, 10)])
        elif kind == "image":
            caption, target = value
            path = (Path(markdown_path).parent / target).resolve()
            if path.suffix.lower()==".svg":
                index = len(figures)+1
                from render_pipeline_doc import catalog_spec
                tree = ET.parse(path).getroot()
                validate_svg(tree, facts["flow"] if index==1 else catalog_spec())
                check_font_coverage("".join(node.text or "" for node in tree.iter() if node.tag.endswith("}text")))
                figures.append((path, caption, index))
                figure = VectorFlow(path, width, 220, f"figure-inline-{index}", f"figure-full-{index}")
                story.extend([figure, Paragraph(f'<link href="#figure-full-{index}" color="{BLUE}">{inline(caption)} · 查看整页大图</link>', styles["caption"])])
            else:
                image = Image(str(path), kind="proportional", width=width, height=220)
                story.extend([image, Paragraph(inline(caption), styles["caption"])])
        elif kind == "code":
            paragraph = AuditedParagraph(html.escape(value).replace("\n", "<br/>"), styles["body"])
            paragraph.audit_id = unit_keys[block_index, None, None]
            story.append(paragraph)
        else:
            paragraph = AuditedParagraph(inline(value), styles["body"], bulletText="•" if kind=="bullet" else None)
            paragraph.audit_id = unit_keys[block_index, None, None]
            if kind == "bullet":
                paragraph.style = ParagraphStyle("bullet", parent=styles["body"], leftIndent=12, bulletIndent=0, bulletFontName="Waterline", bulletFontSize=10)
                # Keep short adjacent bullets together, not a single orphan on a new page.
                if block_index+1 < len(blocks) and blocks[block_index+1][0] == "bullet" and len(value) < 160:
                    paragraph.keepWithNext = True
            story.append(paragraph)
    if figures:
        story.extend([NextPageTemplate("diagram"), PageBreak()])
        for index, (path, caption, number) in enumerate(figures):
            if index:
                story.append(PageBreak())
            paragraph = Paragraph(f"流程图附页 {number} · {inline(caption)}", styles["h1"])
            paragraph.heading_key, paragraph.heading_text, paragraph.heading_level = f"diagram-heading-{number}", f"流程图附页 {number} · {caption}", 0
            story.append(paragraph)
            story.append(Paragraph(f'<link href="#figure-inline-{number}" color="{BLUE}">返回正文中的流程图</link>', styles["body"]))
            story.append(VectorFlow(path, landscape(A3)[0]-72, landscape(A3)[1]-160, f"figure-full-{number}", f"figure-inline-{number}"))
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="waterline_pdf_") as temporary:
        intermediate = Path(temporary) / "document.pdf"
        doc = WaterlineDoc(str(intermediate), facts["document"]["title"], size)
        doc.multiBuild(story)
        reader, writer = PdfReader(intermediate), PdfWriter()
        writer.clone_document_from_reader(reader)
        writer.add_metadata({"/Title": facts["document"]["title"], "/Creator": "Pipeline Document Generator", "/WaterlineContentSHA256": content_digest(markdown, facts["flow"]), "/WaterlineTextAudit": "1", "/WaterlineTableCount": str(sum(kind=="table" for kind, _ in blocks)), "/WaterlineFigureCount": str(len(figures)), "/WaterlineProfile": facts["profile"]})
        with output.open("wb") as stream:
            writer.write(stream)
    return output
