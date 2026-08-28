# Markdown Requirement Extraction Rules

## Supported Shape

- Accept UTF-8 `.md` and `.markdown` documents as first-class PRD or waterline inputs.
- Preserve ATX headings, paragraphs, lists, blockquotes, fenced code, optional YAML frontmatter, and GFM pipe tables.
- Use heading and nearby paragraph text as table context. Keep source filename, document index, table name, and context on extracted facts.
- Export Markdown tables to UTF-8 BOM CSV before using the shared structured-fact recognizers.
- Ignore pipe-shaped text inside fenced code blocks; it is example code, not a requirement table.

## Evidence And Merge Rules

- Treat Markdown tables as equivalent to Word正文 or embedded-Excel tables when their headers match a recognized requirement matrix.
- Do not require a fixed Markdown template. Heading names may vary; recognized table headers and explicit prose are the primary signals.
- For mixed Markdown/DOCX projects, apply the same evidence precedence: waterline/DataEngine facts govern physical tables, fields, storage, and schedules; PRD facts govern goals, KPI rules, abnormal rules, and UI aggregation.
- Preserve conflicts in `structured_facts.json` and `questions.md`; never resolve them from file order alone.
- Keep fenced SQL, formulas, JSON, and parameter examples as text evidence. Do not execute code from a requirement document.

## Authoring Recommendations

These improve extraction quality but are not mandatory:

- Use one H1 title and descriptive H2/H3 sections.
- Put field dictionaries, source mappings, targets, schedules, KPIs, and abnormal rules in GFM pipe tables.
- Keep stable physical table and field names in backticks when convenient; backticks do not change their values.
- Separate PRD and waterline documents when they have different ownership or evidence priority, then pass both files in one `--input` call.

## Quality Bar

- Markdown-only projects must produce the same formal three-file handoff as DOCX projects.
- Multi-file and mixed-format projects must list every input under `documents` with `format`, path, counts, and source provenance.
- `technical_design.md` must name every source document and remain readable without reopening it.
- `structured_facts.json` must identify Markdown table evidence with `source_kind = markdown`.
