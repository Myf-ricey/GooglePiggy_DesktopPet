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

if sys.platform == "win32":
    import pig_pet  # noqa: E402
else:
    from export_macos_assets import import_asset_pipeline  # noqa: E402

    pig_pet = import_asset_pipeline()


def main() -> None:
    source_dir = PROJECT_DIR / "assets" / "source-gifs"
    animations = pig_pet.load_animation_cache(PROJECT_DIR / "cache", source_dir)
    assert animations is not None
    assert set(animations) == {
        "idle",
        "left",
        "carrot",
        "jump",
        "flat",
        "question",
        "edge_reveal",
    }
    assert animations["idle"].source == animations["flat"].source
    assert animations["left"].source.name == "left_fixed.gif"
    assert animations["question"].source.name == "question.gif"
    assert len(animations["idle"].frames) == pig_pet.IDLE_BREATH_FRAMES
    assert set(animations["idle"].durations) == {pig_pet.IDLE_BREATH_DURATION_MS}
    assert len(animations["edge_reveal"].frames) == pig_pet.EDGE_REVEAL_FRAME_COUNT
    assert set(animations["edge_reveal"].durations) == {
        pig_pet.EDGE_REVEAL_FRAME_DURATION_MS
    }
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

    tail_dir = PROJECT_DIR / "assets" / "edge-tail"
    for edge in ("left", "right", "top", "bottom"):
        tail_path = tail_dir / f"{edge}.png"
        assert tail_path.is_file()
        with Image.open(tail_path) as tail:
            assert tail.size == (
                pig_pet.EDGE_TAIL_WINDOW_SIZE,
                pig_pet.EDGE_TAIL_WINDOW_SIZE,
            )
            assert tail.getchannel("A").getbbox() is not None

    desktop = (0, 0, 1000, 800)
    safe = (0, 80, 1000, 760)
    fixtures = {
        "left": (-2, 300, 148, 420),
        "right": (852, 300, 1002, 420),
        "top": (400, -2, 550, 118),
        "bottom": (400, 682, 550, 802),
    }
    for edge, contact in fixtures.items():
        assert pig_pet.touched_desktop_edge(contact, desktop) == edge
        delta = pig_pet.offscreen_delta(edge, contact, desktop)
        hidden = (
            contact[0] + delta[0],
            contact[1] + delta[1],
            contact[2] + delta[0],
            contact[3] + delta[1],
        )
        if edge == "left":
            assert hidden[2] == desktop[0] - pig_pet.EDGE_OFFSCREEN_PADDING
        elif edge == "right":
            assert hidden[0] == desktop[2] + pig_pet.EDGE_OFFSCREEN_PADDING
        elif edge == "top":
            assert hidden[3] == desktop[1] - pig_pet.EDGE_OFFSCREEN_PADDING
        else:
            assert hidden[1] == desktop[3] + pig_pet.EDGE_OFFSCREEN_PADDING
        tail = pig_pet.tail_window_rect(edge, contact, desktop)
        if edge == "left":
            assert tail[0] == desktop[0] - pig_pet.EDGE_TAIL_SCREEN_OVERLAP
        elif edge == "right":
            assert tail[2] == desktop[2] + pig_pet.EDGE_TAIL_SCREEN_OVERLAP
        elif edge == "top":
            assert tail[1] == desktop[1] - pig_pet.EDGE_TAIL_SCREEN_OVERLAP
        else:
            assert tail[3] == desktop[3] + pig_pet.EDGE_TAIL_SCREEN_OVERLAP
        bottom_drop = (
            (contact[3] - contact[1])
            if edge == "bottom"
            else 0
        )
        reveal_delta = pig_pet.revealed_delta(
            edge,
            hidden,
            safe,
            bottom_drop=bottom_drop,
        )
        revealed = (
            hidden[0] + round(reveal_delta[0]),
            hidden[1] + round(reveal_delta[1]),
            hidden[2] + round(reveal_delta[0]),
            hidden[3] + round(reveal_delta[1]),
        )
        if edge == "left":
            assert revealed[0] == safe[0] + pig_pet.EDGE_REVEAL_CLEARANCE
        elif edge == "right":
            assert revealed[2] == safe[2] - pig_pet.EDGE_REVEAL_CLEARANCE
        elif edge == "top":
            assert revealed[1] == safe[1] + pig_pet.EDGE_REVEAL_CLEARANCE
        else:
            assert revealed[3] == (
                safe[3]
                - pig_pet.EDGE_REVEAL_CLEARANCE
                + bottom_drop
            )

    seam_left = pig_pet.MonitorInfo((0, 0, 1000, 800), (0, 0, 1000, 800))
    seam_right = pig_pet.MonitorInfo((1000, 0, 2000, 800), (1000, 0, 2000, 800))
    seam_pet = (850, 300, 1000, 420)
    allowed = pig_pet.PigPet._exposed_edges(
        seam_left,
        seam_pet,
        [seam_left, seam_right],
    )
    assert "right" not in allowed
    assert pig_pet.touched_desktop_edge(seam_pet, seam_left.frame, allowed) is None

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
