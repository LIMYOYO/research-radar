"""Project configuration loading and conservative defaults."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .project import ProjectError
from .presets import VENUE_PRESETS


DEFAULTS: dict[str, Any] = {
    "schema_version": 1,
    "cadence": "on-demand",
    "top_n": 5,
    "lookback_days": 14,
    "max_seed_resolution": 12,
    "max_graph_seeds": 8,
    "max_watch_queries": 8,
    "sources": ["crossref", "openalex", "semanticscholar"],
    "discovery_lanes": [
        "forward-citations",
        "reference-neighborhood",
        "related",
        "keywords",
        "authors",
        "venues",
    ],
    "watch": {"keywords": [], "authors": [], "venues": []},
    "venue_presets": [],
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
    presets = config.get("venue_presets", [])
    if not isinstance(presets, list):
        raise ProjectError("venue_presets must be a YAML list.")
    unknown = sorted(str(item) for item in presets if str(item) not in VENUE_PRESETS)
    if unknown:
        raise ProjectError(
            "Unknown venue preset(s): "
            + ", ".join(unknown)
            + ". Choose from: "
            + ", ".join(sorted(VENUE_PRESETS))
        )
    return config


def configured_watch(config: dict[str, Any], kind: str) -> tuple[str, ...]:
    values = config.get("watch", {}).get(kind, [])
    if not isinstance(values, list):
        raise ProjectError(f"watch.{kind} must be a YAML list.")
    result = [str(item).strip() for item in values if str(item).strip()]
    if kind == "venues":
        for name in config.get("venue_presets", []):
            result.extend(VENUE_PRESETS[str(name)])
    return tuple(dict.fromkeys(result))
