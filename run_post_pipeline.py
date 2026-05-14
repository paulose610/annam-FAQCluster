#!/usr/bin/env python3
"""
run_post_pipeline.py — Post-Pipeline: Collect & Deduplicate FAQ outputs

Orchestrates the two post-pipeline stages after the main pipeline has been
run for all crops:
  1. Collect — gather unique_questions_freq_qa.csv from each crop subfolder
               into <input>/final/, renamed as <crop>_faq.csv
  2. Dedup   — LLM-based deduplication of each collected CSV (Gemma-4-26B)

Usage:
    python run_post_pipeline.py \\
        --input outputs/repair \\
        [--skip-collect] \\
        [--skip-dedup]

Output:
    <input>/final/<crop>_faq.csv            (collected per-crop FAQs)
    <input>/final/dedup_<crop>_faq.csv      (deduplicated FAQs)
    <input>/final/phase_data_<crop>_faq.csv (LLM matching phase log)
"""

import sys
import subprocess
import argparse
import textwrap
from pathlib import Path
from datetime import datetime

SCRIPT_DIR        = Path(__file__).resolve().parent
POST_PIPELINE_DIR = SCRIPT_DIR / 'post_pipeline'
sys.path.insert(0, str(SCRIPT_DIR))

try:
    import _job_ctl as _ctl
except ImportError:
    _ctl = None


def banner(msg: str):
    width = 66
    print(f"\n{'═' * width}")
    print(f"  {msg}")
    print(f"{'═' * width}")


def run_collect(input_dir: Path) -> Path:
    banner("Stage 1/2 — Collect Final FAQ Outputs")
    cmd = [
        sys.executable,
        str(POST_PIPELINE_DIR / 'get_final_output.py'),
        '--input', str(input_dir),
    ]
    print(f"  Input dir : {input_dir}")
    proc = subprocess.Popen(cmd, text=True)
    if _ctl:
        _ctl.register_proc(proc)
    proc.wait()
    if _ctl:
        _ctl.deregister_proc()
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd)
    final_dir = input_dir / 'final'
    print(f"\n  ✓ Collect complete — files in: {final_dir}")
    return final_dir


def run_dedup(final_dir: Path):
    banner("Stage 2/2 — LLM Deduplication (Gemma-4-26B)")
    import pandas as pd
    from post_pipeline.post_processing_dedup import deduplicate_and_aggregate

    csv_files = sorted(
        f for f in final_dir.glob("*.csv")
        if not f.stem.startswith(("dedup_", "phase_data_"))
    )

    if not csv_files:
        print(f"  No CSV files found in {final_dir}")
        return

    for csv_file in csv_files:
        print(f"\n  Processing: {csv_file.name}")
        output_name_phase = f"phase_data_{csv_file.name}"
        output_name_final = f"dedup_{csv_file.name}"
        output_path_phase = final_dir / output_name_phase
        output_path_final = final_dir / output_name_final

        try:
            df = pd.read_csv(csv_file, low_memory=False)
            df, df_phase = deduplicate_and_aggregate(df)
        except Exception as e:
            print(f"  [ERROR] Failed processing {csv_file.name}: {e}")
            continue

        df_phase.to_csv(output_path_phase, index=False)
        df = df[df['answer_label'] != "(unclassified)"]
        df.to_csv(output_path_final, index=False)
        print(f"  Saved phase output : {output_name_phase}")
        print(f"  Saved final output : {output_name_final}")

    print(f"\n  ✓ Deduplication complete")


def parse_args():
    parser = argparse.ArgumentParser(
        prog='run_post_pipeline.py',
        description=textwrap.dedent("""\
            Post-pipeline runner: collect per-crop FAQ CSVs then deduplicate.
            Run this after the main pipeline has finished for all crops.
        """),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    io = parser.add_argument_group('I/O')
    io.add_argument(
        '--input', required=True,
        help='Parent folder whose subfolders each contain unique_questions_freq_qa.csv '
             '(e.g. outputs/repair)',
    )
    ctrl = parser.add_argument_group('Pipeline control')
    ctrl.add_argument('--skip-collect', action='store_true',
                      help='Skip Stage 1 — assume files are already in <input>/final/')
    ctrl.add_argument('--skip-dedup', action='store_true',
                      help='Skip Stage 2 — skip LLM deduplication')
    return parser.parse_args()


def main():
    args = parse_args()

    input_dir = Path(args.input).resolve()
    if not input_dir.exists():
        sys.exit(f"ERROR: input folder not found: {input_dir}")

    final_dir = input_dir / 'final'

    start_time = datetime.now()
    banner("KCC FAQ Post-Pipeline")
    print(f"  Input dir  : {input_dir}")
    print(f"  Final dir  : {final_dir}")
    print(f"  Started    : {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Stage 1: Collect
    if args.skip_collect:
        print(f"\n[--skip-collect] Using existing files in: {final_dir}")
        if not final_dir.exists():
            sys.exit(f"ERROR: {final_dir} does not exist. Run without --skip-collect first.")
    else:
        final_dir = run_collect(input_dir)

    # Stage 2: Dedup
    if args.skip_dedup:
        print("\n[--skip-dedup] Skipping LLM deduplication")
    else:
        run_dedup(final_dir)

    elapsed = datetime.now() - start_time
    banner("Post-Pipeline Complete!")
    print(f"  Output dir : {final_dir}")
    print(f"  Elapsed    : {elapsed}")
    print()


if __name__ == '__main__':
    main()
