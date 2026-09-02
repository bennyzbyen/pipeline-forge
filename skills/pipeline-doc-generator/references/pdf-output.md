# PDF Output

Use PDF for an email attachment, printing, or archival review. Generating a PDF does not authorize sending email. Keep the canonical facts and diagrams; later edits regenerate the PDF from facts instead of modifying the PDF directly.

## Interface

```powershell
python scripts/render_pipeline_doc.py --facts <facts.json> --out-dir <directory> --format pdf
python scripts/render_pipeline_doc.py --facts <facts.json> --out-dir <directory> --format html-pdf
python scripts/render_pipeline_doc.py --facts <facts.json> --out-dir <directory> --format all
python scripts/validate_pipeline_doc.py --facts <facts.json> --profile sync --pdf <document.pdf>
```

`both` retains its earlier meaning of Markdown + HTML. PDF-only output does not emit a throwaway HTML/Markdown file, but always retains `facts.json`, `questions.md`, SVG/spec, and layout audit artifacts. The same blocker gate applies to every format.

## Presentation

- Preserve canonical chapter order and all table/field/logic content. Do not add invented release metadata. Contents pages and unnumbered diagram supplements are PDF navigation/layout elements, not new business chapters.
- Body pages are A4. Auto orientation uses landscape when a table has at least seven columns; otherwise portrait. Honor an explicit `render_preferences.pdf_orientation` choice.
- Embed Chinese TrueType fonts, retain selectable/searchable text, wrap long paths and table names, and repeat table headers on continuation pages. Permit an exceptionally tall cell to split instead of dropping text.
- Render Graphviz cards as native PDF vectors, not screenshots. In-text diagrams link to A3 landscape full-page supplements, which link back to their original position. PDF readers provide page zoom/pan; do not promise HTML-style popups or embed viewer scripts.
- Include page numbers, document-title running headers, linked contents, and hierarchical bookmarks. No attachments, network assets, scripts, or recipient-side font installation are required to view the result.

## Dependencies And Validation

The renderer uses ReportLab, pypdf, Pillow, and an embeddable CJK TrueType font. PDF validation also uses pdfplumber. Prefer bundled workspace dependencies. On Windows, Microsoft YaHei is discovered from the Windows font directory. Elsewhere, set `PIPELINE_PDF_FONT` to an available CJK `.ttf` or TrueType `.ttc`; optionally set `PIPELINE_PDF_BOLD_FONT`. Report missing fonts/dependencies instead of silently producing missing Chinese glyphs. Runtime/font paths must not be saved in generated facts or source examples.

Run `validate_pipeline_doc.py --pdf ...` for canonical-content fingerprint, text/table coverage, bookmarks, links, embedded fonts, page bounds, and active-content checks. Each paragraph/cell carries a render-local marked-content ID: the validator reconstructs its actual visible glyphs across pages and compares the complete content, not only a digest or cell endpoints. These IDs are not a PDF/UA accessibility claim. Run `verify_pipeline_pdf.py` for all seven output choices across both profiles, blocked renders, long split cells, deleted middle fragments, and conversational edits. The full `verify_pipeline_doc_generator.py` suite also includes those checks. Use Poppler `pdftoppm` to render all final pages for visual inspection, including repeated headers and large diagrams. Do not treat successful text extraction as sufficient layout verification.
