"""A small, explicitly synthetic TF-IDF + logistic regression baseline.

The score is an uncalibrated classifier probability, not a flood-risk estimate.
Never use this demonstration model to dispatch teams without human review.
"""

from __future__ import annotations

import csv
import re
import json
import hashlib
import platform
import time
from functools import lru_cache
from pathlib import Path

import numpy as np
import joblib
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

DATASET = Path(__file__).resolve().parents[2] / "data" / "severity_dataset" / "synthetic_flood_messages.csv"
DISCLAIMER = "Synthetic training examples; uncalibrated demonstration score; admin verification required."
_model_info = {"serving_mode":"in_memory_training","artifact_status":"not_loaded"}
DANGER_PATTERNS = (
    r"\b(trapped|drowning|unconscious|electrocution|swept away|cannot breathe|can't breathe)\b",
    r"\b(urgent rescue|need rescue|needs rescue|need rescuing|rescue immediately|bleeding heavily)\b",
    r"കുടുങ്ങ|രക്ഷിക്ക|മുങ്ങിക്കൊണ്ട|ശ്വാസം കിട്ടുന്നില്ല|ബോധമില്ല|വൈദ്യുതാഘാത",
)


def affirmative_danger(message: str) -> tuple[bool, list[str]]:
    """Scope negation to clauses; retain a current danger in a mixed report.

    This is a conservative text rule, not a clinical or historical inference.
    Unknown/ambiguous statements remain subject to human verification.
    """
    evidence = []
    clauses = re.split(r"[.!?;,\n]|\b(?:but|however|although|and)\b|എന്നാൽ|പക്ഷേ", message.casefold())
    for clause in clauses:
        for pattern in DANGER_PATTERNS:
            for match in re.finditer(pattern, clause):
                before = clause[max(0, match.start() - 55):match.start()]
                after = clause[match.end():match.end() + 45]
                # 'cannot breathe' is itself an affirmative danger expression.
                negated = bool(re.search(r"\b(?:not|never|without)\s+(?:(?:currently|still|actually|now|any longer)\s+)?$",before))
                negated |= bool(re.search(r"\b(?:nobody|no one|none)\s+(?:(?:is|are|was|were|remains?)\s+)?$",before))
                negated |= bool(re.search(r"\bno\s+(?:children|people|residents|persons?|members|adults)\s+(?:(?:is|are|was|were)\s+)?$",before))
                negated |= bool(re.search(r"^\s*(?:is |are |was |were )?(?:not|no longer)\b|^.{0,20}(?:ഇല്ല|ില്ല|അല്ല)", after))
                negated |= bool(re.search(r"\bno\s+(?:urgent\s+)?$", before))
                resolved = bool(re.search(r"\b(?:yesterday|last (?:week|month|year|night)|previously|were rescued|has been rescued|have been rescued)\b|ഇന്നലെ|നേരത്തെ|മുൻപ്", clause)) and not bool(re.search(r"\b(?:still|now|currently|again|today)\b|ഇപ്പോൾ|ഇപ്പോഴും", clause[match.start():]))
                if not negated and not resolved:
                    evidence.append(match.group())
    return bool(evidence), evidence


def load_examples() -> list[dict]:
    with DATASET.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or any(row["severity"] not in {"LOW", "MODERATE", "HIGH"} for row in rows):
        raise ValueError("Severity training CSV has invalid labels")
    if any(row.get("source") != "synthetic_demo" for row in rows):
        raise ValueError("This demo model expects explicitly labeled synthetic examples")
    return rows


def new_pipeline() -> Pipeline:
    return Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)),
        ("classifier", LogisticRegression(max_iter=1000, class_weight="balanced", C=4.0, random_state=42)),
    ])


@lru_cache(maxsize=1)
def get_model() -> Pipeline:
    root = Path(__file__).resolve().parents[2]
    artifact = root / "models/severity_classifier/pipeline.joblib"
    metadata = root / "models/severity_classifier/metadata.json"
    try:
        info = json.loads(metadata.read_text(encoding="utf-8"))
        compatible = (info.get("sklearn_version") == sklearn.__version__
                      and info.get("python_version", "").split(".")[:2] == platform.python_version().split(".")[:2]
                      and info.get("training_source") == "synthetic_demo"
                      and info.get("training_csv_sha256") == hashlib.sha256(DATASET.read_bytes()).hexdigest()
                      and info.get("artifact_sha256") == hashlib.sha256(artifact.read_bytes()).hexdigest())
        if not compatible: raise ValueError("Artifact metadata/hash mismatch")
        # Fixed, trusted project artifact only. Arbitrary uploaded pickle paths
        # are never accepted. Metadata is checked before deserialization.
        model = joblib.load(artifact)
        if not isinstance(model,Pipeline) or set(model.named_steps) != {"tfidf","classifier"} or set(model.classes_) != {"LOW","MODERATE","HIGH"}:
            raise ValueError("Unexpected classifier artifact")
        _model_info.update(serving_mode="validated_local_artifact",artifact_status="validated",training_count=info.get("training_count"))
        return model
    except Exception:
        _model_info.update(serving_mode="in_memory_training",artifact_status="missing_or_incompatible")
    rows = load_examples()
    return new_pipeline().fit([r["message"] for r in rows], [r["severity"] for r in rows])


def predict_severity(message: str) -> dict:
    model = get_model()
    features = model.named_steps["tfidf"].transform([message])
    probabilities = model.predict_proba([message])[0]
    predicted = str(model.classes_[int(np.argmax(probabilities))])
    confidence = round(float(max(probabilities)), 4)
    recognized = features.nnz > 0
    danger, evidence = affirmative_danger(message)
    # Unknown vocabulary and untranslated languages must never imply low urgency.
    severity = "HIGH" if danger else (predicted if recognized else "MODERATE")
    negated_or_historical = not danger and any(re.search(pattern,message.casefold()) for pattern in DANGER_PATTERNS)
    if negated_or_historical and predicted == "HIGH":
        # The tiny baseline was not trained to understand negation. Ambiguous
        # negative/historical danger requires review, not an affirmative rule.
        severity = "MODERATE"
    return {
        "severity": severity,
        # A rule has no calibrated class probability. Never pair a LOW baseline
        # probability with a rule-escalated HIGH label.
        "confidence": confidence if recognized and severity == predicted and not danger else None,
        "baseline_confidence": confidence if recognized else None,
        "baseline_severity": predicted if recognized else "UNKNOWN",
        "danger_flag": danger,
        "danger_evidence": evidence,
        "confidence_kind": "uncalibrated_synthetic_classifier_probability",
        "severity_source": "conservative_danger_escalation" if danger else "negated_or_historical_danger_review" if negated_or_historical and predicted == "HIGH" else "synthetic_tfidf_logistic_regression",
        "model_notice": DISCLAIMER,
        "vocabulary_recognized": recognized,
        "model_serving_mode": _model_info["serving_mode"],
        "artifact_status": _model_info["artifact_status"],
    }


async def classify_report(message: str) -> dict:
    """Shared helper: Malayalam receives the same translation-first classifier.

    Failure keeps a clearly labelled provisional original-language prediction;
    it cannot invent a successful translation or a calibrated score.
    """
    result = predict_severity(message)
    result.update(severity_input="original_message",translation_status="not_required")
    if not re.search(r"[\u0D00-\u0D7F]",message): return result
    from .agent import _extract_chunks
    from backend.config import settings
    try:
        translated = await _extract_chunks({"message":message,"deadline":time.monotonic()+settings.ai_timeout_seconds})
        prediction = predict_severity(translated)
        if result["danger_flag"] and not prediction["danger_flag"]:
            prediction.update(severity="HIGH",danger_flag=True,confidence=None,severity_source="conservative_danger_escalation",danger_evidence=result["danger_evidence"])
        prediction.update(english_translation=translated,severity_input="english_translation",translation_status="completed")
        return prediction
    except Exception as error:
        result.update(translation_status="unavailable",error_code=type(error).__name__,admin_verification_required=True)
        return result

