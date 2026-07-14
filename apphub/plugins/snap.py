import os
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

from apphub.core.models import (
    AppCategory,
    AppFormat,
    AppManifest,
    HistoryRecords,
    LifeCycleEvent,
)
from apphub.core.utils import is_cmd_available, run_cmd
from apphub.plugins.base import PluginBase


class SnapPlugin(PluginBase):
    def _read_snap_meta(self, name: str) -> tuple[str | None, AppCategory]:
        meta = Path(f"/snap/{name}/current/meta/snap.yaml")
        summary: str | None = None
        snap_type: str = "app"

        try:
            if not meta.exists():
                return None, AppCategory.CLI
            for line in meta.read_text().splitlines():
                stripped = line.strip()
                if stripped.startswith("summary:"):
                    summary = stripped.split(":", 1)[1].strip().strip("'\"")
                elif stripped.startswith("type:"):
                    snap_type = stripped.split(":", 1)[1].strip().strip("'\"")
        except (OSError, PermissionError) as e:
            self.logger.warning(f"Snap metadata extraction failed: {e}")
            pass

        if snap_type in ("base", "core", "snapd", "kernel", "gadget"):
            category = AppCategory.SYSTEM
        else:
            desktop_dir = Path(f"/snap/{name}/current/meta/gui")
            has_desktop = False
            try:
                if desktop_dir.exists():
                    has_desktop = any(
                        f.suffix == ".desktop" for f in desktop_dir.iterdir()
                    )
            except (OSError, PermissionError):
                pass
            category = AppCategory.DESKTOP if has_desktop else AppCategory.CLI
        return summary, category

    # TODO: get actual size + package size , also change it in AppManifest
    def _get_snap_size(self, name: str, revision: str) -> int | None:
        snap_file = Path(f"/var/lib/snapd/snaps/{name}_{revision}.snap")
        try:
            if snap_file.exists():
                return snap_file.stat().st_size
        except (OSError, PermissionError) as e:
            self.logger.warning(f"Snap size extraction failed: {e}")
            pass
        return None

    async def list_apps(self) -> list[AppManifest]:
        apps = []
        try:
            _, stdout, _ = await run_cmd("snap", "list")
            for line in stdout.strip().split("\n")[1:]:
                parts = line.split()
                if len(parts) < 6:
                    continue
                name, version, revision, _, publisher, _ = parts

                summary, category = self._read_snap_meta(name)

                apps.append(
                    AppManifest(
                        name=name,
                        id=f"snap:{name}",
                        format=AppFormat.SNAP,
                        version=version,
                        installed=True,
                        publisher=publisher.rstrip("*"),
                        description=summary,
                        category=category,
                        size_bytes=self._get_snap_size(name, revision),
                    )
                )
        except Exception as e:
            self.logger.warning(f"Snap list failed: {e}")
            pass
        return apps

    async def search(self, query: str) -> list[AppManifest]:
        apps = []
        try:
            _, stdout, _ = await run_cmd("snap", "find", query)
            lines = stdout.strip().split("\n")
            if not lines or "No matching snaps" in lines[0]:
                return apps

            for line in lines[1:]:
                parts = line.split(None, 4)
                if len(parts) < 4:
                    continue

                name = parts[0]
                version = parts[1]
                publisher = parts[2]
                summary = parts[4] if len(parts) > 4 else ""

                apps.append(
                    AppManifest(
                        name=name,
                        id=f"snap:{name}",
                        format=AppFormat.SNAP,
                        version=version,
                        installed=False,
                        publisher=publisher.rstrip("*").replace("✓", ""),
                        description=summary,
                        category=AppCategory.CLI,
                        size_bytes=None,
                    )
                )
        except Exception as e:
            self.logger.warning(f"Snap search failed: {e}")
            pass
        return apps

    async def inspect(self, path: str) -> AppManifest | None:
        try:
            code, stdout, _ = await run_cmd("snap", "info", path)

            if code == 0 and stdout:
                return self._parse_snap_info(stdout, path)

            return await self._inspect_snap_yaml(path)  # Fallback

        except Exception as e:
            self.logger.error(f"Snap inspect error: {str(e)}")
            return None

    @staticmethod
    def _parse_snap_info(output: str, path: str) -> AppManifest:
        name = version = publisher = description = None

        for line in output.splitlines():
            if line.startswith("name:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("version:"):
                version = line.split(":", 1)[1].strip()
            elif line.startswith("publisher:"):
                publisher = line.split(":", 1)[1].strip()
            elif line.startswith("summary:"):
                description = line.split(":", 1)[1].strip()

        size_bytes = os.path.getsize(path)

        return AppManifest(
            name=name or "unknown",
            id=f"snap:{name}" if name else f"snap:{path}",
            format=AppFormat.SNAP,
            version=version or "unknown",
            publisher=publisher or "unknown",
            installed=False,
            description=description,
            size_bytes=size_bytes,
            category=AppCategory.DESKTOP,
        )

    async def _inspect_snap_yaml(self, path: str) -> AppManifest | None:
        try:
            if not is_cmd_available("unsquashfs"):
                return None
            code, stdout, _ = await run_cmd(
                "unsquashfs", "-n", "-cat", path, "meta/snap.yaml"
            )

            if code != 0 or not stdout:
                return None

            data = yaml.safe_load(stdout)

            name = data.get("name")
            version = data.get("version")
            description = data.get("summary") or data.get("description")

            return AppManifest(
                name=name or "unknown",
                id=f"snap:{name}" if name else f"snap:{path}",
                format=AppFormat.SNAP,
                version=version or "unknown",
                publisher="unknown",
                installed=False,
                description=description,
                size_bytes=os.path.getsize(path),
                category=AppCategory.DESKTOP,
            )

        except Exception as e:
            self.logger.error(f"Snap yaml inspect error: {str(e)}")
            return None

    async def install(self, query_or_path: str, launch: bool) -> bool:
        path = Path(query_or_path)

        if path.exists():
            cmd = ["sudo", "snap", "install", "--dangerous", str(path.resolve())]
        else:
            cmd = ["sudo", "snap", "install", query_or_path]

        code, _, stderr = await run_cmd(*cmd)
        if code != 0:
            self.logger.error(f"Snap install failed: {stderr}")
            return False

        if launch and not path.exists():
            code_launch, _, stderr_launch = await run_cmd(query_or_path)
            if code_launch != 0:
                self.logger.error(f"Snap Launch failed: {stderr_launch}")
                return False

        return True

    async def uninstall(self, app_info: AppManifest, clean_uninstall: bool) -> bool:
        if clean_uninstall:
            cmd = ["sudo", "snap", "remove", "--purge", app_info.name]
        else:
            cmd = ["sudo", "snap", "remove", app_info.name]

        code, _, stderr = await run_cmd(*cmd)
        if code != 0:
            self.logger.error(f"Snap uninstall failed : {stderr}")
            return False

        return True

    _SNAP_ACTION_MAP = {
        "install": LifeCycleEvent.INSTALLED,
        "refresh": LifeCycleEvent.UPGRADED,
        "remove": LifeCycleEvent.UNINSTALLED,
    }
    _SNAP_CHANGE_RE = re.compile(r"^(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(.*)$")

    def _parse_snap_change_line(
        self,
        line: str,
        action_categories: list[LifeCycleEvent] | None,
    ) -> list[HistoryRecords]:
        line = line.strip()
        if not line or line.startswith("ID ") or "Spawn" in line:
            return []

        match = self._SNAP_CHANGE_RE.match(line)
        if not match:
            return []

        _, status, _, ready_time_str, summary = match.groups()
        if status != "Done":
            return []

        summary_lower = summary.lower()
        event_type = next(
            (
                enum_val
                for verb, enum_val in self._SNAP_ACTION_MAP.items()
                if summary_lower.startswith(verb)
            ),
            None,
        )
        if not event_type:
            return []
        if action_categories and event_type not in action_categories:
            return []

        try:
            timestamp = datetime.fromisoformat(ready_time_str)
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            else:
                timestamp = timestamp.astimezone(timezone.utc)
        except ValueError:
            return []

        return [
            HistoryRecords(
                timestamp=timestamp,
                format=AppFormat.SNAP,
                lifecycle_event=event_type,
                app_name=app_name,
            )
            for app_name in re.findall(r'"([^"]+)"', summary)
        ]

    async def history(
        self, action_categories: list[LifeCycleEvent] | None = None
    ) -> list[HistoryRecords]:
        code, stdout, stderr = await run_cmd(*["snap", "changes", "--abs-time"])
        if code != 0:
            self.logger.error(f"Snap History Failed : {stderr}")
            return []

        records: list[HistoryRecords] = []
        for line in stdout.strip().splitlines():
            records.extend(self._parse_snap_change_line(line, action_categories))

        return sorted(records, key=lambda x: x.timestamp)
