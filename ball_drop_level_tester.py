#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Launcher for the BallDropParty level tester."""

from __future__ import annotations

import sys
import tkinter as tk

from ball_drop_editor.level_tester_app import LevelTesterWindow


def main() -> None:
    initial_path = sys.argv[1] if len(sys.argv) > 1 else None
    root = tk.Tk()
    root.withdraw()
    window = LevelTesterWindow(root, initial_path=initial_path)
    window.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()


if __name__ == "__main__":
    main()
