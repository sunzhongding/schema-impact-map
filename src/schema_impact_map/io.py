from __future__ import annotations

import json
from pathlib import Path

import yaml


class DataError(Exception):
    """Invalid input data (schema, relations, entities, delta)."""


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DataError(f"file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DataError(f"invalid json: {path}: {exc}") from exc


def load_yaml_text(text: str, source: str = "<inline>") -> dict:
    """Parse YAML handed over by a client instead of read from a file."""
    try:
        return yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise DataError(f"invalid yaml: {source}: {exc}") from exc


def load_yaml(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError as exc:
        raise DataError(f"file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise DataError(f"invalid yaml: {path}: {exc}") from exc


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
