"""Evaluate the bundled synthetic severity baseline without preprocessing leakage."""

from __future__ import annotations

import json
import hashlib
import platform
import sys
from pathlib import Path
import joblib
import sklearn

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split

from backend.ai.severity_model import DISCLAIMER, load_examples, new_pipeline


def main() -> None:
    rows = load_examples()
    messages, labels = [r["message"] for r in rows], [r["severity"] for r in rows]
    train_x, test_x, train_y, test_y = train_test_split(messages, labels, test_size=0.30, random_state=42, stratify=labels)
    model = new_pipeline().fit(train_x, train_y)
    prediction = model.predict(test_x)
    classes = ["LOW", "MODERATE", "HIGH"]
    report = {
        "training_source": "synthetic_demo",
        "notice": DISCLAIMER,
        "sample_count": len(rows),
        "training_count": len(train_x),
        "held_out_count": len(test_x),
        "split_seed": 42,
        "preprocessing": "TF-IDF fitted only on training split",
        "classes": classes,
        "classification_report": classification_report(test_y, prediction, labels=classes, output_dict=True, zero_division=0),
        "confusion_matrix": confusion_matrix(test_y, prediction, labels=classes).tolist(),
        "held_out_examples": [{"message": x, "expected": y, "predicted": str(p)} for x, y, p in zip(test_x, test_y, prediction)],
        "operational_validation": False,
    }
    output = PROJECT_ROOT / "data" / "severity_dataset" / "evaluation.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    # Serving is a separately fitted all-example artifact. Held-out metrics above
    # remain from the fold-safe 42/18 evaluation, never from this deployment fit.
    serving = new_pipeline().fit(messages, labels)
    artifact = PROJECT_ROOT / "models" / "severity_classifier" / "pipeline.joblib"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(serving, artifact)
    metadata = {"training_source": "synthetic_demo", "training_count": len(rows), "notice": DISCLAIMER,
                "operational_validation": False, "python_version": platform.python_version(), "sklearn_version": sklearn.__version__,
                "artifact": "models/severity_classifier/pipeline.joblib", "serving_mode": "validated_local_artifact",
                "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                "training_csv_sha256": hashlib.sha256((PROJECT_ROOT / "data/severity_dataset/synthetic_flood_messages.csv").read_bytes()).hexdigest(),
                "evaluation_note": "Held-out metrics use the separate training/test split; serving fits all bundled synthetic examples."}
    for destination in (artifact.with_name("metadata.json"), PROJECT_ROOT / "backend/ml_models/severity_model/manifest.json"):
        destination.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    vocabulary = serving.named_steps["tfidf"].vocabulary_
    (PROJECT_ROOT / "backend/ml_models/tokenizer/vocabulary.json").write_text(json.dumps(vocabulary, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "held_out_examples"}, indent=2))
    print(f"Saved evaluation to {output}")


if __name__ == "__main__":
    main()

