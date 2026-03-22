import subprocess
from pathlib import Path

from apphub.core.models import AppCategory, AppFormat, AppManifest
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
                    has_desktop = any(f.suffix == ".desktop" for f in desktop_dir.iterdir())
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

    def list_apps(self) -> list[AppManifest]:
        apps = []
        try:
            result = subprocess.run(["snap", "list"], capture_output=True, text=True)
            for line in result.stdout.strip().split("\n")[1:]:
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

    def search(self, query: str) -> list[AppManifest]:
        apps = []
        try:
            result = subprocess.run(["snap", "find", query], capture_output=True, text=True)
            lines = result.stdout.strip().split("\n")
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

    def install(self, query_or_path: str, launch: bool) -> bool:
        path = Path(query_or_path)

        if path.exists():
            cmd = ["sudo", "snap", "install", "--dangerous", str(path.resolve())]
        else:
            cmd = ["sudo", "snap", "install", query_or_path]

        try:
            subprocess.run(cmd, check=True)

            if launch and not path.exists():
                subprocess.Popen([query_or_path], start_new_session=True)

            return True
        except subprocess.CalledProcessError:
            return False

    def uninstall(self, app_name: str) -> bool:
        installed_apps = self.list_apps()
        if not any(app.name == app_name for app in installed_apps):
            return False

        try:
            subprocess.run(["sudo", "snap", "remove", app_name], check=True)
            return True
        except subprocess.CalledProcessError:
            return False
