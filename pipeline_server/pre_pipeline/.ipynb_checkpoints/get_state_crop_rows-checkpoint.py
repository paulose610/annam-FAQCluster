#!/usr/bin/env python3
import argparse
import pandas as pd

parser = argparse.ArgumentParser(
    description="Filter rows by Crop and/or StateName. If not provided, all values are included."
)

parser.add_argument("--input", required=True, help="Input CSV file")
parser.add_argument("--output", required=True, help="Output CSV file")
parser.add_argument("--crop", help="Crop name to filter (optional)")
parser.add_argument("--state", help="StateName to filter (optional)")

args = parser.parse_args()

# Read CSV
df = pd.read_csv(
    args.input,
    low_memory=False,
    encoding="utf-8",
    encoding_errors="ignore"
)

# Ensure required columns exist
if "Crop" not in df.columns:
    raise ValueError("Column 'Crop' not found")

if "StateName" not in df.columns:
    raise ValueError("Column 'StateName' not found")

# Normalize dataframe columns
df["Crop"] = (
    df["Crop"]
    .astype(str)
    .str.strip()
    .str.lower()
)

df["StateName"] = (
    df["StateName"]
    .astype(str)
    .str.strip()
    .str.lower()
)

# Start with all rows
df_filtered = df.copy()

# Apply Crop filter if provided
if args.crop:
    target_crop = args.crop.strip().lower()
    df_filtered = df_filtered[df_filtered["Crop"] == target_crop]

# Apply State filter if provided
if args.state:
    target_state = args.state.strip().lower()
    df_filtered = df_filtered[df_filtered["StateName"] == target_state]

# Optional: restore clean display names
if args.crop:
    df_filtered["Crop"] = args.crop.strip()

if args.state:
    df_filtered["StateName"] = args.state.strip()

# Save output
df_filtered.to_csv(args.output, index=False)

print(
    f"{len(df_filtered):,} rows written to {args.output}"
)