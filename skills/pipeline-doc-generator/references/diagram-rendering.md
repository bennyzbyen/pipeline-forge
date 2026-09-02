# Graphviz Diagram Rendering

The default engine is offline Graphviz `dot`, followed by the skill's SVG card renderer. Python/Pillow measures and wraps complete labels; Graphviz places nodes, ports, edges, and reserved edge-label boxes. Do not truncate labels/details or hand-edit generated SVG/DOT/layout files.

## Runtime

The renderer accepts native `dot` on PATH or the Codex app's bundled Node + `@viz-js/viz`. It does not download packages or silently revert to the old fixed-grid layout. If neither is available, report the dependency and request setup rather than inventing a successful render.

Optional environment overrides: `PIPELINE_GRAPHVIZ_DOT` (native executable); or `PIPELINE_GRAPHVIZ_NODE` plus `PIPELINE_GRAPHVIZ_VIZ` (offline Viz module). `PIPELINE_GRAPHVIZ_FONT` selects a CJK font. Use the app's workspace-dependency discovery when locating bundled dependencies; never persist workstation-specific runtime paths in generated artifacts.

## Facts Interface And Grouping

Existing `flow.nodes`, `flow.edges`, `groups`, `column`, and `order` remain supported. Omit column hints to let Graphviz infer ranks. Graphviz optimizes vertical ordering to reduce crossings; set `flow.presentation.preserve_order = true` only when the specified order is important enough to outweigh crossings. Group titles appear on their member cards without large empty swimlanes.

Three or more same-kind leaf sources or targets with identical neighbors may share one display card. All member names, details, labels, and original node/edge IDs remain represented. Pipelines are not automatically grouped. Disable automatic grouping with `flow.presentation.auto_group = false` when separate cards communicate the relationship better.

For a more compact complex diagram, define presentation-only cards in `facts.json`:

```json
"presentation": {
  "cards": [
    {"id": "independent_entries", "title": "两个独立准备入口", "node_ids": ["daily_entry", "manual_entry"]}
  ]
}
```

Members must have the same node kind and column, must not appear in multiple cards, and must not be directly connected. These are visual groups, not merged jobs. Their individual row ports preserve different downstream branches. Do not duplicate business labels or physical names in presentation configuration: those come from the original nodes. Do not add or remove a relationship for visual convenience.

## Appearance And Interaction

Keep a bright white canvas and stable categorical fills: Blob purple, HBase green (whether source or target), Pipeline blue, ClickHouse amber. Use tinted title bands and paler card bodies, legible dark text, and restrained neutral connectors. Keep labels in addition to color; use dashed lines for control relationships.

HTML embeds the SVG plus the trusted local viewer. Click or keyboard-activate a diagram to focus, use wheel or +/- to zoom, drag to pan, use touch pinch where available, reset with Fit/0, and close with Escape or Close. Return keyboard focus to the original diagram. No network, CDN, or additional files are needed to view the HTML. Markdown continues to reference the static SVG relatively.

## Validation

The renderer checks node/card and label overlap, unrelated edge/card crossings, and text bounds. The document validator checks original node/edge coverage and a facts fingerprint so stale diagrams cannot pass. Run `verify_pipeline_doc_generator.py` and the Node `verify_diagram_viewer.cjs` after changing the engine/viewer, then inspect generated HTML visually. Preserve all existing template, table, question-gate, and conversational-edit contracts.
