"""FastAPI の OpenAPI スキーマを frontend/openapi.json へ出力する

実行（リポジトリルートで）:
    .venv\\Scripts\\python.exe app\\export_openapi.py

API の形式（app/schemas.py・app/main.py）を変えたら必ず実行し、
frontend/openapi.json と frontend/src/api-types.ts を更新すること。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "frontend" / "openapi.json"


def main() -> None:
    from app.main import app  # noqa: PLC0415  (起動チェック込みでimportする)

    spec = app.openapi()
    OUT.write_text(
        json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
