"""BallDropParty level editor package."""

__all__ = ["BallDropLevelEditor"]


def __getattr__(name):
    if name == "BallDropLevelEditor":
        from .app import BallDropLevelEditor

        return BallDropLevelEditor
    raise AttributeError(name)
