"""
data_loader.py
Generates synthetic crawl data and loads it into an in-memory DuckDB database.

HOW TO SWAP IN REAL DATA
-------------------------
When you have real data (CSV or Parquet exports from Databricks):
1. Place the files in the data/ folder.
2. Call `load_from_files(data_dir)` instead of `generate_synthetic_db()`.
3. The rest of the pipeline is identical — validators consume the same DuckDB connection.
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd

from src.config_loader import ClientConfig

# ---------------------------------------------------------------------------
# Synthetic data generation
# ---------------------------------------------------------------------------

NESTLE_SKUS = [
    ("SKU001", "NESTLE CEREGROW BIB 24x300g N5 IN"),
    ("SKU002", "CERELAC STA4 MU&FrtPoshan24x300gN3 NV IN"),
    ("SKU003", "CERELAC STA1 Wheat Apple BIB 24x350g IN"),
    ("SKU004", "MAGGI PAZZTA Masala 96x69.5g IN"),
    ("SKU005", "NESCAFE CLASSIC Jar 25g IN"),
    ("SKU006", "KITKAT 4F 24x41.5g IN"),
    ("SKU007", "MUNCH 30x26g IN"),
    ("SKU008", "MILKMAID SWEETENED CONDENSED MILK 400g IN"),
    ("SKU009", "MAGGI 2-MINUTE NOODLES Masala 12x70g IN"),
    ("SKU010", "NESCAFE SUNRISE 24x200g IN"),
    ("SKU011", "POLO MINT 18x14g IN"),
    ("SKU012", "NESTLE MILKPAK UHT Milk 1L IN"),
    ("SKU013", "MAGGI MASALA Magic 48x6g IN"),
    ("SKU014", "KITKAT MINI 12x163g IN"),
    ("SKU015", "NESPRESSO ORIGINAL Arpeggio 10 Capsules IN"),
]

LOCATIONS = [
    (1, "Mumbai"),
    (2, "Delhi"),
    (3, "Bangalore"),
    (4, "Chennai"),
    (5, "Hyderabad"),
    (6, "Pune"),
    (7, "Ahmedabad"),
    (8, "Kolkata"),
]

PLATFORM_PRODUCT_PREFIXES = {
    53: "AN",   # Amazon Now
    7:  "AF",   # Amazon Fresh Ambient
    20: "AF",   # Amazon Fresh Chilled
    2:  "",     # Amazon FBA — no prefix
}


def _make_product_id(pf_id: int, sku_id: str) -> str:
    """Apply platform-specific product ID prefix convention."""
    prefix = PLATFORM_PRODUCT_PREFIXES.get(pf_id, "")
    if prefix:
        return f"{prefix}-{sku_id}"
    return sku_id


def _generate_rows(pf_id: int, n_skus: int = 15, n_locations: int = 8,
                   status: str = "processed", seed: int = 42) -> list[dict]:
    """
    Generate synthetic PDP crawl rows for one platform.
    Intentionally injects ~10-15% rule violations for realistic validation testing.
    """
    rng = random.Random(seed + pf_id)
    rows = []
    today = date.today()

    for sku_id, sku_name in NESTLE_SKUS[:n_skus]:
        for loc_id, loc_name in LOCATIONS[:n_locations]:
            # Baseline prices
            mrp = round(rng.uniform(50, 800), 2)
            sp = round(mrp * rng.uniform(0.85, 1.0), 2)

            # OSA setup
            r = rng.random()
            if r < 0.07:
                osa_remark = 0   # Out of stock
                osa = 0
            elif r < 0.12:
                osa_remark = 2   # Not listed
                osa = 0
            else:
                osa_remark = 1   # In stock
                osa = 1

            price_rp = round(mrp * rng.uniform(0.9, 1.0), 2)
            price_sp = round(price_rp * rng.uniform(0.85, 1.0), 2)

            # --- Inject violations deliberately ---
            if rng.random() < 0.06:   # ~6%: price rule violation
                sp = round(mrp + rng.uniform(1, 50), 2)

            if rng.random() < 0.04:   # ~4%: OSA remark 0 but osa=1 (incorrect)
                osa_remark = 0
                osa = 1

            if rng.random() < 0.03:   # ~3%: in-stock with blank title
                if osa == 1:
                    sku_name = "0"

            if rng.random() < 0.03:   # ~3%: price_rp < price_sp violation
                if osa == 1:
                    price_rp, price_sp = price_sp - 1, price_sp + 1

            region = "All" if rng.random() < 0.05 else loc_name

            rows.append({
                "pf_id": pf_id,
                "sku_id": sku_id,
                "sku_name": sku_name,
                "mrp": mrp,
                "sp": sp,
                "price_rp": price_rp,
                "price_sp": price_sp,
                "osa": osa,
                "osa_remark": osa_remark,
                "region": region,
                "location_id": loc_id,
                "status": status,
                "crawl_date": (today - timedelta(days=rng.randint(0, 7))).isoformat(),
                "product_id": _make_product_id(pf_id, sku_id),
            })

    return rows


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_synthetic_db(config: ClientConfig) -> duckdb.DuckDBPyConnection:
    """
    Creates an in-memory DuckDB database populated with synthetic crawl data
    for all active platforms in the given client config.

    Returns a DuckDB connection that the validators consume.
    """
    con = duckdb.connect(database=":memory:")

    all_rows: list[dict] = []
    for platform in config.active_platforms:
        all_rows.extend(_generate_rows(pf_id=platform.pf_id))

    df = pd.DataFrame(all_rows)
    con.register("ebux_pdp", df)
    con.execute("CREATE TABLE crawl_data AS SELECT * FROM ebux_pdp")

    return con


def load_from_files(data_dir: Path, config: ClientConfig) -> duckdb.DuckDBPyConnection:
    """
    Load real data from CSV or Parquet files in data_dir.
    File naming convention: ebux_pdp.csv or ebux_pdp.parquet

    This replaces build_synthetic_db() once you have real Databricks exports.
    """
    con = duckdb.connect(database=":memory:")

    parquet = data_dir / "ebux_pdp.parquet"
    csv = data_dir / "ebux_pdp.csv"

    if parquet.exists():
        con.execute(f"CREATE TABLE crawl_data AS SELECT * FROM read_parquet('{parquet}')")
    elif csv.exists():
        con.execute(f"CREATE TABLE crawl_data AS SELECT * FROM read_csv_auto('{csv}')")
    else:
        raise FileNotFoundError(
            f"No data file found in {data_dir}. "
            "Place ebux_pdp.parquet or ebux_pdp.csv there, or use build_synthetic_db()."
        )

    return con


def get_db(config: ClientConfig, data_dir: Optional[Path] = None) -> duckdb.DuckDBPyConnection:
    """
    Smart loader: uses real files if available in data/, otherwise falls back to synthetic.
    """
    if data_dir is None:
        data_dir = Path(__file__).parent.parent / "data"

    if (data_dir / "ebux_pdp.parquet").exists() or (data_dir / "ebux_pdp.csv").exists():
        return load_from_files(data_dir, config)
    else:
        return build_synthetic_db(config)
