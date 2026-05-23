#!/usr/bin/env python3
import argparse
import pandas as pd

parser = argparse.ArgumentParser()
parser.add_argument("--input",  default="zoho_downloaded_file.csv")
parser.add_argument("--output", default="unique_crops.csv")
args = parser.parse_args()

# Load the data
df = pd.read_csv(args.input, low_memory=False, encoding="utf-8", encoding_errors="ignore")

# 1. Drop missing values
# 2. Convert to string and strip out any numbers (digits 0-9)
# 3. Clean up leading/trailing whitespaces left behind
crops = df["Crop"].dropna().astype(str)
crops = crops.str.replace(r"\d+", "", regex=True).str.strip()

# Filter out rows that became empty strings after removing numbers
crops = crops[crops != ""]

# Get unique crop names and their frequencies
crop_counts = crops.value_counts().reset_index()
crop_counts.columns = ["Crop", "frequency"]

# Save to CSV
crop_counts.to_csv(args.output, index=False)
print(f"{len(crop_counts)} unique crops (numbers removed) → {args.output}")