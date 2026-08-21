"""Project configuration loading and conservative defaults."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .project import ProjectError


DEFAULTS: dict[str, Any] = {
    "schema_version": 1,
    "cadence": "daily",
    "top_n": 5,
    "lookback_days": 14,
    "max_seed_resolution": 12,
    "max_graph_seeds": 8,
    "sources": ["crossref", "openalex"],
    "discovery_lanes": ["forward-citations", "related", "keywords"],
    "watch": {"keywords": [], "authors": [], "venues": []},
    "exclude": {"keywords": []},
    "access": {"institution": None, "analysis_policy": "local-test"},
}


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(project: str | Path) -> dict[str, Any]:
    root = Path(project).expanduser().resolve()
    path = root / ".research-radar" / "config.yaml"
    if not path.is_file():
        return _merge({}, DEFAULTS)
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ProjectError(f"Invalid Research Radar configuration {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ProjectError(f"Research Radar configuration must be a YAML mapping: {path}")
    config = _merge(DEFAULTS, loaded)
    if config.get("schema_version") != 1:
        raise ProjectError(
            f"Unsupported config schema_version {config.get('schema_version')!r}; expected 1."
        )
    return config
