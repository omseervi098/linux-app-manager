import json

from apphub.core.models import AppManifest


def to_json(apps: list[AppManifest], indent: int = 2) -> str:
    """Serialize a list of AppManifest objects to a JSON string."""
    return json.dumps(
        [app.model_dump(mode="json") for app in apps],
        indent=indent,
    )


def to_json_single(app: AppManifest, indent: int = 2) -> str:
    """Serialize a single AppManifest to a JSON string."""
    return json.dumps(app.model_dump(mode="json"), indent=indent)
