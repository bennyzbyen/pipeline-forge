#!/usr/bin/env python3
"""Validate facts and the generated Markdown/HTML/PDF waterline bundle."""

from __future__ import annotations

import argparse
import html as html_module
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

from pipeline_doc_common import apply_fixed_defaults, blocking_questions, configure_utf8_stdio, expected_headings, load_json, write_json
from render_waterline_svg import graph_model, validate_spec, validate_svg


FORBIDDEN_MARKDOWN = (".xlsx)", "<details>", "</details>", "<summary>", "Microsoft_Excel_Worksheet", "TODO", "TBD", "待确认")


def normalize_text(value: str) -> str:
    value = html_module.unescape(value)
    value = re.sub(r"<[^>]+>", "", value)
    value = value.replace("\\", "")
    return "".join(re.findall(r"[A-Za-z0-9_\u4e00-\u9fff]+", value)).lower()


def check_ids(facts: dict, errors: list[str]) -> None:
    for collection in ("sources", "targets", "pipelines"):
        ids = [str(item.get("id") or "") for item in facts.get(collection) or []]
        if any(not re.fullmatch(r"[a-z0-9_]+", value) for value in ids):
            errors.append(f"{collection} IDs must be lowercase ASCII snake_case")
        if len(ids) != len(set(ids)):
            errors.append(f"duplicate {collection} IDs")
    for target in facts.get("targets") or []:
        field_ids = [str(field.get("id") or "") for field in target.get("fields") or []]
        if any(not re.fullmatch(r"[a-z0-9_]+", value) for value in field_ids):
            errors.append(f"target {target.get('id')} has an invalid field ID")
        if len(field_ids) != len(set(field_ids)):
            errors.append(f"target {target.get('id')} has duplicate field IDs")


def validate_facts(facts: dict, profile: str, errors: list[str], warnings: list[str]) -> None:
    if facts.get("schema_version") != "1.0":
        errors.append("facts schema_version must be 1.0")
    if facts.get("profile") != profile:
        errors.append(f"facts profile {facts.get('profile')!r} does not match --profile {profile!r}")
    blockers = blocking_questions(facts)
    errors.extend(f"open blocker {item['id']}: {item['question']}" for item in blockers)
    check_ids(facts, errors)
    try:
        flow = facts.get("flow") or {}
        validate_spec(flow)
        graph_model(flow)
    except Exception as exc:
        errors.append(f"invalid flow spec: {exc}")
    source_ids = {item.get("id") for item in facts.get("sources") or []}
    target_ids = {item.get("id") for item in facts.get("targets") or []}
    for pipeline in facts.get("pipelines") or []:
        unknown_sources = set(pipeline.get("sources") or []) - source_ids
        unknown_targets = set(pipeline.get("targets") or []) - target_ids
        if unknown_sources or unknown_targets:
            errors.append(f"pipeline {pipeline.get('id')} has unknown references: sources={sorted(unknown_sources)}, targets={sorted(unknown_targets)}")
    if profile == "report" and (facts.get("catalog") or {}).get("enabled"):
        catalog = facts.get("catalog") or {}
        if not catalog.get("basic_info"):
            warnings.append("Catalog is enabled but basic_info is empty")
        if not catalog.get("dictionary"):
            warnings.append("Catalog is enabled but dictionary is empty")
        if not catalog.get("storage"):
            warnings.append("Catalog is enabled but storage is empty")


def h1_headings(markdown: str) -> list[str]:
    return [match.group(1).strip() for match in re.finditer(r"^# (.+)$", markdown, re.MULTILINE)]


def validate_markdown(path: Path, facts: dict, profile: str, errors: list[str], metrics: dict) -> str:
    text = path.read_text(encoding="utf-8")
    headings = h1_headings(text)
    expected = [facts["document"]["title"], *expected_headings(profile)]
    if headings != expected:
        errors.append(f"Markdown H1 order mismatch: expected={expected}, actual={headings}")
    for token in FORBIDDEN_MARKDOWN:
        if token in text:
            errors.append(f"Markdown contains forbidden token: {token}")
    if "待定" in text and not facts.get("confirmed_pending_paths"):
        errors.append("Markdown contains 待定 without confirmed_pending_paths")
    if "| ---" not in text:
        errors.append("Markdown contains no direct GFM table")
    for match in re.finditer(r"!\[[^\]]*\]\(([^)]+)\)", text):
        target = match.group(1)
        if re.match(r"^[a-z]+://", target, re.IGNORECASE):
            errors.append(f"Markdown image must be local: {target}")
            continue
        candidate = (path.parent / target).resolve()
        if not candidate.is_file():
            errors.append(f"broken Markdown image: {target}")
        elif candidate.suffix.lower() == ".svg":
            try:
                root = ET.parse(candidate).getroot()
                validate_svg(root, facts["flow"] if candidate.name == "data_flow.svg" else None)
            except Exception as exc:
                errors.append(f"invalid SVG XML {candidate}: {exc}")
    normalized = normalize_text(text)
    for source in facts.get("sources") or []:
        if normalize_text(str(source.get("name") or "")) not in normalized:
            errors.append(f"source missing from Markdown: {source.get('name')}")
    for target in facts.get("targets") or []:
        if normalize_text(str(target.get("table") or "")) not in normalized:
            errors.append(f"target missing from Markdown: {target.get('table')}")
        for field in target.get("fields") or []:
            if normalize_text(str(field.get("key") or "")) not in normalized:
                errors.append(f"field missing from Markdown: {target.get('id')}.{field.get('key')}")
    for pipeline in facts.get("pipelines") or []:
        if normalize_text(str(pipeline.get("name") or "")) not in normalized:
            errors.append(f"pipeline missing from Markdown: {pipeline.get('name')}")
    metrics["markdown_h1"] = len(headings)
    metrics["markdown_tables"] = len(re.findall(r"^\|\s*:?-{3,}", text, re.MULTILINE))
    metrics["markdown_images"] = len(re.findall(r"!\[[^\]]*\]\([^)]+\)", text))
    return text


class HTMLSecurityProbe(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.scripts = []
        self.in_script = False
        self.errors = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"link", "iframe", "object", "embed", "base"}:
            self.errors.append(f"HTML contains forbidden element: {tag}")
        if any(key.lower().startswith("on") for key in attrs):
            self.errors.append("HTML contains an event handler")
        if "src" in attrs and not attrs["src"].startswith("data:"):
            self.errors.append("HTML contains a non-embedded resource")
        if tag == "script":
            if attrs != {"data-waterline-viewer": "1"}:
                self.errors.append("HTML contains an untrusted script")
            self.in_script = True
            self.scripts.append("")

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_script = False

    def handle_data(self, data):
        if self.in_script:
            self.scripts[-1] += data


def validate_html(path: Path, facts: dict, errors: list[str], metrics: dict) -> str:
    text = path.read_text(encoding="utf-8")
    lower = text.lower()
    if "<style>" not in lower or "<svg" not in lower:
        errors.append("HTML must contain inline CSS and SVG")
    probe = HTMLSecurityProbe()
    probe.feed(text)
    errors.extend(probe.errors)
    trusted = (Path(__file__).resolve().parent.parent / "assets/diagram-viewer.js").read_text(encoding="utf-8")
    if probe.scripts != [trusted]:
        errors.append("HTML must contain exactly the trusted offline diagram viewer script")
    styles = re.findall(r"<style\b[^>]*>(.*?)</style>", text, re.DOTALL | re.IGNORECASE)
    urls = [url.strip().strip("'\"") for style in styles for url in re.findall(r"url\(([^)]+)\)", style, re.IGNORECASE)]
    if any("@import" in style.lower() for style in styles) or any(not url.startswith(("#", "data:")) for url in urls):
        errors.append("HTML contains external CSS resources")
    svgs = re.findall(r"<svg\b.*?</svg>", text, re.DOTALL)
    for index, svg in enumerate(svgs):
        try:
            validate_svg(ET.fromstring(svg), facts["flow"] if index == 0 else None)
        except Exception as exc:
            errors.append(f"invalid embedded SVG: {exc}")
    for src in re.findall(r"\bsrc=[\"']([^\"']+)", text, re.IGNORECASE):
        if not src.startswith("data:"):
            errors.append(f"HTML contains a non-embedded resource: {src}")
    if any(token in text for token in ("<details>", ".xlsx", "TODO", "TBD", "待确认")):
        errors.append("HTML contains a forbidden attachment, placeholder, or folded-table token")
    normalized = normalize_text(text)
    for target in facts.get("targets") or []:
        if normalize_text(str(target.get("table") or "")) not in normalized:
            errors.append(f"target missing from HTML: {target.get('table')}")
    metrics["html_tables"] = len(re.findall(r"<table\b", lower))
    metrics["html_svgs"] = len(re.findall(r"<svg\b", lower))
    metrics["html_size"] = len(text.encode("utf-8"))
    return text


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--profile", choices=("sync", "report"), required=True)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--html", type=Path)
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    facts = apply_fixed_defaults(load_json(args.facts.resolve()))
    errors: list[str] = []
    warnings: list[str] = []
    metrics: dict[str, int] = {}
    validate_facts(facts, args.profile, errors, warnings)
    markdown_text = validate_markdown(args.markdown.resolve(), facts, args.profile, errors, metrics) if args.markdown else ""
    html_text = validate_html(args.html.resolve(), facts, errors, metrics) if args.html else ""
    if args.pdf:
        from validate_pipeline_pdf import validate_pdf
        validate_pdf(args.pdf.resolve(), facts, errors, metrics)
        if args.markdown and metrics.get("pdf_tables") != metrics.get("markdown_tables"):
            errors.append("Markdown/PDF table count mismatch")
        if args.html and metrics.get("pdf_tables") != metrics.get("html_tables"):
            errors.append("HTML/PDF table count mismatch")
    if markdown_text and html_text:
        if metrics.get("markdown_tables") != metrics.get("html_tables"):
            errors.append(f"Markdown/HTML table count mismatch: {metrics.get('markdown_tables')} != {metrics.get('html_tables')}")
        for heading in expected_headings(args.profile):
            if normalize_text(heading) not in normalize_text(html_text):
                errors.append(f"HTML missing profile heading: {heading}")
    result = {"valid": not errors, "profile": args.profile, "errors": errors, "warnings": warnings, "metrics": metrics}
    if args.json_out:
        write_json(args.json_out.resolve(), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
