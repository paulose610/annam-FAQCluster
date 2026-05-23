# Scripts Reference

Utility scripts for preprocessing and postprocessing the FAQ pipeline data.

---

## `summary.py`

Print a quick overview of any CSV file — size, shape, column names, dtypes, missing value counts, and the first 5 rows.

```bash
python summary.py <file>
```

**Arguments**

| Argument | Required | Description |
|---|---|---|
| `file` | yes | Path to the CSV file |

**Example**
```bash
python summary.py zoho_downloaded_file.csv
```

---

## `filter_query_types.py`

Remove rows whose `QueryType` belongs to a hardcoded blocklist (non-crop domains: dairy, fishery, animal husbandry, weather, etc.). Operates on raw Zoho export CSVs.

```bash
python filter_query_types.py [--input INPUT] [--output OUTPUT]
```

**Arguments**

| Argument | Required | Default | Description |
|---|---|---|---|
| `--input` | no | `zoho_downloaded_file.csv` | Input CSV |
| `--output` | no | `zoho_downloaded_file_filtered.csv` | Output CSV |

**Example**
```bash
python filter_query_types.py --input raw_zoho.csv --output filtered.csv
```

**Notes**
- Prints a per-QueryType breakdown of how many rows were removed.
- Matching is case-insensitive.

---

## `get_unique_crops.py`

Extract all unique crop names from the `Crop` column along with their row frequencies. Filters out entries that contain no alphabetic characters (e.g. nulls serialised as numbers).

```bash
python get_unique_crops.py [--input INPUT] [--output OUTPUT]
```

**Arguments**

| Argument | Required | Default | Description |
|---|---|---|---|
| `--input` | no | `zoho_downloaded_file.csv` | Input CSV with a `Crop` column |
| `--output` | no | `unique_crops.csv` | Output CSV with columns `Crop`, `frequency` |

**Example**
```bash
python get_unique_crops.py --input filtered.csv --output unique_crops.csv
```

---

## `crop_normalizer.py`

Map non-standard crop name variants to canonical names using a lookup table (`crop_mapping`). Rows whose crop does not appear in the map are dropped.

```bash
python crop_normalizer.py --input INPUT --output OUTPUT
```

**Arguments**

| Argument | Required | Description |
|---|---|---|
| `--input` | yes | Input CSV with a `Crop` column |
| `--output` | yes | Output CSV with normalised `Crop` values |

**Example**
```bash
python crop_normalizer.py --input filtered.csv --output normalized.csv
```

**Notes**
- Current mappings: `"paddy dhan"` and `"paddy (dhan)"` → `"Paddy"`.
- To add more crops, extend the `crop_mapping` dict at the top of the file.
- Prints how many rows were removed vs. kept.

---

## `get_state_crop_rows.py`

Filter a CSV to rows matching a specific crop, state, or both. Filters are optional — omitting both returns the full dataset.

```bash
python get_state_crop_rows.py --input INPUT --output OUTPUT [--crop CROP] [--state STATE]
```

**Arguments**

| Argument | Required | Description |
|---|---|---|
| `--input` | yes | Input CSV with `Crop` and `StateName` columns |
| `--output` | yes | Output CSV |
| `--crop` | no | Crop name to keep (case-insensitive) |
| `--state` | no | State name to keep (case-insensitive) |

**Examples**
```bash
# Filter by crop only
python get_state_crop_rows.py --input normalized.csv --output paddy.csv --crop Paddy

# Filter by both crop and state
python get_state_crop_rows.py --input normalized.csv --output paddy_bihar.csv --crop Paddy --state Bihar
```

---

## `get_final_output.py`

Collect `unique_questions_freq_qa.csv` from every immediate subfolder of a parent directory and copy them into a `final/` subdirectory, renaming each file to `<subfolder_name>_faq.csv`.

```bash
python get_final_output.py --input PARENT_DIR
```

**Arguments**

| Argument | Required | Description |
|---|---|---|
| `--input` | yes | Parent directory whose subfolders each contain a `unique_questions_freq_qa.csv` |

**Example**
```bash
python get_final_output.py --input outputs/repair
# Creates outputs/repair/final/<crop>_faq.csv for each subfolder
```

**Notes**
- Creates `final/` if it does not exist.
- Reports which subfolders were missing the expected file.

---

## `dedup_using_gemma4.ipynb`

Jupyter notebook that deduplicates generated FAQ questions within each category using a **2-pass LLM approach** backed by Gemma-4 26B (served via a local vLLM endpoint at `http://100.100.108.44:8013`).

### How it works

1. **Pass 1 — batch scan**: questions are batched (default 100 at a time) and the LLM flags potential duplicates of a reference question.
2. **Pass 2 — verification**: the flagged candidates are sent back to the LLM for a stricter confirmation pass to eliminate false positives.
3. Confirmed duplicates are merged into the reference question and their `raw_frequency` counts are summed.
4. A `phase_data_*.csv` audit trail is saved alongside the deduplicated output so you can inspect pass-1 candidates, pass-2 confirmations, and false positives.

### Key functions

#### `gemma_4_26b_it_completion(prompt, max_tokens, temperature, top_p, stop)`

Low-level wrapper that calls the vLLM OpenAI-compatible endpoint and returns the model's text response.

#### `deduplicate_and_aggregate(df, text_col, batch_size)`

Main deduplication loop. Iterates over every `Generated_Category`, finds and merges duplicate `Generated_Question` rows, and aggregates `raw_frequency`.

- `df` — DataFrame with columns `Generated_Category`, `Generated_Question`, `raw_frequency`, `unique_q_id`, `representative_question`, `answer_label`.
- `text_col` — column to compare for similarity (default `"Generated_Question"`).
- `batch_size` — number of candidates per LLM call in Pass 1 (default `100`).

Returns `(cleaned_df, phase_df)`.

#### `_get_verified_matches(reference_row, candidate_df, text_col, batch_size, ref_phase)`

Internal helper that runs the two-pass matching logic for a single reference question. Returns `(list_of_matched_ids, updated_ref_phase_df)`.

### Running the notebook

```bash
# From the scripts/ directory
jupyter notebook dedup_using_gemma4.ipynb
```

The main execution cell at the bottom iterates over all CSVs in `../outputs/repair/final/` and writes:
- `dedup_<filename>.csv` — deduplicated FAQ rows (with `(unclassified)` answer labels removed)
- `phase_data_<filename>.csv` — audit trail of LLM matching decisions
