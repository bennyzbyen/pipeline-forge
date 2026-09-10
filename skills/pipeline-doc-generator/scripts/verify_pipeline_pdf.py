#!/usr/bin/env python3
"""Offline PDF output, text coverage, pagination, navigation, and edit regressions."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import tempfile

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4, A3, landscape

from pipeline_doc_common import OUTPUT_FORMATS
from render_pipeline_doc import document_stem, render_markdown
from render_pipeline_pdf import parse_markdown, text_units
from validate_pipeline_pdf import compact, validate_pdf
from verify_pipeline_doc_generator import facts, run, RENDER, VALIDATE, render_and_validate


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def test_pdf_blockers(root):
    for choice in OUTPUT_FORMATS:
        if "pdf" not in OUTPUT_FORMATS[choice]:
            continue
        output = root / choice
        data = facts("sync", "合成阻塞测试")
        data["pipelines"][0]["trigger"] = ""
        path = output / "facts.json"
        save(path, data)
        run(str(RENDER), "--facts", str(path), "--out-dir", str(output), "--format", choice, expected=2)
        assert (output / "questions.md").exists()
        assert not any(output.glob("*.pdf")) and not any(output.glob("*.html"))
        assert list(output.glob("*.md")) == [output / "questions.md"]
        assert not list(output.glob("*_files"))
    return {"all_pdf_combinations_blocked": True}


def test_pdf_long_table(root):
    output = root / "long_table"
    data = facts("report", "合成多页水线文档")
    data["document"]["description"] += ' <script>alert("not executed")</script> & 原始文本'
    data["render_preferences"]["pdf_orientation"] = "portrait"
    for index in range(70):
        field = copy.deepcopy(data["targets"][0]["fields"][0])
        field.update(id=f"field_{index}", key=f"metric_{index:03d}", name=f"指标 {index}", logic=f"第 {index} 个字段的完整逻辑：SUM(amount) / count(store)；保留空值。")
        data["targets"][0]["fields"].append(field)
    long_logic = "\n".join(f"规则{index:03d}：保留原值和金额精度，校验 source_a | source_b 后写入目标表。" for index in range(160))
    data["targets"][0]["fields"][1]["logic"] = long_logic
    data["targets"][0]["fields"][1]["source_field"] = ""
    data["targets"][0]["fields"][-1]["logic"] += " END_OF_DICTIONARY"
    path = output / "facts.json"
    save(path, data)
    run(str(RENDER), "--facts", str(path), "--out-dir", str(output), "--format", "all")
    data = json.loads(path.read_text(encoding="utf-8"))
    stem = document_stem(data["document"]["title"])
    pdf_path = output / f"{stem}.pdf"
    run(str(VALIDATE), "--facts", str(path), "--profile", "report", "--markdown", str(output/f"{stem}.md"), "--html", str(output/f"{stem}.html"), "--pdf", str(pdf_path))
    reader = PdfReader(pdf_path)
    assert len(reader.pages) > 5
    assert abs(float(reader.pages[0].mediabox.width)-A4[0]) < 1
    assert abs(float(reader.pages[-1].mediabox.width)-landscape(A3)[0]) < 1
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert compact(text).count("字段名") > 3 and "END_OF_DICTIONARY" in compact(text)
    assert compact('<script>alert("not executed")</script>') in compact(text)
    # Corrupt visible content in a middle fragment, retaining matching metadata.
    # The validator must not accept the digest alone or only inspect endpoints.
    markdown = render_markdown(data, f"{stem}_files/data_flow.svg", f"{stem}_files/catalog_registration_flow.svg")
    units, _ = text_units(parse_markdown(markdown))
    unit_id = next(key for key, value in units.items() if value["text"].startswith("规则000"))
    hit_pages = []
    for index, page in enumerate(reader.pages):
        if any(operator == b"BDC" and operands[1].get("/MCID") == unit_id for operands, operator in page.get_contents().operations):
            hit_pages.append(index)
    assert len(hit_pages) >= 3, hit_pages
    page = reader.pages[hit_pages[len(hit_pages)//2]]
    content = page.get_contents()
    kept, skipping = [], False
    for operands, operator in content.operations:
        if operator == b"BDC" and operands[1].get("/MCID") == unit_id:
            skipping = True
        if not skipping:
            kept.append((operands, operator))
        if operator == b"EMC":
            skipping = False
    content.operations = kept
    page.replace_contents(content)
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    tampered = output / "tampered.pdf"
    with tampered.open("wb") as stream:
        writer.write(stream)
    errors = []
    validate_pdf(tampered, data, errors, {})
    assert any(f"text unit {unit_id}" in error for error in errors), errors
    assert not any("stale" in error for error in errors), errors

    # Fact edits must invalidate the old PDF; regenerate all three formats.
    release = copy.deepcopy(data["document"]["release_history"])
    sources = copy.deepcopy(data["sources"])
    data["targets"][0]["table"] = "renamed_target"
    data["targets"][0]["fields"][0]["key"] = "renamed_field"
    data["pipelines"][0]["trigger"] = "每日 09:30"
    data["flow"]["nodes"][2]["label"] = "demo.renamed_target"
    data["flow"]["nodes"][1]["details"] = ["每日 09:30"]
    data["flow"]["edges"][1]["label"] = "修改后的写入"
    save(path, data)
    errors = []
    validate_pdf(pdf_path, data, errors, {})
    assert any("stale" in error for error in errors), errors
    run(str(RENDER), "--facts", str(path), "--out-dir", str(output), "--format", "all")
    run(str(VALIDATE), "--facts", str(path), "--profile", "report", "--markdown", str(output/f"{stem}.md"), "--html", str(output/f"{stem}.html"), "--pdf", str(pdf_path))
    current = json.loads(path.read_text(encoding="utf-8"))
    history = current["document"]["release_history"]
    assert history[:-1] == release and history[-1]["version"] == "0.0.2" and history[-1]["summary"]
    assert current["sources"] == sources
    for suffix in (".md", ".html"):
        assert "renamed_target" in (output/f"{stem}{suffix}").read_text(encoding="utf-8")
    assert "修改后的写入" in (output/f"{stem}_files/data_flow.svg").read_text(encoding="utf-8")
    text = "".join(page.extract_text() for page in PdfReader(pdf_path).pages)
    assert "renamed_target" in compact(text) and "renamed_field" in compact(text) and "09:30" in compact(text)
    return {"pages": len(reader.pages), "split_cell_pages": len(hit_pages), "all_cells_checked": True, "middle_fragment_deletion_rejected": True, "stale_pdf_rejected": True, "all_formats_updated": True, "unrelated_facts_preserved": True}


def run_pdf_regressions(root, check_formats=True):
    root.mkdir(parents=True, exist_ok=True)
    metrics = {}
    if check_formats:
        metrics["formats"] = []
        for profile in ("sync", "report"):
            for choice in OUTPUT_FORMATS:
                render_and_validate(root, profile, choice)
                metrics["formats"].append(f"{profile}:{choice}")
    metrics["blockers"] = test_pdf_blockers(root)
    metrics["long_table_and_edits"] = test_pdf_long_table(root)
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="waterline_pdf_test_") as temporary:
        metrics = run_pdf_regressions(args.work_dir or Path(temporary))
        print(json.dumps({"status": "ok", **metrics}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
