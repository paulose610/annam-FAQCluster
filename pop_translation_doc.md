# POP-Translation Pipeline — Technical Documentation

## Overview

The POP-Translation pipeline converts agricultural POP (Package of Practices) PDFs into editable English Word documents (`.docx`). It uses Google's Gemini API for translation and Pandoc for final document generation. The output is intended for review and correction by agriculture domain experts.

---

## Pipeline Architecture

The pipeline has five sequential stages, all orchestrated by `scripts/run_pop_to_docx.py`.

```
Source PDF
   ↓  [Step 1] Split into page-wise PDFs
   ↓  [Step 2] Translate each page PDF → HTML via Gemini
   ↓  [Step 3] Extract embedded images and inject into translated HTML
   ↓  [Step 4] Merge all page HTML into one combined HTML document
   ↓  [Step 5] Convert combined HTML → DOCX via Pandoc
Final editable Word file
```

---

## Repository Structure

```
POP-Translation/
├── prompts/
│   └── page_to_pdf.txt        # Translation prompt sent to Gemini
├── scripts/
│   └── run_pop_to_docx.py     # Main pipeline script
├── requirements.txt
├── README.md
└── .gitignore
```

Recommended local working directory layout:

```
POP_Work/
├── Data/
│   └── Karnataka/
│       └── <Crop>/
│           └── <source>.pdf
├── Workdir/
│   └── Karnataka/
│       └── <Crop>/
│           └── <Document_Output_Folder>/
├── prompts/
├── scripts/
└── requirements.txt
```

---

## Dependencies

**Python 3.11+**

Python packages (`requirements.txt`):
- `google-genai` — Gemini API client
- `pymupdf` (`fitz`) — PDF reading, splitting, image extraction
- `beautifulsoup4` — HTML parsing and manipulation
- `python-docx` — DOCX utilities
- `docxcompose` — DOCX merging utilities

External tool:
- **Pandoc** — HTML to DOCX conversion. Must be installed separately and available in system PATH.

**Environment variable:**
- `GEMINI_API_KEY` — required unless `--skip-translation` is used.

---

## Step-by-Step Breakdown

### Step 1: PDF Splitting (`split_pdf_to_page_folders`)

- Opens source PDF with PyMuPDF (`fitz`).
- Splits into individual single-page PDFs.
- Creates one folder per page under `workdir_root`:
  ```
  page_001/page_001.pdf
  page_002/page_002.pdf
  ...
  ```
- Skips already-split pages unless `--overwrite` is passed.
- Respects `--start-page` and `--end-page` to process a subset.

### Step 2: Gemini Translation (`translate_pages`)

- Reads each page PDF as raw bytes and sends it to Gemini along with the translation prompt.
- Uses streaming (`generate_content_stream`) to handle long responses.
- Gemini configuration:
  - Model: `gemini-3.1-pro-preview` (configurable via `--model`)
  - Thinking level: `HIGH`
  - Google Search tool: enabled by default
- Output: `page_NNN/translated.html` — a clean HTML fragment for the page.
- Retry logic: up to `--max-retries` (default 5) with `--retry-wait-seconds` (default 15s) between attempts.
- Supports parallel page translation via `--concurrency` (uses `ThreadPoolExecutor`).
- Skips pages where `translated.html` already exists unless `--overwrite` is passed.
- On completion, saves `translation_summary.json` to `workdir_root`.

### Step 3: Image Extraction and Injection (`inject_images_for_pages`)

- Extracts embedded images from each page PDF using PyMuPDF's `extract_image`.
- Saves extracted images under `page_NNN/images/`.
- Injects images into `translated.html` by matching against `<figure class="image-placeholder">` tags that Gemini inserts when it encounters figures.
- Falls back to replacing raw `[IMAGE]` text placeholders if no figure tags are found.
- Output: `page_NNN/final_with_images.html`.
- Skips pages where `final_with_images.html` already exists unless `--overwrite` is passed.
- On completion, saves `image_injection_summary.json` to `workdir_root`.

### Step 4: Combined HTML Build (`build_combined_docx_html`)

- Reads each page's `final_with_images.html`.
- Rewrites image `src` paths from page-local relative paths to paths relative to `workdir_root` so they resolve correctly from the combined file.
- Wraps each page in a `<section class="translated-page">` block.
- Assembles a single `<!DOCTYPE html>` document with embedded CSS (fonts, tables, figures, page breaks).
- Output: `<doc-name>_combined_pages_NNN_to_NNN.html` saved in `workdir_root`.

### Step 5: DOCX Conversion (`convert_html_to_docx`)

- Invokes Pandoc as a subprocess: `pandoc <combined.html> -f html -t docx -o <output.docx>`.
- Pandoc runs from `workdir_root` so relative image paths resolve correctly.
- Supports an optional `--reference-docx` for applying a custom Word style template.
- Output: `final_output/<doc-name>_translated_pages_NNN_to_NNN.docx`.

---

## Translation Prompt

Located at `prompts/page_to_pdf.txt`. Key constraints given to Gemini:

- Return only a clean HTML fragment — no Markdown, no code fences.
- Preserve headings, paragraphs, lists, tables, and reading order.
- Tables must remain valid HTML tables (not converted to prose).
- Preserve chemical names, crop names, pest names, formulation codes, units, doses, and numbers exactly.
- Do not omit, summarize, paraphrase, or add content.
- Use semantic HTML tags: `h1-h6`, `p`, `ul`, `ol`, `li`, `table`, `thead`, `tbody`, `tr`, `th`, `td`, `figure`, `figcaption`, `div`, `span`.
- Replace figures with `<figure class="image-placeholder">[IMAGE]</figure>` — no invented descriptions.

A `DEFAULT_PROMPT` string is hardcoded in the script as a fallback if the prompt file is missing.

---

## CLI Reference

```
python scripts/run_pop_to_docx.py [OPTIONS]
```

| Argument | Required | Default | Description |
|---|---|---|---|
| `--source-pdf` | Yes | — | Path to input POP PDF |
| `--workdir-root` | Yes | — | Output working directory for this document |
| `--doc-name` | No | PDF stem | Base name for output files |
| `--prompt-file` | No | `prompts/page_to_pdf.txt` | Path to translation prompt |
| `--model` | No | `gemini-3.1-pro-preview` | Gemini model ID |
| `--start-page` | No | `1` | First page to process (1-indexed) |
| `--end-page` | No | Last page | Last page to process (1-indexed) |
| `--concurrency` | No | `1` | Parallel Gemini translation workers |
| `--overwrite` | No | false | Reprocess and overwrite existing outputs |
| `--max-retries` | No | `5` | Max Gemini retry attempts per page |
| `--retry-wait-seconds` | No | `15` | Wait between retries (seconds) |
| `--disable-google-search` | No | false | Disable Gemini's Google Search tool |
| `--reference-docx` | No | None | Pandoc reference DOCX for Word styling |
| `--skip-translation` | No | false | Skip Gemini calls; reuse existing `translated.html` |
| `--skip-image-injection` | No | false | Skip image extraction; reuse existing `final_with_images.html` |

### Example

```bash
python scripts/run_pop_to_docx.py \
  --source-pdf "Data/Karnataka/Ginger/Rhizome rot management.pdf" \
  --workdir-root "Workdir/Karnataka/Ginger/Rhizome rot management" \
  --doc-name "Rhizome rot management" \
  --prompt-file "prompts/page_to_pdf.txt" \
  --start-page 1 \
  --end-page 10 \
  --concurrency 2
```

---

## Output Structure

```
Workdir/<State>/<Crop>/<Document_Name>/
├── page_001/
│   ├── page_001.pdf
│   ├── translated.html
│   ├── images/
│   │   ├── image_1.png
│   │   └── ...
│   └── final_with_images.html
├── page_002/
│   └── ...
├── translation_summary.json
├── image_injection_summary.json
├── pipeline_runtime.log
├── <doc-name>_combined_pages_001_to_NNN.html
└── final_output/
    └── <doc-name>_translated_pages_001_to_NNN.docx
```

---

## Resume Behavior

The pipeline is fully resumable. If a run is interrupted:

- Re-run the same command **without** `--overwrite`.
- Pages with `translated.html` already present skip Gemini translation.
- Pages with `final_with_images.html` already present skip image injection.
- Only incomplete pages are reprocessed.

To force a full rerun, add `--overwrite`.

To rebuild the DOCX from existing HTML without re-translating:

```bash
--skip-translation --skip-image-injection
```

---

## Logging

Each run appends to `pipeline_runtime.log` in `workdir_root`. The log captures:

- Pipeline configuration
- Page splitting progress
- Per-page Gemini request timing, chunk counts, and retry attempts
- Image injection progress and match counts
- Combined HTML generation timing
- Pandoc conversion output
- Final DOCX path and total elapsed time

Log messages are also printed to stdout during execution.

---

## Known Limitations

1. Pandoc can produce incomplete DOCX for very large or complex HTML documents. Chunk-wise generation may be needed.
2. Specific problematic pages may need to be processed separately and merged manually.
3. Pandoc must be installed system-wide; there is no fallback if it is missing.
4. High concurrency increases the risk of Gemini API rate-limit errors or stalled requests.
5. Translation quality is bounded by the source PDF quality and Gemini response accuracy.
6. Image injection depends on Gemini producing `<figure class="image-placeholder">` tags; if Gemini varies its output format, the fallback `[IMAGE]` replacement is used instead.
