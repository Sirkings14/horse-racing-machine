from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Sequence
import numpy as np
from src.model.v3_features import FEATURE_NAMES, build_v3_matrix
from src.model.calibration import apply_sigmoid_calibrator

@dataclass
class V3LogisticModel:
    feature_names: list[str]
    mean: list[float]
    std: list[float]
    intercept: float
    coefficients: list[float]
    positive_weight: float
    calibration: dict | None = None

    def predict_proba(self, rows: Sequence[dict[str, Any]]) -> np.ndarray:
        x = build_v3_matrix(rows)
        if len(x) == 0:
            return np.empty(0, dtype=float)
        mean = np.asarray(self.mean, dtype=float)
        std = np.where(np.asarray(self.std, dtype=float) < 1e-9, 1.0, np.asarray(self.std, dtype=float))
        z = (x - mean) / std
        logits = np.clip(self.intercept + z @ np.asarray(self.coefficients, dtype=float), -30.0, 30.0)
        weighted = 1.0 / (1.0 + np.exp(-logits))
        denominator = self.positive_weight * (1.0 - weighted) + weighted
        raw = np.clip(weighted / np.maximum(denominator, 1e-12), 0.0, 1.0)
        return np.asarray([apply_sigmoid_calibrator(v, self.calibration) for v in raw], dtype=float)

    def to_dict(self) -> dict[str, Any]:
        return {"model_type":"v3_evidence_logistic","feature_names":self.feature_names,"mean":self.mean,"std":self.std,"intercept":self.intercept,"coefficients":self.coefficients,"positive_weight":self.positive_weight,"calibration":self.calibration}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "V3LogisticModel":
        return cls(list(payload["feature_names"]), list(payload["mean"]), list(payload["std"]), float(payload["intercept"]), list(payload["coefficients"]), float(payload.get("positive_weight",1.0)),payload.get("calibration"))

def fit_v3_model(rows: Sequence[dict[str, Any]], target_field: str="top3", epochs: int=900, learning_rate: float=0.03, l2: float=1.5, feature_matrix: np.ndarray | None = None) -> V3LogisticModel:
    if not rows: raise ValueError("Cannot train V3 on empty rows.")
    x=build_v3_matrix(rows) if feature_matrix is None else np.asarray(feature_matrix,dtype=float)
    if x.ndim != 2 or x.shape != (len(rows), len(FEATURE_NAMES)):
        raise ValueError("Precomputed feature matrix has an invalid shape.")
    if not np.isfinite(x).all():
        raise ValueError("Training feature matrix contains non-finite values.")
    y=np.asarray([1.0 if int(row.get(target_field,0))==1 else 0.0 for row in rows],dtype=float)
    positive=float(y.sum()); negative=float(len(y)-positive)
    if positive<=0 or negative<=0: raise ValueError("V3 training data needs positive and negative examples.")
    mean=x.mean(axis=0); std=np.where(x.std(axis=0)<1e-9,1.0,x.std(axis=0)); z=(x-mean)/std
    weights=np.where(y>0.5,negative/positive,1.0)
    intercept=float(np.log(positive/negative)); coefficients=np.zeros(z.shape[1],dtype=float)
    for _ in range(epochs):
        p=1.0/(1.0+np.exp(-np.clip(intercept+z@coefficients,-30.0,30.0)))
        error=(p-y)*weights
        intercept-=learning_rate*float(error.mean())
        coefficients-=learning_rate*((z.T@error)/len(y)+l2*coefficients/len(y))
    return V3LogisticModel(list(FEATURE_NAMES),mean.tolist(),std.tolist(),intercept,coefficients.tolist(),negative/positive)
