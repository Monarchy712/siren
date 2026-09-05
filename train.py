"""Fit the Logistic Regression and save it (SPEC section 5).

    python train.py

Uses the tiny semi-synthetic dataset in data/training_data.py. HONEST framing
(SPEC section 0): this does NOT establish real-world fraud accuracy -- it fits
inspectable coefficients that turn the 7 features into an explainable risk_score.
"""
from __future__ import annotations

import os
import sys

_SIREN_ROOT = os.path.dirname(os.path.abspath(__file__))
if _SIREN_ROOT not in sys.path:
    sys.path.insert(0, _SIREN_ROOT)

import numpy as np
from sklearn.linear_model import LogisticRegression

from data.training_data import build_dataset
from engine.features import FEATURE_NAMES
from engine.model import MODEL_PATH, RiskModel


def main() -> int:
    X, y = build_dataset()
    Xa, ya = np.asarray(X, dtype=float), np.asarray(y, dtype=int)

    clf = LogisticRegression(max_iter=1000, C=4.0)
    clf.fit(Xa, ya)

    model = RiskModel(clf)
    model.save(MODEL_PATH)

    train_acc = clf.score(Xa, ya)
    print(f"Trained LR on {len(y)} semi-synthetic samples "
          f"({sum(y)} risky / {len(y) - sum(y)} safe).")
    print(f"Model saved -> {MODEL_PATH}")
    print(f"Train-set accuracy (sanity only, NOT a fraud-accuracy claim): {train_acc:.3f}")
    print("\nLearned coefficients (inspectable, contestable hypothesis):")
    for name, coef in sorted(model.coefficients().items(), key=lambda kv: -abs(kv[1])):
        print(f"  {name:<22} {coef:+.3f}")
    print(f"  {'(intercept)':<22} {clf.intercept_[0]:+.3f}")
    assert list(model.coefficients().keys()) == FEATURE_NAMES
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
