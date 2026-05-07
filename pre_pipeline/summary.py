#!/usr/bin/env python3
import argparse
import os
import pandas as pd

parser = argparse.ArgumentParser(description="CSV file summary")
parser.add_argument("file", help="Path to CSV file")
args = parser.parse_args()

file_path = args.file

if not os.path.exists(file_path):
    raise FileNotFoundError(f"File not found: {file_path}")

# File size
size_mb = os.path.getsize(file_path) / (1024 * 1024)

# Read CSV
df = pd.read_csv(file_path, low_memory=False)

# Summary
print(f"\nFile: {file_path}")
print(f"Size: {size_mb:.2f} MB")
print(f"Rows: {len(df):,}")
print(f"Columns: {len(df.columns)}")

print("\nColumns:")
for col in df.columns:
    print(f"  - {col}")

print("\nData Types:")
print(df.dtypes)

print("\nMissing Values:")
print(df.isna().sum())

print("\nSample (first 5 rows):")
print(df.head())