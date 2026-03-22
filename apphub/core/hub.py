from typing import Any, Dict
from pathlib import Path

from apphub.core.exceptions import InstallError
from apphub.core.models import AppFormat, AppManifest
from apphub.core.utils import detect_distro_info, detect_format
from apphub.core.logger import get_logger

from apphub.plugins.appimage import AppImagePlugin
from apphub.plugins.apt import AptPlugin
from apphub.plugins.flatpak import FlatpakPlugin
from apphub.plugins.snap import SnapPlugin


class AppHubCore:
    plugins: Dict[AppFormat, Any] = {
        AppFormat.SNAP: SnapPlugin(),
        AppFormat.FLATPAK: FlatpakPlugin(),
        AppFormat.APPIMAGE: AppImagePlugin(),
    }

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)

        self.distro_info = detect_distro_info()
        self._add_native_format()

    def _add_native_format(self):
        if self.distro_info.id in ("ubuntu", "debian", "linuxmint", "pop", "elementary"):
            self.plugins[AppFormat.DEBIAN] = AptPlugin()
        # TODO: Add Support for `dnf`

    def inspect(self, path: str) -> AppManifest:
        result = self.plugins[detect_format(path=path)].inspect(Path(path))
        return result

    def search(self, query: str, formats: list[AppFormat] | None = None) -> list[AppManifest]:
        apps = []
        for plugin_format, plugin in self.plugins.items():
            if formats and plugin_format not in formats:
                continue
            try:
                apps.extend(plugin.search(query))
            except NotImplementedError:
                self.logger.warning(f"{plugin_format} doesn't implement search")
                continue
            except Exception as e:
                self.logger.error(f"Exception while search {query} on remote repo: {str(e)}")
                continue
        return apps

    def install(self, query_or_path: str, install_format: AppFormat, launch: bool = False) -> bool:
        try:
            result = self.plugins[install_format].install(query_or_path, launch)
        except NotImplementedError:
            raise
        except Exception as e:
            raise InstallError(f"Installation Error: {str(e)}") from None
        return result

    def uninstall(self, name: str) -> bool:
        pass

    def list_apps(
        self,
        query: str | None = None,
        formats: list[AppFormat] | None = None,
        exclude_defaults: bool = False,
    ) -> list[AppManifest]:
        apps = []
        for plugin_format, plugin in self.plugins.items():
            if formats and plugin_format not in formats:
                continue

            for app in plugin.list_apps():
                if exclude_defaults and app.category == "system":
                    continue
                if query and query.lower() not in app.name.lower():
                    continue
                apps.append(app)
        return apps

    def info(self, query: str) -> AppManifest | None:
        matches = self.list_apps(query=query)
        exact = [a for a in matches if a.name.lower() == query.lower()]
        return exact[0] if exact else (matches[0] if matches else None)

    def storage(self, formats: list[AppFormat] | None = None, top: int | None = None) -> list[AppManifest]:
        apps = self.list_apps(formats=formats)
        apps = sorted(apps, key=lambda a: a.size_bytes or 0, reverse=True)
        if top is not None:
            apps = apps[:top]
        return apps
