"""Bot whitelist — authorized user/chat management."""

import json
import os


def _whitelist_path(data_dir: str) -> str:
    return os.path.join(data_dir, "whitelist.json")


def load_whitelist(data_dir: str = "./data") -> set[int]:
    """Reads whitelist.json, returns set of chat_ids. Creates file with [] if missing."""
    path = _whitelist_path(data_dir)
    if not os.path.exists(path):
        os.makedirs(data_dir, exist_ok=True)
        with open(path, "w") as f:
            json.dump([], f)
        return set()
    try:
        with open(path, "r") as f:
            data = json.load(f)
        return set(int(x) for x in data)
    except (json.JSONDecodeError, ValueError, TypeError):
        with open(path, "w") as f:
            json.dump([], f)
        return set()


def save_whitelist(chat_ids: set[int], data_dir: str = "./data") -> None:
    """Writes whitelist.json."""
    path = _whitelist_path(data_dir)
    os.makedirs(data_dir, exist_ok=True)
    with open(path, "w") as f:
        json.dump(sorted(chat_ids), f)


def is_whitelisted(chat_id: int, admin_chat_id: int, data_dir: str = "./data") -> bool:
    """Returns True if chat_id is in whitelist OR is admin_chat_id."""
    if chat_id == admin_chat_id:
        return True
    return chat_id in load_whitelist(data_dir)


def add_to_whitelist(chat_id: int, data_dir: str = "./data") -> bool:
    """Adds chat_id to whitelist. Returns True if newly added, False if already present."""
    wl = load_whitelist(data_dir)
    if chat_id in wl:
        return False
    wl.add(chat_id)
    save_whitelist(wl, data_dir)
    return True


def remove_from_whitelist(chat_id: int, data_dir: str = "./data") -> bool:
    """Removes chat_id from whitelist. Returns True if was present, False if not found."""
    wl = load_whitelist(data_dir)
    if chat_id not in wl:
        return False
    wl.discard(chat_id)
    save_whitelist(wl, data_dir)
    return True
