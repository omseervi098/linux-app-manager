import json

from apphub.core.models import AppManifest, HistoryRecords


def to_json(apps: list[AppManifest | HistoryRecords], indent: int = 2) -> str:
    return json.dumps(
        [app.model_dump(mode="json") for app in apps],
        indent=indent,
    )


def to_json_single(app: AppManifest, indent: int = 2) -> str:
    return json.dumps(app.model_dump(mode="json"), indent=indent)
