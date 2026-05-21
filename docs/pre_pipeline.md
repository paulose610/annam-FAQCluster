# Pre-Pipeline

The pre-pipeline prepares raw KCC CSV data for the main pipeline by:
1. Filtering rows to a specific state (and optionally domain/query-type).
2. Normalizing crop name variants to canonical names.

**Location**: `pre_pipeline/`
**Entry point**: `run_pre_pipeline.py` (see [Entry Points](entry_points.md))

---

## File Structure

```
pre_pipeline/
├── get_state_crop_rows.py   # Stage 1: state + domain filter
├── crop_normalizer.py       # Stage 2: crop name normalization
├── mapping.py               # Crop name variant → canonical mapping dict
├── filter_query_types.py    # Utility: inspect QueryType values in a CSV
├── get_unique_crops.py      # Utility: list unique crop names in a CSV
└── summary.py               # Utility: print dataset summary statistics
```

---

## Stage 1 — State Filter (`get_state_crop_rows.py`)

Filters the raw CSV to rows matching a target state, with an optional domain filter.

**Input columns expected**:
- `StateName` — state of the farmer query
- `QueryType` or `Domain` — query category (used for domain filtering)
- `Crop` — raw crop name (passed through unchanged)

**CLI usage**:
```bash
python pre_pipeline/get_state_crop_rows.py \
  --input app-data/cleaned_data.csv \
  --state "Karnataka" \
  --domains "pest,disease,nutrient" \
  --output app-data/karnataka_filtered.csv
```

**Arguments**:
| Argument | Required | Description |
|---|---|---|
| `--input` | Yes | Path to raw CSV |
| `--state` | Yes | State name to filter (case-insensitive) |
| `--domains` | No | Comma-separated `QueryType` values; omit to keep all |
| `--output` | Yes | Output CSV path |

**Behaviour**:
- Normalises `StateName` column to lowercase for matching.
- Normalises `QueryType` values to lowercase for domain matching.
- Writes filtered rows to output CSV, preserving all original columns.

---

## Stage 2 — Crop Normalizer (`crop_normalizer.py`)

Maps raw crop name variants to canonical names and removes unmapped rows.

**CLI usage**:
```bash
python pre_pipeline/crop_normalizer.py \
  --input app-data/karnataka_filtered.csv \
  --crops Cotton Sugarcane Paddy \
  --output app-data/karnataka_norm.csv
```

**Arguments**:
| Argument | Required | Description |
|---|---|---|
| `--input` | Yes | State-filtered CSV |
| `--crops` | No | Whitelist of canonical crop names; omit to include all mapped crops |
| `--output` | Yes | Output CSV path |

**Behaviour**:
1. Loads the crop mapping from `mapping.py`.
2. Applies `get_filtered_mapping(crops)` to get the subset relevant to `--crops`.
3. Normalises the raw `Crop` column (strip whitespace, lowercase).
4. Replaces raw values with canonical names.
5. Drops rows whose crop variant is not in the mapping.
6. Writes result to output CSV.

---

## `mapping.py` — Crop Name Mapping

A Python dict (`CROP_MAPPING`) with 200+ entries mapping regional/variant crop names to canonical names.

**Example entries**:
```python
CROP_MAPPING = {
    "cotton kapas":      "Cotton",
    "kapas":             "Cotton",
    "paddy (dhan)":      "Paddy",
    "dhan":              "Paddy",
    "makka":             "Maize",
    "maize makka":       "Maize",
    "tur dal":           "Pigeon Pea",
    "arhar":             "Pigeon Pea",
    # ... 200+ more entries
}
```

Covers grains, pulses, oilseeds, spices, vegetables, fruits, and plantation crops.

**Helper function**:
```python
def get_filtered_mapping(crop_list: list[str]) -> dict:
    """Return the subset of CROP_MAPPING whose values are in crop_list."""
```

---

## Data Flow

```
app-data/cleaned_data.csv  (raw KCC export)
        │
        ▼
get_state_crop_rows.py  ──── filter by state + domain
        │
        ▼
app-data/<state>_filtered.csv  (intermediate, kept if --keep-intermediate)
        │
        ▼
crop_normalizer.py  ──── map crop variants → canonical names
        │
        ▼
app-data/<state>_norm.csv  (ready for pipeline)
```

---

## Utility Scripts

### `filter_query_types.py`
Print the distinct `QueryType` values present in a CSV. Useful for deciding which domains to include in `--domains`.

```bash
python pre_pipeline/filter_query_types.py --input app-data/cleaned_data.csv
```

### `get_unique_crops.py`
Print the distinct raw crop names in a CSV. Useful for auditing what crop variants exist before running the normalizer.

```bash
python pre_pipeline/get_unique_crops.py --input app-data/karnataka_filtered.csv
```

### `summary.py`
Print row count, crop distribution, and domain distribution for a CSV.

```bash
python pre_pipeline/summary.py --input app-data/karnataka_norm.csv
```

---

## Called From

- `run_pre_pipeline.py` (CLI entry point)
- `backend/routes/faq_cluster.py:_run_pre_sync()` (direct function import, not subprocess)
- `backend/routes/faq_cluster.py:_run_full_sync()` (as part of end-to-end run)
