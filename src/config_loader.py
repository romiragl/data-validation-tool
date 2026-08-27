"""
config_loader.py
Loads and validates client configuration from YAML files.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, field_validator


# ---------------------------------------------------------------------------
# Pydantic models — validated at load time so bad configs fail fast
# ---------------------------------------------------------------------------

class PlatformEntry(BaseModel):
    pf_id: int
    name: str
    alias: str
    pdp_table: str


class CompletenessTarget(BaseModel):
    expected_skus: Optional[int] = None
    expected_locations: Optional[int] = None


class ColumnMap(BaseModel):
    pf_id: str = "pf_id"
    sku_id: str = "sku_id"
    sku_name: str = "sku_name"
    mrp: str = "mrp"
    sp: str = "sp"
    price_rp: str = "price_rp"
    price_sp: str = "price_sp"
    osa: str = "osa"
    osa_remark: str = "osa_remark"
    region: str = "region"
    location_id: str = "location_id"
    status: str = "status"
    crawl_date: str = "crawl_date"
    product_id: str = "product_id"


class OSARemarkCodes(BaseModel):
    out_of_stock: int = 0
    in_stock: int = 1
    not_listed: int = 2


class StatusValues(BaseModel):
    raw: str = "raw"
    processed: str = "processed"


class ClientConfig(BaseModel):
    client_id: str
    client_display_name: str
    location_master_table: str
    pdp_table: str
    active_platforms: list[PlatformEntry]
    column_map: ColumnMap = ColumnMap()
    osa_remark_codes: OSARemarkCodes = OSARemarkCodes()
    status_values: StatusValues = StatusValues()
    completeness_targets: dict[int, CompletenessTarget] = {}

    @field_validator("completeness_targets", mode="before")
    @classmethod
    def parse_completeness(cls, v):
        if not v:
            return {}
        return {int(k): CompletenessTarget(**(vv or {})) for k, vv in v.items()}

    def platform_by_id(self, pf_id: int) -> Optional[PlatformEntry]:
        for p in self.active_platforms:
            if p.pf_id == pf_id:
                return p
        return None

    def platform_ids(self) -> list[int]:
        return [p.pf_id for p in self.active_platforms]


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

CONFIG_DIR = Path(__file__).parent.parent / "config"


def load_client_config(client_id: str) -> ClientConfig:
    """Load config for a given client_id (e.g. 'nestle')."""
    path = CONFIG_DIR / f"{client_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"No config file found for client '{client_id}' at {path}.\n"
            f"Available configs: {[p.stem for p in CONFIG_DIR.glob('*.yaml')]}"
        )
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return ClientConfig(**raw)


def list_clients() -> list[str]:
    """Return all available client IDs."""
    return [p.stem for p in CONFIG_DIR.glob("*.yaml")]
