"""Command line entry point. Offline-first: nothing here needs network or credentials."""
import argparse
import sys
from pathlib import Path

from . import config
from .generate import generate
from .graph import build_graph, draw_account_graph, draw_segment_map
from .ingest import connect, ingest
from .queries import account_profile, digest, find_company, rank_opportunities
from .scoring import load_weights
from .synthesis import build_narrative, render_brief


def _slug(name: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in name).strip("_")


def _ensure_db():
    if not config.DB_PATH.exists():
        cmd_init(argparse.Namespace(regen=False))
    return connect(config.DB_PATH)


def cmd_init(args):
    if args.regen or not (config.DATA_DIR / "signals.jsonl").exists():
        counts = generate()
        print(f"Generated synthetic data: {counts}")
    ingest().close()
    print(f"Ingested into {config.DB_PATH} (provenance enforced on every signal)")


def _write_brief(conn, weights, name, use_llm):
    p = account_profile(conn, name, weights)
    n = build_narrative(p, use_llm=use_llm)
    slug = _slug(p["company"]["name"])
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    md, html = config.OUT_DIR / f"brief_{slug}.md", config.OUT_DIR / f"brief_{slug}.html"
    md.write_text(render_brief(p, n, "md"), encoding="utf-8")
    html.write_text(render_brief(p, n, "html"), encoding="utf-8")
    return p, n, [md, html]


def cmd_brief(args):
    conn, weights = _ensure_db(), load_weights()
    p, n, files = _write_brief(conn, weights, args.company, args.llm)
    print(f"{p['company']['name']}: score {p['score']} (rank {p['rank']}/{p['of']}), narrative: {n['mode']}")
    for f in files:
        print(f"  wrote {f}")


def _opps_table(ranked, top):
    lines = [f"{'#':>2}  {'Company':<34}{'Segment':<24}{'Score':>7}  Top contributions"]
    for r in ranked[:top]:
        parts = ", ".join(f"{c['label']} {c['points']}" for c in sorted(r["contributions"], key=lambda x: -x["points"])[:3])
        lines.append(f"{r['rank']:>2}  {r['company']['name']:<34}{r['company']['segment']:<24}{r['total']:>7}  {parts}")
    return "\n".join(lines)


def cmd_opportunities(args):
    conn, weights = _ensure_db(), load_weights()
    ranked = rank_opportunities(conn, weights, segment=args.segment)
    table = _opps_table(ranked, args.top)
    print(table)
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    (config.OUT_DIR / "opportunities.txt").write_text(table + "\n", encoding="utf-8")


def cmd_map(args):
    conn, weights = _ensure_db(), load_weights()
    segment = args.segment or find_company(conn, config.HERO_COMPANY)["segment"]
    ranked = rank_opportunities(conn, weights, segment=segment)
    path = draw_segment_map(build_graph(conn), ranked, segment, config.OUT_DIR / f"map_{_slug(segment)}.png")
    print(f"wrote {path}")


def cmd_digest(args):
    conn, weights = _ensure_db(), load_weights()
    movers = digest(conn, weights, days=args.days, top=args.top)
    lines = [f"# Weekly intelligence digest (synthetic), last {args.days} days to {config.AS_OF}", ""]
    for i, m in enumerate(movers, start=1):
        lines.append(f"{i}. **{m['company']['name']}** ({m['company']['segment']}), +{m['recent_points']} points from new signals, total {m['total']}")
        for s in m["signals"]:
            lines.append(f"   - {s['observed_at']} {s['label']}: {s['summary']} [{s['signal_id']} / {s['source_id']}]")
    text = "\n".join(lines) + "\n"
    print(text)
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    (config.OUT_DIR / "digest.md").write_text(text, encoding="utf-8")


def cmd_demo(args):
    """End-to-end account research: data -> ingest -> graph -> score -> brief."""
    print("== 1/5 Generate + ingest synthetic data")
    cmd_init(argparse.Namespace(regen=True))
    conn, weights = connect(config.DB_PATH), load_weights()
    print("\n== 2/5 Score every account (weights in scoring.yaml)")
    ranked = rank_opportunities(conn, weights)
    print(_opps_table(ranked, 5))
    print(f"\n== 3/5 Research the hero account: {config.HERO_COMPANY}")
    p, n, files = _write_brief(conn, weights, config.HERO_COMPANY, args.llm)
    print(f"narrative mode: {n['mode']}")
    for c in p["contributions"][:5]:
        ev = f"{c['signal_id']} / {c['source_id']}" if c["signal_id"] else "graph structure"
        print(f"  +{c['points']:>5}  {c['label']:<26} {ev}")
    print("\n== 4/5 Draw graphs")
    g = build_graph(conn)
    hero_id = p["company"]["company_id"]
    files.append(draw_account_graph(g, hero_id, config.OUT_DIR / "graph_northwind_analytics.png", p["score"]))
    seg = p["company"]["segment"]
    seg_ranked = [r for r in ranked if r["company"]["segment"] == seg]
    files.append(draw_segment_map(g, seg_ranked, seg, config.OUT_DIR / f"map_{_slug(seg)}.png"))
    print("\n== 5/5 Weekly digest")
    cmd_digest(argparse.Namespace(days=30, top=5))
    (config.OUT_DIR / "opportunities.txt").write_text(_opps_table(ranked, 10) + "\n", encoding="utf-8")
    print("Outputs:")
    for f in files + [config.OUT_DIR / "digest.md", config.OUT_DIR / "opportunities.txt"]:
        print(f"  {f}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="cig", description="Commercial Intelligence Graph (synthetic showcase)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init", help="generate (if missing) and ingest synthetic data")
    s.add_argument("--regen", action="store_true")
    s.set_defaults(fn=cmd_init)
    s = sub.add_parser("brief", help="account research brief for one company")
    s.add_argument("company")
    s.add_argument("--llm", action="store_true", help="optional single grounded model call")
    s.set_defaults(fn=cmd_brief)
    s = sub.add_parser("opportunities", help="ranked, explainable opportunity list")
    s.add_argument("--top", type=int, default=10)
    s.add_argument("--segment")
    s.set_defaults(fn=cmd_opportunities)
    s = sub.add_parser("map", help="segment market map image")
    s.add_argument("--segment")
    s.set_defaults(fn=cmd_map)
    s = sub.add_parser("digest", help="weekly top-movers digest")
    s.add_argument("--days", type=int, default=30)
    s.add_argument("--top", type=int, default=5)
    s.set_defaults(fn=cmd_digest)
    s = sub.add_parser("demo", help="run the full end-to-end account research demo")
    s.add_argument("--llm", action="store_true")
    s.set_defaults(fn=cmd_demo)
    args = ap.parse_args(argv)
    try:
        args.fn(args)
    except KeyError as exc:
        print(f"error: {exc.args[0]}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
