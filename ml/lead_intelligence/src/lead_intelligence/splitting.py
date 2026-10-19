"""Reproducible stratified splits with connected duplicate messages kept together."""

from collections import defaultdict

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.neighbors import NearestNeighbors

from lead_intelligence.data import normalize_message

DEFAULT_SEED = 42
DEFAULT_NEAR_DUPLICATE_THRESHOLD = 0.8


def near_duplicate_groups(
    messages: list[str] | pd.Series,
    *,
    similarity_threshold: float = DEFAULT_NEAR_DUPLICATE_THRESHOLD,
) -> np.ndarray:
    """Group normalized duplicates and close character n-gram text matches.

    Similarity is cosine similarity over character 2-5 gram TF-IDF vectors. Pairwise
    links are joined transitively, so a connected near-duplicate cluster stays intact.
    """
    if not 0 < similarity_threshold <= 1:
        raise ValueError("similarity_threshold must be in (0, 1]")

    normalized = [normalize_message(message) for message in messages]
    if not normalized or any(not message for message in normalized):
        raise ValueError("messages must be a nonempty collection of nonempty text")

    parent = list(range(len(normalized)))

    def find(item: int) -> int:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    by_text: dict[str, int] = {}
    for i, message in enumerate(normalized):
        if message in by_text:
            union(i, by_text[message])
        else:
            by_text[message] = i

    if similarity_threshold < 1 and len(normalized) > 1:
        vectors = TfidfVectorizer(
            analyzer="char", ngram_range=(2, 5), lowercase=False, norm="l2"
        ).fit_transform(normalized)
        neighbors = NearestNeighbors(
            metric="cosine",
            algorithm="brute",
            radius=np.nextafter(1 - similarity_threshold, np.inf),
            n_jobs=1,
        ).fit(vectors)
        graph = neighbors.radius_neighbors_graph(vectors, mode="connectivity")
        rows, columns = graph.nonzero()
        for left, right in zip(rows.tolist(), columns.tolist()):
            if left < right:
                union(left, right)

    root_to_group: dict[int, int] = {}
    groups = np.empty(len(normalized), dtype=np.int64)
    for i in range(len(normalized)):
        root = find(i)
        root_to_group.setdefault(root, len(root_to_group))
        groups[i] = root_to_group[root]
    return groups


def create_train_validation_test_split(
    frame: pd.DataFrame,
    *,
    seed: int = DEFAULT_SEED,
    similarity_threshold: float = DEFAULT_NEAR_DUPLICATE_THRESHOLD,
) -> dict[str, np.ndarray]:
    """Return row positions for approximate 60/20/20 stratified partitions.

    Five group-stratified folds reserve one fold (about 20%) for test. Four folds on
    the remaining rows reserve one fold (about 20% overall) for validation. Duplicate
    groups are never divided between partitions.
    """
    if not {"message", "intent"}.issubset(frame.columns) or frame.empty:
        raise ValueError("frame must be nonempty and contain message and intent columns")

    labels = frame["intent"].to_numpy(dtype=str)
    groups = near_duplicate_groups(
        frame["message"].astype(str).tolist(),
        similarity_threshold=similarity_threshold,
    )
    group_labels: dict[int, set[str]] = defaultdict(set)
    groups_per_intent: dict[str, set[int]] = defaultdict(set)
    for group, label in zip(groups.tolist(), labels.tolist()):
        group_labels[group].add(label)
        groups_per_intent[label].add(group)
    conflicts = [group for group, values in group_labels.items() if len(values) > 1]
    if conflicts:
        raise ValueError("Near-duplicate messages have conflicting intent labels")
    sparse_intents = sorted(label for label, values in groups_per_intent.items() if len(values) < 5)
    if sparse_intents:
        raise ValueError(
            "At least five independent message groups per intent are required for "
            f"the requested split; insufficient groups for: {sparse_intents}"
        )

    all_indices = np.arange(len(frame))
    outer = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=seed)
    train_validation, test = next(outer.split(all_indices, labels, groups))

    inner = StratifiedGroupKFold(n_splits=4, shuffle=True, random_state=seed)
    train_local, validation_local = next(
        inner.split(train_validation, labels[train_validation], groups[train_validation])
    )
    return {
        "train": np.sort(train_validation[train_local]),
        "validation": np.sort(train_validation[validation_local]),
        "test": np.sort(test),
    }
