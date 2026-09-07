# Diagram Design integration

Use this route for new or redesigned diagrams. Codex applies the installed Diagram Design skill; it is a visual authoring workflow, not a callable rendering API. Keep the plugins independently installed and discover the skill from the session catalog, never from hard-coded cache/version paths. Missing Diagram Design must be reported before new visual authoring; an already bound SVG can still render without that plugin. No other drawing engine or automatic fallback is supported.

## Author and retain the design

1. Update `facts.json` first, including node/edge labels and confirmed `flow.platforms` ownership. Business facts remain canonical there. Record user confirmation and the actual change summary. Preserve existing document release policies.
2. Apply Diagram Design's chosen type, style/profile, connector rules, complexity budget, and visual checks. Read its skill and selected type reference. Reuse style choices already confirmed in the session. Confirm platform ownership for each project; do not assume every HBase instance belongs to DataEngine.
3. Save the authored self-contained HTML under `diagram_design/`. Its SVG is the presentation source; facts own semantics. Export that SVG as part of the requested three-format waterline delivery using Diagram Design's export instructions, with the offline constraints below. Keep HTML and SVG together so layout-only edits remain reviewable.
4. Annotate and validate the SVG interface, then explicitly bind the reviewed asset:

```powershell
python scripts/diagram_design_bridge.py --facts <facts.json> --svg diagram_design/data_flow.svg
python scripts/render_pipeline_doc.py --facts <facts.json> --out-dir <project-dir> --format all
```

For a report Catalog diagram, use `--slot catalog`. Both data_flow and enabled report catalog slots require reviewed Diagram Design bindings. Missing bindings stop generation before existing documents are overwritten. Facts-only preflight can run before authoring; complete bundle validation requires all bindings.

Binding checks semantic coverage and stamps the current flow hash. It records `render_preferences.diagrams.<slot> = {engine: "diagram-design", svg: "relative/path.svg", sha256: "..."}`. Normal rendering verifies that the asset bytes and flow hash still match; it does not redraw or overwrite the approved design. Changed flow facts require updating and reviewing the diagram before rebinding. Do not rebind a stale diagram just to suppress a failure. Missing, modified, or unsupported SVGs fail rather than falling back. Changes to unrelated prose/tables reuse the approved diagram.

## SVG interchange contract (version 1)

- Root: SVG namespace, zero-origin positive `viewBox`, `data-engine="diagram-design"`, `data-visual-version="1"`, `role="img"`, unique IDs and `aria-labelledby` pointing to title/description. The binder sets `data-spec-sha256`.
- Each node group: `data-node-id` matching its stable fact ID and `data-bounds="x y width height"` describing its actual visible boundary. Show the complete fact label and physical identifiers in text children; wrapping into multiple text elements is allowed.
- Each edge group: `data-edge-ids`, `data-from`, `data-to`; draw the actual connector and show its fact label. Use one edge ID per group. Attach paths to the source/target boundaries, with labels/masks clear of node and platform borders.
- Each platform group: `data-platform-id`, `data-platform-members` (space-separated IDs), `data-bounds`, and visible product title. Paint its boundary behind the edges and nodes. Geometric enclosure must match confirmed membership.
- Keep a visible diagram title matching the spec title for the PDF full-page supplement.
- Flatten CSS into explicit SVG presentation attributes. No external fonts/assets, CSS style blocks, transforms, clipping, filters, opacity effects, scripts, images, or foreignObject. Resolve colors to hex or `none`; use local CJK font fallbacks. This is a stricter offline export contract than Diagram Design's standalone HTML defaults.
- Supported vectors: rect, circle, ellipse, polygon, polyline, line, and paths with explicit absolute M/L/H/V/Q/C/Z commands. Repeat the command for each segment. Use paths for arrow connectors. Marker arrows use the renderer's fixed triangular arrowhead in PDF; avoid custom marker semantics.
- Text must have explicit x/y, font-size, fill, and optional font-weight/text-anchor. Use separate text elements for lines. The PDF uses embedded CJK fonts rather than remote design fonts; check wrapping in both formats.

The binding validator checks safety, IDs, visible fact labels, endpoints, bounds, membership and freshness. It does not establish visual quality or prove that hand-authored bounds match every stroke. Inspect the actual SVG/HTML and all PDF pages, particularly connector attachments, background masks, Chinese labels and platform enclosures. Preserve the existing HTML focus/zoom/pan viewer and three-format checks.

## Layout persistence and scope

Do not turn a single simple layout into a mandatory fixed grid. For complex flows use Diagram Design's overview/detail approach with explicit semantic coverage; this version binds one SVG per slot, so compose the reviewed views into one supported SVG or extend the interface before delivering multiple linked views. Never silently drop nodes or relationships to fit a complexity budget.

Modify skill implementation in the source repository first. Plugin mirroring, installation and publishing remain separate actions governed by the user's scope; merely binding a document diagram does not authorize them.
