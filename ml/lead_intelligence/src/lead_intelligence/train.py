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
EPOCHS = 3
BATCH_SIZE = 4
LEARNING_RATE = 2e-5


# 1. Select GPU if available, otherwise use CPU.
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print("Device:", device)


# 2. Load the dataset and select the training examples.
frame = read_labeled_messages(Path("data/synthetic_dev.csv"))
splits = create_train_validation_test_split(frame)

train_frame = frame.iloc[splits["train"]].reset_index(drop=True)

print("Training examples:", len(train_frame))


# 3. Prepare the tokenizer and dataset.
tokenizer = load_tokenizer()

dataset = IntentDataset(train_frame)

train_loader = DataLoader(
    dataset,
    batch_size=BATCH_SIZE,
    shuffle=True,
    collate_fn=create_collate_fn(tokenizer),
)


# 4. Load the model and create the optimizer.
model = create_model().to(device)

optimizer = torch.optim.AdamW(
    model.parameters(),
    lr=LEARNING_RATE,
)


# 5. Train the model.
for epoch in range(EPOCHS):
    model.train()

    total_loss = 0.0

    for batch in train_loader:

        # Move the inputs and labels to the selected device.
        batch = {
            key: batch[key].to(device)
            for key in ("input_ids", "attention_mask", "labels")
        }

        # Clear gradients from the previous training step.
        optimizer.zero_grad()

        # Forward pass: calculate predictions and loss.
        outputs = model(**batch)
        loss = outputs.loss

        # Backpropagation: calculate gradients.
        loss.backward()

        # Update the model's weights.
        optimizer.step()

        total_loss += loss.item()

    average_loss = total_loss / len(train_loader)

    print(
        f"Epoch {epoch + 1}/{EPOCHS} "
        f"| Average training loss: {average_loss:.4f}"
    )

print("Training complete!")

# Save the trained model and tokenizer.
output_dir = Path("models/intent_classifier")

model.save_pretrained(output_dir)
tokenizer.save_pretrained(output_dir)

print(f"Model and tokenizer saved to: {output_dir}")