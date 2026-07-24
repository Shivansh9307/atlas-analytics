"""Source registry: loads sources.yaml, resolves env-var creds, hands out adapters.

Credentials are ONLY ever read from environment variables named in the YAML.
The YAML never contains a secret. Warehouse adapters are dormant until their
referenced env vars are populated (and the optional [warehouse] extra installed).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from atlas.config import PATHS
from atlas.connectors.base import Connector
from atlas.connectors.csv_duckdb import CsvDuckDBConnector
from atlas.lib.query_store import QueryStore


@dataclass
class SourceSpec:
    name: str
    dialect: str
    raw: dict[str, Any]

    @property
    def kind(self) -> str:
        return self.raw.get("kind", "warehouse")


class Registry:
    def __init__(self, sources_yaml: str | Path | None = None):
        self.path = Path(sources_yaml) if sources_yaml else PATHS.sources_yaml
        self._specs: dict[str, SourceSpec] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        data = yaml.safe_load(self.path.read_text()) or {}
        for name, raw in (data.get("sources") or {}).items():
            self._specs[name] = SourceSpec(name=name, dialect=raw["dialect"], raw=raw)

    def names(self) -> list[str]:
        return list(self._specs.keys())

    def specs(self) -> list[SourceSpec]:
        return list(self._specs.values())

    def get_spec(self, name: str) -> SourceSpec:
        if name not in self._specs:
            raise KeyError(f"unknown source '{name}'. Known: {self.names()}")
        return self._specs[name]

    @staticmethod
    def _resolve_env(raw: dict, key: str) -> str | None:
        """Return the VALUE of the env var named by raw[key], or None."""
        env_name = raw.get(key)
        return os.environ.get(env_name) if env_name else None

    def is_live(self, name: str) -> bool:
        """A file source is live if the file exists; a warehouse if its creds resolve."""
        spec = self.get_spec(name)
        if spec.kind == "file":
            p = spec.raw.get("path", "")
            return (PATHS.root / p).exists() if not os.path.isabs(p) else Path(p).exists()
        # warehouse: require the primary connection env vars to be present
        required_hint = {
            "postgres": ["host_env", "user_env"],
            "snowflake": ["account_env", "user_env"],
            "bigquery": ["project_env"],
            "databricks": ["host_env", "token_env"],
        }.get(spec.dialect, [])
        return all(self._resolve_env(spec.raw, k) for k in required_hint) if required_hint else False

    def connector(self, name: str, store: QueryStore | None = None) -> Connector:
        """Instantiate the adapter for `name`. Raises if dormant/unsupported."""
        spec = self.get_spec(name)
        raw = spec.raw

        if spec.dialect == "duckdb" or spec.kind == "file":
            path = raw["path"]
            path = path if os.path.isabs(path) else str(PATHS.root / path)
            return CsvDuckDBConnector(
                name=name, path=path,
                table_name=raw.get("table_name"),
                sheet=raw.get("sheet"),
                store=store, row_limit=raw.get("row_limit"),
            )

        # Warehouse adapters are lazily imported so the [warehouse] extra is
        # only required when actually connecting to one.
        if not self.is_live(name):
            raise RuntimeError(
                f"source '{name}' ({spec.dialect}) is dormant: required env vars "
                f"are not set. Populate .env, then retry."
            )
        if spec.dialect == "postgres":
            from atlas.connectors.postgres import PostgresConnector
            return PostgresConnector(name, raw, store=store)
        if spec.dialect == "snowflake":
            from atlas.connectors.snowflake import SnowflakeConnector
            return SnowflakeConnector(name, raw, store=store)
        if spec.dialect == "bigquery":
            from atlas.connectors.bigquery import BigQueryConnector
            return BigQueryConnector(name, raw, store=store)
        if spec.dialect == "databricks":
            from atlas.connectors.databricks import DatabricksConnector
            return DatabricksConnector(name, raw, store=store)
        raise ValueError(f"no adapter for dialect '{spec.dialect}'")
