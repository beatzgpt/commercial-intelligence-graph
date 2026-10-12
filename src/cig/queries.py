"""Use-case queries: account profile, ranked opportunities, segment view, weekly digest."""
from datetime import date, timedelta

from .config import AS_OF
from .scoring import score_company


def find_company(conn, name_or_id: str):
    row = conn.execute(
        "SELECT * FROM companies WHERE company_id = ? OR lower(name) = lower(?)",
        (name_or_id, name_or_id)).fetchone()
    if row is None:
        row = conn.execute("SELECT * FROM companies WHERE lower(name) LIKE lower(?)",
                           (f"%{name_or_id}%",)).fetchone()
    if row is None:
        raise KeyError(f"No company matching '{name_or_id}'")
    return row


def rank_opportunities(conn, weights: dict, segment: str | None = None, as_of: date = AS_OF) -> list[dict]:
    sql = "SELECT * FROM companies" + (" WHERE segment = ?" if segment else "") + " ORDER BY company_id"
    rows = conn.execute(sql, (segment,) if segment else ()).fetchall()
    ranked = []
    for c in rows:
        s = score_company(conn, c["company_id"], weights, as_of)
        ranked.append({"company": dict(c), **s})
    ranked.sort(key=lambda r: (-r["total"], r["company"]["name"]))
    for i, r in enumerate(ranked, start=1):
        r["rank"] = i
    return ranked


def account_profile(conn, name_or_id: str, weights: dict, as_of: date = AS_OF) -> dict:
    c = find_company(conn, name_or_id)
    cid = c["company_id"]
    ranked = rank_opportunities(conn, weights, as_of=as_of)
    me = next(r for r in ranked if r["company"]["company_id"] == cid)
    people = [dict(r) for r in conn.execute(
        """SELECT * FROM people WHERE company_id = ? ORDER BY
           CASE role_type WHEN 'economic_buyer' THEN 1 WHEN 'champion' THEN 2
                          WHEN 'technical_evaluator' THEN 3 ELSE 4 END, name""", (cid,))]
    tech = [dict(r) for r in conn.execute(
        """SELECT t.*, ct.since FROM company_technologies ct JOIN technologies t USING (tech_id)
           WHERE ct.company_id = ? ORDER BY t.generation, t.name""", (cid,))]
    signals = [dict(r) for r in conn.execute(
        "SELECT * FROM signals WHERE company_id = ? ORDER BY observed_at DESC", (cid,))]
    return {"company": dict(c), "people": people, "tech": tech, "signals": signals,
            "score": me["total"], "contributions": sorted(me["contributions"], key=lambda x: -x["points"]),
            "rank": me["rank"], "of": len(ranked), "as_of": as_of.isoformat()}


def digest(conn, weights: dict, days: int = 30, top: int = 5, as_of: date = AS_OF) -> list[dict]:
    """Top movers: accounts ranked by points earned from signals observed in the last `days`."""
    cutoff = as_of - timedelta(days=days)
    movers = []
    for c in conn.execute("SELECT * FROM companies ORDER BY company_id"):
        s = score_company(conn, c["company_id"], weights, as_of)
        recent = [x for x in s["contributions"] if x["kind"] == "signal" and date.fromisoformat(x["observed_at"]) >= cutoff]
        if recent:
            movers.append({"company": dict(c), "recent_points": round(sum(x["points"] for x in recent), 2),
                           "total": s["total"], "signals": sorted(recent, key=lambda x: -x["points"])})
    movers.sort(key=lambda m: (-m["recent_points"], m["company"]["name"]))
    return movers[:top]
