# NudgeFlow AI: customer-message intent experiment

This isolated Python 3.11 workspace prepares a text-classification experiment. It does not change the production backend. Real customer messages are not included. The only included messages are clearly marked synthetic examples used for pipeline tests; they say nothing about customer behavior or model performance.

## Intent taxonomy

Use one canonical label per message:

| Label | Meaning |
| --- | --- |
| `booking_enquiry` | Asking to make, check, or arrange a booking, reservation, or appointment. |
| `purchase_enquiry` | Asking about price, product availability, or how to buy/order. |
| `service_enquiry` | Asking about a service, repair, installation, maintenance, or service appointment. |
| `complaint_support` | Reporting a problem or dissatisfaction, or asking for help with an existing account/order/product. |
| `cancellation` | Explicitly asking to cancel or stop an order, booking, subscription, or service. |
| `other_uncertain` | Out-of-scope, unclear, or insufficiently specific messages. |

Prefer the customer's main request. Use `cancellation` for an explicit cancellation even when it concerns a booking or purchase. Use `complaint_support` for a problem with an existing service/order rather than a new service enquiry. Reserve `other_uncertain` for genuinely ambiguous or out-of-scope text; document annotation decisions for borderline cases.

## Data format and loading

The expected UTF-8 CSV has exactly two columns, `message,intent`. See [data/README.md](data/README.md) for details and the privacy boundary. A real labeled file may be placed at `data/customer_messages.csv` (CSV files in `data/` are ignored by Git). The loader validates headers, non-empty values, supported labels, and conflicting normalized duplicates. Run an inspection with:

```powershell
Set-Location C:\Nudge-Flow\ml\lead_intelligence
uv run python -m lead_intelligence.inspect_data --csv .\data\customer_messages.csv
```

Without a real file, inspect the test-only fixture:

```powershell
uv run python -m lead_intelligence.inspect_data
```

`data/synthetic_dev.csv` is entirely synthetic, small, and for tests only. Never report its metrics as real-world or customer performance.

## Leakage-aware reproducible split

`lead_intelligence.splitting.create_train_validation_test_split` returns row positions for approximate 60/20/20 train, validation, and test partitions. It groups normalized exact duplicates and near-duplicates before splitting. Near-duplicate detection uses cosine similarity over character 2–5 gram TF-IDF vectors, with a default threshold of `0.8`; links are joined transitively. Conflicting labels within a duplicate group are rejected.

`StratifiedGroupKFold` with seed `42` creates the held-out test fold, then validation from the remaining data. Grouped splits avoid putting duplicate or near-duplicate messages into different partitions; the ratios and class balance are approximate when groups have different sizes. The helper requires at least five independent text groups for each intent. Preserve the exact CSV row order and record its checksum, seed, threshold, and returned indices to reproduce a split. Do not tune this threshold based on test metrics.

Fit any tokenizer vocabulary, normalization learned from data, or other preprocessing only on training messages. Use validation data for model and decision-rule choices. Keep the test partition untouched until final evaluation.

## Model and evaluation work

PyTorch and Hugging Face Transformers are available in the isolated `uv` project. This scaffold does not implement a tokenizer pipeline, neural network, loss, optimizer, training loop, or fine-tuning logic. Start your implementation in `src/lead_intelligence/model.py`; the training entry point `train.py` is also a placeholder.

`evaluation.evaluate_intents` provides macro-F1, per-class precision and recall, and a confusion matrix in the fixed taxonomy order. `write_json_report` can save those results under `reports/`. Compare against a simple baseline as a future learning/evaluation goal; its implementation is left to you. No metrics are included in this scaffold.

## Setup and checks

From `C:\Nudge-Flow\ml\lead_intelligence`:

```powershell
uv sync --group dev
uv run pytest
uv run python -m lead_intelligence.inspect_data
```

This reuses the workspace's isolated `.venv` and `uv.lock`. Production dependencies remain separate.
