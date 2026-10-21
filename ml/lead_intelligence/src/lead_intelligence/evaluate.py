"""Evaluate the saved NudgeFlow intent classifier."""

from pathlib import Path

import torch
from torch.utils.data import DataLoader

from lead_intelligence.data import read_labeled_messages
from lead_intelligence.dataset import IntentDataset, create_collate_fn
from lead_intelligence.model import create_model
from lead_intelligence.splitting import create_train_validation_test_split
from lead_intelligence.taxonomy import INTENTS
from lead_intelligence.tokenization import load_tokenizer


# 1. Select the device.
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print("Device:", device)

# 2. Load the data and recreate the same split.
frame = read_labeled_messages(Path("data/synthetic_dev.csv"))
splits = create_train_validation_test_split(frame)

test_frame = frame.iloc[splits["train"]].reset_index(drop=True)
print("Test examples:", len(test_frame))

# 3. Load the saved model and tokenizer.
model_dir = Path("models/intent_classifier")

tokenizer = load_tokenizer(str(model_dir))
model = create_model(str(model_dir)).to(device)
model.eval()

# 4. Prepare the test messages.
test_dataset = IntentDataset(test_frame)

test_loader = DataLoader(
    test_dataset,
    batch_size=4,
    shuffle=False,
    collate_fn=create_collate_fn(tokenizer),
)

# 5. Predict intents without training the model.
actual_ids = []
predicted_ids = []

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

# 6. Compare predictions with the correct labels.
correct = sum(
    actual == predicted
    for actual, predicted in zip(actual_ids, predicted_ids)
)

accuracy = correct / len(actual_ids)

print(f"\nCorrect predictions: {correct}/{len(actual_ids)}")
print(f"Test accuracy: {accuracy:.2%}")

print("\nIndividual predictions:")

for message, actual_id, predicted_id in zip(
    test_frame["message"],
    actual_ids,
    predicted_ids,
):
    actual_intent = INTENTS[actual_id]
    predicted_intent = INTENTS[predicted_id]

    status = "CORRECT" if actual_id == predicted_id else "INCORRECT"

    print(f"\nMessage: {message}")
    print(f"Actual: {actual_intent}")
    print(f"Predicted: {predicted_intent} — {status}")