from __future__ import annotations

BALL_COLORS = [
    "None", "Black", "Blue", "Brown", "Cyan", "Gray", "Green",
    "LightPink", "Lime", "Orange", "Periwinkle", "Pink", "Purple",
    "Red", "Teal", "Violet", "White", "Yellow", "LightBeige",
    "LightRed", "DarkGreen", "Wild"
]

COLOR_HEX = {
    "None": "#BBBBBB",
    "Black": "#2E2D33",
    "Blue": "#3361FA",
    "Brown": "#6B4A2D",
    "Cyan": "#32E0F1",
    "Gray": "#788CB1",
    "Green": "#2CC32C",
    "LightPink": "#FFB6C1",
    "Lime": "#B1ED19",
    "Orange": "#FF8122",
    "Periwinkle": "#9DB2FD",
    "Pink": "#FA68BD",
    "Purple": "#9851F5",
    "Red": "#FF4A50",
    "Teal": "#12AF89",
    "Violet": "#ED66FF",
    "White": "#DBDCDC",
    "Yellow": "#FFE10C",
    "LightBeige": "#F2D9B6",
    "LightRed": "#FE567E",
    "DarkGreen": "#1E7A3A",
    "Wild": "#FFFFFF",
}

ENTITY_TYPES = ["Empty", "Shooter", "Wall", "Tunnel"]
RUNTIME_ENTITY_TYPES = ["Shooter", "Wall", "Tunnel"]
DIRECTIONS = ["Up", "Down", "Left", "Right"]
SHOOTER_MODIFIER_TYPES = ["Ice", "Hidden", "Special", "Hammer", "Arrow", "Shutter"]
SHOOTER_FIXED_CAPACITY = 9
TRAY_MODIFIER_TYPES = ["Ice", "RemoteConnected", "Hidden"]
TRAY_ICE_DEFAULT_HP = 2
GRID_OBSTACLE_TYPES = ["IceBlock", "LockBar", "GlassBarrier"]
GLASS_BARRIER_DEFAULT_LENGTH = 3
GRID_OBSTACLE_SHAPE_TYPES = ["Rect", "CustomCells", "Plus", "LineHorizontal", "LineVertical"]
SHOOTER_GROUP_TYPES = ["Connected", "Chain", "Pair"]
GAME_MODES = ["Classic"]
LEVEL_DIFFICULTIES = ["Normal", "Hard", "SuperHard"]
LEVEL_DIFFICULTY_LABELS = {
    "Normal": "Normal",
    "Hard": "Hard",
    "SuperHard": "Super Hard",
}


def canonical_level_difficulty(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    compact = "".join(char for char in text.lower() if char.isalnum())
    lookup = {
        "".join(char for char in difficulty.lower() if char.isalnum()): difficulty
        for difficulty in LEVEL_DIFFICULTIES
    }
    return lookup.get(compact)


def normalize_level_difficulty(value: object, default: str = "Normal") -> str:
    return canonical_level_difficulty(value) or default

# Canonical mechanic ids. Keep in sync with BallDropMechanicIds.cs and the MechanicCatalogConfig asset.
MECHANIC_IDS = [
    "Tunnel",
    "IceShooter",
    "HiddenShooter",
    "IceTray",
    "LockBar",
    "ConnectedShooter",
    "IceBlock",
    "SpecialShooter",
    "GlassBarrier",
    "ConnectedTray",
    "HiddenTray",
    "ArrowShooter",
    "ShutterShooter",
]

MECHANIC_ID_ALIASES = {
    "LinkedShooter": "ConnectedShooter",
}
