"""PyQt interface for Funes."""

from .application import build_application, main
from .main_window import MainWindow

__all__ = ["MainWindow", "build_application", "main"]
