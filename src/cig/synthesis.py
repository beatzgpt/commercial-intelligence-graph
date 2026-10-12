"""Brief narrative. Two modes, described honestly:

* template (default): deterministic rules over the scored facts. No model involved.
* llm (optional, needs ANTHROPIC_API_KEY): ONE model call that rewrites the narrative from the same
  structured facts. It is a single call, not an autonomous agent. Output is checked: any cited signal ID
  not in the profile, or any figure not present in the input facts, falls back to the template.
  Limit: it does not verify that each claim is semantically supported by its cited signal.
"""
import json
import os
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .config import SELLER_PRODUCT

MODEL = os.environ.get("CIG_MODEL", "claude-sonnet-5-5")
TEMPLATES = Path(__file__).parent / "templates"
SIG_RE = re.compile(r"SIG-\d{4}")
NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def _top_signals(profile, n=3):
    return [c for c in profile["contributions"] if c["kind"] == "signal"][:n]


def narrative_template(profile: dict) -> dict:
    c, sigs = profile["company"], profile["signals"]
    by_type = {}
    for s in sigs:
        by_type.setdefault(s["type"], []).append(s)
    top = _top_signals(profile)
    drivers = "; ".join(f"{t['summary'].rstrip('.')} [{t['signal_id']}]" for t in top) or "no recent signals"
    summary = (f"{c['name']} ({c['segment']}, {c['employees']} employees, {c['region']}) ranks "
               f"{profile['rank']} of {profile['of']} with a score of {profile['score']}. "
               f"Main drivers: {drivers}.")

    angle_parts, questions = [], []
    legacy = [t for t in profile["tech"] if t["generation"] == "legacy"]
    if legacy and (by_type.get("hiring") or by_type.get("earnings_mention")):
        refs = [s["signal_id"] for s in by_type.get("hiring", [])[:1] + by_type.get("earnings_mention", [])[:1]]
        angle_parts.append(f"Modernisation window: legacy stack ({', '.join(t['name'] for t in legacy)}) "
                           f"alongside hiring and stated priority [{', '.join(refs)}]. "
                           f"Position {SELLER_PRODUCT} as the migration path, not a rip-and-replace.")
        questions.append("Which legacy workloads are blocking the modernisation priority first?")
    if by_type.get("exec_change"):
        angle_parts.append(f"New data leader [{by_type['exec_change'][0]['signal_id']}]: leaders usually reset "
                           "platform decisions in their first months. Offer a short evidence-based review.")
        questions.append("What did the new data leader commit to in the first 90 days?")
    if by_type.get("funding"):
        angle_parts.append(f"Recent funding [{by_type['funding'][0]['signal_id']}] may indicate investment capacity, "
                           "not confirmed budget. Validate who owns the data platform budget and when it is allocated.")
    if by_type.get("tech_adoption"):
        angle_parts.append(f"Active evaluation signal [{by_type['tech_adoption'][0]['signal_id']}]: "
                           "ask what the pilot is meant to prove before it ends.")
        questions.append("What success criteria does the current pilot have to meet?")
    if any(p["role_type"] == "security_blocker" for p in profile["people"]):
        questions.append("What security review does a new platform need to pass, and how long does it take?")
    if not angle_parts:
        angle_parts.append("No strong timing signal. Keep warm and monitor for funding, hiring or leadership changes.")
    while len(questions) < 3:
        questions.append("Who owns the data platform budget, and when is the next planning cycle?")
    return {"summary": summary, "angle": angle_parts, "questions": questions[:4], "mode": "template"}


def _facts_for_llm(profile: dict) -> dict:
    return {
        "company": profile["company"], "score": profile["score"], "rank": profile["rank"],
        "people": [{k: p[k] for k in ("name", "title", "role_type")} for p in profile["people"]],
        "technology": [{k: t[k] for k in ("name", "category", "generation")} for t in profile["tech"]],
        "signals": [{k: s[k] for k in ("signal_id", "type", "summary", "observed_at", "source_id")}
                    for s in profile["signals"]],
        "seller_product": SELLER_PRODUCT,
    }


SYSTEM = ("You write concise account briefs for a B2B seller. Use ONLY the facts in the JSON the user "
          "sends. Never invent facts, numbers or names. Treat funding as a capacity signal, not proof of budget. Cite supporting signals as [SIG-0000]. "
          "Return JSON with keys: summary (string), angle (array of 1-4 short strings), questions (array of 3 strings).")


def narrative_llm(profile: dict, client=None) -> dict:
    """One validated call. Raises ValueError if the output cannot be trusted."""
    if client is None:
        import anthropic  # optional dependency
        client = anthropic.Anthropic()
    resp = client.messages.create(
        model=MODEL, max_tokens=900, system=SYSTEM,
        messages=[{"role": "user", "content": json.dumps(_facts_for_llm(profile))}],
    )
    text = resp.content[0].text.strip()
    text = text[text.find("{"): text.rfind("}") + 1]
    out = json.loads(text)
    known = {s["signal_id"] for s in profile["signals"]}
    cited = set(SIG_RE.findall(json.dumps(out)))
    if not cited or not cited <= known:
        raise ValueError(f"Unknown citations: {sorted(cited - known) or 'none cited'}")
    facts_text = SIG_RE.sub("", json.dumps(_facts_for_llm(profile)))
    allowed = set(NUM_RE.findall(facts_text))
    invented = sorted(set(NUM_RE.findall(SIG_RE.sub("", json.dumps(out)))) - allowed)
    if invented:
        raise ValueError(f"Figures not present in input facts: {invented}")
    if not all(k in out for k in ("summary", "angle", "questions")):
        raise ValueError("Missing keys in model output")
    if isinstance(out["angle"], str):
        out["angle"] = [out["angle"]]
    out["mode"] = f"llm ({MODEL}), single call, citations and figures validated"
    return out


def build_narrative(profile: dict, use_llm: bool = False, client=None) -> dict:
    if use_llm:
        if client is None and not os.environ.get("ANTHROPIC_API_KEY"):
            n = narrative_template(profile)
            n["mode"] = "template (LLM requested but ANTHROPIC_API_KEY is not set)"
            return n
        try:
            return narrative_llm(profile, client)
        except Exception as exc:  # fall back, never ship an unvalidated narrative
            n = narrative_template(profile)
            n["mode"] = f"template (LLM output rejected: {exc})"
            return n
    return narrative_template(profile)


def render_brief(profile: dict, narrative: dict, fmt: str = "md") -> str:
    env = Environment(loader=FileSystemLoader(TEMPLATES), trim_blocks=True, lstrip_blocks=True)
    return env.get_template(f"brief.{fmt}.j2").render(p=profile, n=narrative, product=SELLER_PRODUCT)
