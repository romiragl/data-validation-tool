"""
validation_runner.py
Orchestrates all validation checks and writes an audit log per run.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import duckdb

from src.config_loader import ClientConfig
from src.validators import ALL_VALIDATORS, ValidationResult

logger = logging.getLogger(__name__)

LOGS_DIR = Path(__file__).parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)


def run_validation(
    con: duckdb.DuckDBPyConnection,
    config: ClientConfig,
    pf_id: int,
    status: str = "processed",
) -> tuple[list[ValidationResult], Path]:
    """
    Run all registered validators for a given platform and return:
      - list of ValidationResult objects
      - path to the audit log file written

    Parameters
    ----------
    con     : DuckDB connection with crawl_data table loaded
    config  : Client config (drives column names, rule params)
    pf_id   : Which platform to validate
    status  : 'raw' or 'processed'
    """
    run_id = str(uuid.uuid4())[:8]
    started_at = datetime.utcnow()
    platform = config.platform_by_id(pf_id)
    platform_name = platform.name if platform else f"pf_id={pf_id}"

    logger.info(f"[{run_id}] Starting validation: {config.client_id} / {platform_name} / status={status}")

    results: list[ValidationResult] = []
    for validator_fn in ALL_VALIDATORS:
        try:
            result = validator_fn(con, config, pf_id, status)
            results.append(result)
            flag = result.status
            logger.info(f"  [{flag}] {result.rule_name}: {result.failed}/{result.total_checked} failed")
        except Exception as e:
            logger.error(f"  [ERROR] {validator_fn.__name__}: {e}")
            results.append(
                ValidationResult(
                    rule_name=validator_fn.__name__,
                    description="Rule execution failed",
                    total_checked=0,
                    passed=0,
                    failed=0,
                    failure_pct=0.0,
                    skipped=True,
                    skip_reason=str(e),
                )
            )

    finished_at = datetime.utcnow()
    log_path = _write_audit_log(
        run_id=run_id,
        client_id=config.client_id,
        platform_name=platform_name,
        pf_id=pf_id,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        results=results,
    )
    logger.info(f"[{run_id}] Done. Audit log → {log_path}")

    return results, log_path


def _write_audit_log(
    run_id: str,
    client_id: str,
    platform_name: str,
    pf_id: int,
    status: str,
    started_at: datetime,
    finished_at: datetime,
    results: list[ValidationResult],
) -> Path:
    """Write a structured JSON audit log for this validation run."""
    duration_s = (finished_at - started_at).total_seconds()
    total_rules = len(results)
    passed_rules = sum(1 for r in results if not r.skipped and r.failed == 0)
    failed_rules = sum(1 for r in results if not r.skipped and r.failed > 0)
    skipped_rules = sum(1 for r in results if r.skipped)

    log = {
        "run_id": run_id,
        "client": client_id,
        "platform": platform_name,
        "pf_id": pf_id,
        "status_filter": status,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": round(duration_s, 3),
        "summary": {
            "total_rules": total_rules,
            "passed_rules": passed_rules,
            "failed_rules": failed_rules,
            "skipped_rules": skipped_rules,
        },
        "results": [
            {
                "rule_name": r.rule_name,
                "description": r.description,
                "status": r.status,
                "total_checked": r.total_checked,
                "passed": r.passed,
                "failed": r.failed,
                "failure_pct": r.failure_pct,
                "skipped": r.skipped,
                "skip_reason": r.skip_reason,
                "sample_failures": r.sample_failures[:5],  # keep log small
            }
            for r in results
        ],
    }

    ts = started_at.strftime("%Y%m%d_%H%M%S")
    safe_name = platform_name.replace(" ", "_").replace("/", "-")
    filename = f"{client_id}_{safe_name}_{ts}_{run_id}.json"
    log_path = LOGS_DIR / filename

    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, default=str)

    return log_path
