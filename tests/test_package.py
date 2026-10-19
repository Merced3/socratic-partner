"""Minimal import smoke test; packaging/CLI execution still requires black-box coverage."""

import tomllib
from pathlib import Path

import socratic_partner


def test_package_exposes_version() -> None:
    assert socratic_partner.__version__


def test_package_version_matches_project_metadata() -> None:
    """Runtime status must not report a stale release after packaging metadata moves."""
    pyproject = Path(__file__).parents[1] / "pyproject.toml"
    expected = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]

    assert socratic_partner.__version__ == expected
