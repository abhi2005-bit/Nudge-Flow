
"""Train the NudgeFlow customer intent classifier."""

from pathlib import Path

import torch
from torch.utils.data import DataLoader

from lead_intelligence.data import read_labeled_messages
from lead_intelligence.dataset import IntentDataset, create_collate_fn
from lead_intelligence.model import create_model
from lead_intelligence.splitting import create_train_validation_test_split
from lead_intelligence.tokenization import load_tokenizer


# Training settings
EPOCHS = 1
BATCH_SIZE = 4
LEARNING_RATE = 2e-5
LOG_EVERY = 500

# Dataset and model output paths
DATA_PATH = Path("data/nudgeflow_intents_60k.csv")
OUTPUT_DIR = Path("models/intent_classifier_60k")


def main():
    # 1. Select the GPU if available; otherwise, use the CPU.
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("Device:", device)

    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"Dataset not found: {DATA_PATH.resolve()}"
        )

    # 2. Load the dataset and create the train/validation/test split.
    print("Loading dataset and creating splits...")

    frame = read_labeled_messages(DATA_PATH)
    splits = create_train_validation_test_split(frame)

    train_frame = frame.iloc[splits["train"]].reset_index(drop=True)

    if train_frame.empty:
        raise ValueError("The training dataset must not be empty.")

    print("Total messages:", len(frame))
    print("Training examples:", len(train_frame))
    print("Validation examples:", len(splits["validation"]))
    print("Test examples:", len(splits["test"]))

    # 3. Prepare the tokenizer and training dataset.
    print("Loading tokenizer...")

    tokenizer = load_tokenizer()
    dataset = IntentDataset(train_frame)

    train_loader = DataLoader(
        dataset,
        batch_size=BATCH_SIZE,
        shuffle=True,
        collate_fn=create_collate_fn(tokenizer),
    )

    print("Training batches per epoch:", len(train_loader))

    # 4. Load the pretrained model and create the optimizer.
    print("Loading pretrained model...")

    model = create_model().to(device)

    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=LEARNING_RATE,
    )

    # 5. Train the model.
    for epoch in range(EPOCHS):
        model.train()

        total_loss = 0.0
        total_examples = 0

        print(f"\nStarting epoch {epoch + 1}/{EPOCHS}...")

        for batch_number, batch in enumerate(train_loader, start=1):
            # Move the input tensors and labels to the selected device.
            batch = {
                key: batch[key].to(device)
                for key in ("input_ids", "attention_mask", "labels")
            }

            # Clear gradients from the previous batch.
            optimizer.zero_grad(set_to_none=True)

            # Forward pass: calculate predictions and loss.
            outputs = model(**batch)
            loss = outputs.loss

            # Backpropagation: calculate gradients.
            loss.backward()

            # Update the model weights.
            optimizer.step()

            # Track loss weighted by the number of examples in this batch.
            batch_size = batch["labels"].size(0)
            total_loss += loss.item() * batch_size
            total_examples += batch_size

            # Print progress periodically.
            if (
                batch_number % LOG_EVERY == 0
                or batch_number == len(train_loader)
            ):
                running_loss = total_loss / total_examples

                print(
                    f"Epoch {epoch + 1}/{EPOCHS} "
                    f"| Batch {batch_number}/{len(train_loader)} "
                    f"| Running average loss: {running_loss:.4f}",
                    flush=True,
                )

        average_loss = total_loss / total_examples

        print(
            f"Epoch {epoch + 1}/{EPOCHS} complete "
            f"| Average training loss: {average_loss:.4f}"
        )

    print("\nTraining complete!")

    # 6. Save this model separately from the previous model.
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)

    print(f"Model and tokenizer saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
