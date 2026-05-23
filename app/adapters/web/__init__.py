"""Dedicated web views module."""

from app.adapters.web.routes import router
from app.adapters.web.web_module import register_web_module

__all__ = ["router", "register_web_module"]
