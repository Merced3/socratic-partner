"""Minimal import smoke test; packaging/CLI execution still requires black-box coverage."""

import socratic_partner


def test_package_exposes_version() -> None:
    assert socratic_partner.__version__
