"""
Vercel's Python runtime auto-detects an entrypoint at one of: app.py, index.py,
server.py, main.py, wsgi.py, asgi.py — and loads a top-level `app` variable
from whichever one it finds. This file exists only so Vercel finds it at the
project root; the real application lives in app/main.py and is unchanged
either way you run it.
"""

from app.main import app
