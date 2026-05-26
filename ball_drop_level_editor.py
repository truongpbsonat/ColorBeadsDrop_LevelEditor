#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Launcher for the BallDropParty level editor."""

from __future__ import annotations

from ball_drop_editor.app import BallDropLevelEditor


def main():
    app = BallDropLevelEditor()
    app.mainloop()


if __name__ == "__main__":
    main()
