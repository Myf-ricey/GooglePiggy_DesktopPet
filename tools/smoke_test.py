#!/usr/bin/env python3
"""Headless smoke tests for portable assets, animation anchors, and state flow."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from PIL import Image


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

import pig_pet  # noqa: E402


def main() -> None:
    source_dir = PROJECT_DIR / "assets" / "source-gifs"
    animations = pig_pet.load_animation_cache(PROJECT_DIR / "cache", source_dir)
    assert animations is not None
    assert set(animations) == {"idle", "left", "carrot", "jump", "flat", "question"}
    assert animations["idle"].source == animations["flat"].source
    assert animations["left"].source.name == "left_fixed.gif"
    assert animations["question"].source.name == "question.gif"
    assert len(animations["idle"].frames) == pig_pet.IDLE_BREATH_FRAMES
    assert set(animations["idle"].durations) == {pig_pet.IDLE_BREATH_DURATION_MS}
    assert len(animations["left"].frames) == 15
    left_source_path = source_dir / animations["left"].source.name
    with Image.open(left_source_path) as left_source:
        source_duration = int(left_source.info.get("duration", 100))
    assert set(animations["left"].durations) == {
        max(
            pig_pet.MIN_DURATION_MS,
            round(source_duration / pig_pet.LEFT_HUMP_SPEED_MULTIPLIER),
        )
    }

    for key, animation in animations.items():
        first = pig_pet.pig_body_bbox(
            animation.frames[0],
            isolate_center_component=(key == "carrot"),
        )
        last = pig_pet.pig_body_bbox(
            animation.frames[-1],
            isolate_center_component=(key == "carrot"),
        )
        for box in (first, last):
            center_x = (box[0] + box[2]) / 2
            assert abs(center_x - pig_pet.BODY_ANCHOR_X) <= 1
            assert abs(box[3] - pig_pet.BODY_ANCHOR_BOTTOM) <= 1

    status_path = PROJECT_DIR / "qa" / "smoke-status.json"
    try:
        pig_pet.write_status("idle", path=status_path)
        pet = pig_pet.PigPet(
            animations,
            PROJECT_DIR / "qa" / "qa-report.json",
            PROJECT_DIR,
            status_path,
        )
        assert pet.current_key == "idle"
        pig_pet.write_status("thinking", event="UserPromptSubmit", path=status_path)
        pet._poll_bridge(force=True)
        assert pet.current_key == "carrot"
        stale_time = time.time() - pig_pet.THINKING_STATUS_STALE_SECONDS - 1
        os.utime(status_path, (stale_time, stale_time))
        pet._poll_bridge(force=True)
        assert pet.current_key == "idle"

        pig_pet.write_status("thinking", event="PreToolUse", path=status_path)
        pet._poll_bridge(force=True)
        assert pet.current_key == "carrot"
        pig_pet.write_status("thinking", event="PostToolUse", path=status_path)
        pet._poll_bridge(force=True)
        assert pet.current_key == "carrot"
        for _ in range(10):
            pet._advance()
            assert pet.current_key == "carrot"
        pig_pet.write_status("success", event="Stop", path=status_path)
        pet._poll_bridge(force=True)
        assert pet.current_key == "jump"
        for _ in range(len(animations["jump"].frames)):
            pet._advance()
        assert pet.current_key == "idle"

        pig_pet.write_status("thinking", event="UserPromptSubmit", path=status_path)
        pet._poll_bridge(force=True)
        assert pet.current_key == "carrot"
        pig_pet.write_status("success", path=status_path)
        pet._poll_bridge(force=True)
        assert pet.current_key == "jump"
        for _ in range(len(animations["jump"].frames)):
            pet._advance()
        assert pet.current_key == "idle"

        permission_dir = status_path.parent / "permission-requests"
        permission_id = "smoke-permission"
        pig_pet.write_json_atomic(
            permission_dir / f"{permission_id}.request.json",
            {
                "request_id": permission_id,
                "tool_name": "Shell",
                "summary": "Run a harmless smoke-test command",
                "created_at": pig_pet.utc_timestamp(),
            },
        )
        pig_pet.write_status(
            "permission",
            event="PermissionRequest",
            permission_request_id=permission_id,
            path=status_path,
        )
        pet._poll_bridge(force=True)
        assert pet.current_key == "question"
        pet._write_permission_decision("deny")
        assert (permission_dir / f"{permission_id}.response.json").is_file()
        pet._poll_bridge(force=True)
        assert pet.current_key == "idle"
    finally:
        status_path.unlink(missing_ok=True)
        permission_dir = status_path.parent / "permission-requests"
        for path in permission_dir.glob("smoke-permission.*.json"):
            path.unlink(missing_ok=True)

    print("smoke_test=ok")


if __name__ == "__main__":
    main()
