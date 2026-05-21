# POP-Translation

The POP-Translation module translates agricultural PDF documents — "Package of Practices" (POPs) — from regional languages to English, producing a Word document (`.docx`) as output.

**Location**: `POP-Translation/`
**Working data directory**: `POP_Work/`
**Main script**: `POP-Translation/scripts/run_pop_to_docx.py`

---

## File Structure

```
POP-Translation/
├── scripts/
│   └── run_pop_to_docx.py   # Pipeline entry point
├── prompts/
│   └── page_to_pdf.txt      # Gemini translation prompt template
└── requirements.txt

POP_Work/                    # Runtime data (not in POP-Translation/)
├── Data/
│   └── <State>/
│       └── <Crop>/
│           └── <document>.pdf   # Source PDFs
└── Workdir/
    └── <State>/
        └── <Crop>/
            └── <document>/      # Per-document working directory
```

---

## Pipeline Stages

The script runs 6 sequential stages. Each stage is skipped if its outputs already exist (resume-safe).

### Stage 1 — PDF Splitting
- Splits the source PDF into one PDF per page using `pypdf`.
- Output: `Workdir/<State>/<Crop>/<doc>/page_001/page_001.pdf`, `page_002/page_002.pdf`, …

### Stage 2 — Gemini Translation
- Sends each page PDF to the **Gemini API** for translation and structured extraction.
- Model: `gemini-2.5-pro-preview` (or as configured)
- Settings: thinking level HIGH, Google Search enabled (for agricultural term grounding).
- Prompt loaded from `prompts/page_to_pdf.txt`.
- Pages run in parallel up to `--concurrency` workers.
- Output: `page_NNN/translated.html` — structured HTML with translated content.

### Stage 3 — Image Extraction
- Extracts images embedded in each original PDF page using `pdf2image` + `pypdf`.
- Output: `page_NNN/images/img_001.png`, `img_002.png`, …

### Stage 4 — Image Injection
- Reads `translated.html` for each page.
- Injects `<img>` tags referencing extracted images at appropriate positions.
- Output: `page_NNN/final_with_images.html`

### Stage 5 — HTML Merging
- Concatenates all `final_with_images.html` pages in page order.
- Output: `<doc>_combined_pages.html` at the document root.

### Stage 6 — DOCX Conversion
- Converts the merged HTML to `.docx` using **Pandoc**.
- Output: `final_output/<doc>_translated.docx`

---

## CLI Usage

```bash
python POP-Translation/scripts/run_pop_to_docx.py \
  --source-pdf POP_Work/Data/Karnataka/Ginger/kcc_ginger.pdf \
  --workdir-root POP_Work/Workdir/Karnataka/Ginger/kcc_ginger \
  --doc-name "kcc_ginger" \
  --prompt-file POP-Translation/prompts/page_to_pdf.txt \
  --start-page 1 \
  --end-page 20 \
  --concurrency 3
```

**Arguments**:
| Argument | Default | Description |
|---|---|---|
| `--source-pdf` | required | Path to source PDF |
| `--workdir-root` | required | Root directory for all working files |
| `--doc-name` | required | Base name for output files |
| `--prompt-file` | required | Path to Gemini prompt template |
| `--start-page` | `1` | First page to translate (1-indexed) |
| `--end-page` | last page | Last page to translate |
| `--concurrency` | `2` | Parallel Gemini API calls |
| `--skip-translation` | `false` | Skip Stage 2; reuse existing `translated.html` files |
| `--skip-image-injection` | `false` | Skip Stage 4 |

---

## Output Structure

```
POP_Work/Workdir/<State>/<Crop>/<document>/
├── page_001/
│   ├── page_001.pdf            # Extracted page
│   ├── translated.html         # Gemini translation output
│   ├── images/
│   │   ├── img_001.png
│   │   └── img_002.png
│   └── final_with_images.html  # Translation + images
├── page_002/
│   └── ...
├── translation_summary.json    # Per-page API timing and token counts
├── image_injection_summary.json
├── pipeline_runtime.log        # Full run log with timestamps
├── <doc>_combined_pages.html   # Merged HTML (all pages)
└── final_output/
    └── <doc>_translated.docx   # Final Word document
```

---

## Resume Safety

Each stage checks for existing output files before running:
- If `page_NNN/translated.html` exists, Stage 2 skips that page.
- If `page_NNN/final_with_images.html` exists, Stage 4 skips that page.
- If `<doc>_combined_pages.html` exists, Stage 5 is skipped.
- If `final_output/<doc>_translated.docx` exists, Stage 6 is skipped.

To re-run a stage, delete its output files.

---

## Backend Integration

The backend triggers POP-Translation via `POST /run/pop`. The route (`backend/routes/pop_translation.py`) builds the subprocess command and launches `run_pop_to_docx.py`:

```python
cmd = [
    "python", "POP-Translation/scripts/run_pop_to_docx.py",
    "--source-pdf", source_pdf,
    "--workdir-root", workdir,
    "--doc-name", doc_name,
    "--prompt-file", prompt_file,
    "--concurrency", str(concurrency),
    "--start-page", str(start_page),
    "--end-page", str(end_page),
]
```

The process output is captured into job `5` and polled by the frontend via `GET /jobs/5`.

---

## Dependencies

| Package | Purpose |
|---|---|
| `google-generativeai` | Gemini API client |
| `pdf2image` | Convert PDF pages to images |
| `pypdf` | Read and split PDF files |
| `pandas` | Tabular data utilities |
| `pandoc` (system) | HTML → DOCX conversion (must be installed separately) |

Install Python dependencies:
```bash
pip install -r POP-Translation/requirements.txt
```

Install Pandoc (Ubuntu):
```bash
sudo apt install pandoc
```
