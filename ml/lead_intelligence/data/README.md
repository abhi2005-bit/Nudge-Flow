# Customer-message data

## Labeled CSV format

Provide a UTF-8 CSV with exactly these headers:

```csv
message,intent
"Can you reserve a table for Friday?",booking_enquiry
"How much does the starter plan cost?",purchase_enquiry
```

Each row is one short customer message and one label. `message` and `intent` must be non-empty. Labels are case-sensitive canonical IDs from the taxonomy in the project README. The loader trims surrounding whitespace, rejects unknown labels and conflicting labels on normalized duplicate text, and preserves message text for later model work.

Put a real labeled dataset at `data/customer_messages.csv`; CSV files in `data/` are Git-ignored. Use only data you are permitted to use. Remove names, phone numbers, email addresses, account numbers, addresses, and other personal or sensitive information before placing data in this workspace. Record annotation guidance and provenance separately; do not add secrets or private CRM data to Git.

## Synthetic development fixture

[`synthetic_dev.csv`](synthetic_dev.csv) contains only invented example messages for checking parsing, validation, duplicate grouping, splitting, and metric output structure. It is not collected from customers and must never be used to claim model quality or real-world performance. It is deliberately small and is not a training benchmark.
