#!/usr/bin/env python3
import argparse
import pandas as pd

crop_mapping = {
    # Cotton
    "cotton kapas": "Cotton",
    "cotton (kapas)": "Cotton",
 
    # Onion
    "onion": "Onion",
 
    # Sugarcane
    "sugarcane noble cane": "Sugarcane",
    "sugarcane (noble cane)": "Sugarcane",
 
    # Bengal Gram
    "bengal gram gramchick peakabulichana": "Bengal Gram",
    "bengal gram (gram/chick pea/kabuli/chana)": "Bengal Gram",
 
    # Ginger
    "ginger": "Ginger",
 
    # Pomegranate
    "pomegranate": "Pomegranate",
 
    # Brinjal
    "brinjal": "Brinjal",
 
    # Finger Millet
    "fingermillet  ragimandika": "Finger Millet",
    "fingermillet  (ragi/mandika)": "Finger Millet",
 
    # Sunflower
    "sunflower suryamukhi": "Sunflower",
    "sunflower (suryamukhi)": "Sunflower",
 
    # Green Gram
    "green gram moong bean moong": "Green Gram",
    "green gram (moong bean/ moong)": "Green Gram",
 
    # Watermelon
    "watermelon": "Watermelon",
 
    # Soybean bhat
    "soybean bhat": "Soybean bhat",
    "soybean (bhat)": "Soybean bhat",
 
    # Beans
    "beans": "Beans",
    "french bean": "Beans",
    "cluster bean": "Beans",
    "dolichos bean": "Beans",
    "broad bean": "Beans",
    "winged bean": "Beans",
    "rajma french bean": "Beans",
    "rajma (french bean)": "Beans",
    "rajmash bean": "Beans",
 
    # Mango
    "mango": "Mango",
 
    # Grape
    "grape": "Grape",
 
    # Black Gram
    "black gram urd bean": "Black Gram",
    "black gram (urd bean)": "Black Gram",
 
    # Sorghum (Grain/Jowar only)
    "sorghum jowargreat millet": "Sorghum",
    "sorghum (jowar/great millet)": "Sorghum",
 
    # Papaya
    "papaya": "Papaya",
 
    # Turmeric
    "turmeric": "Turmeric",
 
    # Wheat
    "wheat": "Wheat"
}



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",  required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

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

    crop_mapping_normalized = {k.strip().lower(): v for k, v in crop_mapping.items()}

    df["Crop"] = df["Crop"].map(crop_mapping_normalized)
    df = df[df["Crop"].notna()]

    df.to_csv(args.output, index=False)
    print(f"{before - len(df):,} rows removed (crop not in map)")
    print(f"{len(df):,} rows kept → {args.output}")