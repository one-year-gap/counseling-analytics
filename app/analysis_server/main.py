"""Backward-compatible alias for the unified intelligence server runtime."""

from app.realtime.main import app, create_app, run

__all__ = ["app", "create_app", "run"]
