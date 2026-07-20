"""Run one explicitly mocked orchestrator job against a running container."""

from __future__ import annotations

import argparse
import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {args.api_key}", "Content-Type": "application/json"}
    body = json.dumps({"idea": "container smoke job", "project_id": "smoke"}).encode("utf-8")
    created, session_cookie = _json(
        Request(f"{base_url}/api/orchestrate", data=body, headers=headers, method="POST")
    )
    if created.get("status") != "queued" or not created.get("session_id"):
        raise RuntimeError(f"unexpected create response: {created}")

    deadline = time.monotonic() + args.timeout
    status_url = f"{base_url}{created['status_url']}"
    headers["Cookie"] = session_cookie
    while time.monotonic() < deadline:
        status, _ = _json(Request(status_url, headers=headers))
        if status.get("terminal"):
            if status.get("status") != "completed":
                raise RuntimeError(f"mocked job did not complete: {status}")
            dashboard, _ = _json(
                Request(
                    f"{base_url}/api/orchestrate/dashboard/{created['session_id']}",
                    headers={"Cookie": session_cookie},
                )
            )
            if dashboard.get("execution", {}).get("status") != "completed":
                raise RuntimeError(f"dashboard projection is not completed: {dashboard}")
            events = _text(
                Request(
                    f"{base_url}{created['events_url']}?after=0",
                    headers={"Cookie": session_cookie},
                )
            )
            if "event: pipeline.completed" not in events:
                raise RuntimeError(f"terminal SSE event missing: {events}")
            return
        time.sleep(0.5)
    raise TimeoutError("mocked container job did not reach a terminal state")


def _json(request: Request) -> tuple[dict, str]:
    try:
        with urlopen(request, timeout=10) as response:
            cookie = response.headers.get("Set-Cookie", "").split(";", 1)[0]
            return json.loads(response.read().decode("utf-8")), cookie
    except (HTTPError, URLError) as exc:
        raise RuntimeError(f"HTTP smoke request failed: {exc}") from exc


def _text(request: Request) -> str:
    try:
        with urlopen(request, timeout=10) as response:
            return response.read().decode("utf-8")
    except (HTTPError, URLError) as exc:
        raise RuntimeError(f"HTTP smoke request failed: {exc}") from exc


if __name__ == "__main__":
    main()
