"""Shared bot config: allow-list, automations, per-chat notifications, clocks."""

import copy
import json
import os
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "bot_config.json"
LEGACY_OFFSET = ROOT / ".store"

EMPTY_FLAGS = {
    "incoming": False,
    "storage": False,
    "farm_list": False,
    "build": False,
    "adventure": False,
    "tasks": False,
}

DEFAULTS = {
    "allow_chat_ids": [],
    "automations": {
        "farm_list": {
            "enabled": False,
            "interval_min": 600,
            "interval_max": 900,
            "last_sent": {},
        },
        "build": {
            "enabled": False,
            "interval_min": 60,
            "interval_max": 180,
            "preset": "settler",
            "cursor": {"line": 0, "progress": 0},
            "watch_video": False,
            "use_inventory": False,
        },
        "adventure": {"enabled": False, "interval_min": 600, "interval_max": 900},
        "tasks": {
            "enabled": False,
            "daily_enabled": False,
            "interval_min": 600,
            "interval_max": 900,
        },
    },
    "notifications": {},
    "clocks": {},
    "conditions": {},
    "update_id": None,
}

_lock = threading.Lock()


def _legacy_update_id():
    if not LEGACY_OFFSET.is_file():
        return None
    for line in LEGACY_OFFSET.read_text().splitlines():
        if line.startswith("update_id="):
            value = line.split("=", 1)[1].strip()
            return int(value) if value.isdigit() else None
    return None


def _merge(saved: dict) -> dict:
    data = copy.deepcopy(DEFAULTS)
    data["allow_chat_ids"] = [str(item) for item in saved.get("allow_chat_ids", [])]
    env_chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if env_chat and env_chat not in data["allow_chat_ids"]:
        data["allow_chat_ids"].append(env_chat)
    for name, defaults in DEFAULTS["automations"].items():
        current = dict(defaults)
        current.update(saved.get("automations", {}).get(name) or {})
        if "cursor" in defaults:
            cursor = current.get("cursor") or {}
            current["cursor"] = {
                "line": int(cursor.get("line") or 0),
                "progress": int(cursor.get("progress") or 0),
            }
        if "last_sent" in defaults:
            raw = current.get("last_sent") or {}
            current["last_sent"] = {
                str(key): float(value)
                for key, value in raw.items()
                if value is not None
            }
        data["automations"][name] = current
    data["notifications"] = {
        str(chat_id): {**EMPTY_FLAGS, **(flags or {})}
        for chat_id, flags in (saved.get("notifications") or {}).items()
    }
    data["clocks"] = dict(saved.get("clocks") or {})
    data["conditions"] = {
        str(chat_id): dict(values or {})
        for chat_id, values in (saved.get("conditions") or {}).items()
    }
    data["update_id"] = saved.get("update_id")
    if data["update_id"] is None:
        data["update_id"] = _legacy_update_id()
    return data


def _read() -> dict:
    if not PATH.is_file():
        return _merge({})
    try:
        return _merge(json.loads(PATH.read_text()))
    except (OSError, json.JSONDecodeError):
        return _merge({})


def _write(data: dict) -> None:
    PATH.write_text(json.dumps(data, indent=2) + "\n")


_cache = _read()
_write(_cache)


def resolve(data: dict | None = None) -> dict:
    """Return config with defaults filled in."""
    if data is None:
        return load()
    return _merge(data)


def load() -> dict:
    with _lock:
        return copy.deepcopy(_cache)


def update(mutator) -> dict:
    with _lock:
        mutator(_cache)
        _cache.update(_merge(_cache))
        _write(_cache)
        return copy.deepcopy(_cache)


def allow_chat(chat_id) -> None:
    chat_id = str(chat_id)
    if not chat_id:
        return

    def mutate(config):
        ids = [str(item) for item in config["allow_chat_ids"]]
        if chat_id not in ids:
            ids.append(chat_id)
        config["allow_chat_ids"] = ids

    update(mutate)


def allowed(chat_id, data: dict | None = None) -> bool:
    config = data if data is not None else load()
    return str(chat_id) in {str(item) for item in config["allow_chat_ids"]}


def flags(data: dict, chat_id) -> dict:
    return {**EMPTY_FLAGS, **(data["notifications"].get(str(chat_id)) or {})}
