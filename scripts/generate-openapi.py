#!/usr/bin/env python3
"""Generate OpenAPI schema from the MK OS FastAPI application.

Usage:
    python scripts/generate-openapi.py

Output:
    docs/openapi.json
"""

import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

from mk.web.app import create_app


def main() -> None:
    """Generate OpenAPI JSON schema and write to docs/openapi.json."""
    app = create_app()
    schema = app.openapi()

    output_path = project_root / "docs" / "openapi.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"OpenAPI schema written to {output_path}")
    print(f"  Title: {schema.get('info', {}).get('title', 'N/A')}")
    print(f"  Version: {schema.get('info', {}).get('version', 'N/A')}")
    print(f"  Paths: {len(schema.get('paths', {}))}")


if __name__ == "__main__":
    main()
