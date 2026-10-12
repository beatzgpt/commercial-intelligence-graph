import json
import re
import types
from pathlib import Path

import pytest

from cig import config
from cig.generate import generate
from cig.graph import build_graph
from cig.ingest import ProvenanceError, ingest
from cig.queries import account_profile, digest, rank_opportunities
from cig.scoring import load_weights
from cig.synthesis import build_narrative, narrative_llm, narrative_template, render_brief


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    root = tmp_path_factory.mktemp("cig")
    generate(root / "data")
    conn = ingest(root / "data", root / "cig.db")
    return root, conn, load_weights("scoring.yaml")


def test_generator_is_deterministic(tmp_path):
    generate(tmp_path / "a")
    generate(tmp_path / "b")
    for name in ("companies.csv", "people.csv", "signals.jsonl", "company_technologies.csv"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()


def test_every_signal_has_full_provenance(env):
    root, conn, _ = env
    for line in (root / "data" / "signals.jsonl").read_text().splitlines():
        s = json.loads(line)
        assert all(s.get(k) not in (None, "") for k in config.REQUIRED_SIGNAL_FIELDS), s["signal_id"]
        assert s["evidence_url"].startswith("https://example.test/")
        assert s["source_type"].startswith("synthetic_")


def test_ingest_rejects_unsourced_signal(tmp_path):
    generate(tmp_path / "d")
    path = tmp_path / "d" / "signals.jsonl"
    rows = [json.loads(x) for x in path.read_text().splitlines()]
    rows[0]["source_id"] = ""
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    with pytest.raises(ProvenanceError):
        ingest(tmp_path / "d", tmp_path / "bad.db")


def test_score_equals_sum_of_visible_contributions(env):
    _, conn, weights = env
    for r in rank_opportunities(conn, weights):
        assert r["total"] == pytest.approx(sum(c["points"] for c in r["contributions"]), abs=1e-9)
        for c in r["contributions"]:
            if c["kind"] == "signal":
                assert c["signal_id"] and c["source_id"]
                assert c["points"] == pytest.approx(c["weight"] * c["confidence"] * c["recency"], abs=0.01)


def test_hero_account_ranks_first_and_graph_edges_exist(env):
    _, conn, weights = env
    ranked = rank_opportunities(conn, weights)
    assert ranked[0]["company"]["name"] == config.HERO_COMPANY
    g = build_graph(conn)
    p = account_profile(conn, config.HERO_COMPANY, weights)
    cid = p["company"]["company_id"]
    rels = {d["rel"] for _, _, d in g.in_edges(cid, data=True)} | {d["rel"] for _, _, d in g.out_edges(cid, data=True)}
    assert {"works_at", "uses", "observed_at_company"} <= rels


def test_digest_only_includes_recent_signals(env):
    _, conn, weights = env
    for m in digest(conn, weights, days=30):
        assert all(s["observed_at"] >= "2026-09-01" for s in m["signals"])


def test_template_brief_cites_only_real_signals_and_renders(env):
    _, conn, weights = env
    p = account_profile(conn, config.HERO_COMPANY, weights)
    n = narrative_template(p)
    known = {s["signal_id"] for s in p["signals"]}
    cited = set(re.findall(r"SIG-\d{4}", json.dumps(n)))
    assert cited and cited <= known
    assert "Northwind Analytics" in render_brief(p, n, "md")
    assert "<html" in render_brief(p, n, "html")


class FakeClient:
    def __init__(self, text):
        self.messages = types.SimpleNamespace(create=lambda **kw: types.SimpleNamespace(
            content=[types.SimpleNamespace(text=text)]))


def test_llm_mode_accepts_grounded_output(env):
    _, conn, weights = env
    p = account_profile(conn, config.HERO_COMPANY, weights)
    out = json.dumps({"summary": "Funding landed [SIG-0001].", "angle": ["Lead with time to value [SIG-0001]"],
                      "questions": ["a", "b", "c"]})
    n = narrative_llm(p, FakeClient(out))
    assert n["mode"].startswith("llm") and isinstance(n["angle"], list)


def test_llm_mode_rejects_invented_citation_and_falls_back(env):
    _, conn, weights = env
    p = account_profile(conn, config.HERO_COMPANY, weights)
    bad = json.dumps({"summary": "Made up [SIG-9999].", "angle": ["x"], "questions": ["a", "b", "c"]})
    with pytest.raises(ValueError):
        narrative_llm(p, FakeClient(bad))
    n = build_narrative(p, use_llm=True, client=FakeClient(bad))
    assert n["mode"].startswith("template (LLM output rejected")


def test_llm_requested_without_key_falls_back(env, monkeypatch):
    _, conn, weights = env
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    n = build_narrative(account_profile(conn, config.HERO_COMPANY, weights), use_llm=True)
    assert "not set" in n["mode"]


def test_cli_demo_runs_offline(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src = Path(__file__).resolve().parent.parent / "scoring.yaml"
    (tmp_path / "scoring.yaml").write_text(src.read_text())
    from cig.cli import main
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert main(["demo"]) == 0
    for f in ("brief_northwind_analytics.md", "brief_northwind_analytics.html",
              "graph_northwind_analytics.png", "digest.md", "opportunities.txt"):
        assert (tmp_path / "outputs" / f).exists(), f
