"""Streamlit Community Cloud entry point."""

from pathlib import Path

_app = Path(__file__).with_name("bsi_assistant_app_2.py")
exec(compile(_app.read_text(encoding="utf-8"), str(_app), "exec"))
