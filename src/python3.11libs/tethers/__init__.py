"""Tether network editor items to a leader by position."""

__version__ = "0.1.0"


def install():
    """Hook the network editor and the hip callbacks. Called from uiready.py."""
    from tethers import core, editor
    editor.install()
    core.install_hip_callbacks()
