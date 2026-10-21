import lead_intelligence.model as model_module
from lead_intelligence.taxonomy import INTENTS


def test_create_model_configures_intent_labels(monkeypatch):
    captured = {}
    expected_model = object()

    def fake_from_pretrained(model_name, **kwargs):
        captured["model_name"] = model_name
        captured.update(kwargs)
        return expected_model

    monkeypatch.setattr(
        model_module.AutoModelForSequenceClassification,
        "from_pretrained",
        fake_from_pretrained,
    )

    model = model_module.create_model()

    assert model is expected_model
    assert captured["model_name"] == model_module.DEFAULT_MODEL_NAME
    assert captured["num_labels"] == len(INTENTS)
    assert captured["label2id"] == {
        intent: index
        for index, intent in enumerate(INTENTS)
    }
    assert captured["id2label"] == {
        index: intent
        for index, intent in enumerate(INTENTS)
    }