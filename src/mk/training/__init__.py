"""MK training-support package.

Runtime helpers that feed MK's local-brain retraining loop — most importantly
:class:`~mk.training.capture.ConversationCapture`, which records real
user/assistant exchanges (opt-in) in the same JSONL format the fine-tuning
scripts consume.
"""

from mk.training.capture import DEFAULT_SYSTEM_PROMPT, ConversationCapture
from mk.training.ingest import ingest, load_jsonl

__all__ = ["ConversationCapture", "DEFAULT_SYSTEM_PROMPT", "ingest", "load_jsonl"]
