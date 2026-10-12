# Architecture notes

## Flow

1. **Sources** (`data/synthetic/`): `companies.csv`, `people.csv`, `technologies.csv`, `company_technologies.csv`, `signals.jsonl`. Produced by `src/cig/generate.py` from a fixed seed and a fixed as-of date (`2026-10-01`), so output is reproducible.
2. **Ingest** (`ingest.py`): loads into SQLite at `.cig/cig.db`. A signal missing any of `signal_id, company_id, type, source_type, source_id, observed_at, evidence_url, confidence, summary` raises `ProvenanceError`.
3. **Graph** (`graph.py`): NetworkX `MultiDiGraph`. Node kinds: company, person, tech, signal. Edge relations: `works_at`, `uses`, `observed_at_company`, `mentions_tech`, `mentions_person`. Signal edges keep the `signal_id`.
4. **Scoring** (`scoring.py`): per-signal points = `weight x confidence x 0.5^(age/half_life)`; structural points from graph facts. Each contribution keeps `signal_id`, `source_id`, `evidence_url`.
5. **Queries** (`queries.py`): account profile, ranked opportunities, segment filter, 30-day digest.
6. **Narrative** (`synthesis.py`): template rules by default. Optional single LLM call receives only the structured facts, must cite signal IDs, and is rejected if any cited ID is not in the profile or if it contains a number that does not appear in the input facts. It does not check that each claim is semantically supported by its cited signal (planned).
7. **Outputs**: Jinja2 templates render Markdown and HTML briefs; Matplotlib draws the account graph and segment map.

## Design choices

- **Provenance at the boundary.** Rejecting unsourced signals at ingest is cheaper than auditing scores later.
- **Scoring as data.** Weights are in `scoring.yaml`; a seller or manager can change priorities without touching code.
- **LLM as a bounded component.** It rewrites text from facts already scored by deterministic code and cannot add facts. It is one call, not an autonomous loop.
- **Offline-first.** The full demo needs no network or credentials.

## Extension points (not implemented)

- Replace `generate.py` with connectors that emit the same CSV/JSONL contract.
- Swap SQLite for a graph database behind `graph.build_graph`.
- Add a multi-step research loop that calls queries as tools and verifies its own citations.
