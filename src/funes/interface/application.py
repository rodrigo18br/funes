"""Application entrypoint for the PyQt interface."""
from __future__ import annotations

import argparse
import sys
import locale
from pathlib import Path
from typing import Optional, Sequence

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QLocale

from funes.cli import DEFAULT_DB_PATH

from .main_window import MainWindow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="funes",
        description="Launch the Funes desktop interface.",
    )
    parser.add_argument(
        "--db",
        default=DEFAULT_DB_PATH,
        help="path to the SQLite index file (default: %(default)s)",
    )
    return parser


def build_application(db_path: str | Path = DEFAULT_DB_PATH) -> tuple[QApplication, MainWindow]:
    """Create the Qt application and main window without starting the event loop."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    QLocale.setDefault(QLocale(locale.setlocale(locale.LC_ALL, 'C')))

    window = MainWindow(db_path=Path(db_path))
    window.show()
    return app, window


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    app, _window = build_application(args.db)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
