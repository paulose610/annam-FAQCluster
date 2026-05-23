#!/usr/bin/env python3
import argparse
import pandas as pd

parser = argparse.ArgumentParser()
parser.add_argument("--input",  default="input.csv")
parser.add_argument("--output", default="unique_domain.csv")
args = parser.parse_args()

df = pd.read_csv(args.input, low_memory=False, encoding="utf-8", encoding_errors="ignore")

domains = df["QueryType"].dropna().str.strip().value_counts().reset_index()
domains.columns = ["QueryType", "frequency"]

domains.to_csv(args.output, index=False)
print(f"{len(domains)} unique query types → {args.output}")
