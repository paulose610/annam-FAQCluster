#!/usr/bin/env python3
"""
run_full.py — Full end-to-end runner: pre-pipeline + per-crop pipeline + post-pipeline

Optionally runs run_pre_pipeline.py (state filter + crop normalization) first,
then runs run_pipeline.py for each crop in sequence, then runs run_post_pipeline.py
once on the shared output directory.

Usage:
    # Full run including pre-pipeline (raw input → normalized → FAQ)
    python run_full.py \\
        --raw-file zoho_raw.csv \\
        --state Karnataka \\
        --crops Cotton Sugarcane \\
        --model ../models/qwen2.5-7b-instruct

    # Skip pre-pipeline (pass already-normalized file directly)
    python run_full.py \\
        --raw-file karna_norm.csv \\
        --crops Cotton Sugarcane \\
        --model ../models/qwen2.5-7b-instruct \\
        --skip-pre-pipeline

    # Load crop list from a text file (one crop per line):
    python run_full.py \\
        --raw-file zoho_raw.csv \\
        --state Karnataka \\
        --crops-file crops.txt \\
        --model ../models/qwen2.5-7b-instruct
"""

import sys
import os
import argparse
import subprocess
import textwrap
from pathlib import Path
from datetime import datetime

try:
    import _job_ctl as _ctl
except ImportError:
    _ctl = None

SCRIPT_DIR = Path(__file__).resolve().parent


def banner(msg: str):
    width = 66
    print(f"\n{'═' * width}")
    print(f"  {msg}")
    print(f"{'═' * width}")


def run_pipeline_for_crop(args, crop: str) -> bool:
    cmd = [
        sys.executable, str(SCRIPT_DIR / 'run_pipeline.py'),
        '--raw-file',   args.raw_file,
        '--crop',       crop,
        '--model',      args.model,
        '--output-dir', args.output_dir,
        '--grid-mode',  args.grid_mode,
        '--gpu-id',     str(args.gpu_id),
        '--batch-size', str(args.batch_size),
    ]
    if args.api_key:
        cmd += ['--api-key', args.api_key]
    if args.skip_qa_gen:
        cmd += ['--skip-qa-gen']

    env = os.environ.copy()
    if args.gpu_id is not None:
        env['CUDA_VISIBLE_DEVICES'] = str(args.gpu_id)

    proc = subprocess.Popen(cmd, env=env)
    if _ctl:
        _ctl.register_proc(proc)
    proc.wait()
    if _ctl:
        _ctl.deregister_proc()
    return proc.returncode == 0


def run_pre_pipeline(args, crops: list[str]) -> Path:
    """Run the pre-pipeline and return the path to the normalized output CSV."""
    raw_file  = Path(args.raw_file).resolve()
    state_slug = args.state.strip().lower().replace(" ", "_")
    norm_file  = raw_file.parent / f"{state_slug}_norm.csv"

    cmd = [
        sys.executable, str(SCRIPT_DIR / 'run_pre_pipeline.py'),
        '--input',  str(raw_file),
        '--state',  args.state,
        '--crops',  *crops,
        '--output', str(norm_file),
    ]
    subprocess.run(cmd, check=True)
    return norm_file


def run_post_pipeline(args):
    cmd = [
        sys.executable, str(SCRIPT_DIR / 'run_post_pipeline.py'),
        '--input', args.output_dir,
    ]
    subprocess.run(cmd, check=True)


def load_crops(args) -> list[str]:
    if args.crops:
        return args.crops
    crops_file = Path(args.crops_file)
    if not crops_file.exists():
        sys.exit(f"ERROR: crops file not found: {crops_file}")
    lines = crops_file.read_text().splitlines()
    return [l.strip() for l in lines if l.strip() and not l.startswith('#')]


def parse_args():
    parser = argparse.ArgumentParser(
        prog='run_full.py',
        description=textwrap.dedent("""\
            Full pipeline runner: processes each crop with run_pipeline.py,
            then collects and deduplicates outputs with run_post_pipeline.py.
        """),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    io = parser.add_argument_group('I/O (required)')
    io.add_argument('--raw-file', required=True,
                    help='Path to raw KCC CSV file')
    crops_grp = io.add_mutually_exclusive_group(required=True)
    crops_grp.add_argument('--crops', nargs='+', metavar='CROP',
                           help='One or more crop names (e.g. Cotton Onion Wheat)')
    crops_grp.add_argument('--crops-file', metavar='FILE',
                           help='Text file with one crop name per line')

    mdl = parser.add_argument_group('Model / API')
    mdl.add_argument('--model',
                     default='/home/kshitij/models/qwen2.5-7b-instruct',
                     help='Local Qwen 7B model path')
    mdl.add_argument('--api-key', default=None,
                     help='Anthropic API key (optional, for Claude Haiku in Stage 4)')
    mdl.add_argument('--gpu-id', type=int, default=0,
                     help='CUDA device index (default: 0)')
    mdl.add_argument('--batch-size', type=int, default=8,
                     help='LLM batch size (default: 8)')

    ctrl = parser.add_argument_group('Pipeline control')
    ctrl.add_argument('--state', default=None,
                      help='State name for pre-pipeline filter (e.g. Karnataka). '
                           'Required unless --skip-pre-pipeline is set.')
    ctrl.add_argument('--output-dir', default='outputs/repair',
                      help='Base output directory (default: outputs/repair)')
    ctrl.add_argument('--grid-mode', default='quick',
                      choices=['quick', 'medium', 'full', 'exhaustive'],
                      help='HP search grid size (default: quick)')
    ctrl.add_argument('--skip-pre-pipeline', action='store_true',
                      help='Skip Stage 0 pre-pipeline — use --raw-file directly as normalized input')
    ctrl.add_argument('--skip-qa-gen', action='store_true',
                      help='Skip Q&A generation (Stage 7) for each crop')
    ctrl.add_argument('--skip-post-pipeline', action='store_true',
                      help='Skip run_post_pipeline.py after all crops are done')

    args = parser.parse_args()

    if not args.skip_pre_pipeline and not args.state:
        parser.error("--state is required unless --skip-pre-pipeline is set")

    return args


def main():
    args = parse_args()
    crops = load_crops(args)

    if not crops:
        sys.exit("ERROR: no crops specified.")

    start_time = datetime.now()
    banner("KCC FAQ — Full Pipeline")
    print(f"  Raw file   : {args.raw_file}")
    if not args.skip_pre_pipeline:
        print(f"  State      : {args.state}")
    print(f"  Crops      : {len(crops)}")
    for c in crops:
        print(f"               • {c}")
    print(f"  Output dir : {args.output_dir}")
    print(f"  Model      : {args.model}")
    print(f"  Grid mode  : {args.grid_mode}")
    print(f"  Started    : {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Stage 0: Pre-pipeline (state filter + crop normalization)
    if args.skip_pre_pipeline:
        print("\n[--skip-pre-pipeline] Using raw file directly as normalized input")
        effective_raw = args.raw_file
    else:
        banner("Stage 0 — Pre-Pipeline")
        norm_file = run_pre_pipeline(args, crops)
        effective_raw = str(norm_file)
        print(f"\n  Normalized file : {effective_raw}")

    # Temporarily point args.raw_file at the normalized file for the pipeline calls
    args.raw_file = effective_raw

    failed = []
    for i, crop in enumerate(crops, 1):
        banner(f"Crop {i}/{len(crops)} — {crop}")
        ok = run_pipeline_for_crop(args, crop)
        if ok:
            print(f"\n  ✓ {crop} complete")
        else:
            print(f"\n  ✗ {crop} FAILED — continuing with next crop")
            failed.append(crop)

    if not args.skip_post_pipeline:
        banner("Post-Pipeline")
        run_post_pipeline(args)

    elapsed = datetime.now() - start_time
    banner("Full Pipeline Complete!")
    print(f"  Crops processed : {len(crops) - len(failed)}/{len(crops)}")
    if failed:
        print(f"  Failed crops    : {', '.join(failed)}")
    print(f"  Output dir      : {args.output_dir}")
    print(f"  Elapsed         : {elapsed}")
    print()


if __name__ == '__main__':
    main()
