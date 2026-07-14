from collections.abc import Iterable

from apphub.core.models import AppRuntime


def detect_runtime_from_names(names: Iterable[str]) -> AppRuntime:
    """Infer app runtime from a set of file/path base-names."""
    name_set = set(names)

    if (
        "chrome-sandbox" in name_set
        or "libnode.so" in name_set
        or any(n.endswith(".asar") for n in name_set)
    ):
        return AppRuntime.ELECTRON

    if any("tauri" in n.lower() for n in name_set):
        return AppRuntime.TAURI

    if any(n.endswith(".jar") for n in name_set):
        return AppRuntime.JAVA

    if "package.json" in name_set or "node_modules" in name_set:
        return AppRuntime.NODE

    if "libcef.so" in name_set or "chrome" in name_set:
        return AppRuntime.CHROMIUM

    if "site-packages" in name_set or any(n.endswith(".py") for n in name_set):
        return AppRuntime.PYTHON

    return AppRuntime.NATIVE


def parse_appimage_stem(stem: str) -> tuple[str, str]:
    parts = stem.split("-")
    name_parts: list[str] = []
    version = "unknown"

    for part in parts:
        if part.lower() in {"x86_64", "amd64", "arm64", "aarch64"}:
            break
        if part and part[0].isdigit():
            version = part
            break
        name_parts.append(part)

    name = " ".join(name_parts) if name_parts else stem
    return name, version
