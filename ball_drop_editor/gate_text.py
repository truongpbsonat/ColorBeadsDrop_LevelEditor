from __future__ import annotations

from typing import Any, Dict, List

from .constants import BALL_COLORS
from .utils import safe_int, short_id

def parse_gate_text(text: str, gate_count: int) -> List[Dict[str, Any]]:
    """
    User-friendly syntax.

    One gate per section:
        Gate 0:
        t_001: Blue3, Orange3, Purple3
        t_002: Red5

        Gate 1:
        Blue4, Red4

    Tray line formats:
        trayId: Blue3, Orange3
        Blue3, Orange3          -> auto trayId
        Blue:3, Orange:3
        Blue 3, Orange 3
    """
    gates = [{"gateIndex": i, "trayQueue": []} for i in range(gate_count)]
    current_gate = 0

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        lowered = line.lower()
        if lowered.startswith("gate"):
            digits = "".join(ch if ch.isdigit() else " " for ch in line).split()
            if digits:
                gi = safe_int(digits[0], current_gate)
                if 0 <= gi < gate_count:
                    current_gate = gi
            continue

        tray_id = short_id("t")
        payload = line
        if ":" in line:
            first, rest = line.split(":", 1)
            # If first part looks like a tray id, use it. Otherwise it is probably Blue:3.
            if first.strip().lower().startswith("t"):
                tray_id = first.strip()
                payload = rest.strip()

        layers = parse_layers(payload)
        if layers:
            gates[current_gate]["trayQueue"].append({
                "trayId": tray_id,
                "layers": layers
            })
    return gates


def parse_layers(text: str) -> List[Dict[str, Any]]:
    layers = []
    parts = [p.strip() for p in text.split(",") if p.strip()]
    for part in parts:
        color = None
        count = None

        if ":" in part:
            c, n = part.split(":", 1)
            color = c.strip()
            count = safe_int(n.strip(), 0)
        else:
            tokens = part.split()
            if len(tokens) >= 2:
                color = tokens[0].strip()
                count = safe_int(tokens[1], 0)
            else:
                # Support Blue3 / Orange10
                letters = "".join(ch for ch in part if ch.isalpha())
                digits = "".join(ch for ch in part if ch.isdigit())
                color = letters.strip()
                count = safe_int(digits, 0)

        if color in BALL_COLORS and color != "None" and count and count > 0:
            layers.append({"colorId": color, "requiredCount": count})
    return layers


def gates_to_text(gates: List[Dict[str, Any]]) -> str:
    lines = []
    for gate in gates:
        lines.append(f"Gate {gate.get('gateIndex', 0)}:")
        for tray in gate.get("trayQueue", []):
            layers = tray.get("layers", [])
            layer_text = ", ".join(f"{l.get('colorId')}:{l.get('requiredCount')}" for l in layers)
            lines.append(f"{tray.get('trayId', short_id('t'))}: {layer_text}")
        lines.append("")
    return "\n".join(lines)


