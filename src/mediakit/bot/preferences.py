"""Bot preferences — per-user configuration storage."""

import json
import os
from datetime import datetime

DEFAULT_PREFERENCES = {"language": "en", "style": "detailed", "history": []}

VALID_STYLES = ("brief", "detailed")
VALID_PREF_KEYS = ("language", "style")


def _prefs_path(data_dir: str) -> str:
    return os.path.join(data_dir, "preferences.json")


def _load_all(data_dir: str) -> dict:
    path = _prefs_path(data_dir)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, ValueError, TypeError):
        return {}


def _save_all(data: dict, data_dir: str) -> None:
    path = _prefs_path(data_dir)
    os.makedirs(data_dir, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def get_preferences(chat_id: int, data_dir: str = "./data") -> dict:
    """Returns user prefs dict. Returns defaults if user has no saved prefs."""
    all_prefs = _load_all(data_dir)
    key = str(chat_id)
    if key not in all_prefs:
        return dict(DEFAULT_PREFERENCES)
    user_prefs = dict(DEFAULT_PREFERENCES)
    user_prefs.update(all_prefs[key])
    return user_prefs


def set_preference(chat_id: int, key: str, value: str, data_dir: str = "./data") -> None:
    """Updates a single preference key for a user. Persists to file."""
    if key not in VALID_PREF_KEYS:
        raise ValueError(f"Invalid preference key: {key}. Valid keys: {', '.join(VALID_PREF_KEYS)}")
    if key == "style" and value not in VALID_STYLES:
        raise ValueError(f"Invalid style: {value}. Valid options: {', '.join(VALID_STYLES)}")
    all_prefs = _load_all(data_dir)
    str_id = str(chat_id)
    if str_id not in all_prefs:
        all_prefs[str_id] = dict(DEFAULT_PREFERENCES)
    all_prefs[str_id][key] = value
    _save_all(all_prefs, data_dir)


def add_to_history(chat_id: int, item_info: dict, data_dir: str = "./data") -> None:
    """Appends item_info to user's history. Keeps last 20 entries."""
    all_prefs = _load_all(data_dir)
    str_id = str(chat_id)
    if str_id not in all_prefs:
        all_prefs[str_id] = dict(DEFAULT_PREFERENCES)
        all_prefs[str_id]["history"] = []
    history = all_prefs[str_id].get("history", [])
    item_info["processed_at"] = datetime.now().isoformat()
    history.append(item_info)
    all_prefs[str_id]["history"] = history[-20:]
    _save_all(all_prefs, data_dir)


def get_history(chat_id: int, data_dir: str = "./data") -> list[dict]:
    """Returns user's processing history list."""
    prefs = get_preferences(chat_id, data_dir)
    return prefs.get("history", [])
