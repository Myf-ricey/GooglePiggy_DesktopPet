#!/usr/bin/env python3
"""Print a redacted, read-only snapshot for Codex hook compatibility debugging."""

from __future__ import annotations

import json
import os
import plistlib
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.11+ is required.
    tomllib = None


HOME = Path.home()
CODEX_HOME = Path(os.environ.get("CODEX_HOME", HOME / ".codex"))


def display_path(value: str | Path) -> str:
    text = str(value)
    home = str(HOME)
    return text.replace(home, "~")


def command_version(executable: str | Path | None) -> str | None:
    if not executable:
        return None
    try:
        result = subprocess.run(
            [str(executable), "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    output = (result.stdout or result.stderr).strip()
    return output or None


def desktop_snapshot() -> dict[str, object]:
    candidates = [Path("/Applications/ChatGPT.app"), Path("/Applications/Codex.app")]
    app = next((candidate for candidate in candidates if candidate.is_dir()), None)
    if app is None:
        return {"installed": False}
    info_path = app / "Contents" / "Info.plist"
    info: dict[str, object] = {}
    try:
        with info_path.open("rb") as handle:
            info = plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException):
        pass
    embedded = app / "Contents" / "Resources" / "codex"
    return {
        "installed": True,
        "path": display_path(app),
        "bundle_identifier": info.get("CFBundleIdentifier"),
        "version": info.get("CFBundleShortVersionString"),
        "build": info.get("CFBundleVersion"),
        "embedded_codex": command_version(embedded if embedded.is_file() else None),
    }


def hook_snapshot() -> dict[str, object]:
    path = CODEX_HOME / "hooks.json"
    result: dict[str, object] = {"path": display_path(path), "exists": path.is_file()}
    if not path.is_file():
        return result
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        result["error"] = str(error)
        return result
    events: dict[str, list[dict[str, object]]] = {}
    for event, groups in document.get("hooks", {}).items():
        handlers: list[dict[str, object]] = []
        for group in groups if isinstance(groups, list) else []:
            if not isinstance(group, dict):
                continue
            for hook in group.get("hooks", []):
                if not isinstance(hook, dict):
                    continue
                handlers.append(
                    {
                        key: display_path(value) if key == "command" else value
                        for key, value in hook.items()
                        if key in {"type", "command", "timeout", "async", "enabled"}
                    }
                )
        events[event] = handlers
    result["events"] = events
    return result


def config_snapshot() -> dict[str, object]:
    path = CODEX_HOME / "config.toml"
    result: dict[str, object] = {"path": display_path(path), "exists": path.is_file()}
    if not path.is_file() or tomllib is None:
        return result
    try:
        with path.open("rb") as handle:
            config = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as error:
        result["error"] = str(error)
        return result
    safe_keys = (
        "model",
        "model_reasoning_effort",
        "approval_policy",
        "sandbox_mode",
        "web_search",
    )
    result["selected"] = {
        key: config[key] for key in safe_keys if key in config
    }
    features = config.get("features", {})
    if isinstance(features, dict):
        result["features"] = {
            "hooks": features.get("hooks"),
        }
    return result


def main() -> int:
    terminal_codex = shutil.which("codex")
    snapshot = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "platform": sys.platform,
        "desktop": desktop_snapshot(),
        "terminal_codex": {
            "path": display_path(terminal_codex) if terminal_codex else None,
            "version": command_version(terminal_codex),
        },
        "config": config_snapshot(),
        "hooks": hook_snapshot(),
        "diagnostic_paths": {
            "sessions": display_path(CODEX_HOME / "sessions"),
            "desktop_logs": "~/Library/Logs/com.openai.codex/YYYY/MM/DD",
            "pig_state": "~/Library/Application Support/GifPigDesktopPet",
            "pig_hook_log": (
                "~/Library/Application Support/GifPigDesktopPet/"
                "codex-hook-events.jsonl"
            ),
        },
    }
    print(json.dumps(snapshot, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
