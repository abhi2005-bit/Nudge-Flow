# NudgeFlow Intent Datasets

## 1. nudgeflow_intents_60k.csv

The main synthetic dataset for training the NudgeFlow customer intent
classifier.

- Total messages: 60,000
- Six intent classes
- 10,000 messages per intent
- CSV columns: `message`, `intent`

The intent classes are:

- `booking_enquiry`
- `purchase_enquiry`
- `service_enquiry`
- `complaint_support`
- `cancellation`
- `other_uncertain`

The current training workflow uses a group-aware split with approximately
60% training, 20% validation, and 20% test data.

## 2. nudgeflow_challenge_v1.csv

A separate collection of 60 synthetic messages, with 10 examples for
each intent. It is used to investigate how the model handles varied
wording and difficult intent distinctions.

This challenge set has already been used during development and should
not be treated as an independent benchmark.

## Important limitations

These datasets are synthetic and include template-generated wording.
They help develop and test the training pipeline but do not establish
accuracy on real customer conversations.

Before deploying the classifier, evaluate it on appropriately collected,
representative customer messages and review any privacy requirements.

Do not combine the challenge dataset with the training dataset.
