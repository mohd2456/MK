#!/usr/bin/env python3
"""Fold captured conversations into the MK fine-tuning dataset.

As you use MK, the web/gateway can capture successful conversations (opt-in via
MK_CAPTURE_CONVERSATIONS) to a JSONL file. This script merges those into the
training split, de-duplicating against existing examples, so the next retrain
learns from real usage.

Usage:
    python training/scripts/ingest_captured.py \
        --captured ~/.mk/training/captured.jsonl \
        --data-dir training/data

Then retrain as usual (see training/README.md).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make the mk package importable when run from a source checkout.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
if _SRC.exists():
    sys.path.insert(0, str(_SRC))

from mk.training.ingest import ingest  # noqa: E402


def _canonical_system_prompt(data_dir: Path) -> str | None:
    """Best-effort load of the dataset's canonical system prompt.

    generate_dataset.py defines MK_SYSTEM_PROMPT; if present we normalize
    captured examples to it so the training data stays consistent.
    """
    gen = data_dir.parent / "data" / "generate_dataset.py"
    if not gen.exists():
        gen = Path(__file__).resolve().parent.parent / "data" / "generate_dataset.py"
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("mk_generate_dataset", gen)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)  # type: ignore[union-attr]
            return getattr(module, "MK_SYSTEM_PROMPT", None)
    except Exception:
        return None
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge captured conversations into the dataset")
    parser.add_argument(
        "--captured",
        default=str(Path.home() / ".mk" / "training" / "captured.jsonl"),
        help="Path to captured conversations JSONL",
    )
    parser.add_argument(
        "--data-dir",
        default=str(Path(__file__).resolve().parent.parent / "data"),
        help="Dataset directory containing mk_train.jsonl and mk_val.jsonl",
    )
    parser.add_argument(
        "--no-normalize",
        action="store_true",
        help="Do not rewrite captured system prompts to the canonical one",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    train_path = data_dir / "mk_train.jsonl"
    val_path = data_dir / "mk_val.jsonl"

    normalize = None if args.no_normalize else _canonical_system_prompt(data_dir)

    stats = ingest(
        captured_path=args.captured,
        train_path=train_path,
        val_path=val_path,
        normalize_system=normalize,
    )

    print("Captured conversation ingest complete:")
    print(f"  captured examples : {stats['captured']}")
    print(f"  added (new)       : {stats['added']}")
    print(f"  duplicates skipped: {stats['duplicates']}")
    print(f"  invalid skipped   : {stats['invalid']}")
    print(f"  dataset total now : {stats['total_after']}")
    if stats["added"]:
        print(f"\nAppended {stats['added']} examples to {train_path}")
        print("Retrain with the pipeline in training/README.md to update MK's brain.")
    else:
        print("\nNothing new to add.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
