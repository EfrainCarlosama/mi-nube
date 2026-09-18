from __future__ import annotations

import json
from importlib.resources import files


def load_bundled_config() -> dict[str, str | None]:
    try:
        content = files("mi_nube.assets").joinpath("runtime_config.json").read_text("utf-8")
        values = json.loads(content)
    except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(values, dict):
        return {}
    return {
        key: value if isinstance(value, str) and value else None
        for key, value in values.items()
        if key in {"microsoft_client_id", "microsoft_tenant_id", "update_manifest_url"}
    }
