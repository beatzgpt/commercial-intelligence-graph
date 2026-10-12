"""Explainable opportunity score. Deterministic: same data + same scoring.yaml = same score.
Every contribution keeps its signal_id and source_id so the score can be audited line by line."""
from datetime import date
from pathlib import Path

import yaml

from .config import AS_OF, SCORING_PATH


def load_weights(path: Path = SCORING_PATH) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def score_company(conn, company_id: str, weights: dict, as_of: date = AS_OF) -> dict:
    half_life = weights["recency_half_life_days"]
    contributions = []

    for s in conn.execute("SELECT * FROM signals WHERE company_id = ? ORDER BY signal_id", (company_id,)):
        weight = weights["signals"].get(s["type"], 0)
        age = (as_of - date.fromisoformat(s["observed_at"])).days
        recency = 0.5 ** (max(age, 0) / half_life)
        contributions.append({
            "kind": "signal", "label": s["type"], "summary": s["summary"],
            "signal_id": s["signal_id"], "source_id": s["source_id"],
            "evidence_url": s["evidence_url"], "observed_at": s["observed_at"],
            "weight": weight, "confidence": s["confidence"], "recency": round(recency, 3),
            "points": round(weight * s["confidence"] * recency, 2),
        })

    st = weights["structural"]
    legacy = [r["name"] for r in conn.execute(
        """SELECT t.name FROM company_technologies ct JOIN technologies t USING (tech_id)
           WHERE ct.company_id = ? AND t.generation = 'legacy' ORDER BY t.name""", (company_id,))]
    roles = {r["role_type"] for r in conn.execute(
        "SELECT role_type FROM people WHERE company_id = ?", (company_id,))}
    structural = [
        ("legacy_tech_present", bool(legacy), f"Legacy footprint: {', '.join(legacy)}"),
        ("champion_mapped", "champion" in roles, "Likely champion mapped in the graph"),
        ("economic_buyer_mapped", "economic_buyer" in roles, "Budget owner mapped in the graph"),
        ("security_blocker_identified", "security_blocker" in roles, "Security/procurement gatekeeper adds friction"),
    ]
    for key, present, summary in structural:
        if present:
            contributions.append({
                "kind": "structural", "label": key, "summary": summary, "signal_id": None,
                "source_id": None, "evidence_url": None, "observed_at": None,
                "weight": st[key], "confidence": 1.0, "recency": 1.0, "points": float(st[key]),
            })

    total = round(sum(c["points"] for c in contributions), 2)
    return {"company_id": company_id, "total": total, "contributions": contributions}
