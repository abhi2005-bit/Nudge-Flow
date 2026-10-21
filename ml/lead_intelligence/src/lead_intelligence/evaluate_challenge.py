
"""Evaluate the saved intent classifier on a separate challenge set."""

from pathlib import Path

import torch
from torch.utils.data import DataLoader

from lead_intelligence.data import read_labeled_messages
from lead_intelligence.dataset import IntentDataset, create_collate_fn
from lead_intelligence.model import create_model
from lead_intelligence.taxonomy import INTENTS
from lead_intelligence.tokenization import load_tokenizer


def main():
    # 1. Select the available device.
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("Device:", device)

    # 2. Load the independent challenge dataset.
    frame = read_labeled_messages(
        Path("data/nudgeflow_challenge_v1.csv")
    )
    print("Challenge examples:", len(frame))

    # 3. Load the already-trained model.
    model_dir = Path("models/intent_classifier_60k")
    tokenizer = load_tokenizer(str(model_dir))
    model = create_model(str(model_dir)).to(device)
    model.eval()

    # 4. Prepare batches of challenge messages.
    dataset = IntentDataset(frame)
    loader = DataLoader(
        dataset,
        batch_size=4,
        shuffle=False,
        collate_fn=create_collate_fn(tokenizer),
    )

    actual_ids = []
    predicted_ids = []

    # 5. Predict without training or updating model weights.
    with torch.no_grad():
        for batch in loader:
            inputs = {
                key: batch[key].to(device)
                for key in ("input_ids", "attention_mask")
            }

            outputs = model(**inputs)
            predictions = outputs.logits.argmax(dim=1)

            actual_ids.extend(batch["labels"].tolist())
            predicted_ids.extend(predictions.cpu().tolist())

    # 6. Calculate overall and per-intent accuracy.
    correct = sum(
        actual == predicted
        for actual, predicted in zip(actual_ids, predicted_ids)
    )
    accuracy = correct / len(actual_ids) if actual_ids else 0.0

    print(f"\nCorrect predictions: {correct}/{len(actual_ids)}")
    print(f"Challenge accuracy: {accuracy:.2%}")

    print("\nAccuracy by intent:")

    for intent_id, intent in enumerate(INTENTS):
        indices = [
            i for i, actual in enumerate(actual_ids)
            if actual == intent_id
        ]
        intent_correct = sum(
            predicted_ids[i] == intent_id for i in indices
        )
        intent_accuracy = (
            intent_correct / len(indices) if indices else 0.0
        )

        print(
            f"{intent}: {intent_correct}/{len(indices)} "
            f"({intent_accuracy:.2%})"
        )

    # 7. Show only the mistakes so they're easier to investigate.
    print("\nIncorrect predictions:")

    errors = 0
    for i, (actual, predicted) in enumerate(
        zip(actual_ids, predicted_ids)
    ):
        if actual != predicted:
            errors += 1
            print(f"\nMessage: {frame.iloc[i]['message']}")
            print(f"Actual: {INTENTS[actual]}")
            print(f"Predicted: {INTENTS[predicted]}")

    if errors == 0:
        print("No incorrect predictions on this challenge set.")


if __name__ == "__main__":
    main()
