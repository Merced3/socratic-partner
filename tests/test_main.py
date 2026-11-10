"""Installed-entrypoint composition contracts for operational state."""

from types import SimpleNamespace
from unittest.mock import patch

from socratic_partner import main as entrypoint


def test_main_constructs_harness_from_environment():
    """The CLI must not silently choose SQLite when a managed harness DB is configured."""
    captured = {}

    class FakeHarness:
        def __init__(self, config, *, name):
            captured["config"] = config
            captured["name"] = name

        def add_service(self, name, service):
            captured["service"] = (name, service)

        def run(self):
            captured["ran"] = True

    fake_settings = SimpleNamespace(log_level="INFO")
    with (
        patch.object(entrypoint.Settings, "from_environment", return_value=fake_settings),
        patch.object(entrypoint, "Harness", FakeHarness),
        patch.dict(
            "os.environ",
            {
                "HARNESS_DATABASE_URL": "postgresql://unit-test.invalid/harness_socratic",
                "AUTOMATION_HARNESS_DATA_DIR": "/runtime/socratic",
            },
        ),
    ):
        entrypoint.main()

    assert captured["ran"] is True
    assert captured["name"] == "socratic-partner"
    assert captured["config"].database_url == "postgresql://unit-test.invalid/harness_socratic"
    assert captured["config"].database_path.as_posix() == "/runtime/socratic/harness.db"
