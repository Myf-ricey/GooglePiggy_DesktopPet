#!/usr/bin/env python3
"""Portable local status bridge shared by Codex hooks and the desktop pet."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


APP_DATA_DIR_NAME = "GifPigDesktopPet"
STATUS_FILE_NAME = "codex-status.json"
HEARTBEAT_FILE_NAME = "pig-heartbeat.json"
PERMISSION_REQUESTS_DIR_NAME = "permission-requests"
VALID_STATUSES = {"idle", "thinking", "working", "compacting", "interrupted", "success", "error", "permission"}


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False) + '\n', encoding='utf-8')
        for attempt in range(8):
            try:
                os.replace(temporary, path)
                return
            except PermissionError:
                if attempt == 7:
                    raise
                time.sleep(.01 * (attempt+1))
    finally:
        temporary.unlink(missing_ok=True)


def actor_path(directory: Path, actor: str) -> Path:
    name = base64.b64encode(actor.encode('utf-8')).decode('ascii').replace('/', '_')
    return directory / 'actors' / (name + '.json')


def publish_event(directory: Path, payload: dict, legacy_path: Path | None = None) -> Path:
    payload = dict(payload)
    payload.setdefault('token', uuid.uuid4().hex)
    payload.setdefault('updated_at', datetime.now(timezone.utc).isoformat())
    payload.setdefault('received_at', time.time())
    actor = payload.get('agent_id') or payload.get('session_id')
    target = actor_path(directory, actor) if actor else legacy_path or directory / STATUS_FILE_NAME
    atomic_json(target, payload)
    if actor:
        atomic_json(directory / 'family-events' / (f"{int(payload['received_at']*1_000_000):020d}-{uuid.uuid4().hex}.json"), payload)
    return target


def default_status_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / APP_DATA_DIR_NAME / STATUS_FILE_NAME
    if sys.platform == "darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / APP_DATA_DIR_NAME
            / STATUS_FILE_NAME
        )
    return Path.home() / f".{APP_DATA_DIR_NAME}" / STATUS_FILE_NAME


def default_state_dir() -> Path:
    return default_status_path().parent


def default_heartbeat_path() -> Path:
    return default_state_dir() / HEARTBEAT_FILE_NAME


def default_permission_requests_dir() -> Path:
    return default_state_dir() / PERMISSION_REQUESTS_DIR_NAME


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
    turn_id: str = "",
    permission_request_id: str = "",
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
        "turn_id": turn_id,
    }
    if permission_request_id:
        payload["permission_request_id"] = permission_request_id
    return publish_event(status_path.parent, payload, legacy_path=status_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("status", nargs="?", choices=sorted(VALID_STATUSES))
    parser.add_argument("--event", default="")
    parser.add_argument("--message", default="")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--turn-id", default="")
    parser.add_argument("--permission-request-id", default="")
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
        turn_id=args.turn_id,
        permission_request_id=args.permission_request_id,
        path=status_path,
    )
    print(status_path)


if __name__ == "__main__":
    main()
