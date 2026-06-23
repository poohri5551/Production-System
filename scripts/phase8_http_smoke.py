import re
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app  # noqa: E402
from scripts.smoke_helpers import ensure_smoke_admin, cleanup_smoke_user  # noqa: E402


def print_check(name, ok, detail=None):
    status = "PASS" if ok else "FAIL"
    print(f"{status} {name}")
    if detail:
        print(f"  {detail}")
    return ok


def main():
    checks = []
    warnings = 0
    smoke_admin = f"smoke_phase8_admin_{int(time.time())}"
    smoke_password = "SmokeAdmin123"

    ensure_smoke_admin(smoke_admin, smoke_password)
    try:
        with app.test_client() as client:
            default_landing = client.get("/")
            checks.append(
                print_check(
                    "default / redirects to Vue /app",
                    default_landing.status_code in (301, 302, 303, 307, 308) and default_landing.headers.get("Location", "").endswith("/app"),
                    f"status={default_landing.status_code} location={default_landing.headers.get('Location')}",
                )
            )

            legacy_login = client.get("/legacy-login")
            checks.append(print_check("legacy /legacy-login returns 200", legacy_login.status_code == 200, f"status={legacy_login.status_code}"))

            legacy_main = client.get("/mainpage")
            checks.append(print_check("legacy /mainpage returns 200", legacy_main.status_code == 200, f"status={legacy_main.status_code}"))

            vue_index = client.get("/app")
            vue_html = vue_index.get_data(as_text=True)
            checks.append(print_check("Vue /app returns 200", vue_index.status_code == 200, f"status={vue_index.status_code}"))
            checks.append(print_check("Vue /app contains app mount", '<div id="app"></div>' in vue_html))
            checks.append(print_check("Vue build uses /app asset base", "/app/assets/" in vue_html and '"/assets/' not in vue_html))

            vue_fallback = client.get("/app/future/internal/route")
            fallback_html = vue_fallback.get_data(as_text=True)
            checks.append(
                print_check(
                    "Vue /app/<path> SPA fallback returns index",
                    vue_fallback.status_code == 200 and '<div id="app"></div>' in fallback_html,
                    f"status={vue_fallback.status_code}",
                )
            )

            asset_paths = re.findall(r'(?:src|href)="([^"]+/assets/[^"]+)"', vue_html)
            checks.append(print_check("Vue index references build assets", bool(asset_paths), f"assets={asset_paths}"))
            for asset_path in asset_paths:
                response = client.get(asset_path)
                checks.append(
                    print_check(
                        f"asset loads {asset_path}",
                        response.status_code == 200 and len(response.get_data()) > 0,
                        f"status={response.status_code} bytes={len(response.get_data())}",
                    )
                )

            api_login = client.post("/api/login", data={"username": smoke_admin, "password": smoke_password})
            api_payload = api_login.get_json(silent=True) or {}
            checks.append(print_check("/api/login still works", api_login.status_code == 200 and api_payload.get("success") is True, str(api_payload)))

            upload_dir = ROOT / "static" / "uploads"
            upload_file = next((path for path in upload_dir.glob("*") if path.is_file()), None) if upload_dir.exists() else None
            if upload_file:
                response = client.get(f"/static/uploads/{upload_file.name}")
                checks.append(
                    print_check(
                        f"uploaded file route works {upload_file.name}",
                        response.status_code == 200 and len(response.get_data()) > 0,
                        f"status={response.status_code} bytes={len(response.get_data())}",
                    )
                )
            else:
                warnings += 1
                print("WARN /static/uploads smoke skipped because no uploaded file exists")
    finally:
        cleanup_smoke_user(smoke_admin)

    passed = sum(1 for ok in checks if ok)
    failed = len(checks) - passed
    print("\nSUMMARY")
    print(f"  total checks: {len(checks)}")
    print(f"  passed: {passed}")
    print(f"  failed: {failed}")
    print(f"  warnings: {warnings}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
