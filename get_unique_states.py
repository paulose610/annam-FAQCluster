#!/usr/bin/env python3
import argparse
import pandas as pd

parser = argparse.ArgumentParser()
parser.add_argument("--input",  default="zoho_downloaded_file.csv")
parser.add_argument("--output", default="unique_states.csv")
args = parser.parse_args()

df = pd.read_csv(args.input, low_memory=False, encoding="utf-8", encoding_errors="ignore")
states = df["State"].dropna().str.strip().value_counts().reset_index()
states.columns = ["State", "frequency"]
states.to_csv(args.output, index=False)
print(f"{len(states)} unique states → {args.output}")
