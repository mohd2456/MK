"""Fold captured conversations back into the fine-tuning dataset.

Takes the JSONL produced by :class:`~mk.training.capture.ConversationCapture`
and merges new, unique examples into the training split, de-duplicating against
what is already in the train/val files. Pure stdlib so it runs anywhere and is
easy to test.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional, Union

PathLike = Union[str, Path]


def load_jsonl(path: PathLike) -> List[dict]:
    """Load a JSONL file into a list of dicts (missing file -> empty list)."""
    p = Path(path)
    if not p.exists():
        return []
    out: List[dict] = []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def is_valid_example(example: object) -> bool:
    """A valid example is a dict with a messages list containing user+assistant."""
    if not isinstance(example, dict):
        return False
    messages = example.get("messages")
    if not isinstance(messages, list) or not messages:
        return False
    roles = {m.get("role") for m in messages if isinstance(m, dict)}
    return "user" in roles and "assistant" in roles


def example_key(example: dict) -> str:
    """Stable dedup key from the user+assistant turns (system prompt ignored)."""
    parts: List[str] = []
    for m in example.get("messages", []):
        if isinstance(m, dict) and m.get("role") in ("user", "assistant"):
            parts.append(f"{m['role']}:{(m.get('content') or '').strip()}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _normalize(example: dict, system_prompt: str) -> dict:
    """Return a copy of example with its system message set to system_prompt."""
    non_system = [
        m for m in example["messages"] if not (isinstance(m, dict) and m.get("role") == "system")
    ]
    return {"messages": [{"role": "system", "content": system_prompt}, *non_system]}


def ingest(
    captured_path: PathLike,
    train_path: PathLike,
    val_path: Optional[PathLike] = None,
    normalize_system: Optional[str] = None,
) -> Dict[str, int]:
    """Merge captured examples into the training split.

    Args:
        captured_path: JSONL of captured conversations.
        train_path: Training split JSONL (new examples are appended here).
        val_path: Optional validation split, used only for de-duplication.
        normalize_system: If given, rewrite each added example's system message
            to this canonical prompt so captured data matches the dataset.

    Returns:
        Stats dict: captured, added, duplicates, invalid, total_after.
    """
    captured = load_jsonl(captured_path)
    existing = load_jsonl(train_path) + (load_jsonl(val_path) if val_path else [])
    seen = {example_key(e) for e in existing if is_valid_example(e)}

    new_examples: List[dict] = []
    duplicates = 0
    invalid = 0
    for ex in captured:
        if not is_valid_example(ex):
            invalid += 1
            continue
        key = example_key(ex)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        new_examples.append(_normalize(ex, normalize_system) if normalize_system else ex)

    if new_examples:
        tp = Path(train_path)
        tp.parent.mkdir(parents=True, exist_ok=True)
        with open(tp, "a", encoding="utf-8") as f:
            for ex in new_examples:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    return {
        "captured": len(captured),
        "added": len(new_examples),
        "duplicates": duplicates,
        "invalid": invalid,
        "total_after": len(existing) + len(new_examples),
    }
