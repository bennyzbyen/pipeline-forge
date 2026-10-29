"""Offline guards derived from the supplied ImportProjectPipelineTemplateHandler.

Source SHA-256: de06a13e0bbf57ecdc36e146b31addb3e3d3ac08e50e2b0e0ccc4bd16adb34c7.
This is a compatibility preflight, not an execution of the Java service.
"""
from datetime import date, datetime
import re
import zipfile
from xml.etree import ElementTree as ET

from pipeline_ooxml import Q, sheet_paths

SHEETS = ["Readme", "Data Utilization", "Target & Catalog", "Target Field", "Pipeline"]
TASK_FIELDS = ("name", "description", "link_target_names", "mlp_params")
EMAIL = re.compile(r"^([a-zA-Z0-9_\-\.]+)@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.)|(([a-zA-Z0-9\-]+\.)+))([a-zA-Z]{2,4}|[0-9]{1,3})(\]?)$")
SOURCE_SHA256 = "de06a13e0bbf57ecdc36e146b31addb3e3d3ac08e50e2b0e0ccc4bd16adb34c7"


def template_headers(wb, base):
    """Use a contiguous 10 + 4*N header profile; Java counts typed cells, not last column."""
    result = {name: list(fields) for name, fields in base.items()}
    if "Pipeline" not in wb:
        return result
    ws = wb["Pipeline"]
    populated = [c for (r, _), c in ws._cells.items() if r == 2 and (c.value is not None or c.data_type in {"s", "inlineStr", "f", "e", "b"})]
    count = len(populated)
    if count < 10 or (count - 10) % 4 or {c.column for c in populated} != set(range(1, count + 1)):
        raise ValueError("Pipeline tasks cols error: headers must be contiguous 10 + 4*N columns (no typed-empty header cells)")
    result["Pipeline"] = list(base["Pipeline"][:10]) + [f"task{n}_{field}" for n in range(1, (count - 10) // 4 + 1) for field in TASK_FIELDS]
    return result


def task_numbers(headers):
    return range(1, (len(headers) - 10) // 4 + 1)


def value_date(value, label, errors):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    # Canonical generated profile is stricter than SimpleDateFormat's partial parsing.
    try:
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError()
        return date.fromisoformat(value)
    except ValueError:
        errors.append(f"{label}: expected valid yyyy-MM-dd date")
        return None


def check_xml(xml, label, strict_json, errors):
    try:
        if not isinstance(xml, str) or "<!DOCTYPE" in xml.upper() or "<!ENTITY" in xml.upper():
            raise ValueError("XML must be text without DTD/entities")
        root = ET.fromstring(xml)
        for element in root.iter():
            text = (element.text or "").strip()
            if text.startswith(("{", "[")):
                strict_json(text)
    except (ET.ParseError, TypeError, ValueError) as exc:
        errors.append(f"{label}: invalid XML/JSON: {exc}")


def validate_java_contract(path, wb, data, schema, errors, warnings, strict_json):
    # getSheetAt(1..4), not getSheet(name): source lines 130-133.
    if wb.sheetnames[:5] != SHEETS:
        errors.append("Java sheet position contract: first five sheets must be " + ", ".join(SHEETS))
    with zipfile.ZipFile(path) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    for name, path_in_zip in sheet_paths(parts).items():
        if name not in schema:
            continue
        nodes = ET.fromstring(parts[path_in_zip]).find(Q("sheetData"))
        physical = {int(row.get("r")): row for row in nodes}
        last = max(physical, default=2)
        missing = [n for n in range(3, last + 1) if n not in physical]
        if missing:
            errors.append(f"{name}: missing physical row shells {missing[:8]}; Java isRowEmpty(null) would fail")
        if last >= 3 and any(c.get("t") is not None or len(c) for c in physical[last]):
            errors.append(f"{name}: final physical row must be a true blank sentinel; Java verification skips it but extraction includes it")
        for number, row in physical.items():
            if number < 3:
                continue
            for cell in row:
                coordinate = cell.get("r")
                current = wb[name][coordinate]
                if current.column > len(schema[name]) and (cell.get("t") is not None or len(cell)):
                    errors.append(f"{name} {coordinate}: populated data outside the declared header would be ignored by Java")
                # Empty STRING is not Java null. Preserve only benign optional text empties.
                task_condition = current.column >= 11 and (current.column - 11) % 4 in (0, 2, 3)
                conditional = (name == "Target & Catalog" and current.column in (4, 8, 21)) or (name == "Pipeline" and (6 <= current.column <= 10 or task_condition))
                if conditional and current.data_type in {"s", "inlineStr"} and not str(current.value or "").strip():
                    errors.append(f"{name} {coordinate}: empty STRING is not null; use a true blank for conditional fields")
                if current.data_type in {"f", "e", "b"}:
                    errors.append(f"{name} {coordinate}: unsupported formula/error/boolean import value")

    targets = data.get("Target & Catalog", [])
    target_du = {row.get("*target_name"): row.get("*data_utilization_name") for row in targets}
    for row in targets:
        label = f"Target & Catalog row {row['_row']}"
        storage = row.get("data_storage_type")
        if storage and storage not in {"HBASE", "HDFS", "MSSQL", "CLICKHOUSE", "SV_CLICKHOUSE"}:
            errors.append(f"{label}: storage {storage} has no supported upsertDataStorage branch in supplied Java")
        required = ["table_name"] if storage == "HBASE" else ["db", "table_name"] if storage else []
        if row.get("dataset_name"):
            required += schema["Target & Catalog"][8:20]
        for field in required:
            if not row.get(field):
                errors.append(f"{label}: Java conditional requirement missing {field}")
        xml = row.get("dataset_source")
        if xml:
            check_xml(xml, label + " dataset_source", strict_json, errors)

    for row in data.get("Pipeline", []):
        number = int(row["_row"])
        label = f"Pipeline row {number}"
        trigger = row.get("pipeline_trigger")
        start = value_date(wb["Pipeline"].cell(number, 7).value, label + " trigger_start", errors)
        end = value_date(wb["Pipeline"].cell(number, 8).value, label + " trigger_end", errors)
        if trigger:
            match = re.fullmatch(r"每([0-9]*)天 ([01]?[0-9]|2[0-3]):[0-5][0-9]", trigger)
            if not match:
                errors.append(f"{label}: pipeline_trigger must use 每天 HH:mm or 每N天 HH:mm, not cron")
            elif match[1] and (int(match[1]) < 1 or int(match[1]) > 2147483647):
                errors.append(f"{label}: day frequency must be a positive Java integer (zero is unsafe even though handler accepts it)")
            if start is None:
                errors.append(f"{label}: a trigger requires pipeline_trigger_start")
            if start and end and end < start:
                errors.append(f"{label}: trigger_end precedes trigger_start")
            if row.get("*is_octopus") == "1":
                warnings.append(f"{label}: is_octopus=1 causes Java to select ALWAYS_RUNNING even with a trigger")
        status = row.get("pipeline_status_notification")
        if status:
            if not trigger:
                errors.append(f"{label}: pipeline_status_notification must be blank without a schedule (generation policy)")
            tokens = status.replace("，", ",").split(",")
            if any(not token or token != token.strip() for token in tokens):
                errors.append(f"{label}: notification status tokens cannot be empty or padded; Java does not trim them")
            emails = row.get("pipeline_notification_emails", "")
            if not emails or any(not EMAIL.fullmatch(email) for email in emails.split(",")):
                errors.append(f"{label}: status notification requires comma-separated email addresses matching Java's regex")
            warnings.append(f"{label}: AsyncJobStatusEnum definition was not supplied; status membership remains unverified")
        for n in task_numbers(schema["Pipeline"]):
            prefix = f"task{n}_"
            name, description, links, xml = (row.get(prefix + field, "") for field in TASK_FIELDS)
            task_label = f"{label} task{n}"
            if (description or links or xml) and not name:
                errors.append(f"{task_label}: missing name would silently discard this task during Java extraction")
            if links:
                # Verification accepts fullwidth commas; resetPipelineTask only splits ASCII commas.
                if "，" in links:
                    errors.append(f"{task_label}: fullwidth comma is unsafe: verification and task creation split links differently")
                tokens = links.split(",")
                if len(tokens) != len(set(tokens)) or any(not token or token != token.strip() for token in tokens):
                    errors.append(f"{task_label}: duplicate/empty/padded task links")
                if any(target_du.get(token) != row.get("*data_utilization_name") for token in tokens):
                    errors.append(f"{task_label}: target link must exist in the same data_utilization")
                if not xml:
                    errors.append(f"{task_label}: linked task needs confirmed MLP XML; Java calls getMlpParameter even when XML is null")
            if xml:
                check_xml(xml, task_label + " MLP", strict_json, errors)
