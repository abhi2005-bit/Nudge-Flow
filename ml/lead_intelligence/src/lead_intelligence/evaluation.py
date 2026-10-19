"""Multi-class intent metrics and JSON report output, independent of training."""

import json
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import confusion_matrix, f1_score, precision_recall_fscore_support

from lead_intelligence.taxonomy import INTENTS


def evaluate_intents(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, Any]:
    """Compute macro-F1, per-intent precision/recall, and confusion matrix."""
    y_true = np.asarray(y_true, dtype=str)
    y_pred = np.asarray(y_pred, dtype=str)
    if y_true.ndim != 1 or y_pred.ndim != 1:
        raise ValueError("y_true and y_pred must be one-dimensional")
    if y_true.size == 0 or y_true.size != y_pred.size:
        raise ValueError("y_true and y_pred must have the same nonzero length")
    unknown = (set(y_true) | set(y_pred)) - set(INTENTS)
    if unknown:
        raise ValueError(f"Unknown intent labels: {sorted(unknown)}")

    precision, recall, _, _ = precision_recall_fscore_support(
        y_true, y_pred, labels=INTENTS, zero_division=0
    )
    return {
        "sample_count": int(y_true.size),
        "macro_f1": float(f1_score(y_true, y_pred, labels=INTENTS, average="macro", zero_division=0)),
        "per_class": {
            intent: {"precision": float(precision[i]), "recall": float(recall[i])}
            for i, intent in enumerate(INTENTS)
        },
        "confusion_matrix": {
            "labels": list(INTENTS),
            "counts": confusion_matrix(y_true, y_pred, labels=INTENTS).tolist(),
        },
    }


def write_json_report(metrics: dict[str, Any], path: Path) -> None:
    """Write metrics to a local report path (normally under ignored reports/)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
