from abc import ABC
from logging import Logger
from pathlib import Path

from apphub.core.logger import get_logger
from apphub.core.models import AppManifest, DistroInfo
from apphub.core.utils import detect_distro_info


class PluginBase(ABC):
    def __init__(self) -> None:
        self.logger: Logger = get_logger(self.__class__.__name__)
        self.distro_info: DistroInfo = detect_distro_info()
        super().__init__()

    def list_apps(self) -> list[AppManifest]:
        """Implement this to list apps"""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support list_apps()"
        )

    def inspect(self, path: Path) -> AppManifest:
        """Implement this to inspect app info from path"""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support inspect()"
        )

    def search(self, query: str) -> list[AppManifest]:
        """Implement this to search app over repository"""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support search()"
        )

    def install(self, query_or_path: str, launch: bool) -> bool:
        """Implement this to install app"""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support install()"
        )

    def uninstall(self, app_info: AppManifest, clean_uninstall: bool) -> bool:
        """Implement this to uninstall app"""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support uninstall()"
        )
