#!/usr/bin/env python3
"""Small, deterministic presentation rules; never infer a business data contract."""
from __future__ import annotations

from datetime import datetime
import re
from urllib.parse import parse_qs, urlsplit


def unique_paragraphs(values):
    """Deduplicate prose only. Never use this on field dictionaries or data rows."""
    seen, result = set(), []
    for value in values:
        text = str(value or "").strip()
        key = re.sub(r"\s+", "", text).rstrip("。.!！;；")
        if key and key not in seen:
            result.append(text)
            seen.add(key)
    return result


def same_prose(left, right):
    return bool(str(left or "").strip() and str(right or "").strip()) and len(unique_paragraphs([left, right])) == 1


def connection_location(facts, connection):
    """Prefer an explicit type or a stable source reference, not a path guess."""
    if connection.get("location"):
        return str(connection["location"])
    ids = connection.get("source_ids") or ([connection["source_id"]] if connection.get("source_id") else [])
    sources = facts.get("sources") or []
    selected = [source for source in sources if source.get("id") in ids] if ids else sources
    locations = {str(source.get("location") or "") for source in selected}
    if locations and all("blob" in value.lower() for value in locations):
        return "Blob"
    return next(iter(locations)) if len(locations) == 1 else ""


def is_blob_connection(facts, connection):
    return "blob" in connection_location(facts, connection).lower()


def sas_url(connection):
    # Legacy host values are accepted only by callers that have confirmed Blob.
    return str(connection.get("sas_url") or connection.get("host") or "").strip()


def valid_sas_url(value):
    try:
        parsed = urlsplit(value)
        query = parse_qs(parsed.query)
        return parsed.scheme == "https" and bool(parsed.hostname) and bool(query.get("sig", [""])[0])
    except ValueError:
        return False


def sas_expiry(connection):
    """Read se without rebuilding the URL (which would alter its signature)."""
    try:
        expiry = parse_qs(urlsplit(sas_url(connection)).query).get("se", [""])[0]
        if expiry:
            parsed = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                return parsed.isoformat(sep=" ")
    except ValueError:
        pass
    return str(connection.get("expires_at") or "").strip()


def connection_note(connection):
    expiry = sas_expiry(connection)
    note = str(connection.get("note") or "").strip()
    values = [f"过期时间：{expiry}"] if expiry else []
    if note and not same_prose(note, values[0] if values else ""):
        values.append(note)
    return "\n".join(values)


def concise_trigger(value):
    """Reject mixed operational prose rather than selecting the wrong clock time."""
    text = str(value or "").strip()
    return bool(text) and len(text) <= 100 and not re.search(
        r"[\r\n]|<br\s*/?>|就绪|ready|truncate|校验|重试|失败|覆盖|读取|写入",
        text, re.IGNORECASE,
    )


def flow_detail_in_label(value):
    return bool(re.search(
        r"\browkey\b|\bttl\s*[:=：]|truncate\s*(?:\+|then|后)|字段类型|自增序号|幂等校验",
        str(value or ""), re.IGNORECASE,
    ))


def presentation_gaps(facts):
    """Return safe diagnostics: never include a signed URL in an error message."""
    gaps = []
    sources = facts.get("sources") or []
    connections = (facts.get("source_connections") or []) if facts.get("profile") != "report" else []
    has_blob = facts.get("profile") != "report" and any("blob" in str(source.get("location", "")).lower() for source in sources)
    if has_blob and not any(is_blob_connection(facts, connection) for connection in connections):
        gaps.append(("PL-BLOCK-BLOB-CONNECTIONS", "/source_connections", "请提供 Blob SAS URL、目录和有效期；不要把凭据写入技能源码。"))
    for index, connection in enumerate(connections):
        path = f"/source_connections/{index}"
        identity = f"PL-BLOCK-CONNECTION-{index+1}"
        if has_blob and not connection_location(facts, connection):
            gaps.append((identity + "-SOURCE", path, "混合数据源的连接需填写 location 或 source_id，明确此连接属于哪个来源。"))
        if not is_blob_connection(facts, connection):
            continue
        if not valid_sas_url(sas_url(connection)):
            gaps.append((identity + "-SAS", path + "/sas_url", "请提供完整 HTTPS Blob SAS URL；若采用其他认证方式，请明确要求改用相应连接格式。"))
        if not connection.get("database"):
            gaps.append((identity + "-PATH", path + "/database", "请确认 Blob 的 Database / 路径。"))
        if not sas_expiry(connection):
            gaps.append((identity + "-EXPIRY", path + "/expires_at", "无法从 SAS 的 se 参数确定有效期，请补充到期时间或已确认的访问策略说明。"))
    for index, pipeline in enumerate(facts.get("pipelines") or []):
        trigger = pipeline.get("trigger")
        if trigger and not concise_trigger(trigger):
            gaps.append((f"PL-BLOCK-PIPELINE-{index+1}-TRIGGER-DISPLAY", f"/pipelines/{index}/trigger", "请将已确认的触发时间单独写入 trigger；上游就绪、校验和重试说明移至 schedule_notes。不要从多个时间中猜选。"))
    flow = facts.get("flow") or {}
    for collection, fields in (("nodes", ("label",)), ("edges", ("label",)), ("groups", ("title",))):
        for index, item in enumerate(flow.get(collection) or []):
            if any(flow_detail_in_label(item.get(field)) for field in fields):
                gaps.append((f"PL-BLOCK-FLOW-{collection.upper()}-{index+1}-DETAIL", f"/flow/{collection}/{index}", "流程图标签只保留数据/节点身份及流向；RowKey、字段类型等实现细节移至事实属性。"))
    return gaps
