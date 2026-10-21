"""Pretrained Transformer model for customer intent classification."""

from transformers import AutoModelForSequenceClassification

from lead_intelligence.taxonomy import INTENTS


DEFAULT_MODEL_NAME = "distilbert/distilbert-base-uncased"


def create_model(model_name: str = DEFAULT_MODEL_NAME):
    """Load a pretrained Transformer with a six-class intent head."""

    # Convert intent names into integer IDs.
    label2id = {
        intent: index
        for index, intent in enumerate(INTENTS)
    }

    # Convert integer IDs back into intent names.
    id2label = {
        index: intent
        for index, intent in enumerate(INTENTS)
    }

    # Load the pretrained Transformer with our six-class classifier.
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=len(INTENTS),
        label2id=label2id,
        id2label=id2label,
    )

    return model