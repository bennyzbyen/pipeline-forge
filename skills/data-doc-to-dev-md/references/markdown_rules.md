# Markdown Requirement Extraction Rules

## Supported Shape

- Accept UTF-8 `.md` and `.markdown` documents as first-class PRD or waterline inputs.
- Preserve ATX headings, paragraphs, lists, blockquotes, fenced code, optional YAML frontmatter, and GFM pipe tables.
- Use heading and nearby paragraph text as table context. Keep source filename, document index, table name, and context on extracted facts.
- Export Markdown tables to UTF-8 BOM CSV before using the shared structured-fact recognizers.
- Ignore pipe-shaped text inside fenced code blocks; it is example code, not a requirement table. Match the fence character and opening run length; a closing fence must have at least that length and no trailing info text. Shorter inner fences do not close an outer example.
- Within pipe rows, paired inline-code markers of the same run length protect their contents under the existing extraction convention. Preserve escaped pipes; an unmatched marker remains literal text and does not absorb later columns.
- Explicit source/target/example section roles apply to tables and reset at document and section boundaries. Retain examples as supporting evidence, and preserve the legacy header-based route when no role is declared.

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
- Pad missing trailing cells as empty and record their source line. Do not silently stop a table at a malformed row: preserve following valid rows and report extraction issues.
- Rows wider than their header remain in original source evidence and are not assigned to guessed columns. Record an extraction error, retain the original text, and keep the affected mapping unconfirmed. Requested row-limit truncation also records an error before full-codegen readiness.
- FS/Gateway confirmation must follow explicit connector/source evidence. Substrings in names such as `offset` or `fs_count` do not establish an FS component; explicit source storage/path evidence takes precedence over prose.
