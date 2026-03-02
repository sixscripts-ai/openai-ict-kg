from __future__ import annotations

import os

import httpx


def main() -> None:
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SECRET_KEY", "")
    if not url or not key:
        raise SystemExit("Set SUPABASE_URL and SUPABASE_SECRET_KEY")

    base = url.rstrip("/")
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    with httpx.Client(timeout=20.0) as client:
        health = client.get(f"{base}/rest/v1/", headers=headers)
        health.raise_for_status()
        payload = health.json()
    print({"ok": True, "paths": list(payload.get("paths", {}).keys())[:20]})
    print("If table paths are missing, run scripts/supabase_schema.sql in Supabase SQL editor.")


if __name__ == "__main__":
    main()
