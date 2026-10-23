"""Local-only message inference for the saved intent classifier checkpoint."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from lead_intelligence.taxonomy import INTENTS
from lead_intelligence.tokenization import load_tokenizer, tokenize_messages


class IntentClassifier:
    """Small inference wrapper reusing this workspace's saved model/tokenizer."""

    def __init__(self, model_path: str | Path) -> None:
        self.model_path = Path(model_path).expanduser().resolve()
        if not self.model_path.is_dir():
            raise FileNotFoundError("The configured model checkpoint is unavailable.")

        import torch
        from transformers import AutoModelForSequenceClassification

        self._torch = torch
        self.tokenizer = load_tokenizer(
            str(self.model_path), local_files_only=True
        )
        self.model = AutoModelForSequenceClassification.from_pretrained(
            str(self.model_path), local_files_only=True
        ).to(torch.device("cpu"))
        self.model.eval()

        id_to_label = self.model.config.id2label
        labels = tuple(id_to_label[index] for index in range(len(INTENTS)))
        if labels != INTENTS:
            raise ValueError("The checkpoint labels do not match the intent taxonomy.")

    def predict(self, message: str) -> dict[str, Any]:
        encoded = tokenize_messages(self.tokenizer, [message])
        with self._torch.inference_mode():
            logits = self.model(**encoded).logits
            probabilities = self._torch.softmax(logits, dim=-1)[0]
            score, class_index = self._torch.max(probabilities, dim=0)
        return {
            "status": "classified",
            "intent": INTENTS[int(class_index.item())],
            "confidence": float(score.item()),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", required=True)
    args = parser.parse_args()
    try:
        message = json.load(sys.stdin)
        if not isinstance(message, str) or not message.strip():
            raise ValueError("Input must be a non-empty message string.")
        prediction = IntentClassifier(args.model_path).predict(message)
    except FileNotFoundError:
        prediction = {"status": "unavailable"}
    except Exception:
        # Do not echo the message or model/library exception into application output.
        prediction = {"status": "error"}
    sys.stdout.write(json.dumps(prediction, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
