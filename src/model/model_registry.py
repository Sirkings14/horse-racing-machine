from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

BASE_DIR = Path(__file__).resolve().parents[2]
MODEL_DIR = BASE_DIR / "data" / "model"
REGISTRY_FILE = MODEL_DIR / "model_registry.json"
CHALLENGER_DIR = MODEL_DIR / "challenger"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_registry() -> dict:
    if not REGISTRY_FILE.exists():
        return {"version": 1, "champion_version": None, "champion_promoted_at": None, "history": []}
    try:
        payload = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except (OSError, json.JSONDecodeError):
        pass
    return {"version": 1, "champion_version": None, "champion_promoted_at": None, "history": []}


def save_registry(payload: dict) -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    REGISTRY_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def new_candidate_version() -> str:
    return datetime.now(timezone.utc).strftime("model-%Y%m%dT%H%M%SZ-") + uuid4().hex[:8]


def record_candidate(version: str, metrics: dict | None = None) -> None:
    payload = load_registry()
    history = payload.setdefault("history", [])
    history.append({
        "version": version,
        "status": "candidate",
        "created_at": _now(),
        "metrics": metrics or {},
    })
    payload["updated_at"] = _now()
    save_registry(payload)


def record_promotion_decision(version: str, decision: str, reason: str, metrics: dict | None = None) -> None:
    payload = load_registry()
    payload.setdefault("promotion_ledger", []).append({
        "version": version,
        "decision": decision,
        "reason": reason,
        "metrics": metrics or {},
        "timestamp": _now(),
    })
    payload["updated_at"] = _now()
    save_registry(payload)


def promote_candidate(version: str, metrics: dict | None = None) -> None:
    payload = load_registry()
    history = payload.setdefault("history", [])
    for item in history:
        if item.get("status") == "champion":
            item["status"] = "retired"
        if item.get("version") == version:
            item["status"] = "champion"
            item["metrics"] = metrics or item.get("metrics", {})
            item["promoted_at"] = _now()
    payload["champion_version"] = version
    payload["champion_promoted_at"] = _now()
    payload["updated_at"] = _now()
    save_registry(payload)
