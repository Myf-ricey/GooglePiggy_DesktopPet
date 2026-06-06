#!/usr/bin/env python3
"""Portable local status bridge shared by Codex hooks and the desktop pet."""

from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


APP_DATA_DIR_NAME = "GifPigDesktopPet"
STATUS_FILE_NAME = "codex-status.json"
VALID_STATUSES = {"idle", "thinking", "success", "error"}


def default_status_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / APP_DATA_DIR_NAME / STATUS_FILE_NAME
    return Path.home() / f".{APP_DATA_DIR_NAME}" / STATUS_FILE_NAME


def read_status(path: Path | None = None) -> dict[str, object]:
    status_path = path or default_status_path()
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {"status": "idle", "token": ""}
    if payload.get("status") not in VALID_STATUSES:
        payload["status"] = "idle"
    return payload


def write_status(
    status: str,
    *,
    source: str = "manual",
    event: str = "",
    message: str = "",
    session_id: str = "",
    path: Path | None = None,
) -> Path:
    if status not in VALID_STATUSES:
        raise ValueError(f"Unsupported status: {status}")
    status_path = path or default_status_path()
    status_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "token": f"{time.time_ns()}-{uuid.uuid4().hex}",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "event": event,
        "message": message,
        "session_id": session_id,
    }
    temporary_path = status_path.with_suffix(status_path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary_path, status_path)
    return status_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("status", nargs="?", choices=sorted(VALID_STATUSES))
    parser.add_argument("--event", default="")
    parser.add_argument("--message", default="")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--source", default="manual")
    parser.add_argument("--status-file", type=Path)
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--show-path", action="store_true")
    args = parser.parse_args()

    status_path = args.status_file or default_status_path()
    if args.show_path:
        print(status_path)
        return
    if args.show:
        print(json.dumps(read_status(status_path), ensure_ascii=False, indent=2))
        return
    if not args.status:
        parser.error("provide a status, --show, or --show-path")
    write_status(
        args.status,
        source=args.source,
        event=args.event,
        message=args.message,
        session_id=args.session_id,
        path=status_path,
    )
    print(status_path)


if __name__ == "__main__":
    main()
