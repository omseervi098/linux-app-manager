from enum import StrEnum

from pydantic import BaseModel


class AppFormat(StrEnum):
    APPIMAGE = "appimage"
    FLATPAK = "flatpak"
    SNAP = "snap"
    DEBIAN = "apt"
    RHEL = "dnf"
    ARCH = "pacman"
    TARBALL = "tarball"

class AppRuntime(StrEnum):
    NATIVE = "native"
    ELECTRON = "electron"
    TAURI = "tauri"
    CHROMIUM = "chromium"
    JAVA = "java"
    PYTHON = "python"
    NODE = "node"
    UNKNOWN = "unknown"

class AppCategory(StrEnum):
    DESKTOP = "desktop"
    SYSTEM = "system"
    CLI = "cli"

class AppManifest(BaseModel):
    name: str
    id: str
    version: str
    format: AppFormat
    icon: str | None = None
    description: str | None = None
    publisher: str | None = None
    installed: bool = False
    category: AppCategory = AppCategory.DESKTOP
    size_bytes: int | None = None
    runtime: AppRuntime = AppRuntime.NATIVE

class DistroInfo(BaseModel):
    name: str
    id: str
    version_id: str