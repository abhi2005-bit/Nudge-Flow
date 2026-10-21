"""Evaluate the NudgeFlow intent classifier on the validation set."""

from pathlib import Path

import torch
from torch.utils.data import DataLoader

from lead_intelligence.data import read_labeled_messages
from lead_intelligence.dataset import IntentDataset, create_collate_fn
from lead_intelligence.model import create_model
from lead_intelligence.splitting import create_train_validation_test_split
from lead_intelligence.taxonomy import INTENTS
from lead_intelligence.tokenization import load_tokenizer


# File paths
DATA_PATH = Path("data/nudgeflow_intents_60k.csv")
MODEL_DIR = Path("models/intent_classifier_60k")

# Evaluation settings
BATCH_SIZE = 4
MAX_ERRORS_TO_PRINT = 20


def main():
    # 1. Select GPU if available; otherwise, use CPU.
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("Device:", device)

    # 2. Load the dataset and recreate the same splits used during training.
    print("Loading dataset...")

    frame = read_labeled_messages(DATA_PATH)
    splits = create_train_validation_test_split(frame)

    test_frame = frame.iloc[
        splits["test"]
    ].reset_index(drop=True)

    if test_frame.empty:
        raise ValueError("The test dataset must not be empty.")

    print("Test examples:", len(test_frame))

    # 3. Load the newly trained model and its tokenizer.
    if not MODEL_DIR.exists():
        raise FileNotFoundError(
            f"Trained model not found: {MODEL_DIR.resolve()}"
        )

    print("Loading trained model...")

    tokenizer = load_tokenizer(str(MODEL_DIR))
    model = create_model(str(MODEL_DIR)).to(device)
    model.eval()

    # 4. Prepare batches of test messages.
    test_dataset = IntentDataset(test_frame)

    test_loader = DataLoader(
        test_dataset,
        batch_size=BATCH_SIZE,
        shuffle=False,
        collate_fn=create_collate_fn(tokenizer),
    )

    # 5. Predict intents without updating model weights.
    actual_ids = []
    predicted_ids = []

    print("Evaluating model...")

    with torch.no_grad():
        for batch in test_loader:
            inputs = {
                key: batch[key].to(device)
                for key in ("input_ids", "attention_mask")
            }

            outputs = model(**inputs)
            predictions = outputs.logits.argmax(dim=1)

            actual_ids.extend(batch["labels"].tolist())
            predicted_ids.extend(predictions.cpu().tolist())

    # 6. Calculate overall accuracy.
    correct = sum(
        actual == predicted
        for actual, predicted in zip(actual_ids, predicted_ids)
    )

    total = len(actual_ids)
    accuracy = correct / total if total else 0.0

    print("\n========== TEST RESULTS ==========")
    print(f"Correct predictions: {correct}/{total}")
    print(f"Incorrect predictions: {total - correct}/{total}")
    print(f"Test accuracy: {accuracy:.2%}")

    # 7. Calculate accuracy for each intent.
    print("\n========== ACCURACY BY INTENT ==========")

    for intent_id, intent in enumerate(INTENTS):
        indices = [
            i
            for i, actual in enumerate(actual_ids)
            if actual == intent_id
        ]

        intent_correct = sum(
            predicted_ids[i] == intent_id
            for i in indices
        )

        intent_total = len(indices)
        intent_accuracy = (
            intent_correct / intent_total
            if intent_total
            else 0.0
        )

        print(
            f"{intent}: {intent_correct}/{intent_total} "
            f"({intent_accuracy:.2%})"
        )

    # 8. Display a limited number of incorrect predictions.
    print("\n========== INCORRECT PREDICTIONS ==========")

    errors = 0

    for i, (actual, predicted) in enumerate(
        zip(actual_ids, predicted_ids)
    ):
        if actual == predicted:
            continue

        if errors >= MAX_ERRORS_TO_PRINT:
            break

        message = test_frame.iloc[i]["message"]

        print(f"\nMessage: {message}")
        print(f"Actual: {INTENTS[actual]}")
        print(f"Predicted: {INTENTS[predicted]}")

        errors += 1

    if errors == 0:
        print("No incorrect predictions!")

    total_errors = total - correct

    if total_errors > errors:
        print(
            f"\nShowing {errors} of {total_errors} incorrect predictions."
        )

    print("\nEvaluation complete.")


if __name__ == "__main__":
    main()