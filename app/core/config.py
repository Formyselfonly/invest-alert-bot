"""Invest Alert Bot module.

Author: Shijie Zheng (Kerry Zheng) — https://github.com/Formyselfonly
Repository: https://github.com/Formyselfonly/invest-alert-bot
"""

import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import ValidationError

from app.schemas.config import AppConfig

_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):

        def replacer(match: re.Match[str]) -> str:
            key = match.group(1)
            env_val = os.getenv(key)
            if env_val is None:
                msg = f"Environment variable {key} is not set"
                raise ValueError(msg)
            return env_val

        return _ENV_PATTERN.sub(replacer, value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    return value


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    load_dotenv()
    config_path = Path(path)
    if not config_path.exists():
        msg = f"Config file not found: {config_path}"
        raise FileNotFoundError(msg)

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    expanded = _expand_env(raw)

    try:
        return AppConfig.model_validate(expanded)
    except ValidationError as exc:
        msg = f"Invalid configuration: {exc}"
        raise ValueError(msg) from exc


def validate_telegram_credentials(config: AppConfig) -> None:
    token = config.telegram.bot_token.strip()
    chat_id = config.telegram.chat_id.strip()
    if not token or token.startswith("your_"):
        msg = (
            "TELEGRAM_BOT_TOKEN is missing. "
            "Create a bot via @BotFather and set .env — see readme.md."
        )
        raise ValueError(msg)
    if not chat_id or chat_id.startswith("your_"):
        msg = (
            "TELEGRAM_CHAT_ID is missing. "
            "Send /start to your bot and set .env — see readme.md."
        )
        raise ValueError(msg)


def get_config_path() -> Path:
    env_path = os.getenv("CONFIG_PATH")
    if env_path:
        return Path(env_path)
    return Path("config.yaml")
