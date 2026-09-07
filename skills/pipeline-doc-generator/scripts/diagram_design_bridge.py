#!/usr/bin/env python3
"""Bind reviewed, offline Diagram Design SVGs to canonical flow facts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def digest(spec):
    return hashlib.sha256(json.dumps(spec, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def path_commands(value):
    """Normalize the supported absolute SVG path grammar to PDF M/L/C/Z."""
    tokens = re.findall(r"[A-Za-z]|[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?", value)
    residue = re.sub(r"[A-Za-z]|[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?|[\s,]", "", value)
    if residue:
        raise ValueError("Invalid SVG path syntax")
    index, x, y, start = 0, 0., 0., (0., 0.)
    while index < len(tokens):
        command = tokens[index]
        index += 1
        count = {"M": 2, "L": 2, "H": 1, "V": 1, "Q": 4, "C": 6, "Z": 0, "z": 0}.get(command)
        if count is None:
            raise ValueError(f"Unsupported SVG path command: {command}; use explicit absolute M/L/H/V/Q/C/Z")
        values = list(map(float, tokens[index:index+count]))
        if len(values) != count:
            raise ValueError("Incomplete SVG path command")
        index += count
        if command in {"Z", "z"}:
            x, y = start
            yield "Z", []
            continue
        if command == "H":
            command, values = "L", [values[0], y]
        elif command == "V":
            command, values = "L", [x, values[0]]
        elif command == "Q":
            qx, qy, nx, ny = values
            command, values = "C", [x+2*(qx-x)/3, y+2*(qy-y)/3, nx+2*(qx-nx)/3, ny+2*(qy-ny)/3, nx, ny]
        x, y = values[-2:]
        if command == "M":
            start = (x, y)
        yield command, values


def bounds(element):
    values = [float(v) for v in element.get("data-bounds", "").split()]
    if len(values) != 4 or values[2] <= 0 or values[3] <= 0:
        raise ValueError("Diagram node/platform requires data-bounds='x y width height'")
    return values


def contains(outer, inner):
    x, y, w, h = outer
    a, b, c, d = inner
    return x <= a and y <= b and a+c <= x+w and b+d <= y+h


def validate_design(root, spec, check_digest=True):
    from pipeline_diagram_contract import validate_spec, validate_svg_safety, platform_definitions
    validate_spec(spec)
    validate_svg_safety(root)
    if root.tag != "{http://www.w3.org/2000/svg}svg" or root.get("data-engine") != "diagram-design" or root.get("data-visual-version") != "1":
        raise ValueError("Expected Diagram Design SVG interface version 1")
    vb = [float(v) for v in root.get("viewBox", "").split()]
    if len(vb) != 4 or vb[:2] != [0., 0.] or min(vb[2:]) <= 0:
        raise ValueError("Diagram Design SVG requires a positive zero-origin viewBox")
    ids = [e.get("id") for e in root.iter() if e.get("id")]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate SVG IDs")
    if root.get("role") != "img" or not root.get("aria-labelledby") or any(i not in ids for i in root.get("aria-labelledby").split()):
        raise ValueError("Missing accessible diagram title/description")
    allowed = {"svg", "g", "path", "rect", "circle", "ellipse", "line", "text", "title", "desc", "metadata", "defs", "marker", "polygon", "polyline"}
    for element in root.iter():
        name = element.tag.rsplit("}", 1)[-1]
        if name not in allowed or any(k in element.attrib for k in ("style", "transform", "clip-path", "filter", "opacity", "fill-opacity", "stroke-opacity")):
            raise ValueError("Use flattened SVG presentation attributes and supported vector primitives; CSS/transforms/effects are unsupported")
        if name == "path":
            list(path_commands(element.get("d", "")))
        if name == "text" and (not element.get("fill") or not element.get("font-size") or not (element.text or "").strip()):
            raise ValueError("Text requires explicit fill, font-size, and visible content")
    nodes = [e for e in root.iter() if e.get("data-node-id")]
    edges = [e for e in root.iter() if e.get("data-edge-ids")]
    platforms = [e for e in root.iter() if e.get("data-platform-id")]
    if sorted(e.get("data-node-id") for e in nodes) != sorted(n["id"] for n in spec["nodes"]):
        raise ValueError("Diagram Design node coverage differs from facts")
    if sorted(i for e in edges for i in e.get("data-edge-ids").split()) != sorted(e["id"] for e in spec.get("edges", [])):
        raise ValueError("Diagram Design edge coverage differs from facts")
    compact = lambda value: re.sub(r"\s+", "", value)
    visible = lambda e: compact("".join(t.text or "" for t in e.iter() if t.tag.rsplit("}", 1)[-1] == "text"))
    node_map = {e.get("data-node-id"): e for e in nodes}
    for node in spec["nodes"]:
        drawn = node_map[node["id"]]
        if not contains(vb, bounds(drawn)):
            raise ValueError("Node outside SVG canvas")
        for label in [node["label"], *(node.get("identifiers") or [])]:
            if compact(label) not in visible(drawn):
                raise ValueError("Diagram node is missing its visible fact label/identifier")
    edge_map = {i: e for e in edges for i in e.get("data-edge-ids").split()}
    for edge in spec.get("edges", []):
        drawn = edge_map[edge["id"]]
        if (drawn.get("data-from"), drawn.get("data-to")) != (edge["from"], edge["to"]):
            raise ValueError("Diagram edge endpoints differ from facts")
        if compact(edge.get("label", "")) not in visible(drawn):
            raise ValueError("Diagram edge label differs from facts")
    expected = platform_definitions(spec)
    if sorted(e.get("data-platform-id") for e in platforms) != sorted(p["id"] for p in expected):
        raise ValueError("Diagram platform coverage differs from facts")
    for platform in expected:
        drawn = next(e for e in platforms if e.get("data-platform-id") == platform["id"])
        if set(drawn.get("data-platform-members", "").split()) != set(platform["node_ids"]):
            raise ValueError("Diagram platform membership differs from facts")
        box = bounds(drawn)
        if not contains(vb, box) or compact(platform["title"]) not in visible(drawn):
            raise ValueError("Invalid platform boundary/title")
        for identity, node in node_map.items():
            if contains(box, bounds(node)) != (identity in platform["node_ids"]):
                raise ValueError("Drawn platform enclosure differs from confirmed membership")
    if check_digest and root.get("data-spec-sha256") != digest(spec):
        raise ValueError("Diagram Design SVG is stale; update the diagram and explicitly rebind it")


def local_asset(directory, relative):
    path = Path(relative)
    root = directory.resolve()
    result = (root / path).resolve()
    if path.is_absolute() or not result.is_relative_to(root):
        raise ValueError("Diagram asset must be a relative path within the facts directory")
    return result


def render_diagram(spec, output, facts, facts_dir, slot):
    config = facts.get("render_preferences", {}).get("diagrams", {}).get(slot)
    if not config or config.get("engine") != "diagram-design":
        raise ValueError(f"Missing Diagram Design binding for {slot}; author and bind a reviewed SVG first")
    payload = read_bound_asset(spec, config, facts_dir)
    output.write_bytes(payload)


def read_bound_asset(spec, config, facts_dir):
    if config.get("engine") != "diagram-design":
        raise ValueError("Only Diagram Design is supported")
    source = local_asset(facts_dir, config["svg"])
    payload = source.read_bytes()
    if hashlib.sha256(payload).hexdigest() != config["sha256"]:
        raise ValueError("Diagram asset changed since binding; review and rebind it")
    validate_design(ET.fromstring(payload), spec)
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--svg", required=True, help="Reviewed SVG, relative to facts.json")
    parser.add_argument("--slot", choices=["data_flow", "catalog"], default="data_flow")
    args = parser.parse_args()
    from pipeline_doc_common import load_json, write_json
    from render_pipeline_doc import catalog_spec
    facts = load_json(args.facts)
    spec = facts["flow"] if args.slot == "data_flow" else catalog_spec()
    source = local_asset(args.facts.parent, args.svg)
    root = ET.parse(source).getroot()
    validate_design(root, spec, check_digest=False)
    root.set("data-spec-sha256", digest(spec))
    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    source.write_bytes(payload)
    facts.setdefault("render_preferences", {}).setdefault("diagrams", {})[args.slot] = {
        "engine": "diagram-design", "svg": Path(args.svg).as_posix(), "sha256": hashlib.sha256(payload).hexdigest()}
    write_json(args.facts, facts)
    print(f"Bound reviewed Diagram Design SVG: {args.slot}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def required_slots(facts):
    slots = {"data_flow"}
    if facts.get("profile") == "report" and (facts.get("catalog") or {}).get("enabled"):
        slots.add("catalog")
    return slots


def require_bindings(facts):
    missing = required_slots(facts) - facts.get("render_preferences", {}).get("diagrams", {}).keys()
    if missing:
        raise ValueError("Missing Diagram Design binding: " + ", ".join(sorted(missing)) + "; author and bind reviewed SVGs first")
