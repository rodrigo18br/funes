from pathlib import Path

from funes import Embedder, SQLiteStore
from funes.cli import DEFAULT_DB_PATH, build_parser
from funes.interface.application import build_parser as build_interface_parser
from funes.search import SearchEngine


def test_search_api_is_importable_from_package() -> None:
    assert SearchEngine.__name__ == "SearchEngine"
    assert Embedder.__name__ == "Embedder"
    assert SQLiteStore.__name__ == "SQLiteStore"


def test_console_script_is_funes_cli() -> None:
    pyproject_path = Path(__file__).parents[1] / "pyproject.toml"
    scripts = {}
    in_scripts_section = False
    for line in pyproject_path.read_text().splitlines():
        if line == "[project.scripts]":
            in_scripts_section = True
            continue
        if line.startswith("["):
            in_scripts_section = False
        if in_scripts_section and "=" in line:
            name, target = line.split("=", 1)
            scripts[name.strip()] = target.strip().strip('"')

    assert scripts == {
        "funes-cli": "funes.cli:main",
        "funes": "funes.interface.application:main",
    }


def test_cli_parser_uses_funes_cli_program_name() -> None:
    parser = build_parser()

    assert parser.prog == "funes-cli"


def test_interface_parser_uses_cli_database_default() -> None:
    parser = build_interface_parser()
    args = parser.parse_args([])

    assert parser.prog == "funes"
    assert args.db == DEFAULT_DB_PATH
