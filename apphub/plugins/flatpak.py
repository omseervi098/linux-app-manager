import re
import os
import subprocess
from pathlib import Path

from apphub.core.exceptions import InstallError
from apphub.core.models import AppCategory, AppFormat, AppManifest
from apphub.plugins.base import PluginBase

_SIZE_UNITS = {
    "B": 1,
    "KB": 1024,
    "kB": 1024,
    "KiB": 1024,
    "MB": 1024**2,
    "MiB": 1024**2,
    "GB": 1024**3,
    "GiB": 1024**3,
    "TB": 1024**4,
    "TiB": 1024**4,
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
                size_bytes = self._get_exact_size(app_id) or (
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

    def _inspect_flatpak_bundle(self, path: str) -> AppManifest | None:
        try:
            result = subprocess.run(
                ["flatpak", "info", path],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                return None

            name = app_id = version = None

            for line in result.stdout.splitlines():
                if line.startswith("Name:"):
                    name = line.split(":", 1)[1].strip()
                elif line.startswith("ID:"):
                    app_id = line.split(":", 1)[1].strip()
                elif line.startswith("Version:"):
                    version = line.split(":", 1)[1].strip()

            return AppManifest(
                name=name or app_id,
                id=f"flatpak:{app_id}" if app_id else f"flatpak:{path}",
                format=AppFormat.FLATPAK,
                version=version or "unknown",
                publisher="bundle",
                installed=False,
                description=None,
                size_bytes=os.path.getsize(path),
                category=AppCategory.DESKTOP,
            )

        except Exception as e:
            self.logger.error(f"Flatpak bundle inspect error: {str(e)}")
            return None

    def inspect(self, path: str) -> AppManifest | None:
        try:
            if path.endswith(".flatpak"):
                return self._inspect_flatpak_bundle(path)

            return None

        except Exception as e:
            self.logger.error(f"Flatpak inspect error: {str(e)}")
            return None

    def search(self, query: str) -> list[AppManifest]:
        apps = []
        try:
            result = subprocess.run(
                ["flatpak", "search", query],
                capture_output=True,
                text=True,
            )

            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue

                parts = line.split("\t")
                if len(parts) < 3:
                    continue

                name = parts[0]
                description = parts[1] if len(parts) > 1 else ""
                app_id = parts[2]

                apps.append(
                    AppManifest(
                        name=name,
                        id=f"flatpak:{app_id}",
                        format=AppFormat.FLATPAK,
                        version="unknown",
                        installed=False,
                        publisher="flathub",
                        description=description,
                        category=AppCategory.DESKTOP,
                        size_bytes=None,
                    )
                )

        except Exception as e:
            self.logger.warning(f"Flatpak search failed: {e}")
            pass

        return apps

    def install(self, query_or_path: str, launch: bool) -> bool:
        path = Path(query_or_path)

        subprocess.run(
            [
                "flatpak",
                "remote-add",
                "--if-not-exists",
                "flathub",
                "https://dl.flathub.org/repo/flathub.flatpakrepo",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        if path.is_file() and path.exists():
            cmd = ["flatpak", "install", "-y", str(path.resolve())]
        else:
            app_id = query_or_path.lstrip("flatpak:")
            cmd = ["flatpak", "install", "-y", "flathub", app_id]

        try:
            subprocess.run(cmd, check=True)

            # Optional launch
            if launch and query_or_path:
                subprocess.Popen(
                    ["flatpak", "run", query_or_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )

            return True

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Flatpak install failed: {e}")
            raise InstallError(f"Flatpak installation failed: {query_or_path}")

    def uninstall(self, app_info: AppManifest, clean_uninstall: bool) -> bool:
        if not clean_uninstall:
            cmd = ["flatpak", "uninstall", app_info.name]
        else:
            cmd = [
                "flatpak",
                "uninstall",
                app_info.name,
                "--delete-data",
                "&&",
                "flatpak",
                "uninstall",
                "--unused",
            ]
        try:
            subprocess.run(cmd, check=True)
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Flatpak uninstall failed : {e}")
            return False
