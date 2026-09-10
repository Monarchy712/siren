"""Logistic Regression wrapper (SPEC section 5).

The trained LR maps the 8-feature vector -> one risk_score in [0,1]. LR is chosen
deliberately: tiny semi-synthetic dataset, explainability is the product
(coefficients -> reasons), decision-support not ML research.

This module only wraps persistence + inference. Fitting lives in train.py.
"""
from __future__ import annotations

import os

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression

from engine.features import FEATURE_NAMES

MODEL_PATH = os.path.join(os.path.dirname(__file__), "model.joblib")


class RiskModel:
    def __init__(self, clf: LogisticRegression):
        self.clf = clf

    # --- inference ----------------------------------------------------------
    def risk_score(self, vector: list[float]) -> float:
        """P(risky) for one feature vector, as a plain float in [0,1]."""
        X = np.asarray(vector, dtype=float).reshape(1, -1)
        return float(self.clf.predict_proba(X)[0, 1])

    def coefficients(self) -> dict[str, float]:
        """Feature -> coefficient. The inspectable, contestable hypothesis."""
        return dict(zip(FEATURE_NAMES, self.clf.coef_[0].tolist()))

    # --- persistence --------------------------------------------------------
    def save(self, path: str = MODEL_PATH) -> None:
        joblib.dump({"clf": self.clf, "features": FEATURE_NAMES}, path)

    @classmethod
    def load(cls, path: str = MODEL_PATH) -> "RiskModel":
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"No trained model at {path}. Run `python train.py` first."
            )
        blob = joblib.load(path)
        if blob.get("features") != FEATURE_NAMES:
            raise ValueError(
                "Saved model feature order does not match engine.features.FEATURE_NAMES. "
                "Retrain with `python train.py`."
            )
        return cls(blob["clf"])
