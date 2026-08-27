"""
validators.py
All validation rules as parameterized functions.

Each function:
- Takes a DuckDB connection + ClientConfig + pf_id + status filter
- Runs pure SQL (never LLM logic)
- Returns a ValidationResult dataclass

Adding a new rule: add a new function + register it in ALL_VALIDATORS.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import duckdb
import pandas as pd

from src.config_loader import ClientConfig


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    rule_name: str
    description: str
    total_checked: int
    passed: int
    failed: int
    failure_pct: float
    sample_failures: list[dict] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""

    @property
    def status(self) -> str:
        if self.skipped:
            return "⚪ SKIPPED"
        if self.failed == 0:
            return "✅ PASS"
        if self.failure_pct >= 20:
            return "🔴 FAIL"
        return "🟡 WARN"

    @classmethod
    def skipped_result(cls, rule_name: str, description: str, reason: str) -> "ValidationResult":
        return cls(
            rule_name=rule_name,
            description=description,
            total_checked=0,
            passed=0,
            failed=0,
            failure_pct=0.0,
            skipped=True,
            skip_reason=reason,
        )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _col(config: ClientConfig, logical: str) -> str:
    """Resolve logical column name → actual column name via config remap."""
    return getattr(config.column_map, logical)


def _base_filter(config: ClientConfig, pf_id: int, status: str) -> str:
    """Build the WHERE clause common to all queries."""
    s_col = _col(config, "status")
    p_col = _col(config, "pf_id")
    r_col = _col(config, "region")
    # Strip dummy rollup rows (region = 'All')
    return (
        f"WHERE {p_col} = {pf_id} "
        f"AND {s_col} = '{status}' "
        f"AND {r_col} != 'All'"
    )


def _sample_failures(con: duckdb.DuckDBPyConnection, sql: str, limit: int = 10) -> list[dict]:
    """Run a SQL query and return sample failure rows as list of dicts."""
    try:
        df: pd.DataFrame = con.execute(sql).df()
        return df.head(limit).to_dict(orient="records")
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Rule 1: Data Hygiene — count rows stripped by region='All'
# ---------------------------------------------------------------------------

def check_data_hygiene(
    con: duckdb.DuckDBPyConnection, config: ClientConfig, pf_id: int, status: str
) -> ValidationResult:
    """
    Counts how many rows have region = 'All' (dummy rollup rows that should be excluded).
    These are stripped from all other checks automatically.
    """
    p_col = _col(config, "pf_id")
    s_col = _col(config, "status")
    r_col = _col(config, "region")

    total_sql = f"""
        SELECT COUNT(*) FROM crawl_data
        WHERE {p_col} = {pf_id} AND {s_col} = '{status}'
    """
    rollup_sql = f"""
        SELECT COUNT(*) FROM crawl_data
        WHERE {p_col} = {pf_id} AND {s_col} = '{status}'
        AND {r_col} = 'All'
    """
    sample_sql = f"""
        SELECT * FROM crawl_data
        WHERE {p_col} = {pf_id} AND {s_col} = '{status}'
        AND {r_col} = 'All'
        LIMIT 10
    """

    total = con.execute(total_sql).fetchone()[0]
    failed = con.execute(rollup_sql).fetchone()[0]
    passed = total - failed

    return ValidationResult(
        rule_name="Data Hygiene",
        description="Rows with region='All' (dummy rollup rows) — stripped before other checks",
        total_checked=total,
        passed=passed,
        failed=failed,
        failure_pct=round(100 * failed / total, 2) if total > 0 else 0.0,
        sample_failures=_sample_failures(con, sample_sql),
    )


# ---------------------------------------------------------------------------
# Rule 2: Price Rule — MRP >= SP
# ---------------------------------------------------------------------------

def check_price_rule(
    con: duckdb.DuckDBPyConnection, config: ClientConfig, pf_id: int, status: str
) -> ValidationResult:
    """MRP must be >= SP on every row. Violation: MRP < SP."""
    base = _base_filter(config, pf_id, status)
    mrp_col = _col(config, "mrp")
    sp_col = _col(config, "sp")

    total_sql = f"SELECT COUNT(*) FROM crawl_data {base}"
    fail_sql = f"""
        SELECT COUNT(*) FROM crawl_data {base}
        AND {mrp_col} < {sp_col}
    """
    sample_sql = f"""
        SELECT sku_id, sku_name, {mrp_col}, {sp_col}
        FROM crawl_data {base}
        AND {mrp_col} < {sp_col}
        LIMIT 10
    """

    total = con.execute(total_sql).fetchone()[0]
    failed = con.execute(fail_sql).fetchone()[0]
    passed = total - failed

    return ValidationResult(
        rule_name="Price Rule (MRP ≥ SP)",
        description="Maximum Retail Price must always be ≥ Selling Price",
        total_checked=total,
        passed=passed,
        failed=failed,
        failure_pct=round(100 * failed / total, 2) if total > 0 else 0.0,
        sample_failures=_sample_failures(con, sample_sql),
    )


# ---------------------------------------------------------------------------
# Rule 3: OSA Derivation — osa_remark=0 → osa=0 (Out of Stock)
# ---------------------------------------------------------------------------

def check_osa_out_of_stock(
    con: duckdb.DuckDBPyConnection, config: ClientConfig, pf_id: int, status: str
) -> ValidationResult:
    """When osa_remark=0 (OOS), osa must be 0. Violation: osa_remark=0 AND osa!=0."""
    base = _base_filter(config, pf_id, status)
    osa_col = _col(config, "osa")
    osa_r_col = _col(config, "osa_remark")
    oos_code = config.osa_remark_codes.out_of_stock

    total_sql = f"""
        SELECT COUNT(*) FROM crawl_data {base}
        AND {osa_r_col} = {oos_code}
    """
    fail_sql = f"""
        SELECT COUNT(*) FROM crawl_data {base}
        AND {osa_r_col} = {oos_code} AND {osa_col} != 0
    """
    sample_sql = f"""
        SELECT sku_id, sku_name, {osa_col}, {osa_r_col}
        FROM crawl_data {base}
        AND {osa_r_col} = {oos_code} AND {osa_col} != 0
        LIMIT 10
    """

    total = con.execute(total_sql).fetchone()[0]
    failed = con.execute(fail_sql).fetchone()[0]
    passed = total - failed

    return ValidationResult(
        rule_name="OSA Derivation — OOS (remark=0 → osa=0)",
        description="When osa_remark=0 (Out of Stock), osa must be 0",
        total_checked=total,
        passed=passed,
        failed=failed,
        failure_pct=round(100 * failed / total, 2) if total > 0 else 0.0,
        sample_failures=_sample_failures(con, sample_sql),
    )


# ---------------------------------------------------------------------------
# Rule 4: OSA Derivation — osa_remark=2 → osa=0 (Not Listed)
# ---------------------------------------------------------------------------

def check_osa_not_listed(
    con: duckdb.DuckDBPyConnection, config: ClientConfig, pf_id: int, status: str
) -> ValidationResult:
    """When osa_remark=2 (Not Listed), osa must be 0. Violation: osa_remark=2 AND osa!=0."""
    base = _base_filter(config, pf_id, status)
    osa_col = _col(config, "osa")
    osa_r_col = _col(config, "osa_remark")
    nl_code = config.osa_remark_codes.not_listed

    total_sql = f"""
        SELECT COUNT(*) FROM crawl_data {base}
        AND {osa_r_col} = {nl_code}
    """
    fail_sql = f"""
        SELECT COUNT(*) FROM crawl_data {base}
        AND {osa_r_col} = {nl_code} AND {osa_col} != 0
    """
    sample_sql = f"""
        SELECT sku_id, sku_name, {osa_col}, {osa_r_col}
        FROM crawl_data {base}
        AND {osa_r_col} = {nl_code} AND {osa_col} != 0
        LIMIT 10
    """

    total = con.execute(total_sql).fetchone()[0]
    failed = con.execute(fail_sql).fetchone()[0]
    passed = total - failed

    return ValidationResult(
        rule_name="OSA Derivation — Not Listed (remark=2 → osa=0)",
        description="When osa_remark=2 (Not Listed), osa must be 0",
        total_checked=total,
        passed=passed,
        failed=failed,
        failure_pct=round(100 * failed / total, 2) if total > 0 else 0.0,
        sample_failures=_sample_failures(con, sample_sql),
    )


# ---------------------------------------------------------------------------
# Rule 5: In-Stock Integrity — osa=1 requires valid prices and title
# ---------------------------------------------------------------------------

def check_instock_integrity(
    con: duckdb.DuckDBPyConnection, config: ClientConfig, pf_id: int, status: str
) -> ValidationResult:
    """
    For rows where osa=1 (in stock):
      - price fields must not be zero (mrp > 0 AND sp > 0 AND price_rp > 0 AND price_sp > 0)
      - title (sku_name) must not be blank or '0'
      - price_rp >= price_sp
    """
    base = _base_filter(config, pf_id, status)
    osa_col = _col(config, "osa")
    osa_r_col = _col(config, "osa_remark")
    mrp_col = _col(config, "mrp")
    sp_col = _col(config, "sp")
    prp_col = _col(config, "price_rp")
    psp_col = _col(config, "price_sp")
    name_col = _col(config, "sku_name")
    in_stock_code = config.osa_remark_codes.in_stock

    instock_base = f"""
        {base}
        AND {osa_col} = 1
        AND {osa_r_col} = {in_stock_code}
    """

    total_sql = f"SELECT COUNT(*) FROM crawl_data {instock_base}"
    fail_sql = f"""
        SELECT COUNT(*) FROM crawl_data {instock_base}
        AND (
            {mrp_col} <= 0
            OR {sp_col} <= 0
            OR {prp_col} <= 0
            OR {psp_col} <= 0
            OR TRIM(CAST({name_col} AS VARCHAR)) = ''
            OR TRIM(CAST({name_col} AS VARCHAR)) = '0'
            OR {prp_col} < {psp_col}
        )
    """
    sample_sql = f"""
        SELECT sku_id, sku_name, {mrp_col}, {sp_col}, {prp_col}, {psp_col}, {osa_col}, {osa_r_col}
        FROM crawl_data {instock_base}
        AND (
            {mrp_col} <= 0
            OR {sp_col} <= 0
            OR {prp_col} <= 0
            OR {psp_col} <= 0
            OR TRIM(CAST({name_col} AS VARCHAR)) = ''
            OR TRIM(CAST({name_col} AS VARCHAR)) = '0'
            OR {prp_col} < {psp_col}
        )
        LIMIT 10
    """

    total = con.execute(total_sql).fetchone()[0]
    failed = con.execute(fail_sql).fetchone()[0]
    passed = total - failed

    return ValidationResult(
        rule_name="In-Stock Integrity (osa=1 checks)",
        description="In-stock rows must have non-zero prices, a valid title, and price_rp ≥ price_sp",
        total_checked=total,
        passed=passed,
        failed=failed,
        failure_pct=round(100 * failed / total, 2) if total > 0 else 0.0,
        sample_failures=_sample_failures(con, sample_sql),
    )


# ---------------------------------------------------------------------------
# Rule 6: Completeness — expected rows = SKUs × locations
# ---------------------------------------------------------------------------

def check_completeness(
    con: duckdb.DuckDBPyConnection, config: ClientConfig, pf_id: int, status: str
) -> ValidationResult:
    """
    Checks whether the row count matches expected_skus × expected_locations.
    Skipped if no completeness target is configured for this platform.
    """
    target = config.completeness_targets.get(pf_id)
    if target is None or target.expected_skus is None or target.expected_locations is None:
        return ValidationResult.skipped_result(
            rule_name="Completeness Check",
            description="Row count = SKUs × Locations",
            reason="No completeness target configured. Set expected_skus and expected_locations in nestle.yaml.",
        )

    base = _base_filter(config, pf_id, status)
    actual_sql = f"SELECT COUNT(*) FROM crawl_data {base}"
    actual = con.execute(actual_sql).fetchone()[0]

    expected = target.expected_skus * target.expected_locations
    shortfall = max(0, expected - actual)
    failed = 1 if shortfall > 0 else 0

    return ValidationResult(
        rule_name="Completeness Check",
        description=f"Expected {expected} rows ({target.expected_skus} SKUs × {target.expected_locations} locations)",
        total_checked=actual,
        passed=actual if failed == 0 else 0,
        failed=shortfall,
        failure_pct=round(100 * shortfall / expected, 2) if expected > 0 else 0.0,
        sample_failures=[{
            "expected_rows": expected,
            "actual_rows": actual,
            "shortfall": shortfall,
        }] if shortfall > 0 else [],
    )


# ---------------------------------------------------------------------------
# Rule 7: Platform ID Convention — prefix check for sub-platforms
# ---------------------------------------------------------------------------

PLATFORM_PREFIX_MAP = {
    53: "AN-",   # Amazon Now
    7:  "AF-",   # Amazon Fresh Ambient
    20: "AF-",   # Amazon Fresh Chilled
}


def check_platform_id_convention(
    con: duckdb.DuckDBPyConnection, config: ClientConfig, pf_id: int, status: str
) -> ValidationResult:
    """
    Sub-platforms (Amazon Now, Amazon Fresh) share a base product_id with the parent
    but carry a prefix (AN-, AF-). Checks that the prefix is present.
    Skipped for platforms without a defined prefix convention.
    """
    expected_prefix = PLATFORM_PREFIX_MAP.get(pf_id)
    if expected_prefix is None:
        return ValidationResult.skipped_result(
            rule_name="Platform ID Convention",
            description="Sub-platform product_id prefix check",
            reason=f"No prefix convention defined for pf_id={pf_id}.",
        )

    base = _base_filter(config, pf_id, status)
    pid_col = _col(config, "product_id")

    total_sql = f"SELECT COUNT(*) FROM crawl_data {base}"
    fail_sql = f"""
        SELECT COUNT(*) FROM crawl_data {base}
        AND NOT STARTS_WITH(CAST({pid_col} AS VARCHAR), '{expected_prefix}')
    """
    sample_sql = f"""
        SELECT sku_id, sku_name, {pid_col}
        FROM crawl_data {base}
        AND NOT STARTS_WITH(CAST({pid_col} AS VARCHAR), '{expected_prefix}')
        LIMIT 10
    """

    total = con.execute(total_sql).fetchone()[0]
    failed = con.execute(fail_sql).fetchone()[0]
    passed = total - failed

    return ValidationResult(
        rule_name="Platform ID Convention",
        description=f"product_id must start with '{expected_prefix}' for this sub-platform",
        total_checked=total,
        passed=passed,
        failed=failed,
        failure_pct=round(100 * failed / total, 2) if total > 0 else 0.0,
        sample_failures=_sample_failures(con, sample_sql),
    )


# ---------------------------------------------------------------------------
# Registry — all validators in run order
# ---------------------------------------------------------------------------

ALL_VALIDATORS = [
    check_data_hygiene,
    check_price_rule,
    check_osa_out_of_stock,
    check_osa_not_listed,
    check_instock_integrity,
    check_completeness,
    check_platform_id_convention,
]
