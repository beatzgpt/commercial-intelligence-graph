"""Shared constants. The 'as of' date is fixed so every run is reproducible."""
from datetime import date
from pathlib import Path

SEED = 42
AS_OF = date(2026, 10, 1)
HERO_COMPANY = "Northwind Analytics"
SELLER_PRODUCT = "Aster Data Cloud"  # fictional

DATA_DIR = Path("data/synthetic")
OUT_DIR = Path("outputs")
DB_PATH = Path(".cig/cig.db")
SCORING_PATH = Path("scoring.yaml")

REQUIRED_SIGNAL_FIELDS = (
    "signal_id", "company_id", "type", "source_type", "source_id",
    "observed_at", "evidence_url", "confidence", "summary",
)
