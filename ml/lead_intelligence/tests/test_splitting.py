from pathlib import Path

import numpy as np
import pandas as pd

from lead_intelligence.data import read_labeled_messages
from lead_intelligence.splitting import (
    create_train_validation_test_split,
    near_duplicate_groups,
)
from lead_intelligence.taxonomy import INTENTS

SYNTHETIC_FIXTURE = Path(__file__).parents[1] / "data" / "synthetic_dev.csv"


def test_near_duplicate_texts_share_a_group() -> None:
    groups = near_duplicate_groups(
        [
            "I need help with a damaged order",
            "I need help with my damaged order",
            "Can you reserve a table for Friday?",
        ]
    )
    assert groups[0] == groups[1]
    assert groups[0] != groups[2]


def test_split_is_reproducible_and_never_splits_duplicate_groups() -> None:
    frame = read_labeled_messages(SYNTHETIC_FIXTURE)
    first = create_train_validation_test_split(frame, seed=42)
    second = create_train_validation_test_split(frame, seed=42)

    assert all(np.array_equal(first[name], second[name]) for name in first)
    assert sorted(np.concatenate(list(first.values())).tolist()) == list(range(len(frame)))

    groups = near_duplicate_groups(frame["message"].tolist())
    group_partitions = [set(groups[indices]) for indices in first.values()]
    assert group_partitions[0].isdisjoint(group_partitions[1])
    assert group_partitions[0].isdisjoint(group_partitions[2])
    assert group_partitions[1].isdisjoint(group_partitions[2])

    for indices in first.values():
        assert set(frame.iloc[indices]["intent"]) == set(INTENTS)
