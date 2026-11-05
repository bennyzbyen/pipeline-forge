# Diagram Design integration

PipelineForge binds one reviewed `data_flow` SVG. Discover the separately installed `diagram-design:diagram-design` from the session catalog. It owns visual authoring, templates and export; facts own the data relationships. Reuse the approved palette or project profile.

## Choose the diagram from the question

- For “which source feeds which output?” use Diagram Design's **Architecture** type, or **Data flow** when roles and handoffs are the point. For a requested topology comparison use **Architecture delta**. Read the selected type reference only. Start with the minimal static variant at document width; omit editorial cards, animation and explanatory sidebars.
- Trace each branch in facts first. Identify every evidenced source table/manual file, the actual Pipeline and the physical destination with a short business description. Keep storage-specific names and unequal writes distinct. Keep unverified physical names distinguishable from confirmed names. Similar pure-sync tasks can share a node with their `pipeline_ids`; keep distinct writers, transformations and dependencies visible.
- Give each arrow one evidenced action. Use `kind: control` for a trigger. For an in-database SQL transformation, show which tables feed the result and the Pipeline that triggers execution as separate relationships when the evidence supports both. Keep SQL text, schedules and field rules in their document sections. A store's type alone cannot decide a route.
- Keep supplied illustrations when the user requests the original image. When asked to redraw, start from the source and latest sketch. Preserve direction, grouping, names and synchronization labels such as incremental vs T-1. In Before/After, freeze the historical panel unless explicitly corrected. Match projects by documented Project Name and color across panels. Change only the affected panel, label or route.

## Lay out and inspect once before binding

1. Order inputs and outputs by relationship, align each Pipeline with its result, and size nodes to their longest wrapped identifier. Keep database cylinders, a recognizable Blob/file source and a prominent Pipeline label. Enclose only confirmed `flow.platforms` members, titled with the platform name. Crop the viewBox to the occupied content plus a readable margin.
2. Apply Diagram Design's connector rules in `references/primitives-core.md`: orthogonal routes, distinct ports, short verb labels beside their own segments, masks clear of text and borders. Reorder nodes before adding bends; bridge unavoidable crossings. Group shared identities only when the reader can still trace every branch. If crowded, compose overview/detail panels in the same bound SVG. Cut duplicate captions and step numbers before shrinking text.
3. Run the installed skill's `scripts/self_check.py --offline <design.html>`. When its plugin checkout provides `scripts/verify-geometry.py`, run that checker on the same HTML for crowded ports, stacked routes and label-mask collisions. Inspect the actual image at reading width; trace each source and trigger to its destination, check whitespace, then correct the affected routes before export. For a frozen Before panel, limit corrections to the requested scope.

## Offline SVG contract

Retain the HTML under `diagram_design/`. Follow the installed skill's `references/export.md` and run `scripts/export_svg.py <design.html> <design.svg> --system-fonts`. Set presentation attributes on the artwork while authoring. If export carries CSS into `defs`, resolve inherited paint and fonts on the affected elements before removing the stylesheet. Verify the SVG and PDF at final size.

- Root SVG namespace, positive zero-origin `viewBox`, `data-engine="diagram-design"`, `data-visual-version="1"`, unique IDs, `role="img"` and `aria-labelledby` resolving to the title and description. Include the visible spec title for PDF.
- Nodes use `data-node-id` and actual `data-bounds="x y width height"`. Show the complete fact label and identifiers, wrapped as needed. Once per edge use `data-edge-ids`, `data-from`, `data-to`, a drawn connector and its short label. Each platform has `data-platform-id`, space-separated `data-platform-members`, visible title and bounds matching membership. Paint platform boundaries behind edges and nodes.
- Use rect, circle, ellipse, polygon, polyline, line and explicit absolute M/L/H/V/Q/C/Z paths. Use ordinary arrow markers; PDF draws a triangular arrowhead. Text needs explicit x/y, font-size and fill, plus optional font-weight/text-anchor. Use one text element per line and local CJK fallbacks. Resolve colors to hex or `none`; flatten CSS, transforms and effects. External resources, images, scripts and foreignObject are unsupported.

Run from this skill's directory. The SVG path is relative to the facts directory.

```powershell
python scripts/diagram_design_bridge.py --facts <facts.json> --svg diagram_design/data_flow.svg
```

Binding records the engine, relative SVG path and file hash in `render_preferences.diagrams.data_flow` and stamps the current flow hash on the SVG. Review and rebind changes to the design or flow. Reuse a valid binding for other edits. Legacy Catalog bindings are audit-only.
