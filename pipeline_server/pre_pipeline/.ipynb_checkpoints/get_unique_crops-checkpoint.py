#!/usr/bin/env python3
import argparse
import re
import pandas as pd

parser = argparse.ArgumentParser()
parser.add_argument("--input",  default="zoho_downloaded_file.csv")
parser.add_argument("--output", default="unique_crops.csv")
args = parser.parse_args()

df = pd.read_csv(args.input, low_memory=False, encoding="utf-8", encoding_errors="ignore")

crops = df["Crop"].dropna().str.strip().value_counts().reset_index()
crops.columns = ["Crop", "frequency"]

# Keep only rows where the Crop contains at least one a-zA-Z character
crops = crops[crops["Crop"].str.contains(r'[a-zA-Z]', regex=True)]

crops.to_csv(args.output, index=False)
print(f"{len(crops)} unique crops → {args.output}")