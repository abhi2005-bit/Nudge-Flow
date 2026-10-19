from pathlib import Path

import pandas as pd
import pytest

from lead_intelligence.data import read_labeled_messages
from lead_intelligence.taxonomy import INTENTS

SYNTHETIC_FIXTURE = Path(__file__).parents[1] / "data" / "synthetic_dev.csv"


def test_synthetic_fixture_loads_with_all_intents() -> None:
    frame = read_labeled_messages(SYNTHETIC_FIXTURE)
    assert set(frame["intent"]) == set(INTENTS)
    assert frame["message"].str.len().gt(0).all()


def test_loader_rejects_unsupported_label(tmp_path: Path) -> None:
    path = tmp_path / "invalid.csv"
    pd.DataFrame({"message": ["A synthetic message"], "intent": ["unknown"]}).to_csv(path, index=False)
    with pytest.raises(ValueError, match="Unknown intent"):
        read_labeled_messages(path)


def test_loader_rejects_conflicting_normalized_duplicates(tmp_path: Path) -> None:
    path = tmp_path / "conflict.csv"
    pd.DataFrame(
        {
            "message": ["Please cancel my booking!", " please  cancel my booking "],
            "intent": ["cancellation", "booking_enquiry"],
        }
    ).to_csv(path, index=False)
    with pytest.raises(ValueError, match="conflicting"):
        read_labeled_messages(path)
