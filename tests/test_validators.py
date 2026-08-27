"""
test_validators.py
Unit tests for each validation rule using controlled in-memory data.
Run with: pytest tests/ -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config_loader import ClientConfig, ColumnMap, OSARemarkCodes, PlatformEntry, StatusValues
from src.validators import (
    check_data_hygiene,
    check_instock_integrity,
    check_osa_not_listed,
    check_osa_out_of_stock,
    check_platform_id_convention,
    check_price_rule,
)

# ────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def config() -> ClientConfig:
    """Minimal ClientConfig for tests — uses all default column names."""
    return ClientConfig(
        client_id="test",
        client_display_name="Test Client",
        location_master_table="test_location_master",
        pdp_table="test_pdp",
        active_platforms=[
            PlatformEntry(pf_id=1, name="Test Platform", alias="TP", pdp_table="test_pdp"),
            PlatformEntry(pf_id=53, name="Amazon Now", alias="ANW", pdp_table="amazon_now_crawl_pdp"),
        ],
        column_map=ColumnMap(),
        osa_remark_codes=OSARemarkCodes(),
        status_values=StatusValues(),
    )


def _make_con(rows: list[dict]) -> duckdb.DuckDBPyConnection:
    """Create an in-memory DuckDB connection with the given rows as crawl_data."""
    df = pd.DataFrame(rows)
    # Ensure all expected columns exist (fill missing with defaults)
    defaults = {
        "pf_id": 1, "sku_id": "SKU001", "sku_name": "Test SKU",
        "mrp": 100.0, "sp": 90.0, "price_rp": 95.0, "price_sp": 90.0,
        "osa": 1, "osa_remark": 1, "region": "Delhi",
        "location_id": 1, "status": "processed",
        "crawl_date": "2025-01-01", "product_id": "SKU001",
    }
    for col, val in defaults.items():
        if col not in df.columns:
            df[col] = val
    con = duckdb.connect(":memory:")
    con.register("crawl_data_view", df)
    con.execute("CREATE TABLE crawl_data AS SELECT * FROM crawl_data_view")
    return con


# ────────────────────────────────────────────────────────────────────────────
# Test: Data Hygiene
# ────────────────────────────────────────────────────────────────────────────

class TestDataHygiene:
    def test_no_rollup_rows(self, config):
        con = _make_con([
            {"pf_id": 1, "region": "Delhi", "status": "processed"},
            {"pf_id": 1, "region": "Mumbai", "status": "processed"},
        ])
        r = check_data_hygiene(con, config, pf_id=1, status="processed")
        assert r.failed == 0
        assert r.total_checked == 2

    def test_rollup_rows_detected(self, config):
        con = _make_con([
            {"pf_id": 1, "region": "Delhi", "status": "processed"},
            {"pf_id": 1, "region": "All", "status": "processed"},
            {"pf_id": 1, "region": "All", "status": "processed"},
        ])
        r = check_data_hygiene(con, config, pf_id=1, status="processed")
        assert r.failed == 2
        assert r.total_checked == 3


# ────────────────────────────────────────────────────────────────────────────
# Test: Price Rule (MRP >= SP)
# ────────────────────────────────────────────────────────────────────────────

class TestPriceRule:
    def test_all_pass(self, config):
        con = _make_con([
            {"pf_id": 1, "mrp": 100.0, "sp": 90.0, "status": "processed", "region": "Delhi"},
            {"pf_id": 1, "mrp": 100.0, "sp": 100.0, "status": "processed", "region": "Delhi"},
        ])
        r = check_price_rule(con, config, pf_id=1, status="processed")
        assert r.failed == 0

    def test_violation_detected(self, config):
        con = _make_con([
            {"pf_id": 1, "mrp": 100.0, "sp": 90.0,  "status": "processed", "region": "Delhi"},
            {"pf_id": 1, "mrp": 80.0,  "sp": 100.0, "status": "processed", "region": "Delhi"},  # FAIL
            {"pf_id": 1, "mrp": 50.0,  "sp": 60.0,  "status": "processed", "region": "Delhi"},  # FAIL
        ])
        r = check_price_rule(con, config, pf_id=1, status="processed")
        assert r.failed == 2
        assert r.passed == 1

    def test_mrp_equals_sp_passes(self, config):
        con = _make_con([{"pf_id": 1, "mrp": 50.0, "sp": 50.0, "status": "processed", "region": "Mumbai"}])
        r = check_price_rule(con, config, pf_id=1, status="processed")
        assert r.failed == 0


# ────────────────────────────────────────────────────────────────────────────
# Test: OSA Out of Stock (remark=0 → osa must be 0)
# ────────────────────────────────────────────────────────────────────────────

class TestOSAOutOfStock:
    def test_correct_oos(self, config):
        con = _make_con([
            {"pf_id": 1, "osa_remark": 0, "osa": 0, "status": "processed", "region": "Delhi"},
        ])
        r = check_osa_out_of_stock(con, config, pf_id=1, status="processed")
        assert r.failed == 0

    def test_incorrect_oos(self, config):
        con = _make_con([
            {"pf_id": 1, "osa_remark": 0, "osa": 0, "status": "processed", "region": "Delhi"},   # PASS
            {"pf_id": 1, "osa_remark": 0, "osa": 1, "status": "processed", "region": "Delhi"},   # FAIL
        ])
        r = check_osa_out_of_stock(con, config, pf_id=1, status="processed")
        assert r.failed == 1
        assert r.passed == 1


# ────────────────────────────────────────────────────────────────────────────
# Test: OSA Not Listed (remark=2 → osa must be 0)
# ────────────────────────────────────────────────────────────────────────────

class TestOSANotListed:
    def test_correct_not_listed(self, config):
        con = _make_con([
            {"pf_id": 1, "osa_remark": 2, "osa": 0, "status": "processed", "region": "Delhi"},
        ])
        r = check_osa_not_listed(con, config, pf_id=1, status="processed")
        assert r.failed == 0

    def test_incorrect_not_listed(self, config):
        con = _make_con([
            {"pf_id": 1, "osa_remark": 2, "osa": 1, "status": "processed", "region": "Delhi"},   # FAIL
        ])
        r = check_osa_not_listed(con, config, pf_id=1, status="processed")
        assert r.failed == 1


# ────────────────────────────────────────────────────────────────────────────
# Test: In-Stock Integrity
# ────────────────────────────────────────────────────────────────────────────

class TestInStockIntegrity:
    def test_clean_instock_row(self, config):
        con = _make_con([
            {
                "pf_id": 1, "osa": 1, "osa_remark": 1,
                "mrp": 100.0, "sp": 90.0, "price_rp": 95.0, "price_sp": 90.0,
                "sku_name": "MAGGI 2-MINUTE NOODLES",
                "status": "processed", "region": "Delhi",
            }
        ])
        r = check_instock_integrity(con, config, pf_id=1, status="processed")
        assert r.failed == 0

    def test_blank_title_fails(self, config):
        con = _make_con([
            {
                "pf_id": 1, "osa": 1, "osa_remark": 1,
                "mrp": 100.0, "sp": 90.0, "price_rp": 95.0, "price_sp": 90.0,
                "sku_name": "0",   # invalid
                "status": "processed", "region": "Delhi",
            }
        ])
        r = check_instock_integrity(con, config, pf_id=1, status="processed")
        assert r.failed == 1

    def test_price_rp_lt_price_sp_fails(self, config):
        con = _make_con([
            {
                "pf_id": 1, "osa": 1, "osa_remark": 1,
                "mrp": 100.0, "sp": 90.0, "price_rp": 80.0, "price_sp": 85.0,  # price_rp < price_sp
                "sku_name": "Valid SKU",
                "status": "processed", "region": "Delhi",
            }
        ])
        r = check_instock_integrity(con, config, pf_id=1, status="processed")
        assert r.failed == 1

    def test_zero_price_fails(self, config):
        con = _make_con([
            {
                "pf_id": 1, "osa": 1, "osa_remark": 1,
                "mrp": 0.0, "sp": 0.0, "price_rp": 0.0, "price_sp": 0.0,
                "sku_name": "Valid SKU",
                "status": "processed", "region": "Delhi",
            }
        ])
        r = check_instock_integrity(con, config, pf_id=1, status="processed")
        assert r.failed == 1


# ────────────────────────────────────────────────────────────────────────────
# Test: Platform ID Convention
# ────────────────────────────────────────────────────────────────────────────

class TestPlatformIDConvention:
    def test_correct_prefix(self, config):
        con = _make_con([
            {"pf_id": 53, "product_id": "AN-SKU001", "status": "processed", "region": "Delhi"},
            {"pf_id": 53, "product_id": "AN-SKU002", "status": "processed", "region": "Delhi"},
        ])
        r = check_platform_id_convention(con, config, pf_id=53, status="processed")
        assert r.failed == 0

    def test_missing_prefix_fails(self, config):
        con = _make_con([
            {"pf_id": 53, "product_id": "AN-SKU001", "status": "processed", "region": "Delhi"},  # PASS
            {"pf_id": 53, "product_id": "SKU002",    "status": "processed", "region": "Delhi"},  # FAIL
        ])
        r = check_platform_id_convention(con, config, pf_id=53, status="processed")
        assert r.failed == 1

    def test_no_convention_skipped(self, config):
        """pf_id=1 (Flipkart) has no prefix convention — should be skipped."""
        con = _make_con([
            {"pf_id": 1, "product_id": "SKU001", "status": "processed", "region": "Delhi"},
        ])
        r = check_platform_id_convention(con, config, pf_id=1, status="processed")
        assert r.skipped is True
