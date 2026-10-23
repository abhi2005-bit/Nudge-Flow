"""Lightweight process adapter for the isolated ML workspace."""

import json
import math
import os
import subprocess
import sys
from pathlib import Path
from shutil import which
from typing import Any


_INTENTS = {
    "booking_enquiry",
    "purchase_enquiry",
    "service_enquiry",
    "complaint_support",
    "cancellation",
    "other_uncertain",
}
_REPOSITORY_ROOT = Path(__file__).resolve().parents[6]
_ML_PROJECT = _REPOSITORY_ROOT / "ml" / "lead_intelligence"


def _unavailable(code: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "reason": None,
        "intent": None,
        "confidence": None,
        "error_code": code,
    }


def _error(code: str) -> dict[str, Any]:
    return {
        "status": "error",
        "reason": None,
        "intent": None,
        "confidence": None,
        "error_code": code,
    }


def classify_customer_message(message: str) -> dict[str, Any]:
    """Run local inference without importing PyTorch into the backend process.

    The ML interpreter and checkpoint can be set explicitly with
    NUDGEFLOW_INTENT_PYTHON and NUDGEFLOW_INTENT_MODEL_PATH. No model is downloaded.
    """

    configured_python = os.getenv("NUDGEFLOW_INTENT_PYTHON")
    python = (
        Path(configured_python).expanduser()
        if configured_python
        else _ML_PROJECT / ".venv" / "Scripts" / "python.exe"
    )
    if not python.is_file():
        discovered = which(configured_python) if configured_python else None
        if discovered:
            python = Path(discovered)
        else:
            return _unavailable("ml_environment_missing")

    model_setting = os.getenv("NUDGEFLOW_INTENT_MODEL_PATH")
    model_path = Path(model_setting).expanduser() if model_setting else (
        _ML_PROJECT / "models" / "intent_classifier_60k"
    )
    if not model_path.is_absolute():
        model_path = (_REPOSITORY_ROOT / model_path).resolve()
    if not model_path.is_dir():
        return _unavailable("model_artifact_missing")

    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(
            None,
            [str(_ML_PROJECT / "src"), environment.get("PYTHONPATH")],
        )
    )
    environment["HF_HUB_OFFLINE"] = "1"
    environment["TRANSFORMERS_OFFLINE"] = "1"
    try:
        completed = subprocess.run(
            [
                str(python),
                "-m",
                "lead_intelligence.inference",
                "--model-path",
                str(model_path),
            ],
            input=json.dumps(message),
            text=True,
            capture_output=True,
            check=False,
            cwd=_ML_PROJECT,
            env=environment,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return _error("inference_timeout")
    except OSError:
        return _unavailable("ml_environment_unavailable")

    if completed.returncode != 0:
        return _error("inference_failed")
    try:
        result = json.loads(completed.stdout)
    except (json.JSONDecodeError, TypeError):
        return _error("invalid_inference_response")

    status = result.get("status") if isinstance(result, dict) else None
    if status == "unavailable":
        return _unavailable("model_artifact_missing")
    if status != "classified":
        return _error("inference_failed")
    intent = result.get("intent")
    confidence = result.get("confidence")
    if (
        intent not in _INTENTS
        or not isinstance(confidence, (int, float))
        or not math.isfinite(confidence)
        or not 0 <= confidence <= 1
    ):
        return _error("invalid_inference_response")
    return {
        "status": "classified",
        "reason": None,
        "intent": intent,
        "confidence": float(confidence),
        "error_code": None,
    }
