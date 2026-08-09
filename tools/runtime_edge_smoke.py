"""Exercise the Windows edge hide/reveal path against a real desktop window."""

from __future__ import annotations

import ctypes
import json
import subprocess
import sys
import time
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
STATUS_PATH = PROJECT_DIR / "qa" / "runtime-edge-status.json"
HEARTBEAT_PATH = STATUS_PATH.parent / "pig-heartbeat.json"
WM_MOUSEMOVE = 0x0200
WM_LBUTTONUP = 0x0202
MK_LBUTTON = 0x0001


def read_heartbeat() -> dict[str, object] | None:
    try:
        return json.loads(HEARTBEAT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def wait_for(predicate, timeout: float = 8.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        payload = read_heartbeat()
        if payload is not None and predicate(payload):
            return payload
        time.sleep(0.08)
    raise AssertionError(f"Timed out waiting for heartbeat: {read_heartbeat()}")


def main() -> None:
    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.unlink(missing_ok=True)
    HEARTBEAT_PATH.unlink(missing_ok=True)

    process = subprocess.Popen(
        [
            sys.executable,
            str(PROJECT_DIR / "pig_pet.py"),
            "--status-file",
            str(STATUS_PATH),
        ],
        cwd=PROJECT_DIR,
    )
    try:
        initial = wait_for(
            lambda payload: payload.get("window_visible") is True
            and payload.get("presentation") == "visible"
        )
        window_rect = initial["window_rect"]
        if not isinstance(window_rect, list) or len(window_rect) != 4:
            raise AssertionError(f"Invalid initial window rect: {window_rect}")
        hwnd = int(initial["hwnd"])
        body_x = int(window_rect[0]) + 410
        body_y = int(window_rect[1]) + 505
        screen_right = user32.GetSystemMetrics(0)
        body_right = int(window_rect[0]) + 486
        drag_delta = screen_right - body_right + 3

        user32.SetCursorPos(body_x, body_y)
        user32.SendMessageW(hwnd, 0x0201, 0, 0)
        user32.SetCursorPos(body_x + drag_delta, body_y)
        user32.SendMessageW(hwnd, WM_MOUSEMOVE, MK_LBUTTON, 0)
        user32.SendMessageW(hwnd, WM_LBUTTONUP, 0, 0)

        hidden = wait_for(
            lambda payload: payload.get("presentation") == "hidden"
            and payload.get("tail_visible") is True
        )
        tail_hwnd = int(hidden["tail_hwnd"])
        tail_rect = hidden["tail_rect"]
        if not isinstance(tail_rect, list) or len(tail_rect) != 4:
            raise AssertionError(f"Invalid tail rect: {tail_rect}")
        tail_x = (int(tail_rect[0]) + int(tail_rect[2])) // 2
        tail_y = (int(tail_rect[1]) + int(tail_rect[3])) // 2
        user32.SetCursorPos(tail_x, tail_y)
        user32.SendMessageW(tail_hwnd, WM_LBUTTONUP, 0, 0)

        wait_for(
            lambda payload: payload.get("presentation") == "visible"
            and payload.get("tail_visible") is False
            and payload.get("window_visible") is True
        )
        print("runtime_edge_smoke=ok")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        STATUS_PATH.unlink(missing_ok=True)
        HEARTBEAT_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
