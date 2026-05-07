#!/usr/bin/env python3
import argparse
import pandas as pd
from mapping import crop_mapping, get_filtered_mapping


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Normalize Crop column to canonical names and drop unrecognised crops."
    )
    parser.add_argument("--input",  required=True, help="Input CSV with a Crop column")
    parser.add_argument("--output", required=True, help="Output CSV with normalized Crop values")
    parser.add_argument(
        "--crops", nargs="+", metavar="CROP",
        help="Primary crop names to keep (e.g. Cotton Sugarcane). "
             "If omitted, the full mapping is used.",
    )
    args = parser.parse_args()

    effective_mapping = (
        get_filtered_mapping(args.crops) if args.crops else crop_mapping
    )

    df = pd.read_csv(args.input, low_memory=False, encoding="utf-8", encoding_errors="ignore")

    if "Crop" not in df.columns:
        raise ValueError("Column 'Crop' not found")

    before = len(df)

    df["Crop"] = (
        df["Crop"]
        .astype(str)
        .str.strip()
        .str.lower()
        .str.replace(r"\s+", " ", regex=True)
    )

    normalized_mapping = {k.strip().lower(): v for k, v in effective_mapping.items()}

    df["Crop"] = df["Crop"].map(normalized_mapping)
    df = df[df["Crop"].notna()]

    df.to_csv(args.output, index=False)
    print(f"{before - len(df):,} rows removed (crop not in map)")
    print(f"{len(df):,} rows kept → {args.output}")