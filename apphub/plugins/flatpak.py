import re
import os
from pathlib import Path
from datetime import datetime, timezone

from apphub.core.models import AppCategory, AppFormat, AppManifest, LifeCycleEvent, HistoryRecords
from apphub.core.utils import run_cmd
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
    async def _get_exact_size(self, app_id: str) -> int | None:
        try:
            code, stdout, stderr = await run_cmd("flatpak", "info", "--show-size", app_id)
            output = stdout.strip()

            if output.isdigit():
                return int(output)

            return _parse_flatpak_size(output)

        except Exception as e:
            self.logger.error(f"Flatpak Error while extracting size: {str(e)}")
            return None

    async def list_apps(self) -> list[AppManifest]:
        apps = []

        try:
            _, stdout, stderr = await run_cmd("flatpak", "list")

            for line in stdout.strip().split("\n"):
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
                size_str = parts[5].strip() if len(parts) > 5 else "-"
                ref = parts[6].strip() if len(parts) > 6 else ""

                # Prefer exact size
                size_bytes = await self._get_exact_size(app_id) or _parse_flatpak_size(size_str)

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

    async def _inspect_flatpak_bundle(self, path: str) -> AppManifest | None:
        try:
            code, stdout, stderr = await run_cmd("flatpak", "info", path)

            if code != 0:
                return None

            name = app_id = version = None

            for line in stdout.splitlines():
                if line.startswith("Name:"):
                    name = line.split(":", 1)[1].strip()
                elif line.startswith("ID:"):
                    app_id = line.split(":", 1)[1].strip()
                elif line.startswith("Version:"):
                    version = line.split(":", 1)[1].strip()

            return AppManifest(
                name=name or app_id or "unknown",
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

    async def inspect(self, path: str) -> AppManifest | None:
        try:
            if path.endswith(".flatpak"):
                return await self._inspect_flatpak_bundle(path)

            return None

        except Exception as e:
            self.logger.error(f"Flatpak inspect error: {str(e)}")
            return None

    async def search(self, query: str) -> list[AppManifest]:
        apps = []
        try:
            code, stdout, stderr = await run_cmd("flatpak", "search", query)

            for line in stdout.strip().split("\n"):
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

    async def install(self, query_or_path: str, launch: bool) -> bool:
        path = Path(query_or_path)

        await run_cmd("flatpak", "remote-add", "--if-not-exists", "flathub", "https://dl.flathub.org/repo/flathub.flatpakrepo")

        if path.is_file() and path.exists():
            cmd = ["flatpak", "install", "-y", str(path.resolve())]
        else:
            app_id = query_or_path.lstrip("flatpak:")
            cmd = ["flatpak", "install", "-y", "flathub", app_id]

        code, _, stderr = await run_cmd(*cmd)
        if code != 0:
            self.logger.error(f"Flatpak install failed: {stderr}")
            return False

        if launch and query_or_path:
            code_launch, _, stderr_launch = await run_cmd("flatpak", "run", query_or_path)
            if code_launch != 0:
                self.logger.error(f"Flatpak launch failed: {stderr_launch}")
                return False

        return True

    async def uninstall(self, app_info: AppManifest, clean_uninstall: bool) -> bool:
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
        code, _, stderr = await run_cmd(*cmd)
        if code != 0:
            self.logger.error(f"Flatpak uninstall failed: {stderr}")
            return False
        return True

    async def history(self, action_categories: list[LifeCycleEvent] | None = None) -> list[HistoryRecords]:
        code, stdout, stderr = await run_cmd(*["flatpak", "history", "--columns=time,change,application,commit,old-commit"])
        if code != 0:
            self.logger.error(f"Flatpak History Failed : {stderr}")
            return []

        change_map = {
            "install": LifeCycleEvent.INSTALLED,
            "update": LifeCycleEvent.UPGRADED,
            "uninstall": LifeCycleEvent.UNINSTALLED,
        }
        records = []

        for line in stdout.strip().splitlines():
            if not line or line.startswith("Time"):
                continue

            parts = [item.strip() for item in line.split("\t")]
            if len(parts) < 3:
                continue

            time_str, change_str, app_name = parts[0], parts[1], parts[2]
            commit = parts[3] if len(parts) > 3 and parts[3] != "-" else None
            old_commit = parts[4] if len(parts) > 4 and parts[4] != "-" else None

            event_type = None
            for verb, enum_val in change_map.items():
                if change_str.lower().find(verb) != -1:
                    event_type = enum_val
                    break

            if not event_type:
                continue

            records.append(
                HistoryRecords(
                    timestamp=datetime.strptime(f"2026 {time_str}", "%Y %b\u2007%d %H:%M:%S").replace(tzinfo=timezone.utc),
                    format=AppFormat.FLATPAK,
                    lifecycle_event=event_type,
                    app_name=app_name,
                    version_id=commit,
                    old_version_id=old_commit,
                )
            )

        return sorted(records, key=lambda x: x.timestamp)