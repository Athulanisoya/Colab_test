# Demonstration severity data

Every row is an invented English flood scenario labeled `synthetic_demo`. These are neither real Kerala reports nor operationally reviewed urgency labels. The balanced 60-row dataset demonstrates TF-IDF and logistic regression; it does not establish real-world accuracy, multilingual coverage, fairness, or calibrated risk.

`python scripts/train_severity.py` evaluates a stratified held-out split with training-only vectorization and writes per-class precision, recall and F1 plus the confusion matrix. The running service fits the same pipeline on these examples and reports its uncalibrated score explicitly. A conservative danger phrase flag can escalate urgency to HIGH. Unrecognized vocabulary defaults to MODERATE for review. The admin always makes the operational decision.

For deployment, collect consented representative reports, have qualified reviewers define and annotate urgency, hold out incidents and locations to prevent leakage, evaluate Malayalam separately, calibrate scores, and perform operational validation before replacing this demonstration model.

