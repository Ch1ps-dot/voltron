"""Load public configuration with local, non-versioned LLM credentials."""

from __future__ import annotations

import copy
import os
import re
from pathlib import Path

import yaml


_ENV_PLACEHOLDER = re.compile(r"^\$\{([A-Z][A-Z0-9_]*)\}$")
_API_KEY_ENV = {
    "llm_doc": "VOLTRON_LLM_DOC_API_KEY",
    "llm_fuzz": "VOLTRON_LLM_FUZZ_API_KEY",
    "llm_compliance": "VOLTRON_LLM_COMPLIANCE_API_KEY",
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge local overrides without mutating the tracked base mapping."""
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _read_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as stream:
        payload = yaml.safe_load(stream)
    if not isinstance(payload, dict):
        raise ValueError(f"invalid configuration mapping: {path}")
    return payload


def _resolve_api_keys(config_data: dict) -> None:
    for profile, env_name in _API_KEY_ENV.items():
        values = config_data.get(profile)
        if not isinstance(values, dict):
            continue
        override = os.environ.get(env_name)
        if override:
            values["api_key"] = override
            continue
        configured = values.get("api_key", "")
        if isinstance(configured, str):
            match = _ENV_PLACEHOLDER.fullmatch(configured.strip())
            if match:
                values["api_key"] = os.environ.get(match.group(1), "")


def load_runtime_config(config_dir: Path) -> dict:
    """Load tracked defaults, optional ignored local overrides, then env keys.

    ``configs.local.yaml`` is intentionally optional and ignored by Git.  An
    environment variable takes precedence over the local file so container and
    CI deployments do not need to materialize a credential on disk.
    """
    config_dir = Path(config_dir)
    config_data = _read_yaml(config_dir / "configs.yaml")
    local_path = config_dir / "configs.local.yaml"
    if local_path.is_file():
        config_data = _deep_merge(config_data, _read_yaml(local_path))
    _resolve_api_keys(config_data)
    return config_data
