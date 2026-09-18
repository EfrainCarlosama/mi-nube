from __future__ import annotations

import argparse
import json
from pathlib import Path

from mi_nube.app.settings import Settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera configuración pública para el ejecutable")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    settings = Settings.from_environment()
    values = {
        "microsoft_client_id": settings.microsoft_client_id,
        "microsoft_tenant_id": settings.microsoft_tenant_id,
        "update_manifest_url": settings.update_manifest_url,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(values, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Configuración pública generada: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
