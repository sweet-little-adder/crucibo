"""Load YAML defaults and merge with environment overrides."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

from crucibo.config.models import CruciboConfig

_DEFAULT_YAML = Path(__file__).resolve().parent / "default.yaml"


@lru_cache(maxsize=1)
def load_config() -> CruciboConfig:
    payload: dict = {}
    if _DEFAULT_YAML.is_file():
        raw = yaml.safe_load(_DEFAULT_YAML.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            payload = raw

    env_root = os.environ.get("CRUCIBO_DATA_ROOT", "").strip()
    if env_root:
        payload["data_root"] = env_root

    return CruciboConfig.model_validate(payload)


def resolve_data_root(override: Path | None = None) -> Path:
    if override is not None:
        return override.resolve()
    return load_config().data_root.resolve()