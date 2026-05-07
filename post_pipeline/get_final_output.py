#!/usr/bin/env python3
import argparse
import shutil
from pathlib import Path

TARGET_FILE = "unique_questions_freq_qa.csv"
FINAL_DIR_NAME = "final"


def main():
    parser = argparse.ArgumentParser(
        description="Collect unique_questions_freq_qa.csv from subfolders."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Parent folder containing subfolders"
    )
    args = parser.parse_args()

    input_dir = Path(args.input).resolve()

    if not input_dir.exists():
        raise FileNotFoundError(f"Input folder not found: {input_dir}")

    if not input_dir.is_dir():
        raise NotADirectoryError(f"Not a folder: {input_dir}")

    final_dir = input_dir / FINAL_DIR_NAME
    final_dir.mkdir(exist_ok=True)

    missing = []
    copied = 0

    # Iterate through immediate subfolders only
    for item in sorted(input_dir.iterdir()):
        if not item.is_dir():
            continue

        # Skip the final folder itself
        if item.name == FINAL_DIR_NAME:
            continue

        target_path = item / TARGET_FILE

        if not target_path.exists():
            missing.append(item.name)
            continue

        new_name = f"{item.name}_faq.csv"
        destination = final_dir / new_name

        shutil.copy2(target_path, destination)
        copied += 1
        print(f"Copied: {target_path.name} -> {destination.name}")

    print("\n--- Summary ---")
    print(f"Files collected: {copied}")
    print(f"Folders missing file: {len(missing)}")

    if missing:
        print("\nMissing:")
        for name in missing:
            print(name)


if __name__ == "__main__":
    main()