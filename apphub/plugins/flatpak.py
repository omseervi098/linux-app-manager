import re
import subprocess
from apphub.core.models import AppCategory, AppFormat, AppManifest
from apphub.plugins.base import PluginBase

_SIZE_UNITS = {
    "B": 1,
    "KB": 1024, "kB": 1024, "KiB": 1024,
    "MB": 1024**2, "MiB": 1024**2,
    "GB": 1024**3, "GiB": 1024**3,
    "TB": 1024**4, "TiB": 1024**4,
    "bytes": 1,
}


def _parse_flatpak_size(size_str: str) -> int | None:
    if not size_str or size_str == "-":
        return None

    match = re.match(r"([\d.]+)\s*(\S+)", size_str.strip())
    if not match:
        return None

    try:
        value = float(match.group(1))
        unit = match.group(2)
        multiplier = _SIZE_UNITS.get(unit, _SIZE_UNITS.get(unit.upper(), 1))
        return int(value * multiplier)
    except (ValueError, TypeError):
        return None


def _categorize_flatpak(ref: str, app_id: str) -> AppCategory:
    if ref.startswith("runtime/"):
        return AppCategory.SYSTEM
    return AppCategory.DESKTOP


class FlatpakPlugin(PluginBase):
    def _get_exact_size(self, app_id: str) -> int | None:
        try:
            result = subprocess.run(
                ["flatpak", "info", "--show-size", app_id],
                capture_output=True,
                text=True,
            )
            output = result.stdout.strip()

            if output.isdigit():
                return int(output)

            return _parse_flatpak_size(output)

        except Exception as e:
            self.logger.error(f"Flatpak Error while extracting size: {str(e)}")
            return None

    def list_apps(self) -> list[AppManifest]:
        apps = []

        try:
            results = subprocess.run(
                ["flatpak", "list"],
                capture_output=True,
                text=True,
            )

            for line in results.stdout.strip().split("\n"):
                if not line:
                    continue

                parts = line.split("\t")
                if len(parts) < 4:
                    continue

                name = parts[0]
                app_id = parts[1]
                version = parts[2]
                origin = parts[3]
                description = parts[4].strip() if len(parts) > 4 else None
                size_str = parts[5].strip() if len(parts) > 5 else None
                ref = parts[6].strip() if len(parts) > 6 else ""

                # Prefer exact size
                size_bytes = _get_exact_size(app_id) or (
                    _parse_flatpak_size(size_str) if size_str else None
                )

                apps.append(
                    AppManifest(
                        name=name,
                        id=f"flatpak:{app_id}",
                        format=AppFormat.FLATPAK,
                        version=version or "unknown",
                        publisher=origin,
                        installed=True,
                        description=description or None,
                        size_bytes=size_bytes,
                        category=_categorize_flatpak(ref, app_id),
                    )
                )

        except Exception as e:
            self.logger.warning(f"Flatpak Error while listing apps: {str(e)}")
            pass

        return apps