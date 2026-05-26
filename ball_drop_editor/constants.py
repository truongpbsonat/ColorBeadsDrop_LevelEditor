from __future__ import annotations

BALL_COLORS = [
    "None", "Red", "Blue", "Yellow", "Green", "Purple",
    "Cyan", "Orange", "Pink", "Wild"
]

COLOR_HEX = {
    "None": "#BBBBBB",
    "Red": "#E74C3C",
    "Blue": "#3498DB",
    "Yellow": "#F1C40F",
    "Green": "#2ECC71",
    "Purple": "#9B59B6",
    "Cyan": "#00BCD4",
    "Orange": "#E67E22",
    "Pink": "#FF7EB6",
    "Wild": "#FFFFFF",
}

ENTITY_TYPES = ["Empty", "Shooter", "Wall", "Tunnel"]
RUNTIME_ENTITY_TYPES = ["Shooter", "Wall", "Tunnel"]
DIRECTIONS = ["Up", "Down", "Left", "Right"]
SHOOTER_MODIFIER_TYPES = ["Ice", "Hidden"]
GRID_OBSTACLE_TYPES = ["IceBlock"]
GRID_OBSTACLE_SHAPE_TYPES = ["Rect", "CustomCells", "Plus", "LineHorizontal", "LineVertical"]
SHOOTER_GROUP_TYPES = ["Connected", "Chain", "Pair"]
SHOOTER_GROUP_RULES = ["UnlockTogether", "SelectTogether", "RemoveTogether"]
GAME_MODES = ["Classic"]
LEVEL_DIFFICULTIES = ["Normal", "Hard", "SuperHard"]
