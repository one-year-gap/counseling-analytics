"""Backward-compatible entrypoint.

Prefer `app.realtime.main` for the unified intelligence server.
"""

from app.realtime.main import app, run


if __name__ == "__main__":
    run()
