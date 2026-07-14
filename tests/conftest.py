from unittest.mock import patch

import pytest

from apphub.core.models import AppCategory, AppFormat, AppManifest, DistroInfo


@pytest.fixture(autouse=True)
def _stable_distro_info():
    """Plugins call detect_distro_info() in __init__; stub for macOS hosts."""
    info = DistroInfo(name="Ubuntu", id="ubuntu", version_id="24.04")
    with (
        patch("apphub.core.utils.detect_distro_info", return_value=info),
        patch("apphub.plugins.base.detect_distro_info", return_value=info),
    ):
        yield info


def make_manifest(
    name: str = "app",
    *,
    fmt: AppFormat = AppFormat.FLATPAK,
    version: str = "1.0",
    **kwargs,
) -> AppManifest:
    fields = {
        "name": name,
        "id": kwargs.get("id", f"{fmt.value}:{name}"),
        "version": version,
        "format": fmt,
        "category": kwargs.get("category", AppCategory.DESKTOP),
        "installed": kwargs.get("installed", True),
    }
    for key in ("size_bytes", "description", "publisher", "icon", "runtime"):
        if key in kwargs:
            fields[key] = kwargs[key]
    return AppManifest(**fields)
