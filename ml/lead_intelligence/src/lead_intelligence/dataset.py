"""PyTorch dataset and batch preparation for intent classification."""

import pandas as pd
import torch
from torch.utils.data import Dataset

from lead_intelligence.taxonomy import INTENTS
from lead_intelligence.tokenization import tokenize_messages


INTENT_TO_ID = {
    intent: index
    for index, intent in enumerate(INTENTS)
}


class IntentDataset(Dataset):
    """Store customer messages and their encoded intent labels."""

    def __init__(self, frame: pd.DataFrame):
        required_columns = {"message", "intent"}

        if not required_columns.issubset(frame.columns):
            raise ValueError(
                "Dataset must contain message and intent columns."
            )

        if frame.empty:
            raise ValueError("Dataset must not be empty.")

        self.messages = frame["message"].astype(str).str.strip().tolist()
        intents = frame["intent"].astype(str).str.strip().tolist()

        if any(not message for message in self.messages):
            raise ValueError("Messages must not be empty.")

        unknown_intents = set(intents) - set(INTENT_TO_ID)

        if unknown_intents:
            raise ValueError(
                f"Unknown intent labels: {sorted(unknown_intents)}"
            )

        self.labels = [
            INTENT_TO_ID[intent]
            for intent in intents
        ]

    def __len__(self):
        """Return the number of examples."""
        return len(self.messages)

    def __getitem__(self, index):
        """Return one message and its numeric label."""
        return {
            "message": self.messages[index],
            "label": self.labels[index],
        }


def create_collate_fn(tokenizer, max_length: int = 128):
    """Create a function that prepares one batch for the model."""

    if max_length < 1:
        raise ValueError("max_length must be greater than zero.")

    def collate_batch(examples):
        messages = [
            example["message"]
            for example in examples
        ]

        labels = torch.tensor(
            [example["label"] for example in examples],
            dtype=torch.long,
        )

        batch = tokenize_messages(
            tokenizer,
            messages,
            max_length=max_length,
        )

        batch["labels"] = labels
        return batch

    return collate_batch