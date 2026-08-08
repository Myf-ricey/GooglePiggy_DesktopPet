#!/usr/bin/env python3
"""Black-box tests for the native macOS app CLI and Codex hook bridge."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageChops


EDGE_TAIL_CANVAS_SIZE = 68
# The 40° left rump arc naturally spans 13 thresholded pixels at its tangent;
# the original rectangular crop seam spanned 33, so 14 keeps useful separation.
EDGE_TAIL_MAX_EXPOSED_CUT_RUN = 14
EDGE_TAIL_SCREEN_OVERLAP = {
    "left": 30,
    "right": 30,
    "top": 30,
    "bottom": 30,
}


def longest_true_run(values: list[bool]) -> int:
    longest = 0
    current = 0
    for value in values:
        current = current + 1 if value else 0
        longest = max(longest, current)
    return longest


def exposed_tail_cut_run(image: Image.Image, edge: str) -> int:
    """Measure the former rectangular cut on the visible side of each pose."""

    alpha = image.getchannel("A")
    opaque = alpha.point(lambda value: 255 if value >= 96 else 0)
    bounds = opaque.getbbox()
    assert bounds is not None
    opaque = opaque.crop(bounds)
    if edge == "right":
        values = [opaque.getpixel((x, 0)) > 0 for x in range(opaque.width)]
    elif edge == "bottom":
        values = [
            opaque.getpixel((opaque.width - 1, y)) > 0
            for y in range(opaque.height)
        ]
    elif edge == "top":
        values = [opaque.getpixel((0, y)) > 0 for y in range(opaque.height)]
    else:
        values = [
            opaque.getpixel((x, opaque.height - 1)) > 0
            for x in range(opaque.width)
        ]
    return longest_true_run(values)


def run(
    executable: Path,
    args: list[str],
    *,
    env: dict[str, str],
    payload: dict[str, object] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(executable), *args],
        input=json.dumps(payload) if payload is not None else None,
        text=True,
        capture_output=True,
        env=env,
        check=True,
        timeout=20,
    )


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def wait_for_request(permission_dir: Path) -> Path:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        matches = list(permission_dir.glob("*.request.json"))
        if matches:
            return matches[0]
        time.sleep(0.05)
    raise AssertionError("permission request did not appear")


def write_session_tool_calls(
    codex_home: Path,
    session_id: str,
    cwd: Path,
    calls: list[tuple[str, str, str]],
) -> None:
    session_dir = codex_home / "sessions" / "2026" / "07" / "18"
    session_dir.mkdir(parents=True, exist_ok=True)
    session_path = session_dir / f"rollout-test-{session_id}.jsonl"
    records = [
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "session_meta",
            "payload": {
                "id": session_id,
                "cwd": str(cwd),
            },
        }
    ]
    for turn_id, name, tool_input in calls:
        records.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "status": "completed",
                    "name": name,
                    "input": tool_input,
                    "internal_chat_message_metadata_passthrough": {
                        "turn_id": turn_id,
                    },
                },
            }
        )
    session_path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )


def test_permission(
    executable: Path,
    env: dict[str, str],
    state_dir: Path,
    decision: str,
    payload: dict[str, object],
    expected_tool_name: str,
    expected_summary: str,
) -> None:
    heartbeat = {
        "app": "GooglePiggy Desktop Pet",
        "pid": os.getpid(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    (state_dir / "pig-heartbeat.json").write_text(
        json.dumps(heartbeat),
        encoding="utf-8",
    )
    process = subprocess.Popen(
        [str(executable), "--hook"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert process.stdin is not None
    process.stdin.write(json.dumps(payload))
    process.stdin.close()
    request_path = wait_for_request(state_dir / "permission-requests")
    request = read_json(request_path)
    response_path = request_path.with_name(
        request_path.name.replace(".request.json", ".response.json")
    )
    response = {
        "request_id": request["request_id"],
        "decision": decision,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "release-test",
    }
    if decision == "deny":
        response["message"] = "Denied by release test."
    response_path.write_text(json.dumps(response), encoding="utf-8")
    stdout = process.stdout.read() if process.stdout else ""
    stderr = process.stderr.read() if process.stderr else ""
    return_code = process.wait(timeout=10)
    assert return_code == 0, stderr
    output = json.loads(stdout)
    decision_body = output["hookSpecificOutput"]["decision"]
    assert decision_body["behavior"] == decision
    assert request["tool_name"] == expected_tool_name
    assert request["summary"] == expected_summary
    assert "Apply patch" not in str(request["summary"])
    assert "*** Begin Patch" not in str(request["summary"])
    assert not request_path.exists()
    assert not response_path.exists()
    state = read_json(state_dir / "codex-status.json")
    assert state["status"] == ("thinking" if decision == "allow" else "idle")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path)
    args = parser.parse_args()
    app = args.app.resolve()
    executable = app / "Contents" / "MacOS" / "GooglePiggy"
    assert executable.is_file()
    icon = app / "Contents" / "Resources" / "AppIcon.icns"
    assert icon.is_file()
    assert icon.read_bytes()[:4] == b"icns"
    manifest = read_json(app / "Contents" / "Resources" / "animation-manifest.json")
    animations = manifest["animations"]
    assert isinstance(animations, dict)
    for animation in animations.values():
        assert isinstance(animation, dict)
        for frame in animation["frames"]:
            assert isinstance(frame, dict)
            bounds = frame["visible_bounds"]
            assert isinstance(bounds, list) and len(bounds) == 4
            assert 0 <= bounds[0] < bounds[2] <= 640
            assert 0 <= bounds[1] < bounds[3] <= 640
    reveal_frames = animations["edge_reveal"]["frames"]
    assert len(reveal_frames) == 19
    reveal_bounds = [frame["visible_bounds"] for frame in reveal_frames]
    assert reveal_bounds[0] == reveal_bounds[-1]
    assert min(bounds[1] for bounds in reveal_bounds) < reveal_bounds[0][1]
    assert max(bounds[3] - bounds[1] for bounds in reveal_bounds) > (
        reveal_bounds[0][3] - reveal_bounds[0][1]
    )
    reveal_gif = app / "Contents" / "Resources" / "animations" / "edge-reveal.gif"
    assert reveal_gif.read_bytes()[:3] == b"GIF"
    with Image.open(reveal_gif) as image:
        assert image.size == (640, 640)
        assert image.n_frames == 19

    tail_images: dict[str, Image.Image] = {}
    for edge in ("left", "right", "top", "bottom"):
        tail = app / "Contents" / "Resources" / "edge-tail" / f"{edge}.png"
        assert tail.is_file()
        with Image.open(tail) as image:
            rgba = image.convert("RGBA")
            assert rgba.size == (
                EDGE_TAIL_CANVAS_SIZE,
                EDGE_TAIL_CANVAS_SIZE,
            )
            bounds = rgba.getchannel("A").getbbox()
            assert bounds is not None
            assert bounds[2] - bounds[0] >= 52
            assert bounds[3] - bounds[1] >= 52
            assert exposed_tail_cut_run(rgba, edge) <= (
                EDGE_TAIL_MAX_EXPOSED_CUT_RUN
            )
            overlap = EDGE_TAIL_SCREEN_OVERLAP[edge]
            if edge == "right":
                visible_depth = EDGE_TAIL_CANVAS_SIZE - overlap - bounds[0]
            elif edge == "bottom":
                visible_depth = EDGE_TAIL_CANVAS_SIZE - overlap - bounds[1]
            elif edge == "top":
                visible_depth = bounds[3] - overlap
            else:
                visible_depth = bounds[2] - overlap
            assert 22 <= visible_depth <= 24
            if edge == "left":
                assert bounds[0] == 0
            elif edge == "right":
                assert bounds[2] == EDGE_TAIL_CANVAS_SIZE
            elif edge == "top":
                assert bounds[1] == 0
            else:
                assert bounds[3] == EDGE_TAIL_CANVAS_SIZE
            tail_images[edge] = rgba.crop(bounds)
    expected_right = tail_images["bottom"].transpose(Image.Transpose.ROTATE_90)
    assert expected_right.size == tail_images["right"].size
    assert ImageChops.difference(expected_right, tail_images["right"]).getbbox() is None
    common_left = tail_images["bottom"].transpose(Image.Transpose.ROTATE_270)
    assert common_left.size != tail_images["left"].size or (
        ImageChops.difference(common_left, tail_images["left"]).getbbox()
        is not None
    )

    if args.source_dir is not None:
        source_dir = args.source_dir.resolve()
        controller_source = (
            source_dir / "macos" / "Sources" / "GooglePiggy" / "PetController.swift"
        ).read_text(encoding="utf-8")
        edge_hiding_source = (
            source_dir / "macos" / "Sources" / "GooglePiggy" / "EdgeHiding.swift"
        ).read_text(encoding="utf-8")
        installer_source = (source_dir / "macos" / "install.command").read_text(
            encoding="utf-8"
        )
        main_source = (
            source_dir / "macos" / "Sources" / "GooglePiggy" / "main.swift"
        ).read_text(encoding="utf-8")
        package_source = (source_dir / "tools" / "package_github_source.py").read_text(
            encoding="utf-8"
        )
        asset_export_source = (
            source_dir / "tools" / "export_macos_assets.py"
        ).read_text(encoding="utf-8")
        gitignore_source = (source_dir / ".gitignore").read_text(encoding="utf-8")
        assert "applicationShouldTerminateAfterLastWindowClosed" in controller_source
        assert "return false" in controller_source
        assert "restorePetWindowAfterMenuDismissal()" in controller_source
        assert controller_source.index("menu.popUp(") < controller_source.index(
            "restorePetWindowAfterMenuDismissal()"
        )
        assert "paragraph.lineBreakMode = .byCharWrapping" in controller_source
        assert "permissionBodyText(summary).draw(" in controller_source
        assert ".truncatesLastVisibleLine" not in controller_source
        assert "beginEdgeHideIfNeeded()" in controller_source
        assert "activityRequiresVisiblePet" in controller_source
        assert "let edgeFrame = screen.frame" in controller_source
        assert "let revealFrame = screen.visibleFrame" in controller_source
        edge_transition_source = controller_source[
            controller_source.index("private func beginEdgeHideIfNeeded"):
            controller_source.index("private func revealForActivityIfNeeded")
        ]
        assert edge_transition_source.count('switchVisual("edge_reveal"') == 2
        assert 'switchVisual("jump"' not in edge_transition_source
        assert "func canEnterEdgeHide(" in edge_hiding_source
        assert "func touchedDesktopEdge(" in edge_hiding_source
        assert "static let revealClearance" in edge_hiding_source
        assert "static let tailScreenOverlap: CGFloat = 30" in edge_hiding_source
        assert (
            "bottomRevealDropHeightMultiplier: CGFloat = 1"
            in edge_hiding_source
        )
        assert "bottomDrop: bottomRevealDrop(for:" in controller_source
        assert (
            "EDGE_TAIL_COMMON_CLOCKWISE_TILT_DEGREES = 55"
            in asset_export_source
        )
        assert (
            "EDGE_TAIL_LEFT_CLOCKWISE_TILT_DEGREES = 50"
            in asset_export_source
        )
        assert '"learning-materials"' in package_source
        assert "learning-materials/" in gitignore_source
        assert "--preview-edge-hide" in main_source
        assert "/hooks" in installer_source
        assert "Trust all and continue" in installer_source
        assert 'pkill -x "GooglePiggy"' in installer_source

    subprocess.run(
        [str(executable), "--self-test"],
        check=True,
        text=True,
        capture_output=True,
        timeout=30,
    )

    with tempfile.TemporaryDirectory(prefix="googlepiggy-macos-test-") as root:
        root_path = Path(root)
        state_dir = root_path / "state"
        codex_home = root_path / "codex"
        state_dir.mkdir()
        codex_home.mkdir()
        existing_hook = {
            "hooks": {
                "Stop": [
                    {
                        "matcher": "keep-me",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "printf existing",
                                "timeout": 5,
                            }
                        ],
                    }
                ]
            }
        }
        (codex_home / "hooks.json").write_text(
            json.dumps(existing_hook),
            encoding="utf-8",
        )
        env = os.environ.copy()
        env["GOOGLEPIGGY_STATE_DIR"] = str(state_dir)
        env["CODEX_HOME"] = str(codex_home)

        run(executable, ["--install-hooks"], env=env)
        installed = read_json(codex_home / "hooks.json")
        for event in (
            "SessionStart",
            "UserPromptSubmit",
            "PreToolUse",
            "PostToolUse",
            "Stop",
            "PermissionRequest",
        ):
            assert installed["hooks"][event][0]["hooks"][0]["command"].endswith(
                "' --hook"
            )
        assert any(
            group.get("matcher") == "keep-me"
            for group in installed["hooks"]["Stop"]
        )

        run(
            executable,
            ["--hook"],
            env=env,
            payload={
                "hook_event_name": "PreToolUse",
                "session_id": "session",
                "turn_id": "turn",
            },
        )
        state = read_json(state_dir / "codex-status.json")
        assert state["status"] == "thinking"

        run(
            executable,
            ["--hook"],
            env=env,
            payload={
                "hook_event_name": "Stop",
                "session_id": "session",
                "turn_id": "turn",
            },
        )
        state = read_json(state_dir / "codex-status.json")
        assert state["status"] == "success"

        run(
            executable,
            ["--hook"],
            env=env,
            payload={
                "hook_event_name": "PostToolUse",
                "session_id": "session",
                "turn_id": "turn",
            },
        )
        state = read_json(state_dir / "codex-status.json")
        assert state["status"] == "success"

        shell_permission = {
            "hook_event_name": "PermissionRequest",
            "session_id": "session-shell",
            "turn_id": "turn-shell",
            "tool_name": "Shell",
            "tool_input": {
                "command": "printf harmless",
                "token": "this-secret-must-not-be-shown",
            },
        }
        test_permission(
            executable,
            env,
            state_dir,
            "allow",
            shell_permission,
            "终端命令",
            "Codex 准备执行终端命令“printf harmless”，是否允许？",
        )
        test_permission(
            executable,
            env,
            state_dir,
            "deny",
            shell_permission,
            "终端命令",
            "Codex 准备执行终端命令“printf harmless”，是否允许？",
        )

        chinese_reason = (
            "是否允许我在现有文件夹"
            "“~/Documents/杂七杂八的东东”中创建“测试一下.txt”并写入 123？"
        )
        shell_with_chinese_reason = {
            "hook_event_name": "PermissionRequest",
            "session_id": "session-shell-chinese-reason",
            "turn_id": "turn-shell-chinese-reason",
            "tool_name": "Bash",
            "tool_input": {
                "command": "printf 123 > 测试一下.txt",
                "justification": f"Bash: {chinese_reason}",
            },
        }
        test_permission(
            executable,
            env,
            state_dir,
            "allow",
            shell_with_chinese_reason,
            "终端命令",
            (
                "Codex 准备创建或覆盖文件"
                f"“{Path.cwd() / '测试一下.txt'}”，是否允许？"
            ),
        )

        apply_patch_permission = {
            "hook_event_name": "PermissionRequest",
            "session_id": "session-apply-patch",
            "turn_id": "turn-apply-patch",
            "tool_name": "apply_patch",
            "tool_input": {
                "description": "Apply patch to update the requested file",
                "input": (
                    "*** Begin Patch\n"
                    "*** Update File: "
                    f"{Path.home()}/Documents/杂七杂八的东东/测试一下.txt\n"
                    "@@\n"
                    "-旧内容\n"
                    "+新内容\n"
                    "*** End Patch\n"
                )
            },
        }
        test_permission(
            executable,
            env,
            state_dir,
            "allow",
            apply_patch_permission,
            "修改文件",
            (
                "Codex 准备修改文件"
                f"“{Path.home()}/Documents/杂七杂八的东东/测试一下.txt”，"
                "是否允许执行本次修改？"
            ),
        )

        recovered_session_id = "session-recover-tool-details"
        recovered_session_cwd = Path.home() / "Documents" / "权限测试工程"
        recovered_update_turn = "turn-recover-update"
        recovered_mixed_turn = "turn-recover-mixed"
        recovered_relative_turn = "turn-recover-relative"
        recovered_shell_patch_turn = "turn-recover-shell-patch"
        recovered_shell_patch_no_reason_turn = (
            "turn-recover-shell-patch-no-reason"
        )
        recovered_open_turn = "turn-recover-open-app"
        recovered_brightness_turn = "turn-recover-brightness"
        recovered_create_turn = "turn-recover-create-file"
        recovered_delete_turn = "turn-recover-delete-file"
        write_session_tool_calls(
            codex_home,
            recovered_session_id,
            recovered_session_cwd,
            [
                (
                    recovered_update_turn,
                    "apply_patch",
                    (
                        "*** Begin Patch\n"
                        "*** Update File: "
                        f"{Path.home()}/Documents/权限测试/配置.txt\n"
                        "@@\n"
                        "-旧配置\n"
                        "+新配置\n"
                        "*** End Patch\n"
                    ),
                ),
                (
                    recovered_mixed_turn,
                    "apply_patch",
                    (
                        "*** Begin Patch\n"
                        "*** Add File: "
                        f"{Path.home()}/Documents/权限测试/新建.txt\n"
                        "+新内容\n"
                        "*** Delete File: "
                        f"{Path.home()}/Documents/权限测试/旧文件.txt\n"
                        "*** End Patch\n"
                    ),
                ),
                (
                    recovered_relative_turn,
                    "apply_patch",
                    (
                        "*** Begin Patch\n"
                        "*** Update File: config/相对配置.txt\n"
                        "@@\n"
                        "-旧配置\n"
                        "+新配置\n"
                        "*** End Patch\n"
                    ),
                ),
                (
                    recovered_shell_patch_turn,
                    "exec",
                    (
                        "const r = await tools.exec_command({"
                        "cmd:\"apply_patch <<'PATCH'\\n"
                        "*** Begin Patch\\n"
                        "*** Update File: "
                        f"{Path.home()}/Documents/杂七杂八的东东/"
                        "测试二下 副本 2.txt\\n"
                        "@@\\n-567890\\n+6\\n"
                        "*** End Patch\\nPATCH\","
                        f"workdir:\"{Path.cwd()}\","
                        "yield_time_ms:10000,max_output_tokens:2000,"
                        "sandbox_permissions:\"require_escalated\","
                        "justification:\"是否允许我将“"
                        f"{Path.home()}/Documents/杂七杂八的东东/"
                        "测试二下 副本 2.txt”的内容改为 6？\""
                        "});\ntext(r.output);\n"
                    ),
                ),
                (
                    recovered_shell_patch_turn,
                    "exec",
                    (
                        "const r = await tools.exec_command({"
                        "cmd:\"sed -n '1p' '"
                        f"{Path.home()}/Documents/杂七杂八的东东/"
                        "测试二下 副本 2.txt'\","
                        f"workdir:\"{Path.cwd()}\","
                        "yield_time_ms:10000,max_output_tokens:1000"
                        "});\ntext(r.output);\n"
                    ),
                ),
                (
                    recovered_shell_patch_no_reason_turn,
                    "exec",
                    (
                        "const r = await tools.exec_command({"
                        "cmd:\"apply_patch <<'PATCH'\\n"
                        "*** Begin Patch\\n"
                        "*** Add File: generated/新文件.txt\\n"
                        "+新内容\\n"
                        "*** End Patch\\nPATCH\","
                        f"workdir:\"{recovered_session_cwd}\","
                        "yield_time_ms:10000,max_output_tokens:2000,"
                        "sandbox_permissions:\"require_escalated\""
                        "});\ntext(r.output);\n"
                    ),
                ),
                (
                    recovered_open_turn,
                    "exec",
                    (
                        'const r = await tools.exec_command({"cmd":'
                        '"open -a \\"Safari\\"","workdir":"/tmp"});'
                    ),
                ),
                (
                    recovered_brightness_turn,
                    "exec",
                    (
                        'const r = await tools.exec_command({"cmd":'
                        '"brightness 0.5","workdir":"/tmp"});'
                    ),
                ),
                (
                    recovered_create_turn,
                    "exec",
                    (
                        'const r = await tools.exec_command({"cmd":'
                        f'"touch \\"{Path.home()}/Documents/权限测试/新文件.txt\\"",'
                        '"workdir":"/tmp"});'
                    ),
                ),
                (
                    recovered_delete_turn,
                    "exec",
                    (
                        'const r = await tools.exec_command({"cmd":'
                        f'"rm -f \\"{Path.home()}/Documents/权限测试/待删除.txt\\"",'
                        '"workdir":"/tmp"});'
                    ),
                ),
            ],
        )

        apply_patch_without_details = {
            "hook_event_name": "PermissionRequest",
            "session_id": recovered_session_id,
            "turn_id": recovered_update_turn,
            "tool_name": "apply_patch",
            "tool_input": {},
        }
        test_permission(
            executable,
            env,
            state_dir,
            "allow",
            apply_patch_without_details,
            "修改文件",
            (
                "Codex 准备修改文件"
                f"“{Path.home()}/Documents/权限测试/配置.txt”，"
                "是否允许执行本次修改？"
            ),
        )

        mixed_patch_without_details = {
            "hook_event_name": "PermissionRequest",
            "session_id": recovered_session_id,
            "turn_id": recovered_mixed_turn,
            "tool_name": "apply_patch",
            "tool_input": {},
        }
        test_permission(
            executable,
            env,
            state_dir,
            "allow",
            mixed_patch_without_details,
            "修改文件",
            (
                f"Codex 准备在“{Path.home()}/Documents/权限测试”中："
                "创建“新建.txt”；删除“旧文件.txt”，是否允许？"
            ),
        )

        relative_patch_without_details = {
            "hook_event_name": "PermissionRequest",
            "session_id": recovered_session_id,
            "turn_id": recovered_relative_turn,
            "tool_name": "apply_patch",
            "tool_input": {},
        }
        test_permission(
            executable,
            env,
            state_dir,
            "allow",
            relative_patch_without_details,
            "修改文件",
            (
                "Codex 准备修改文件"
                f"“{recovered_session_cwd}/config/相对配置.txt”，"
                "是否允许执行本次修改？"
            ),
        )

        shell_patch_without_details = {
            "hook_event_name": "PermissionRequest",
            "session_id": recovered_session_id,
            "turn_id": recovered_shell_patch_turn,
            "tool_name": "Bash",
            "tool_input": {},
        }
        test_permission(
            executable,
            env,
            state_dir,
            "allow",
            shell_patch_without_details,
            "终端命令",
            (
                "是否允许我将“"
                f"{Path.home()}/Documents/杂七杂八的东东/"
                "测试二下 副本 2.txt”的内容改为 6？"
            ),
        )

        shell_patch_no_reason_without_details = {
            "hook_event_name": "PermissionRequest",
            "session_id": recovered_session_id,
            "turn_id": recovered_shell_patch_no_reason_turn,
            "tool_name": "Bash",
            "tool_input": {},
        }
        test_permission(
            executable,
            env,
            state_dir,
            "allow",
            shell_patch_no_reason_without_details,
            "终端命令",
            (
                "Codex 准备创建文件"
                f"“{recovered_session_cwd}/generated/新文件.txt”并写入内容，"
                "是否允许？"
            ),
        )

        open_app_without_details = {
            "hook_event_name": "PermissionRequest",
            "session_id": recovered_session_id,
            "turn_id": recovered_open_turn,
            "tool_name": "Bash",
            "tool_input": {},
        }
        test_permission(
            executable,
            env,
            state_dir,
            "allow",
            open_app_without_details,
            "终端命令",
            "Codex 准备打开应用“Safari”，是否允许？",
        )

        brightness_without_details = {
            "hook_event_name": "PermissionRequest",
            "session_id": recovered_session_id,
            "turn_id": recovered_brightness_turn,
            "tool_name": "Bash",
            "tool_input": {},
        }
        test_permission(
            executable,
            env,
            state_dir,
            "allow",
            brightness_without_details,
            "终端命令",
            "Codex 准备将屏幕亮度调节为 50%，是否允许？",
        )

        create_file_without_details = {
            "hook_event_name": "PermissionRequest",
            "session_id": recovered_session_id,
            "turn_id": recovered_create_turn,
            "tool_name": "Bash",
            "tool_input": {},
        }
        test_permission(
            executable,
            env,
            state_dir,
            "allow",
            create_file_without_details,
            "终端命令",
            (
                "Codex 准备创建文件"
                f"“{Path.home()}/Documents/权限测试/新文件.txt”，是否允许？"
            ),
        )

        delete_file_without_details = {
            "hook_event_name": "PermissionRequest",
            "session_id": recovered_session_id,
            "turn_id": recovered_delete_turn,
            "tool_name": "Bash",
            "tool_input": {},
        }
        test_permission(
            executable,
            env,
            state_dir,
            "allow",
            delete_file_without_details,
            "终端命令",
            (
                "Codex 准备删除"
                f"“{Path.home()}/Documents/权限测试/待删除.txt”，是否允许？"
            ),
        )

        missing_details = run(
            executable,
            ["--hook"],
            env=env,
            payload={
                "hook_event_name": "PermissionRequest",
                "session_id": "missing-session",
                "turn_id": "missing-turn",
                "tool_name": "apply_patch",
                "tool_input": {},
            },
        )
        assert json.loads(missing_details.stdout) == {}
        assert not list((state_dir / "permission-requests").glob("*.request.json"))

        run(executable, ["--uninstall-hooks"], env=env)
        removed = read_json(codex_home / "hooks.json")
        assert all(
            "--hook" not in hook.get("command", "")
            for groups in removed["hooks"].values()
            for group in groups
            for hook in group.get("hooks", [])
        )
        assert removed["hooks"]["Stop"][0]["matcher"] == "keep-me"

    print("macos_release_test=ok")


if __name__ == "__main__":
    main()
