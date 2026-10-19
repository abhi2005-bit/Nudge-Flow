"""Loading, normalization, and validation for labeled customer messages."""

import re
import unicodedata
from pathlib import Path

import pandas as pd

from lead_intelligence.taxonomy import INTENTS

REQUIRED_COLUMNS = ("message", "intent")


def normalize_message(message: str) -> str:
    """Normalize text for duplicate detection without changing model input text."""
    normalized = unicodedata.normalize("NFKC", message).casefold()
    return " ".join(re.findall(r"\w+", normalized, flags=re.UNICODE))


def read_labeled_messages(path: Path) -> pd.DataFrame:
    """Read a UTF-8 CSV and validate its message/intent schema and values."""
    frame = pd.read_csv(path, encoding="utf-8", dtype=str, keep_default_na=False)
    if tuple(frame.columns) != REQUIRED_COLUMNS:
        raise ValueError(f"CSV headers must be exactly {REQUIRED_COLUMNS}")
    if frame.empty:
        raise ValueError("Dataset contains no message rows")

    frame = frame.copy()
    frame["message"] = frame["message"].str.strip()
    frame["intent"] = frame["intent"].str.strip()
    if frame["message"].eq("").any():
        raise ValueError("Messages must not be empty")
    if frame["intent"].eq("").any():
        raise ValueError("Intent labels must not be empty")

    unknown_intents = sorted(set(frame["intent"]) - set(INTENTS))
    if unknown_intents:
        raise ValueError(f"Unknown intent labels: {unknown_intents}")

    normalized = frame["message"].map(normalize_message)
    duplicate_labels = pd.DataFrame({"normalized": normalized, "intent": frame["intent"]})
    conflicting = duplicate_labels.groupby("normalized")["intent"].nunique()
    if (conflicting > 1).any():
        raise ValueError("Normalized duplicate messages have conflicting intent labels")

    return frame
