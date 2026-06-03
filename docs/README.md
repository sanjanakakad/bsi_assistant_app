# BSI Assistant — Technical Documentation

Generated documentation for team presentations and Confluence.

## Files

| File | Use for |
|------|---------|
| `BSI_Assistant_Technical_Documentation.docx` | **Download & share** — Word, email, slide appendix |
| `BSI_Assistant_Technical_Documentation.html` | **Confluence** — open in browser, copy all, paste into Confluence page |
| `diagrams/*.svg` | Editable vector diagrams (draw.io, Figma, Confluence diagram import) |
| `diagrams/*.png` | Embedded images for slides or Confluence attachments |

## Confluence — quick import

1. Open `BSI_Assistant_Technical_Documentation.html` in Chrome/Safari.
2. Select all (Cmd+A) and copy (Cmd+C).
3. In Confluence: create page → paste (Cmd+V).
4. Diagrams render inline. Adjust layout if needed.

**Alternative:** Attach the `.docx` to the Confluence page, or use **Insert → Files and images** for PNGs from `diagrams/`.

## Regenerate after changes

```bash
python docs/generate_documentation.py
```

Requires `python-docx` (included in project venv after first run).
