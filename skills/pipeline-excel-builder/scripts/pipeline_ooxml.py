"""Surgical Pipeline Export writer: retain the supplied export's package and row shells."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import posixpath
import re
import zipfile
from xml.etree import ElementTree as ET

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
ET.register_namespace("", NS)
Q = lambda name: f"{{{NS}}}{name}"
XML_PREFIX = r"(?:[A-Za-z_][\w.-]*:)?"


def sheet_paths(entries):
    rels = ET.fromstring(entries["xl/_rels/workbook.xml.rels"])
    targets = {r.attrib["Id"]: r.attrib["Target"] for r in rels}
    result = {}
    for sheet in ET.fromstring(entries["xl/workbook.xml"]).find(Q("sheets")):
        target = targets[sheet.attrib[f"{{{REL}}}id"]]
        result[sheet.attrib["name"]] = (target.lstrip("/") if target.startswith("/")
                                         else posixpath.normpath("xl/" + target))
    return result


def write_export(template: Path, output: Path, tables, headers, keys):
    # Reuse shared-string indices (including rich text); never renumber existing cells.
    from build_pipeline_excel import (convert_inline_string_cells, shared_string_item,
                                     ensure_shared_strings_content_type,
                                     ensure_shared_strings_relationship)
    with zipfile.ZipFile(template) as archive:
        infos = archive.infolist()
        entries = {info.filename: archive.read(info.filename) for info in infos}
    sst_path = "xl/sharedStrings.xml"
    original_sst = entries.get(sst_path)
    old_items = [] if original_sst is None else list(ET.fromstring(original_sst))
    strings = ["".join(t.text or "" for t in si.iter(Q("t"))) for si in old_items]
    index = {value: i for i, value in enumerate(strings)}

    def intern(value):
        if value not in index:
            index[value] = len(strings)
            strings.append(value)
        return str(index[value])

    def text(cell):
        if cell is None:
            return ""
        if cell.get("t") == "s":
            value = cell.find(Q("v"))
            return strings[int(value.text)] if value is not None and value.text else ""
        return "".join(cell.itertext())

    for name, path in sheet_paths(entries).items():
        if name not in tables:
            continue
        xml = entries[path].decode("utf-8")
        match = re.search(
            rf"<(?P<tag>{XML_PREFIX}sheetData)\b(?P<attrs>[^>]*?)(?:>(?P<body>.*?)</(?P=tag)>|/>)",
            xml, re.S)
        if match is None:
            raise ValueError(f"Unsupported sheetData serialization: {name}")
        raw_rows = [row.group(0) for row in re.finditer(
            rf"<(?P<tag>{XML_PREFIX}row)\b[^>]*?(?:/>|>.*?</(?P=tag)>)",
            match.group("body") or "", re.S)]
        # Parse in the worksheet's namespace context: production rows can contain
        # attributes such as x14ac:dyDescent with declarations only on the root.
        parsed = {int(row.get("r")): deepcopy(row)
                  for row in ET.fromstring(xml).find(Q("sheetData"))}
        old_by_key = {}
        for number, row in parsed.items():
            if number < 3:
                continue
            cells = {re.sub(r"\d", "", c.get("r", "")): c for c in row}
            key = tuple(text(cells.get(column_letter(headers[name].index(h) + 1))) for h in keys[name])
            if any(key):
                old_by_key[key] = row
        old_last = max(parsed, default=2)
        # Verification excludes the final physical row; extraction includes it.
        last = max(old_last, len(tables[name]) + 3, 3)
        result = [raw for raw in raw_rows if int(re.search(r'\br="(\d+)"', raw)[1]) < 3]
        for number in range(3, last + 1):
            values = tables[name][number - 3] if number - 3 < len(tables[name]) else None
            key = tuple(str(values.get(h, "") or "") for h in keys[name]) if values else ()
            original = old_by_key.get(key)
            base = original if original is not None else parsed.get(number, parsed.get(3))
            row = deepcopy(base) if base is not None else ET.Element(Q("row"))
            row.set("r", str(number))
            cells = {}
            for cell in list(row):
                if cell.tag != Q("c"):
                    raise ValueError(f"Unsupported row child in {name}: {cell.tag}")
                column = re.sub(r"\d", "", cell.get("r", ""))
                cell.set("r", f"{column}{number}")
                # Retain style, never retain stale type/formula/value on unused cells.
                keep_empty = (values is not None and original is not None
                              and cell.get("t") == "s" and cell.find(Q("v")) is not None
                              and text(cell) == "")
                if not keep_empty:
                    cell.attrib.pop("t", None)
                    for child in list(cell):
                        cell.remove(child)
                cells[column] = cell
            if values:
                for column, header in enumerate(headers[name], 1):
                    value = values.get(header)
                    if value in (None, ""):
                        continue
                    letter = column_letter(column)
                    cell = cells.get(letter)
                    if cell is None:
                        cell = ET.SubElement(row, Q("c"), r=f"{letter}{number}")
                        cells[letter] = cell
                    for child in list(cell):
                        cell.remove(child)
                    cell.set("t", "s")
                    ET.SubElement(cell, Q("v")).text = intern(str(value))
            row[:] = sorted(row, key=lambda c: column_number(re.sub(r"\d", "", c.get("r", ""))))
            result.append(ET.tostring(row, encoding="unicode"))
        replacement = (f'<{match.group("tag")}{match.group("attrs")}>'
                       + "".join(result) + f'</{match.group("tag")}>')
        xml = xml[:match.start()] + replacement + xml[match.end():]
        if last > max(parsed, default=2):
            xml = re.sub(rf'(<{XML_PREFIX}dimension\b[^>]*ref=")[^"]+("[^>]*/>)',
                         lambda m: m[1] + f"A1:{column_letter(len(headers[name]))}{last}" + m[2], xml)
        entries[path] = xml.encode("utf-8")

    # Synthetic templates can contain inline strings; actual exported shared cells stay intact.
    references = 0
    for path in entries:
        if path.startswith("xl/worksheets/") and path.endswith(".xml"):
            xml, _ = convert_inline_string_cells(entries[path].decode("utf-8"), strings, index)
            entries[path] = xml.encode("utf-8")
            references += sum(1 for c in ET.fromstring(entries[path]).iter(Q("c")) if c.get("t") == "s")
    additions = "".join(shared_string_item(s) for s in strings[len(old_items):])
    if original_sst is not None:
        sst = original_sst.decode("utf-8")
        sst = sst.replace("</sst>", additions + "</sst>")
        sst = re.sub(r'\bcount="\d+"', f'count="{references}"', sst, count=1)
        sst = re.sub(r'\buniqueCount="\d+"', f'uniqueCount="{len(strings)}"', sst, count=1)
    else:
        sst = f'<sst xmlns="{NS}" count="{references}" uniqueCount="{len(strings)}">{additions}</sst>'
    entries[sst_path] = sst.encode("utf-8")
    entries["[Content_Types].xml"] = ensure_shared_strings_content_type(entries["[Content_Types].xml"])
    entries["xl/_rels/workbook.xml.rels"] = ensure_shared_strings_relationship(entries["xl/_rels/workbook.xml.rels"])
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for info in infos:
            archive.writestr(info, entries[info.filename])
        if original_sst is None:
            archive.writestr(sst_path, entries[sst_path])


def column_letter(number):
    result = ""
    while number:
        number, digit = divmod(number - 1, 26)
        result = chr(65 + digit) + result
    return result


def column_number(letters):
    number = 0
    for letter in letters:
        number = number * 26 + ord(letter) - 64
    return number
