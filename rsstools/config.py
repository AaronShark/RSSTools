"""Configuration management for RSSTools."""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import ValidationError

from .models import Config

DEFAULT_CONFIG = Config()


def load_config() -> Config:
    """Load config from ~/.rsstools/config.json, merge with defaults and env vars."""
    load_dotenv()

    config_data: dict = {}

    config_path = Path.home() / ".rsstools" / "config.json"
    if config_path.exists():
        try:
            with open(config_path, encoding="utf-8") as f:
                user_cfg = json.load(f)
            config_data = _merge_config(config_data, user_cfg)
        except (OSError, json.JSONDecodeError):
            pass

    _apply_env_overrides(config_data)

    if "base_dir" in config_data:
        config_data["base_dir"] = os.path.expanduser(config_data["base_dir"])

    if config_data.get("opml_path"):
        config_data["opml_path"] = os.path.expanduser(config_data["opml_path"])
    elif "base_dir" in config_data:
        config_data["opml_path"] = os.path.join(config_data["base_dir"], "subscriptions.opml")
    else:
        config_data["opml_path"] = os.path.join(
            os.path.expanduser(DEFAULT_CONFIG.base_dir), "subscriptions.opml"
        )

    try:
        return Config(**config_data)
    except ValidationError as e:
        error_messages = _format_validation_errors(e)
        raise ValueError(f"Configuration validation failed:\n{error_messages}") from e


def _merge_config(base: dict, override: dict) -> dict:
    """Recursively merge override dict into base dict."""
    result = base.copy()
    for key, value in override.items():
        if isinstance(value, dict) and key in result and isinstance(result[key], dict):
            result[key] = _merge_config(result[key], value)
        else:
            result[key] = value
    return result


def _apply_env_overrides(cfg: dict) -> None:
    """Apply environment variable overrides to config dict."""
    env_mappings = [
        ("RSSKB_BASE_DIR", None, "base_dir"),
        ("RSSKB_OPML_PATH", None, "opml_path"),
        ("GLM_API_KEY", "llm", "api_key"),
        ("GLM_HOST", "llm", "host"),
        ("GLM_MODELS", "llm", "models"),
    ]

    for env_var, section, key in env_mappings:
        value = os.environ.get(env_var)
        if value is None:
            continue

        if section is None:
            cfg[key] = value
        else:
            if section not in cfg:
                cfg[section] = {}
            if key == "models":
                cfg[section][key] = [m.strip() for m in value.split(",") if m.strip()]
            else:
                cfg[section][key] = value


def _format_validation_errors(error: ValidationError) -> str:
    """Format pydantic validation errors into user-friendly messages."""
    messages = []
    for err in error.errors():
        loc = " -> ".join(str(x) for x in err["loc"])
        msg = err["msg"]
        messages.append(f"  - {loc}: {msg}")
    return "\n".join(messages)
