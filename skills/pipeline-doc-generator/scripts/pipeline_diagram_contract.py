"""Semantic and safe-vector contract for Diagram Design waterline assets."""
from collections import defaultdict
import re
import xml.etree.ElementTree as ET
from pipeline_doc_presentation import flow_detail_in_label
SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)
NODE_KINDS = {"blob", "hbase", "pipeline", "clickhouse", "database", "gateway", "process", "table"}
VISUAL_VERSION = "4"

def platform_definitions(spec):
    """Explicit ownership wins; legacy Pipeline-only diagrams use DataEngine."""
    if "platforms" in spec:
        return spec["platforms"]
    groups = {group["id"]: group for group in spec.get("groups", [])}
    members = defaultdict(list)
    for node in spec.get("nodes", []):
        if node.get("kind") != "pipeline":
            continue
        title = groups.get(node.get("group"), {}).get("title", "")
        match = re.search(r"\b(DataEngine|DataHub)\b", title, re.IGNORECASE)
        platform = "DataHub" if match and match[1].lower() == "datahub" else "DataEngine"
        members[platform].append(node["id"])
    return [{"id": name.lower(), "title": name, "node_ids": ids} for name, ids in members.items()]

def tag(name):
    return f"{{{SVG_NS}}}{name}"

def validate_spec(spec):
    if not str(spec.get("title") or "").strip() or not spec.get("nodes"):
        raise ValueError("flow spec requires a title and nodes")
    collections = {key: spec.get(key) or [] for key in ("nodes", "edges", "groups")}
    for key, values in collections.items():
        ids = [v.get("id", "") for v in values]
        if any(not isinstance(i, str) or not re.fullmatch(r"[a-z0-9_]+", i) for i in ids) or len(set(ids)) != len(ids):
            raise ValueError(f"{key} IDs must be unique lowercase ASCII snake_case")
    nodes = {n["id"]: n for n in collections["nodes"]}
    groups = {g["id"]: g for g in collections["groups"]}
    platform_ids, platform_members = set(), set()
    for platform in platform_definitions(spec):
        identity, members = platform.get("id", ""), platform.get("node_ids", [])
        if not re.fullmatch(r"[a-z0-9_]+", identity) or identity in platform_ids:
            raise ValueError("platform IDs must be unique snake_case")
        if not str(platform.get("title", "")).strip() or flow_detail_in_label(platform["title"]):
            raise ValueError("platform requires an identity title without implementation details")
        if not members or len(members) != len(set(members)) or set(members) - nodes.keys() or platform_members.intersection(members):
            raise ValueError("platforms require non-overlapping known node_ids")
        platform_ids.add(identity)
        platform_members.update(members)
    if any(flow_detail_in_label(value) for value in [spec.get("title", ""), *[group.get("title", "") for group in groups.values()]]):
        raise ValueError("flow/group title must not contain implementation details")
    for node in nodes.values():
        if node.get("kind") not in NODE_KINDS:
            raise ValueError(f"unsupported node kind: {node.get('kind')}")
        if node.get("group") and node["group"] not in groups:
            raise ValueError(f"unknown group on {node['id']}")
        group = groups.get(node.get("group"), {})
        for field in ("column", "order"):
            if field in node and (type(node[field]) is not int or node[field] < 0):
                raise ValueError(f"invalid {field} on {node['id']}")
        if "column" in node and "column" in group and node["column"] != group["column"]:
            raise ValueError(f"node {node['id']} is outside its group column")
        if not isinstance(node.get("details", []), list) or any(not isinstance(d, str) for d in node.get("details", [])):
            raise ValueError("node details must be strings")
        if not isinstance(node.get("identifiers", []), list) or any(not isinstance(value, str) for value in node.get("identifiers", [])):
            raise ValueError("node identifiers must be strings")
        if any(flow_detail_in_label(value) for value in [node.get("label", ""), *node.get("identifiers", [])]):
            raise ValueError("flow identity must not contain RowKey or implementation details")
    for edge in collections["edges"]:
        if flow_detail_in_label(edge.get("label", "")):
            raise ValueError("flow edge label must not contain implementation details")
        if edge.get("from") not in nodes or edge.get("to") not in nodes:
            raise ValueError(f"edge {edge['id']} references an unknown node")
        if edge.get("kind", "output") not in {"source", "pipeline", "output", "control"}:
            raise ValueError(f"unsupported edge kind on {edge['id']}")
    seen, card_ids = set(), set()
    for card in (spec.get("presentation") or {}).get("cards", []):
        members = card.get("node_ids") or []
        if not re.fullmatch(r"[a-z0-9_]+", card.get("id", "")) or card["id"] in card_ids:
            raise ValueError("presentation card IDs must be unique snake_case")
        card_ids.add(card["id"])
        if not members or len(members) != len(set(members)) or set(members) - nodes.keys() or seen.intersection(members):
            raise ValueError("presentation cards require non-overlapping known node_ids")
        if len({nodes[m]["kind"] for m in members}) != 1:
            raise ValueError("a presentation card must contain only one node kind")
        if any(e["from"] in members and e["to"] in members for e in collections["edges"]):
            raise ValueError("connected nodes cannot be collapsed into one presentation card")
        seen.update(members)

def validate_svg_safety(root):
    allowed = {"svg", "g", "path", "polyline", "polygon", "rect", "circle", "ellipse", "line", "text", "tspan", "title", "desc", "metadata", "defs", "marker", "clippath", "filter", "fedropshadow"}
    for node in root.iter():
        name = node.tag.rsplit("}", 1)[-1].lower()
        if name not in allowed:
            raise ValueError(f"unsafe SVG element: {name}")
        for key, value in node.attrib.items():
            key = key.rsplit("}", 1)[-1].lower()
            if key.startswith("on") or (key == "href" and value and not value.startswith("#")):
                raise ValueError("SVG event handlers and external references are not allowed")
            for url in re.findall(r"url\(\s*['\"]?([^)'\"]+)", value, re.IGNORECASE):
                if not url.startswith("#"):
                    raise ValueError("external SVG paint/filter URL is not allowed")

def validate_svg(root, spec=None):
    validate_svg_safety(root)
    if root.tag != tag("svg") or root.get("data-engine") != "diagram-design":
        raise ValueError("Only reviewed Diagram Design SVGs are supported")
    if spec is not None:
        from diagram_design_bridge import validate_design
        validate_design(root, spec)
