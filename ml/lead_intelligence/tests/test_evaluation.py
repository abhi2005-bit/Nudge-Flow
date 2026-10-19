import numpy as np
import pytest

from lead_intelligence.evaluation import evaluate_intents
from lead_intelligence.taxonomy import INTENTS


def test_evaluation_returns_requested_report_fields() -> None:
    # Fixed test values verify report shape only; these are not model results.
    labels = np.asarray(INTENTS)
    report = evaluate_intents(labels, labels)

    assert report["sample_count"] == len(INTENTS)
    assert report["macro_f1"] == 1.0
    assert set(report["per_class"]) == set(INTENTS)
    assert all(set(scores) == {"precision", "recall"} for scores in report["per_class"].values())
    assert report["confusion_matrix"]["labels"] == list(INTENTS)
    assert len(report["confusion_matrix"]["counts"]) == len(INTENTS)


@pytest.mark.parametrize(
    ("truth", "prediction", "message"),
    [
        (np.asarray([]), np.asarray([]), "nonzero length"),
        (np.asarray(["booking_enquiry"]), np.asarray([]), "same nonzero length"),
        (
            np.asarray([["booking_enquiry"]]),
            np.asarray([["booking_enquiry"]]),
            "one-dimensional",
        ),
        (np.asarray(["not_an_intent"]), np.asarray(["booking_enquiry"]), "Unknown intent"),
    ],
)
def test_evaluation_rejects_invalid_inputs(truth, prediction, message) -> None:
    with pytest.raises(ValueError, match=message):
        evaluate_intents(truth, prediction)
