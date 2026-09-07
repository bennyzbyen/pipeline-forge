#!/usr/bin/env python3
"""Checks for generated waterline PDFs, shared by the bundle validator and tests."""
from __future__ import annotations

import html
from pathlib import Path
import re

import pdfplumber
from pypdf import PdfReader
from reportlab.lib.pagesizes import A4, A3, landscape

from render_pipeline_pdf import content_digest, parse_markdown, plain, text_units
from pipeline_diagram_contract import platform_definitions


def compact(value):
    value = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1", str(value))
    return re.sub(r"\s+", "", html.unescape(plain(value)))


def validate_pdf(path: Path, facts: dict, errors: list, metrics: dict):
    from render_pipeline_doc import render_markdown, document_stem, catalog_spec
    asset_dir = document_stem(facts["document"]["title"])+"_files"
    catalog = f"{asset_dir}/catalog_registration_flow.svg" if facts["profile"]=="report" and facts.get("catalog", {}).get("enabled") else ""
    markdown = render_markdown(facts, f"{asset_dir}/data_flow.svg", catalog)
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            errors.append("PDF must not require a password")
            return ""
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        metadata = reader.metadata or {}
        if facts.get("render_preferences", {}).get("diagrams"):
            from diagram_design_bridge import digest
            if metadata.get("/WaterlineDiagramBindingsSHA256") != digest(facts["render_preferences"]["diagrams"]):
                errors.append("PDF is stale relative to the reviewed diagram binding")
        if metadata.get("/WaterlineContentSHA256") != content_digest(markdown, facts["flow"]):
            errors.append("PDF is stale relative to the canonical document/flow")
        blocks = parse_markdown(markdown)
        figure_count = sum(kind=="image" and value[1].lower().endswith(".svg") for kind, value in blocks)
        orientation = (facts.get("render_preferences") or {}).get("pdf_orientation", "auto")
        wide = orientation == "landscape" or orientation == "auto" and any(kind=="table" and len(value[0])>=7 for kind, value in blocks)
        for index, page in enumerate(reader.pages):
            expected_size = landscape(A3) if index >= len(reader.pages)-figure_count else landscape(A4) if wide else A4
            if abs(float(page.mediabox.width)-expected_size[0])>1 or abs(float(page.mediabox.height)-expected_size[1])>1:
                errors.append(f"PDF page {index+1} has an unexpected paper size/orientation")
        if int(metadata.get("/WaterlineTableCount", 0)) != sum(kind=="table" for kind, _ in blocks) or int(metadata.get("/WaterlineFigureCount", 0)) != figure_count:
            errors.append("PDF table/figure count differs from the canonical document")
        specs = [facts["flow"], catalog_spec()] if figure_count == 2 else [facts["flow"]]
        if len(reader.pages) < figure_count:
            errors.append("PDF is missing its full-page diagrams")
        else:
            for index, spec in enumerate(specs):
                figure_text = compact(reader.pages[-figure_count+index].extract_text() or "")
                labels = [spec.get("title", "")]
                labels.extend(platform["title"] for platform in platform_definitions(spec))
                for node in spec["nodes"]:
                    labels.append(node.get("label", ""))
                    labels.extend(node.get("identifiers") or [])
                labels.extend(edge.get("label", "") for edge in spec["edges"])
                for label in labels:
                    if compact(label) not in figure_text:
                        errors.append(f"PDF full-page diagram {index+1} is missing visible identity/flow text")
        units, _ = text_units(blocks)
        if metadata.get("/WaterlineTextAudit") != "1":
            errors.append("PDF needs regeneration with per-cell text validation")
        root = reader.trailer["/Root"]
        if root.get("/OpenAction") or root.get("/AA") or root.get("/AcroForm"):
            errors.append("PDF contains unexpected active content")
        names = root.get("/Names", {})
        names = names.get_object() if hasattr(names, "get_object") else names
        if names.get("/JavaScript") or names.get("/EmbeddedFiles"):
            errors.append("PDF must not contain scripts or attached source files")
        links, embedded_fonts = 0, set()
        page_refs = {page.indirect_reference.idnum for page in reader.pages}
        for page in reader.pages:
            resources = page.get("/Resources", {}).get_object()
            for font in resources.get("/Font", {}).get_object().values():
                font = font.get_object()
                descriptor = font.get("/FontDescriptor")
                if descriptor and any(key in descriptor.get_object() for key in ("/FontFile", "/FontFile2", "/FontFile3")):
                    embedded_fonts.add(str(font.get("/BaseFont")))
            for annotation in page.get("/Annots", []):
                annotation = annotation.get_object()
                if annotation.get("/Subtype") != "/Link":
                    errors.append("PDF contains an unexpected interactive annotation")
                    continue
                links += 1
                action = annotation.get("/A", {})
                action = action.get_object() if hasattr(action, "get_object") else action
                if action and action.get("/S") not in {"/GoTo", "/URI"}:
                    errors.append("PDF contains an unsafe link action")
                destination = annotation.get("/Dest") or action.get("/D")
                if isinstance(destination, list) and hasattr(destination[0], "idnum") and destination[0].idnum not in page_refs:
                    errors.append("PDF contains a broken internal link")
        if not embedded_fonts:
            errors.append("PDF has no embedded fonts")
        outline_titles = []
        def visit(items):
            for item in items:
                if isinstance(item, list): visit(item)
                else: outline_titles.append(str(item.get("/Title", "")))
        visit(reader.outline)
        h1 = [plain(value[1]) for kind, value in blocks if kind=="heading" and value[0]==1]
        if [title for title in outline_titles if title in h1] != h1:
            errors.append("PDF chapter bookmarks differ from the template order")
        if not links:
            errors.append("PDF has no navigation links")
        clipped, rendered_units = [], {}
        with pdfplumber.open(path) as pdf:
            for index, page in enumerate(pdf.pages, 1):
                page_units = {}
                if not page.chars:
                    errors.append(f"PDF page {index} has no searchable text")
                for char in page.chars:
                    if char.get("mcid") is not None:
                        page_units.setdefault(char["mcid"], []).append(char["text"])
                    if char["x0"] < -1 or char["top"] < -1 or char["x1"] > page.width+1 or char["bottom"] > page.height+1:
                        if index not in clipped:
                            clipped.append(index)
                for unit_id, chars in page_units.items():
                    rendered_units.setdefault(unit_id, []).append("".join(chars))
        for unit_id, unit in units.items():
            expected = compact(unit["text"])
            fragments = rendered_units.get(unit_id, [])
            # Repeated headers are checked once per page. All other text is
            # reconstructed from its actual visible glyphs across page breaks;
            # never trust a metadata digest or only check a cell's endpoints.
            values = fragments if unit["header"] else ["".join(fragments)]
            if expected and (not values or any((compact(value).removeprefix("•") if unit["bullet"] else compact(value)) != expected for value in values)):
                # A connection cell may contain a signed URL. Identify the unit
                # without copying credentials into logs or test reports.
                errors.append(f"PDF content differs in text unit {unit_id}")
        if clipped:
            errors.append(f"PDF text extends beyond page bounds: {clipped}")
        metrics.update(pdf_pages=len(reader.pages), pdf_links=links, pdf_embedded_fonts=len(embedded_fonts), pdf_text_units=len(units), pdf_tables=int(metadata.get("/WaterlineTableCount", 0)), pdf_figures=int(metadata.get("/WaterlineFigureCount", 0)), pdf_size=path.stat().st_size)
        return text
    except Exception as exc:
        errors.append(f"invalid PDF: {exc}")
        return ""
