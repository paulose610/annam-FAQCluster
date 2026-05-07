#!/usr/bin/env python3
"""
filter_query_types.py — Remove unwanted QueryType rows from raw Zoho CSV.

Usage:
    python filter_query_types.py                          # uses default input/output
    python filter_query_types.py --input my_file.csv
    python filter_query_types.py --input in.csv --output cleaned.csv
"""

import argparse
import pandas as pd
from pathlib import Path

REMOVE_LIST = [
    "Dairy Production",
    "Noisy Data",
    "Animal Husbandry",
    "Market Information",
    "Weather",
    "Government Schemes",
    "Poultry",
    "Animal Production Piggery Goatery Sheep Farming etc",
    "Livestock Products Processing and Packaging",
    "Animal Nutrition",
    "Beekeeping",
    "Coastal Aquaculture",
    "Fish  Marketing",
    "Animal Breeding",
    "Breeding of freshwater prawn",
    "Cattle shed Planning and Management",
    "Freshwater Pearl Farming",
    "Fishery Nutrition",
    "Fish Fingerling Production",
    "Fishery Mechanization",
    "Magur Breeding and Culture",
    "Breeding and culture of ornamental fish",
    "Freshwater pearl culture",
    "Water Testing for Fish Production",
    "Seaweed Cultivation",
    "Artificial Insemination",
    "Fish Dressing   Drying",
    "Deep Sea Fishing and Processing",
    "Fishing Harbours and Landing Centre",
    "Animal Production (Piggery, Goatery, Sheep Farming etc.)",
    "NA (Not Applicable)",
    "Freshwater Pearl Farming.",
    "Vaccine - Viral",
]

QUERY_TYPE_COL = "QueryType"
DEFAULT_INPUT  = "zoho_downloaded_file.csv"
DEFAULT_OUTPUT = "zoho_downloaded_file_filtered.csv"


def main():
    parser = argparse.ArgumentParser(description="Filter unwanted QueryType rows from a CSV.")
    parser.add_argument("--input",  default=DEFAULT_INPUT,  help="Input CSV file (default: zoho_downloaded_file.csv)")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Output CSV file (default: zoho_downloaded_file_filtered.csv)")
    args = parser.parse_args()

    input_path  = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"ERROR: input file not found: {input_path.resolve()}")
        raise SystemExit(1)

    df = pd.read_csv(input_path, low_memory=False, encoding="utf-8", encoding_errors="ignore")
    print(f"Loaded {len(df):,} rows from {input_path}")

    if QUERY_TYPE_COL not in df.columns:
        print(f"ERROR: column '{QUERY_TYPE_COL}' not found.")
        print(f"Available columns: {list(df.columns)}")
        raise SystemExit(1)

    df[QUERY_TYPE_COL] = df[QUERY_TYPE_COL].astype(str).str.strip().str.lower().fillna("")
    remove_set   = {x.strip().lower() for x in REMOVE_LIST}
    mask_removed = df[QUERY_TYPE_COL].isin(remove_set)
    n_removed    = mask_removed.sum()

    removed_counts = df.loc[mask_removed, QUERY_TYPE_COL].value_counts()
    print(f"\nRemoving {n_removed:,} rows across {len(removed_counts)} QueryType(s):")
    for qt, count in removed_counts.items():
        print(f"  {count:>6,}  {qt}")

    df_filtered = df[~mask_removed].copy()
    df_filtered.to_csv(output_path, index=False)
    print(f"\nKept {len(df_filtered):,} rows → {output_path}")


if __name__ == "__main__":
    main()
