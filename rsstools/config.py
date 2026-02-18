"""Configuration management for RSSTools"""

import os
import copy
import json

DEFAULT_CONFIG = {
    "base_dir": "~/RSSKB",
    "opml_path": "",
    "llm": {
        "api_key": "",
        "host": "https://api.z.ai/api/coding/paas/v4",
        "models": "glm-5,glm-4.7",
        "max_tokens": 2048,
        "temperature": 0.3,
        "max_content_chars": 10000,
        "request_delay": 0.5,
        "max_retries": 5,
        "timeout": 60,
        "system_prompt": "You are a helpful assistant that summarizes articles concisely.",
        "user_prompt": (
            "Summarize this article in 2-3 sentences, "
            "in the same language as the article.\n\nTitle: {title}\n\n{content}"
        ),
    },
    "download": {
        "timeout": 15,
        "connect_timeout": 5,
        "max_retries": 3,
        "retry_delay": 2,
        "concurrent_downloads": 5,
        "concurrent_feeds": 3,
        "max_redirects": 5,
        "etag_max_age_days": 30,
        "user_agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    },
    "summarize": {
        "save_every": 20,
    },
}


def load_config() -> dict:
    """Load config from ~/.rsstools/config.json, merge with defaults."""
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    config_path = os.path.expanduser("~/.rsstools/config.json")
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            user_cfg = json.load(f)
        for section, values in user_cfg.items():
            if isinstance(values, dict) and section in cfg and isinstance(cfg[section], dict):
                cfg[section].update(values)
            else:
                cfg[section] = values
    # Env var overrides
    if os.environ.get("RSSKB_BASE_DIR"):
        cfg["base_dir"] = os.environ["RSSKB_BASE_DIR"]
    if os.environ.get("GLM_API_KEY"):
        cfg["llm"]["api_key"] = os.environ["GLM_API_KEY"]
    if os.environ.get("GLM_HOST"):
        cfg["llm"]["host"] = os.environ["GLM_HOST"]
    if os.environ.get("GLM_MODELS"):
        cfg["llm"]["models"] = os.environ["GLM_MODELS"]
    if os.environ.get("RSSKB_OPML_PATH"):
        cfg["opml_path"] = os.environ["RSSKB_OPML_PATH"]
    cfg["base_dir"] = os.path.expanduser(cfg["base_dir"])
    # Default opml_path to {base_dir}/subscriptions.opml if not set
    if not cfg["opml_path"]:
        cfg["opml_path"] = os.path.join(cfg["base_dir"], "subscriptions.opml")
    else:
        cfg["opml_path"] = os.path.expanduser(cfg["opml_path"])
    return cfg
