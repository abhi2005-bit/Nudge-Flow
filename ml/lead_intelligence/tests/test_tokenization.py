import pytest

import lead_intelligence.tokenization as tokenization_module


class FakeTokenizer:
    def __call__(self, messages, **kwargs):
        return {
            "messages": messages,
            "options": kwargs,
        }


def test_tokenize_messages_uses_expected_options():
    tokenizer = FakeTokenizer()

    result = tokenization_module.tokenize_messages(
        tokenizer,
        ["Can I book a slot?", "I need a repair."],
    )

    assert len(result["messages"]) == 2
    assert result["options"]["padding"] is True
    assert result["options"]["truncation"] is True
    assert result["options"]["max_length"] == 128
    assert result["options"]["return_tensors"] == "pt"


def test_tokenize_messages_rejects_empty_batch():
    with pytest.raises(ValueError):
        tokenization_module.tokenize_messages(FakeTokenizer(), [])


def test_tokenize_messages_rejects_blank_message():
    with pytest.raises(ValueError):
        tokenization_module.tokenize_messages(
            FakeTokenizer(),
            ["Can I book a slot?", "   "],
        )


def test_tokenize_messages_rejects_invalid_max_length():
    with pytest.raises(ValueError):
        tokenization_module.tokenize_messages(
            FakeTokenizer(),
            ["Hello"],
            max_length=0,
        )


def test_load_tokenizer_uses_default_model(monkeypatch):
    expected_tokenizer = object()
    captured = {}

    def fake_from_pretrained(model_name):
        captured["model_name"] = model_name
        return expected_tokenizer

    monkeypatch.setattr(
        tokenization_module.AutoTokenizer,
        "from_pretrained",
        fake_from_pretrained,
    )

    result = tokenization_module.load_tokenizer()

    assert result is expected_tokenizer
    assert captured["model_name"] == tokenization_module.DEFAULT_MODEL_NAME