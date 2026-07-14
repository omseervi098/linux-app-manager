from datetime import datetime, timezone
from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rich.console import Console
from typer.testing import CliRunner

from apphub.cli.banner import print_banner, render_logo
from apphub.cli.formatters import (
    _format_size,
    format_app_panel,
    format_app_table,
    format_history_table,
    format_storage_table,
)
from apphub.core.exceptions import AppNotFoundError
from apphub.core.models import (
    AppFormat,
    AppRuntime,
    DistroInfo,
    HistoryRecords,
    LifeCycleEvent,
)
from tests.conftest import make_manifest

_DISTRO = DistroInfo(name="Ubuntu", id="ubuntu", version_id="24.04")

with (
    patch("apphub.core.utils.detect_distro_info", return_value=_DISTRO),
    patch("apphub.plugins.base.detect_distro_info", return_value=_DISTRO),
    patch("apphub.core.hub.is_cmd_available", return_value=False),
):
    import apphub.cli.commands as commands_mod
    from apphub.cli.commands import cli_app
    from apphub.main import app as main_app


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def hub():
    mock = MagicMock()
    mock.list_apps = AsyncMock(
        return_value=[make_manifest("Firefox"), make_manifest("Chrome", version="2")]
    )
    mock.search = AsyncMock(return_value=[make_manifest("Firefox")])
    mock.inspect = AsyncMock(
        return_value=make_manifest("LocalApp", fmt=AppFormat.APPIMAGE)
    )
    mock.install = AsyncMock(return_value=True)
    mock.uninstall = AsyncMock(return_value=True)
    mock.info = AsyncMock(return_value=make_manifest("Firefox"))
    mock.storage = AsyncMock(
        return_value=[
            make_manifest("Big", size_bytes=5000),
            make_manifest("Tiny", size_bytes=None),
        ]
    )
    mock.history = AsyncMock(
        return_value=[
            HistoryRecords(
                timestamp=datetime(2026, 1, 2, tzinfo=timezone.utc),
                format=AppFormat.FLATPAK,
                lifecycle_event=LifeCycleEvent.INSTALLED,
                app_name="Firefox",
                version_id="1.0",
            ),
            HistoryRecords(
                timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
                format=AppFormat.SNAP,
                lifecycle_event=LifeCycleEvent.UPGRADED,
                app_name="vlc",
                version_id="2.0",
                old_version_id="1.0",
            ),
        ]
    )
    with patch.object(commands_mod, "hub", mock):
        yield mock


def test_banner_and_main(runner):
    assert "██" in render_logo().plain
    buf = StringIO()
    c = Console(file=buf, force_terminal=True, width=100, color_system=None)
    print_banner(c)
    print_banner(c, show_panel=False)
    assert "linman" in buf.getvalue().lower() or "██" in buf.getvalue()

    r = runner.invoke(main_app, [])
    assert r.exit_code == 0 and ("██" in r.stdout or "list" in r.stdout)
    r = runner.invoke(main_app, ["--version"])
    assert r.exit_code == 0 and "0.1.0" in r.stdout
    r = runner.invoke(main_app, ["--help"])
    assert r.exit_code == 0


def test_formatters():
    assert _format_size(None) == "—"
    assert _format_size(512).endswith("B")
    assert _format_size(1024**4).endswith("TB")
    app = make_manifest(
        "A",
        fmt=AppFormat.DEBIAN,
        description="hi",
        icon="/i.png",
        runtime=AppRuntime.ELECTRON,
        publisher="me",
    )
    assert format_app_table([app]).row_count == 1
    body = str(format_app_panel(app).renderable)
    assert "hi" in body and "electron" in body
    assert (
        format_history_table(
            [
                HistoryRecords(
                    timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    format=AppFormat.SNAP,
                    lifecycle_event=LifeCycleEvent.UPGRADED,
                    app_name="v",
                    version_id="2",
                    old_version_id="1",
                )
            ]
        ).row_count
        == 1
    )
    apps = [
        make_manifest("Big", size_bytes=99),
        make_manifest("U", size_bytes=None),
        make_manifest("S", size_bytes=1),
    ]
    assert format_storage_table(apps, top=2).row_count == 2


def test_cli_read_commands(runner, hub, tmp_path):
    assert runner.invoke(cli_app, ["list"]).exit_code == 0
    assert "2" in runner.invoke(cli_app, ["list", "--count"]).stdout
    assert (
        "Firefox" in runner.invoke(cli_app, ["list", "--json", "--sort", "name"]).stdout
    )
    assert runner.invoke(cli_app, ["search", "fire"]).exit_code == 0
    assert "1" in runner.invoke(cli_app, ["search", "fire", "-n"]).stdout
    assert "Firefox" in runner.invoke(cli_app, ["search", "fire", "--json"]).stdout

    assert runner.invoke(cli_app, ["inspect", str(tmp_path / "no.deb")]).exit_code == 1
    f = tmp_path / "a.AppImage"
    f.write_bytes(b"x")
    assert runner.invoke(cli_app, ["inspect", str(f)]).exit_code == 0
    assert "LocalApp" in runner.invoke(cli_app, ["inspect", str(f), "--json"]).stdout

    assert runner.invoke(cli_app, ["info", "Firefox"]).exit_code == 0
    assert "Firefox" in runner.invoke(cli_app, ["info", "Firefox", "--json"]).stdout
    hub.info = AsyncMock(side_effect=AppNotFoundError("x"))
    assert runner.invoke(cli_app, ["info", "x"]).exit_code == 1

    assert "Big" in runner.invoke(cli_app, ["storage"]).stdout
    assert runner.invoke(cli_app, ["storage", "--json", "--top", "1"]).exit_code == 0
    assert "Firefox" in runner.invoke(cli_app, ["history"]).stdout
    assert (
        runner.invoke(
            cli_app, ["history", "--json", "--sort", "app_name", "--desc", "--top", "1"]
        ).exit_code
        == 0
    )


def test_cli_install_uninstall(runner, hub, tmp_path):
    f = tmp_path / "p.AppImage"
    f.write_bytes(b"x")
    r = runner.invoke(cli_app, ["install", str(f), "-y"])
    assert r.exit_code == 0 and "successful" in r.stdout

    hub.search = AsyncMock(return_value=[make_manifest("Firefox")])
    assert "successful" in runner.invoke(cli_app, ["install", "Firefox", "-y"]).stdout
    assert (
        "cancelled"
        in runner.invoke(cli_app, ["install", "Firefox"], input="n\n").stdout.lower()
    )

    hub.search = AsyncMock(
        return_value=[make_manifest("A"), make_manifest("B", fmt=AppFormat.SNAP)]
    )
    assert runner.invoke(cli_app, ["install", "app", "-y"], input="1\n").exit_code == 0
    assert runner.invoke(cli_app, ["install", "app", "-y"], input="99\n").exit_code == 1
    hub.search = AsyncMock(return_value=[])
    assert runner.invoke(cli_app, ["install", "nope", "-y"]).exit_code == 1

    hub.list_apps = AsyncMock(return_value=[make_manifest("Firefox")])
    assert (
        "Successfully" in runner.invoke(cli_app, ["uninstall", "Firefox", "-y"]).stdout
    )
    hub.uninstall = AsyncMock(return_value=False)
    assert "Failed" in runner.invoke(cli_app, ["uninstall", "Firefox", "-y"]).stdout
    hub.list_apps = AsyncMock(return_value=[])
    assert runner.invoke(cli_app, ["uninstall", "x", "-y"]).exit_code == 1
    hub.list_apps = AsyncMock(return_value=[make_manifest("A"), make_manifest("B")])
    hub.uninstall = AsyncMock(return_value=True)
    assert runner.invoke(cli_app, ["uninstall", "x", "-y"], input="2\n").exit_code == 0
    hub.list_apps = AsyncMock(return_value=[make_manifest("Firefox")])
    assert runner.invoke(cli_app, ["uninstall", "Firefox"], input="n\n").exit_code == 1

    assert (
        commands_mod._prompt_select_app([make_manifest("Only")], "Only", "i").name
        == "Only"
    )
