"""Tokenization utilities for customer intent classification."""

from collections.abc import Sequence

from transformers import AutoTokenizer

from lead_intelligence.model import DEFAULT_MODEL_NAME


def load_tokenizer(model_name: str = DEFAULT_MODEL_NAME, *, local_files_only: bool = False):
    """Load the tokenizer associated with a pretrained model."""
    if local_files_only:
        return AutoTokenizer.from_pretrained(model_name, local_files_only=True)
    return AutoTokenizer.from_pretrained(model_name)


def tokenize_messages(
    tokenizer,
    messages: Sequence[str],
    max_length: int = 128,
):
    """Convert a batch of customer messages into model inputs."""

    if not messages:
        raise ValueError("At least one message is required.")

    if any(not isinstance(message, str) or not message.strip()
           for message in messages):
        raise ValueError("Messages must be non-empty strings.")

    if max_length < 1:
        raise ValueError("max_length must be greater than zero.")

    return tokenizer(
        list(messages),
        padding=True,
        truncation=True,
        max_length=max_length,
        return_tensors="pt",
    )
