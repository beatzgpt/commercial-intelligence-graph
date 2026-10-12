"""Seeded generator for the synthetic dataset. Every name, number and URL is invented."""
import csv
import json
import random
from datetime import timedelta
from pathlib import Path

from .config import AS_OF, DATA_DIR, SEED

SEGMENTS = {
    "Retail Data Platforms": ["Retail Analytics", "Commerce Data", "Merchant Metrics"],
    "FinServ Analytics": ["Capital Analytics", "Risk Systems", "Ledger Intelligence"],
    "Logistics Cloud": ["Freight Cloud", "Route Systems", "Fleet Data"],
    "Health Data Systems": ["Health Data", "Care Analytics", "Clinical Systems"],
    "Media Measurement": ["Audience Labs", "Media Metrics", "Reach Analytics"],
}
PREFIXES = [
    "Lumenfield", "Harborline", "Cobaltgate", "Junipera", "Quillstone", "Emberwick",
    "Vantora", "Sablewood", "Orchidale", "Tidewater Row", "Granitewell", "Helixor",
    "Marlowe Park", "Pinecrest Row", "Solacewick", "Brightmere", "Kestrelton",
    "Alderbrook", "Fennmoor", "Oakhaven", "Redfern Gate", "Silverlode", "Thornbury",
    "Wrenfield", "Ashgrove", "Birchmoor", "Cinderhall", "Dunmere", "Elmcastle",
]
REGIONS = ["UK", "DACH", "Nordics", "France", "Benelux", "Iberia"]

TECHNOLOGIES = [
    ("T01", "OldVault On-Prem Warehouse", "Data Warehouse", "legacy"),
    ("T02", "Batchline ETL", "ETL / Orchestration", "legacy"),
    ("T03", "Gridlock Reporting Suite", "BI", "legacy"),
    ("T04", "Cirrus Lakehouse", "Data Platform", "modern"),
    ("T05", "Rivulet Streaming", "Streaming", "modern"),
    ("T06", "Vectrix Vector Store", "Vector Database", "modern"),
    ("T07", "Prism BI Studio", "BI", "modern"),
    ("T08", "Tracelight Observability", "Observability", "modern"),
    ("T09", "Featherbed Feature Store", "ML Platform", "modern"),
    ("T10", "Beacon CDP", "Customer Data Platform", "modern"),
]
LEGACY = [t[0] for t in TECHNOLOGIES if t[3] == "legacy"]
MODERN = [t[0] for t in TECHNOLOGIES if t[3] == "modern"]

FIRST = ["Amara", "Ben", "Chloe", "Dev", "Elena", "Farid", "Grace", "Ines", "Jonas", "Kofi",
         "Lena", "Mateo", "Nadia", "Rafa", "Sana", "Theo", "Uma", "Viktor", "Yara", "Zane"]
LAST = ["Bellamy", "Dunmore", "Ellery", "Galbraith", "Hartwell", "Imber", "Jessop", "Kerrigan",
        "Lowther", "Mansfield", "Norcross", "Oakley", "Pemberton", "Quarles", "Rowntree",
        "Sterne", "Tolliver", "Underhill", "Vance", "Yardley", "Zeller"]
TITLES = {
    "economic_buyer": ["Chief Data Officer", "VP Data & Analytics", "Chief Information Officer"],
    "champion": ["Head of Data Platform", "Director of Analytics Engineering"],
    "technical_evaluator": ["Principal Data Engineer", "Staff Platform Architect"],
    "security_blocker": ["Head of Information Security", "Procurement Lead"],
}

# Each template: (source_type, source_id prefix, summary)
SIGNAL_TEMPLATES = {
    "funding": ("synthetic_press_release", "PR", "Announced a ${amt}M growth round"),
    "hiring": ("synthetic_job_board", "JB", "Opened {n} data engineering roles"),
    "tech_adoption": ("synthetic_blog", "BL", "Engineering blog describes a pilot of {tech}"),
    "exec_change": ("synthetic_press_release", "PR", "Appointed a new data leader"),
    "earnings_mention": ("synthetic_filing", "FL", "Management names data modernisation a priority"),
}

HERO = {
    "company": ("C001", "Northwind Analytics", "Retail Data Platforms", "UK", 1200, "$200M-$500M"),
    "people": [
        ("P001", "Priya Ashdown", "Chief Data Officer", "C001", "economic_buyer"),
        ("P002", "Hugo Farrow", "Head of Data Platform", "C001", "champion"),
        ("P003", "Wen Castellan", "Principal Data Engineer", "C001", "technical_evaluator"),
        ("P004", "Owen Whitlock", "Head of Information Security", "C001", "security_blocker"),
    ],
    "tech": [("C001", "T01", "2018-03-01"), ("C001", "T02", "2019-06-01"), ("C001", "T07", "2024-02-01")],
    "signals": [
        ("funding", "2026-08-12", "Announced a $85M Series C round", 0.9, "PR-2026-0812", None, None),
        ("hiring", "2026-09-05", "Opened 6 data engineering roles including a lakehouse migration lead", 0.8, "JB-2026-0905", None, None),
        ("hiring", "2026-09-20", "Opened a Head of ML Platform role", 0.7, "JB-2026-0920", None, None),
        ("exec_change", "2026-07-30", "Appointed Priya Ashdown as Chief Data Officer", 0.9, "PR-2026-0730", None, "P001"),
        ("earnings_mention", "2026-09-10", "Management names data modernisation a top-3 priority", 0.85, "FL-2026-Q3", None, None),
        ("tech_adoption", "2026-09-15", "Engineering blog describes a pilot of Rivulet Streaming", 0.6, "BL-2026-0915", "T05", None),
    ],
}


def _write_csv(path: Path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def _signal(rng, sid, company, kind, people):
    src_type, prefix, tmpl = SIGNAL_TEMPLATES[kind]
    observed = AS_OF - timedelta(days=rng.randint(3, 170))
    tech = rng.choice(MODERN) if kind == "tech_adoption" else None
    tech_name = next(t[1] for t in TECHNOLOGIES if t[0] == tech) if tech else ""
    person = None
    if kind == "exec_change" and people:
        person = rng.choice(people)[0]
    summary = tmpl.format(amt=rng.choice([20, 35, 50, 120]), n=rng.randint(2, 8), tech=tech_name)
    return {
        "signal_id": sid, "company_id": company, "type": kind, "source_type": src_type,
        "source_id": f"{prefix}-{observed:%Y-%m%d}-{rng.randint(100, 999)}",
        "observed_at": observed.isoformat(), "evidence_url": f"https://example.test/evidence/{sid}",
        "confidence": round(rng.uniform(0.5, 0.95), 2), "summary": summary,
        "tech_id": tech, "person_id": person,
    }


def generate(out_dir: Path = DATA_DIR, seed: int = SEED) -> dict:
    rng = random.Random(seed)
    out_dir.mkdir(parents=True, exist_ok=True)

    companies = [HERO["company"]]
    prefixes = PREFIXES[:]
    rng.shuffle(prefixes)
    segs = list(SEGMENTS)
    for i, prefix in enumerate(prefixes, start=2):
        seg = segs[(i - 2) % len(segs)]
        name = f"{prefix} {rng.choice(SEGMENTS[seg])}"
        companies.append((f"C{i:03d}", name, seg, rng.choice(REGIONS),
                          rng.choice([150, 400, 900, 2500, 6000]),
                          rng.choice(["$20M-$50M", "$50M-$200M", "$200M-$500M", "$500M+"])))

    people, used = list(HERO["people"]), {p[1] for p in HERO["people"]}
    pid = 5
    for c in companies[1:]:
        roles = ["economic_buyer", "champion"] + rng.sample(["technical_evaluator", "security_blocker"], rng.randint(0, 1))
        for role in roles:
            while True:
                name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
                if name not in used:
                    used.add(name)
                    break
            people.append((f"P{pid:03d}", name, rng.choice(TITLES[role]), c[0], role))
            pid += 1

    company_tech = list(HERO["tech"])
    for c in companies[1:]:
        picks = {rng.choice(LEGACY)} if rng.random() < 0.7 else set()
        picks |= set(rng.sample(MODERN, rng.randint(1, 2)))
        for t in sorted(picks):
            company_tech.append((c[0], t, f"{rng.randint(2016, 2025)}-01-01"))

    signals, n = [], 1
    for kind, observed, summary, conf, source_id, tech, person in HERO["signals"]:
        sid = f"SIG-{n:04d}"
        n += 1
        src_type = SIGNAL_TEMPLATES[kind][0]
        signals.append({
            "signal_id": sid, "company_id": "C001", "type": kind, "source_type": src_type,
            "source_id": source_id, "observed_at": observed,
            "evidence_url": f"https://example.test/evidence/{sid}", "confidence": conf,
            "summary": summary, "tech_id": tech, "person_id": person,
        })
    for c in companies[1:]:
        c_people = [p for p in people if p[3] == c[0]]
        for _ in range(rng.choice([0, 1, 1, 2, 2, 3])):
            kind = rng.choice(list(SIGNAL_TEMPLATES))
            signals.append(_signal(rng, f"SIG-{n:04d}", c[0], kind, c_people))
            n += 1

    _write_csv(out_dir / "companies.csv", ["company_id", "name", "segment", "region", "employees", "revenue_band"], companies)
    _write_csv(out_dir / "people.csv", ["person_id", "name", "title", "company_id", "role_type"], people)
    _write_csv(out_dir / "technologies.csv", ["tech_id", "name", "category", "generation"], TECHNOLOGIES)
    _write_csv(out_dir / "company_technologies.csv", ["company_id", "tech_id", "since"], company_tech)
    with (out_dir / "signals.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for s in signals:
            f.write(json.dumps(s, sort_keys=True) + "\n")
    return {"companies": len(companies), "people": len(people), "technologies": len(TECHNOLOGIES),
            "company_technologies": len(company_tech), "signals": len(signals)}
