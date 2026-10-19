"""Inspect schema and label balance for a labeled customer-message CSV."""

import argparse
from pathlib import Path

from lead_intelligence.data import read_labeled_messages


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("data/synthetic_dev.csv"),
        help="Path to a labeled message CSV (default: synthetic development fixture)",
    )
    args = parser.parse_args()

    frame = read_labeled_messages(args.csv)
    print(f"Rows: {len(frame):,}")
    print("Intent counts:")
    for intent, count in frame["intent"].value_counts().sort_index().items():
        print(f"  {intent}: {count:,}")


if __name__ == "__main__":
    main()
