#!/usr/bin/env python3
"""
Crop name mapping for the pre-pipeline normalizer.

crop_mapping: {raw_variant: canonical_name}
  - Keys are the original crop name strings as they appear in the raw CSV.
  - Values are the canonical primary crop names used throughout the pipeline.

To add more crops, append entries here — crop_normalizer.py picks them up automatically.
"""

crop_mapping = {
    # Cotton
    "Cotton Kapas":           "Cotton",
    "Cotton (Kapas)":         "Cotton",

    # Sugarcane
    "Sugarcane Noble Cane":   "Sugarcane",
    "Sugarcane (Noble Cane)": "Sugarcane",

    # Sugar Beet
    "Sugar Beet":             "Sugar Beet",
}


def get_filtered_mapping(primary_crops: list[str]) -> dict[str, str]:
    """
    Returns a {variant: canonical} mapping restricted to the given primary crops.

    Example:
        get_filtered_mapping(["Cotton"]) →
        {"Cotton Kapas": "Cotton", "Cotton (Kapas)": "Cotton"}
    """
    primary_set = {c.strip().lower() for c in primary_crops}
    return {k: v for k, v in crop_mapping.items() if v.strip().lower() in primary_set}


def get_reverse_mapping(primary_crops: list[str]) -> dict[str, list[str]]:
    """
    Returns a {canonical: [all_variants]} mapping for the given primary crops.

    Example:
        get_reverse_mapping(["Cotton"]) →
        {"Cotton": ["Cotton Kapas", "Cotton (Kapas)"]}
    """
    result: dict[str, list[str]] = {}
    primary_set = {c.strip().lower() for c in primary_crops}
    for variant, canonical in crop_mapping.items():
        if canonical.strip().lower() in primary_set:
            result.setdefault(canonical, []).append(variant)
    return result
