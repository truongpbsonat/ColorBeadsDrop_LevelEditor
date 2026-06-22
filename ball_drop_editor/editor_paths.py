from __future__ import annotations

import json
import os
from typing import List

DEFAULT_LEVEL_SAVE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Levels"))
ICON_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Icon"))

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".balldrop_level_editor")
RECENT_FOLDERS_PATH = os.path.join(CONFIG_DIR, "recent_folders.json")
RECENT_FOLDERS_LIMIT = 12


def load_recent_folders() -> List[str]:
    """Read the persisted recent-folder list, keeping only existing directories."""
    try:
        with open(RECENT_FOLDERS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []

    folders: List[str] = []
    seen = set()
    for item in data:
        if not isinstance(item, str):
            continue
        path = os.path.abspath(item.strip())
        if not path or not os.path.isdir(path):
            continue
        key = os.path.normcase(path)
        if key in seen:
            continue
        seen.add(key)
        folders.append(path)
        if len(folders) >= RECENT_FOLDERS_LIMIT:
            break
    return folders


def save_recent_folders(folders: List[str]) -> None:
    """Persist the recent-folder list (best effort, never raises)."""
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(RECENT_FOLDERS_PATH, "w", encoding="utf-8") as f:
            json.dump(folders[:RECENT_FOLDERS_LIMIT], f, ensure_ascii=False, indent=2)
    except OSError:
        pass
