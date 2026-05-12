#!/usr/bin/env python3
import argparse
import pandas as pd

crop_mapping = {
    "Paddy Dhan": "Paddy",
    "Paddy (Dhan)": "Paddy",
    "Wheat": "Wheat",
    "Bottle Gourd": "Bottle Gourd",
    "Mustard": "Mustard",
    "Raya Indian Mustard": "Mustard",
    "Raya (Indian Mustard)": "Mustard",
    "Toria": "Mustard",
    "African Sarson": "Mustard",
    "Brown Sarson": "Mustard",
    "Gobhi Sarson": "Mustard",
    "Mango": "Mango",
    "Tomato": "Tomato",
    "Green Gram Moong Bean Moong": "Green Gram",
    "Green Gram (Moong Bean/ Moong)": "Green Gram",
    "Guava": "Guava",
    "Citrus": "Citrus",
    "Orange": "Citrus",
    "Mosambi": "Citrus",
    "Acid Lime": "Citrus",
    "Sugarcane Noble Cane": "Sugarcane",
    "Sugarcane (Noble Cane)": "Sugarcane",
    "Brinjal": "Brinjal",
    "Onion": "Onion",
    "BhindiOkraLadysfinger": "Okra",
    "Bhindi(Okra/Ladysfinger)": "Okra",
    "Pearl Millet BajraBulrush MilletSpiked Millet": "Pearl Millet",
    "Pearl Millet (Bajra/Bulrush Millet/Spiked Millet)": "Pearl Millet",
    "Ber": "Ber",
    "Papaya": "Papaya",
    "Chillies": "Chillies",
    "Capsicum": "Chillies",
    "Bell Pepper": "Chillies",
    "Pepper": "Chillies",
    "Potato": "Potato",
    "Cauliflower": "Cauliflower",
    "Mushroom": "Mushroom",
    "Indian rapeseed and mustard yellow sarson": "Indian Rapeseed and Mustard",
    "Indian rapeseed and mustard (yellow sarson)": "Indian Rapeseed and Mustard",
    "Maize Makka": "Maize",
    "Maize (Makka)": "Maize",
    "fodder maize": "Maize",
    "Baby Corn": "Maize",
    "Carrot": "Carrot",
    "Aloe Vera": "Aloe Vera",
    "Lemon": "Lemon",
    "Pigeon pea red gramarhartur": "Pigeon Pea",
    "Pigeon pea (red gram/arhar/tur)": "Pigeon Pea",
    "Bitter Gourd": "Bitter Gourd",
    "Black Gram urd bean": "Urd Bean",
    "Black Gram (urd bean)": "Urd Bean"
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