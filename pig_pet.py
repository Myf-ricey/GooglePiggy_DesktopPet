#!/usr/bin/env python3
"""A Windows desktop pet that plays the supplied pig GIFs without frame sampling."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
import subprocess
import sys
import time
import traceback
import winreg
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from codex_bridge import (
    default_heartbeat_path,
    default_permission_requests_dir,
    default_status_path,
    read_status,
    write_status,
)


APP_NAME = "GIF Pig Desktop Pet"
CLASS_NAME = "GifPigDesktopPetWindow"
AUTOSTART_VALUE_NAME = "GifPigDesktopPet"
AUTOSTART_REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
WINDOW_SIZE = 640
TARGET_BODY_WIDTH = 152
BODY_ANCHOR_X = WINDOW_SIZE - 230
BODY_ANCHOR_BOTTOM = WINDOW_SIZE - 70
JUMP_MAX_HORIZONTAL_TRAVEL = 25
JUMP_KEEP_INDICES = [*range(0, 26), *range(55, 90)]
LEFT_HUMP_SPEED_MULTIPLIER = 1.5
RIGHT_HUMP_REPAIR_PADDING = 8
RIGHT_HUMP_MAX_CAP_WIDTH = 5
IDLE_BREATH_FRAMES = 49
IDLE_BREATH_DURATION_MS = 45
IDLE_BREATH_MAX_SQUASH = 0.026
STATUS_POLL_INTERVAL_SECONDS = 0.25
THINKING_STATUS_STALE_SECONDS = 45.0
DRAG_THRESHOLD_PIXELS = 4
SUCCESS_EFFECT_DURATION_SECONDS = 1.35
HEARTBEAT_INTERVAL_SECONDS = 1.0
PERMISSION_STATUS_STALE_SECONDS = 620.0
MIN_DURATION_MS = 20
CACHE_VERSION = 21

WM_DESTROY = 0x0002
WM_TIMER = 0x0113
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_NCLBUTTONDOWN = 0x00A1
HTCAPTION = 2
MK_LBUTTON = 0x0001

CS_DBLCLKS = 0x0008
WS_POPUP = 0x80000000
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008

SW_SHOW = 5
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
BI_RGB = 0
DIB_RGB_COLORS = 0

MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
MF_CHECKED = 0x00000008
TPM_RETURNCMD = 0x0100
TPM_NONOTIFY = 0x0080
TPM_RIGHTBUTTON = 0x0002

SPI_GETWORKAREA = 0x0030
ERROR_ALREADY_EXISTS = 183


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", wintypes.LONG), ("cy", wintypes.LONG)]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_ubyte),
        ("BlendFlags", ctypes.c_ubyte),
        ("SourceConstantAlpha", ctypes.c_ubyte),
        ("AlphaFormat", ctypes.c_ubyte),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.GetLastError.restype = wintypes.DWORD

user32.DefWindowProcW.restype = LRESULT
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = wintypes.ATOM
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.HMENU,
    wintypes.HINSTANCE,
    wintypes.LPVOID,
]
user32.CreateWindowExW.restype = wintypes.HWND
user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
user32.LoadCursorW.restype = wintypes.HANDLE
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.UpdateLayeredWindow.argtypes = [
    wintypes.HWND,
    wintypes.HDC,
    ctypes.POINTER(POINT),
    ctypes.POINTER(SIZE),
    wintypes.HDC,
    ctypes.POINTER(POINT),
    wintypes.DWORD,
    ctypes.POINTER(BLENDFUNCTION),
    wintypes.DWORD,
]
user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
user32.GetCursorPos.restype = wintypes.BOOL
user32.SendMessageW.restype = LRESULT
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SetCapture.argtypes = [wintypes.HWND]
user32.SetCapture.restype = wintypes.HWND
user32.ReleaseCapture.restype = wintypes.BOOL
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
user32.SetWindowPos.restype = wintypes.BOOL
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, ctypes.c_void_p]
user32.SetTimer.restype = ctypes.c_size_t
user32.KillTimer.argtypes = [wintypes.HWND, ctypes.c_size_t]
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
user32.TrackPopupMenu.argtypes = [
    wintypes.HMENU,
    wintypes.UINT,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    ctypes.c_void_p,
]
user32.TrackPopupMenu.restype = wintypes.UINT
user32.DestroyMenu.argtypes = [wintypes.HMENU]

gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateDIBSection.argtypes = [
    wintypes.HDC,
    ctypes.POINTER(BITMAPINFO),
    wintypes.UINT,
    ctypes.POINTER(ctypes.c_void_p),
    wintypes.HANDLE,
    wintypes.DWORD,
]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
gdi32.SelectObject.restype = wintypes.HANDLE
gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
gdi32.DeleteDC.argtypes = [wintypes.HDC]


@dataclass
class Animation:
    key: str
    label: str
    source: Path
    frames: list[Image.Image]
    durations: list[int]
    source_indices: list[int]

    @property
    def total_duration(self) -> int:
        return sum(self.durations)


def application_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def default_source_dir(app_dir: Path) -> Path:
    return app_dir / "assets" / "source-gifs"


def heartbeat_path_for_status(status_path: Path) -> Path:
    default_state_dir = default_status_path().parent
    if status_path.parent == default_state_dir:
        return default_heartbeat_path()
    return status_path.parent / "pig-heartbeat.json"


def permission_dir_for_status(status_path: Path) -> Path:
    default_state_dir = default_status_path().parent
    if status_path.parent == default_state_dir:
        return default_permission_requests_dir()
    return status_path.parent / "permission-requests"


def startup_command(app_dir: Path) -> str:
    if getattr(sys, "frozen", False):
        return subprocess.list2cmdline([str(Path(sys.executable).resolve())])
    python = Path(sys.executable).resolve()
    pythonw = python.with_name("pythonw.exe")
    executable = pythonw if pythonw.is_file() else python
    return subprocess.list2cmdline([str(executable), str(app_dir / "pig_pet.py")])


def set_autostart(enabled: bool, app_dir: Path) -> None:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REGISTRY_KEY) as key:
        if enabled:
            winreg.SetValueEx(
                key,
                AUTOSTART_VALUE_NAME,
                0,
                winreg.REG_SZ,
                startup_command(app_dir),
            )
        else:
            try:
                winreg.DeleteValue(key, AUTOSTART_VALUE_NAME)
            except FileNotFoundError:
                pass


def is_autostart_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REGISTRY_KEY) as key:
            winreg.QueryValueEx(key, AUTOSTART_VALUE_NAME)
            return True
    except FileNotFoundError:
        return False


def acquire_single_instance() -> wintypes.HANDLE | None:
    handle = kernel32.CreateMutexW(None, False, f"Local\\{CLASS_NAME}")
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        return None
    return handle


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clear_transparent_rgb(image: Image.Image) -> Image.Image:
    rgba = np.array(image.convert("RGBA"))
    rgba[rgba[:, :, 3] == 0, :3] = 0
    return Image.fromarray(rgba, "RGBA")


def repair_right_hump_edge_clipping(frame: Image.Image) -> Image.Image:
    """Lightly soften cheek clipping at the right edge of the source GIF.

    The source right-hump GIF sometimes touches its right canvas edge. Earlier
    builds used a broad elliptical cap for every touching run; that accidentally
    glued ears to the face and made intermediate frames bulge. This repair keeps
    the original silhouette and only adds a few tapered pixels to the lower
    cheek/body run.
    """
    rgba = np.array(frame.convert("RGBA"))
    height, width = rgba.shape[:2]
    touching_rows = np.flatnonzero(rgba[:, width - 1, 3] > 16)
    if touching_rows.size == 0:
        return frame

    runs: list[tuple[int, int]] = []
    start = previous = int(touching_rows[0])
    for row in touching_rows[1:]:
        row = int(row)
        if row != previous + 1:
            runs.append((start, previous))
            start = row
        previous = row
    runs.append((start, previous))

    expanded = np.zeros(
        (height, width + RIGHT_HUMP_REPAIR_PADDING, 4),
        dtype=np.uint8,
    )
    expanded[:, :width] = rgba
    for index, (start, end) in enumerate(runs):
        run_length = end - start + 1
        if len(runs) > 1 and index == 0:
            cap_width = min(2, max(1, round(run_length * 0.04)))
        elif end < height * 0.36:
            continue
        else:
            if run_length >= 80:
                start = start + round(run_length * 0.45)
                run_length = end - start + 1
            if run_length <= 0:
                continue
            cap_width = min(
                RIGHT_HUMP_MAX_CAP_WIDTH,
                max(1, round(run_length * 0.06)),
            )
        center = (start + end) / 2
        half_height = max(1.0, (end - start) / 2)
        for y in range(start, end + 1):
            normalized_y = (y - center) / half_height
            continuous_width = cap_width * math.sqrt(
                max(0.0, 1.0 - normalized_y * normalized_y)
            )
            full_width = int(math.floor(continuous_width))
            partial_alpha = continuous_width - full_width
            edge_pixel = rgba[y, width - 1].copy()
            if full_width:
                expanded[y, width : width + full_width] = edge_pixel
            if partial_alpha > 0 and width + full_width < expanded.shape[1]:
                partial_pixel = edge_pixel.copy()
                partial_pixel[3] = round(int(edge_pixel[3]) * partial_alpha)
                expanded[y, width + full_width] = partial_pixel

    return clear_transparent_rgb(Image.fromarray(expanded, "RGBA"))


def largest_component(mask: np.ndarray) -> np.ndarray:
    height, width = mask.shape
    seen = np.zeros((height, width), dtype=bool)
    largest: list[tuple[int, int]] = []
    for y in range(height):
        for x in range(width):
            if not mask[y, x] or seen[y, x]:
                continue
            component: list[tuple[int, int]] = []
            stack = [(x, y)]
            seen[y, x] = True
            while stack:
                current_x, current_y = stack.pop()
                component.append((current_x, current_y))
                for neighbor_y in range(max(0, current_y - 1), min(height, current_y + 2)):
                    for neighbor_x in range(max(0, current_x - 1), min(width, current_x + 2)):
                        if mask[neighbor_y, neighbor_x] and not seen[neighbor_y, neighbor_x]:
                            seen[neighbor_y, neighbor_x] = True
                            stack.append((neighbor_x, neighbor_y))
            if len(component) > len(largest):
                largest = component

    result = np.zeros((height, width), dtype=np.uint8)
    for x, y in largest:
        result[y, x] = 255
    return result


def center_component(
    mask: np.ndarray,
    center: tuple[float, float] | None = None,
) -> np.ndarray:
    height, width = mask.shape
    points = np.argwhere(mask)
    result = np.zeros((height, width), dtype=np.uint8)
    if points.size == 0:
        return result

    if center is None:
        center_x = (width - 1) / 2
        center_y = (height - 1) / 2
    else:
        center_x, center_y = center
    distances = (points[:, 0] - center_y) ** 2 + (points[:, 1] - center_x) ** 2
    seed_y, seed_x = points[int(np.argmin(distances))]

    seen = np.zeros((height, width), dtype=bool)
    stack = [(int(seed_x), int(seed_y))]
    seen[seed_y, seed_x] = True
    while stack:
        current_x, current_y = stack.pop()
        result[current_y, current_x] = 255
        for neighbor_y in range(max(0, current_y - 1), min(height, current_y + 2)):
            for neighbor_x in range(max(0, current_x - 1), min(width, current_x + 2)):
                if mask[neighbor_y, neighbor_x] and not seen[neighbor_y, neighbor_x]:
                    seen[neighbor_y, neighbor_x] = True
                    stack.append((neighbor_x, neighbor_y))
    return result


def large_components(mask: np.ndarray, minimum_pixels: int) -> np.ndarray:
    height, width = mask.shape
    seen = np.zeros((height, width), dtype=bool)
    result = np.zeros((height, width), dtype=np.uint8)
    for y in range(height):
        for x in range(width):
            if not mask[y, x] or seen[y, x]:
                continue
            component: list[tuple[int, int]] = []
            stack = [(x, y)]
            seen[y, x] = True
            while stack:
                current_x, current_y = stack.pop()
                component.append((current_x, current_y))
                for neighbor_y in range(max(0, current_y - 1), min(height, current_y + 2)):
                    for neighbor_x in range(max(0, current_x - 1), min(width, current_x + 2)):
                        if mask[neighbor_y, neighbor_x] and not seen[neighbor_y, neighbor_x]:
                            seen[neighbor_y, neighbor_x] = True
                            stack.append((neighbor_x, neighbor_y))
            if len(component) >= minimum_pixels:
                for component_x, component_y in component:
                    result[component_y, component_x] = 255
    return result


def large_and_detached_components(
    mask: np.ndarray,
    minimum_pixels: int,
) -> tuple[np.ndarray, np.ndarray]:
    height, width = mask.shape
    seen = np.zeros((height, width), dtype=bool)
    components: list[list[tuple[int, int]]] = []
    for y in range(height):
        for x in range(width):
            if not mask[y, x] or seen[y, x]:
                continue
            component: list[tuple[int, int]] = []
            stack = [(x, y)]
            seen[y, x] = True
            while stack:
                current_x, current_y = stack.pop()
                component.append((current_x, current_y))
                for neighbor_y in range(max(0, current_y - 1), min(height, current_y + 2)):
                    for neighbor_x in range(max(0, current_x - 1), min(width, current_x + 2)):
                        if mask[neighbor_y, neighbor_x] and not seen[neighbor_y, neighbor_x]:
                            seen[neighbor_y, neighbor_x] = True
                            stack.append((neighbor_x, neighbor_y))
            if len(component) >= minimum_pixels:
                components.append(component)

    selected = np.zeros((height, width), dtype=np.uint8)
    detached = np.zeros((height, width), dtype=np.uint8)
    if not components:
        return selected, detached
    components.sort(key=len, reverse=True)
    for index, component in enumerate(components):
        for component_x, component_y in component:
            selected[component_y, component_x] = 255
            if index > 0:
                detached[component_y, component_x] = 255
    return selected, detached


def detached_large_components(mask: np.ndarray, minimum_pixels: int) -> np.ndarray:
    height, width = mask.shape
    seen = np.zeros((height, width), dtype=bool)
    components: list[list[tuple[int, int]]] = []
    for y in range(height):
        for x in range(width):
            if not mask[y, x] or seen[y, x]:
                continue
            component: list[tuple[int, int]] = []
            stack = [(x, y)]
            seen[y, x] = True
            while stack:
                current_x, current_y = stack.pop()
                component.append((current_x, current_y))
                for neighbor_y in range(max(0, current_y - 1), min(height, current_y + 2)):
                    for neighbor_x in range(max(0, current_x - 1), min(width, current_x + 2)):
                        if mask[neighbor_y, neighbor_x] and not seen[neighbor_y, neighbor_x]:
                            seen[neighbor_y, neighbor_x] = True
                            stack.append((neighbor_x, neighbor_y))
            if len(component) >= minimum_pixels:
                components.append(component)

    result = np.zeros((height, width), dtype=np.uint8)
    if len(components) <= 1:
        return result
    components.sort(key=len, reverse=True)
    for component in components[1:]:
        for component_x, component_y in component:
            result[component_y, component_x] = 255
    return result


def add_detached_component_halo(
    image: Image.Image,
    detached_mask: np.ndarray | None = None,
) -> Image.Image:
    rgba = np.array(image.convert("RGBA"))
    alpha = rgba[:, :, 3]
    if detached_mask is None:
        height, width = alpha.shape
        minimum_pixels = max(32, round(height * width * 0.00016))
        detached_mask = detached_large_components(alpha > 32, minimum_pixels)
    detached = detached_mask.astype(bool)
    if not detached.any():
        return image

    halo_image = Image.fromarray(np.uint8(detached) * 255, "L").filter(
        ImageFilter.MaxFilter(9)
    )
    halo = (np.array(halo_image) > 0) & (~detached) & (alpha < 180)
    rgba[:, :, 0][halo] = 255
    rgba[:, :, 1][halo] = 250
    rgba[:, :, 2][halo] = 244
    rgba[:, :, 3][halo] = np.maximum(alpha[halo], 138)
    return clear_transparent_rgb(Image.fromarray(rgba, "RGBA"))


def fill_mask_holes(mask: np.ndarray) -> np.ndarray:
    height, width = mask.shape
    outside = np.zeros((height, width), dtype=bool)
    stack: list[tuple[int, int]] = []

    for x in range(width):
        if not mask[0, x]:
            stack.append((x, 0))
            outside[0, x] = True
        if not mask[height - 1, x] and not outside[height - 1, x]:
            stack.append((x, height - 1))
            outside[height - 1, x] = True
    for y in range(height):
        if not mask[y, 0] and not outside[y, 0]:
            stack.append((0, y))
            outside[y, 0] = True
        if not mask[y, width - 1] and not outside[y, width - 1]:
            stack.append((width - 1, y))
            outside[y, width - 1] = True

    while stack:
        current_x, current_y = stack.pop()
        for neighbor_y in range(max(0, current_y - 1), min(height, current_y + 2)):
            for neighbor_x in range(max(0, current_x - 1), min(width, current_x + 2)):
                if not mask[neighbor_y, neighbor_x] and not outside[neighbor_y, neighbor_x]:
                    outside[neighbor_y, neighbor_x] = True
                    stack.append((neighbor_x, neighbor_y))

    return mask | (~outside)


def keep_largest_alpha_component(image: Image.Image) -> Image.Image:
    rgba = np.array(image.convert("RGBA"))
    alpha = rgba[:, :, 3]
    subject = center_component(alpha >= 24)
    support = Image.fromarray(subject, "L").filter(ImageFilter.MaxFilter(5))
    support_array = np.array(support, dtype=np.float32) / 255.0
    cleaned_alpha = np.uint8(np.clip(alpha.astype(np.float32) * support_array, 0, 255))
    cleaned_alpha[cleaned_alpha < 48] = 0
    final_subject = center_component(cleaned_alpha > 0).astype(bool)
    cleaned_alpha[~final_subject] = 0
    rgba[:, :, 3] = cleaned_alpha
    rgba[cleaned_alpha == 0, :3] = 0
    return Image.fromarray(rgba, "RGBA")


def remove_dark_background(
    frame: Image.Image,
    preserve_detached_components: bool = False,
) -> Image.Image:
    rgb = np.array(frame.convert("RGB"), dtype=np.float32)
    height, width = rgb.shape[:2]
    corner_size = max(4, min(height, width) // 24)
    corner_samples = np.concatenate(
        [
            rgb[:corner_size, :corner_size].reshape(-1, 3),
            rgb[:corner_size, -corner_size:].reshape(-1, 3),
            rgb[-corner_size:, :corner_size].reshape(-1, 3),
            rgb[-corner_size:, -corner_size:].reshape(-1, 3),
        ],
        axis=0,
    )
    background = np.median(corner_samples, axis=0)
    distance = np.linalg.norm(rgb - background[None, None, :], axis=2)
    seed = distance > 22.0
    detached_mask: np.ndarray | None = None
    if preserve_detached_components:
        minimum_pixels = max(120, round(height * width * 0.0006))
        subject, detached_mask = large_and_detached_components(seed, minimum_pixels)
    else:
        subject = center_component(seed)
    if not subject.any():
        return frame.convert("RGBA")

    filled = fill_mask_holes(subject.astype(bool))
    alpha_image = Image.fromarray(np.uint8(filled) * 255, "L").filter(
        ImageFilter.GaussianBlur(0.45)
    )
    alpha_array = np.array(alpha_image, dtype=np.uint8)
    alpha_array[alpha_array < 18] = 0
    alpha_float = alpha_array.astype(np.float32) / 255.0
    denominator = np.maximum(alpha_float[:, :, None], 0.08)
    foreground = np.clip(
        (rgb - (1.0 - alpha_float[:, :, None]) * background[None, None, :])
        / denominator,
        0,
        255,
    )
    rgba = np.dstack([np.uint8(foreground), alpha_array])
    image = clear_transparent_rgb(Image.fromarray(rgba, "RGBA"))
    if preserve_detached_components:
        return add_detached_component_halo(image, detached_mask)
    return keep_largest_alpha_component(image)


def remove_light_background(frame: Image.Image) -> Image.Image:
    rgb = np.array(frame.convert("RGB"), dtype=np.float32)
    maximum = rgb.max(axis=2)
    minimum = rgb.min(axis=2)
    chroma = maximum - minimum
    luminance = rgb.mean(axis=2)

    darkness_alpha = np.clip((168.0 - luminance) / 24.0, 0.0, 1.0)
    color_alpha = np.clip((chroma - 5.0) / 18.0, 0.0, 1.0)
    alpha = np.maximum(darkness_alpha, color_alpha)
    alpha[(chroma < 7.0) & (luminance > 170.0)] = 0.0
    alpha[alpha < 0.055] = 0.0

    # GIF palette compression leaves detached gray/tinted artifacts across the
    # background. Keep the single connected subject and only a narrow edge band.
    subject = center_component(alpha >= 0.25)
    support = Image.fromarray(subject, "L").filter(ImageFilter.MaxFilter(7))
    support_array = np.array(support, dtype=np.float32) / 255.0
    alpha *= support_array
    alpha[alpha < 0.12] = 0.0

    alpha_image = Image.fromarray(np.uint8(np.clip(alpha * 255.0, 0, 255)), "L")
    alpha_image = alpha_image.filter(ImageFilter.GaussianBlur(0.18))
    alpha_array = np.array(alpha_image, dtype=np.uint8)
    alpha_array[alpha_array < 20] = 0
    alpha_image = Image.fromarray(alpha_array, "L")
    alpha_float = np.array(alpha_image, dtype=np.float32) / 255.0

    background = np.full_like(rgb, 247.0)
    denominator = np.maximum(alpha_float[:, :, None], 0.08)
    foreground = np.clip(
        (rgb - (1.0 - alpha_float[:, :, None]) * background) / denominator,
        0,
        255,
    )
    rgba = np.dstack([np.uint8(foreground), np.array(alpha_image, dtype=np.uint8)])
    return clear_transparent_rgb(Image.fromarray(rgba, "RGBA"))


def unify_carrot_pig_skin(frame: Image.Image) -> Image.Image:
    rgba = np.array(frame.convert("RGBA"))
    red = rgba[:, :, 0].astype(np.int16)
    green = rgba[:, :, 1].astype(np.int16)
    blue = rgba[:, :, 2].astype(np.int16)
    alpha = rgba[:, :, 3]

    # Match the other GIFs' RGB(255, 210, 177) peach while preserving the
    # darker skin shading. Pink markings, carrot, rod, eyes, and outlines stay
    # outside this warm light-peach mask.
    skin = (
        (alpha > 32)
        & (red > 195)
        & (green > 135)
        & (green < 225)
        & (blue > 110)
        & (blue < 210)
        & ((red - green) > 20)
        & ((green - blue) > 8)
        & ((red - blue) > 40)
    )
    rgba[:, :, 0][skin] = np.uint8(np.clip(red[skin] + 20, 0, 255))
    rgba[:, :, 1][skin] = np.uint8(np.clip(green[skin] + 21, 0, 255))
    rgba[:, :, 2][skin] = np.uint8(np.clip(blue[skin] + 19, 0, 255))
    return clear_transparent_rgb(Image.fromarray(rgba, "RGBA"))


def pig_body_bbox(
    frame: Image.Image,
    isolate_center_component: bool = False,
) -> tuple[int, int, int, int]:
    rgba = np.array(frame.convert("RGBA"))
    red = rgba[:, :, 0].astype(np.int16)
    green = rgba[:, :, 1].astype(np.int16)
    blue = rgba[:, :, 2].astype(np.int16)
    alpha = rgba[:, :, 3]
    peach = (
        (alpha > 80)
        & (red > 190)
        & (green > 130)
        & (blue > 100)
        & ((red - green) > 15)
        & ((green - blue) > 8)
        & ((red - blue) > 35)
    )
    if isolate_center_component:
        detection_center = None
        if frame.size == (WINDOW_SIZE, WINDOW_SIZE):
            detection_center = (
                BODY_ANCHOR_X,
                BODY_ANCHOR_BOTTOM - TARGET_BODY_WIDTH * 0.45,
            )
        body = center_component(peach, detection_center).astype(bool)
    else:
        body = peach
    ys, xs = np.where(body)
    if xs.size == 0:
        bbox = frame.getbbox()
        if bbox is None:
            raise ValueError("frame has no visible pig body")
        return bbox
    return (int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1))


def normalize_animation_frames(
    key: str,
    frames: list[Image.Image],
) -> tuple[list[Image.Image], dict[str, object]]:
    body_boxes = [
        pig_body_bbox(frame, isolate_center_component=(key == "carrot"))
        for frame in frames
    ]
    reference_box = body_boxes[0]
    reference_width = reference_box[2] - reference_box[0]
    scale = TARGET_BODY_WIDTH / reference_width

    first_center_x = (reference_box[0] + reference_box[2]) / 2
    first_bottom = reference_box[3]
    body_centers_x = [(box[0] + box[2]) / 2 for box in body_boxes]
    minimum_center_x = min(body_centers_x)
    horizontal_span = max(1.0, first_center_x - minimum_center_x)
    motion_xs = [0.0] * len(frames)
    motion_ys = [0.0] * len(frames)
    if key == "jump":
        raw_motion_xs = [
            (body_center_x - first_center_x)
            / horizontal_span
            * JUMP_MAX_HORIZONTAL_TRAVEL
            for body_center_x in body_centers_x
        ]
        raw_motion_ys = [
            (body_box[3] - first_bottom) * scale
            for body_box in body_boxes
        ]
        final_motion_x = raw_motion_xs[-1]
        final_motion_y = raw_motion_ys[-1]
        denominator = max(1, len(frames) - 1)
        for index, (raw_x, raw_y) in enumerate(
            zip(raw_motion_xs, raw_motion_ys)
        ):
            progress = index / denominator
            motion_xs[index] = raw_x - progress * final_motion_x
            motion_ys[index] = raw_y - progress * final_motion_y

    normalized: list[Image.Image] = []
    for frame, body_box, motion_x, motion_y in zip(
        frames,
        body_boxes,
        motion_xs,
        motion_ys,
    ):
        subject_box = frame.getbbox()
        if subject_box is None:
            raise ValueError("frame is empty")
        subject = frame.crop(subject_box)
        resized_width = max(1, round(subject.width * scale))
        resized_height = max(1, round(subject.height * scale))
        subject = subject.resize((resized_width, resized_height), Image.Resampling.LANCZOS)
        if key == "carrot":
            subject = keep_largest_alpha_component(subject)

        body_center_in_subject = (
            ((body_box[0] + body_box[2]) / 2 - subject_box[0]) * scale
        )
        body_bottom_in_subject = (body_box[3] - subject_box[1]) * scale

        left = round(BODY_ANCHOR_X + motion_x - body_center_in_subject)
        top = round(BODY_ANCHOR_BOTTOM + motion_y - body_bottom_in_subject)
        canvas = Image.new("RGBA", (WINDOW_SIZE, WINDOW_SIZE), (0, 0, 0, 0))
        canvas.alpha_composite(subject, (left, top))
        measured_box = pig_body_bbox(
            canvas,
            isolate_center_component=(key == "carrot"),
        )
        measured_center_x = (measured_box[0] + measured_box[2]) / 2
        correction_x = round(BODY_ANCHOR_X + motion_x - measured_center_x)
        correction_y = round(BODY_ANCHOR_BOTTOM + motion_y - measured_box[3])
        if correction_x or correction_y:
            aligned = Image.new(
                "RGBA",
                (WINDOW_SIZE, WINDOW_SIZE),
                (0, 0, 0, 0),
            )
            aligned.alpha_composite(canvas, (correction_x, correction_y))
            canvas = aligned
        normalized.append(clear_transparent_rgb(canvas))

    return normalized, {
        "reference_body_bbox": list(reference_box),
        "reference_body_width": reference_width,
        "scale": scale,
    }


def identify_sources(source_dir: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    paths = sorted(source_dir.glob("*.gif"))
    explicit_names = {
        "left_fixed.gif": "left",
        "flat.gif": "flat",
        "jump.gif": "jump",
        "carrot.gif": "carrot",
        "question.gif": "question",
        "right_hump.gif": "right",
    }
    for path in paths:
        role = explicit_names.get(path.name.lower())
        if role:
            result[role] = path

    for path in paths:
        if path in result.values():
            continue
        with Image.open(path) as opened:
            size = opened.size
            opaque = opened.mode != "RGBA" and "transparency" not in opened.info
        name = path.name.lower()
        if "left_fixed" in name and "left" not in result:
            result["left"] = path
        elif size == (347, 304) and "right" not in result:
            result["right"] = path
        elif size == (300, 130) and "jump" not in result:
            result["jump"] = path
        elif size == (512, 512) and opaque and "carrot" not in result:
            result["carrot"] = path
        elif "question" in name and "question" not in result:
            result["question"] = path
        elif size == (512, 512) and "flat" not in result:
            result["flat"] = path
    if "left" not in result and "right" in result:
        result["left"] = result["right"]
    missing = sorted({"left", "jump", "flat", "carrot", "question"} - set(result))
    if missing:
        raise SystemExit(f"Could not identify GIF roles: {', '.join(missing)}")
    return result


def load_animation(key: str, label: str, source: Path, remove_background: bool) -> Animation:
    source_frames: list[Image.Image] = []
    source_durations: list[int] = []
    with Image.open(source) as opened:
        for index in range(opened.n_frames):
            opened.seek(index)
            frame = opened.convert("RGBA").copy()
            if remove_background:
                frame = remove_light_background(frame)
                frame = unify_carrot_pig_skin(frame)
            if key == "question":
                frame = remove_dark_background(
                    frame,
                    preserve_detached_components=True,
                )
            frame = clear_transparent_rgb(frame)
            if key == "left" and source.name.lower() != "left_fixed.gif":
                frame = repair_right_hump_edge_clipping(frame)
                frame = frame.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            if remove_background:
                frame = keep_largest_alpha_component(frame)
            frame = clear_transparent_rgb(frame)
            source_frames.append(frame)
            source_durations.append(max(MIN_DURATION_MS, int(opened.info.get("duration", 100))))

    source_indices = list(range(len(source_frames)))
    if key == "jump":
        source_indices = JUMP_KEEP_INDICES
    selected_frames = [source_frames[index] for index in source_indices]
    durations = [source_durations[index] for index in source_indices]
    if key == "left":
        durations = [
            max(MIN_DURATION_MS, round(duration / LEFT_HUMP_SPEED_MULTIPLIER))
            for duration in durations
        ]
    frames, _normalization = normalize_animation_frames(key, selected_frames)
    return Animation(
        key=key,
        label=label,
        source=source,
        frames=frames,
        durations=durations,
        source_indices=source_indices,
    )


def make_idle_breathing_animation(base: Animation) -> Animation:
    base_frame = base.frames[0]
    subject_box = base_frame.getbbox()
    if subject_box is None:
        raise ValueError("base idle frame is empty")
    subject = base_frame.crop(subject_box)
    frames: list[Image.Image] = []
    denominator = max(1, IDLE_BREATH_FRAMES - 1)
    for index in range(IDLE_BREATH_FRAMES):
        phase = 2.0 * math.pi * index / denominator
        squash = IDLE_BREATH_MAX_SQUASH * (0.5 - 0.5 * math.cos(phase))
        resized_height = max(1, round(subject.height * (1.0 - squash)))
        resized = subject.resize(
            (subject.width, resized_height),
            Image.Resampling.LANCZOS,
        )
        canvas = Image.new("RGBA", base_frame.size, (0, 0, 0, 0))
        top = subject_box[3] - resized_height
        canvas.alpha_composite(resized, (subject_box[0], top))
        frames.append(clear_transparent_rgb(canvas))

    return Animation(
        key="idle",
        label="呼吸待机",
        source=base.source,
        frames=frames,
        durations=[IDLE_BREATH_DURATION_MS] * len(frames),
        source_indices=[0] * len(frames),
    )


def cache_signature(source_dir: Path) -> dict[str, object]:
    sources = {
        key: path
        for key, path in identify_sources(source_dir).items()
        if key in {"left", "jump", "flat", "carrot", "question"}
    }
    return {
        "version": CACHE_VERSION,
        "target_body_width": TARGET_BODY_WIDTH,
        "body_anchor": [BODY_ANCHOR_X, BODY_ANCHOR_BOTTOM],
        "jump_max_horizontal_travel": JUMP_MAX_HORIZONTAL_TRAVEL,
        "jump_keep_indices": JUMP_KEEP_INDICES,
        "left_hump_speed_multiplier": LEFT_HUMP_SPEED_MULTIPLIER,
        "right_hump_repair_padding": RIGHT_HUMP_REPAIR_PADDING,
        "right_hump_max_cap_width": RIGHT_HUMP_MAX_CAP_WIDTH,
        "idle_breath_frames": IDLE_BREATH_FRAMES,
        "idle_breath_duration_ms": IDLE_BREATH_DURATION_MS,
        "idle_breath_max_squash": IDLE_BREATH_MAX_SQUASH,
        "sources": {
            key: {
                "name": path.name,
                "size": path.stat().st_size,
                "sha256": file_sha256(path),
            }
            for key, path in sources.items()
        },
    }


def save_animation_cache(
    animations: dict[str, Animation],
    cache_dir: Path,
    source_dir: Path,
) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "signature": cache_signature(source_dir),
        "animations": {},
    }
    for key, animation in animations.items():
        np.savez_compressed(
            cache_dir / f"{key}.npz",
            frames=np.stack([np.asarray(frame, dtype=np.uint8) for frame in animation.frames]),
            durations=np.asarray(animation.durations, dtype=np.int32),
            source_indices=np.asarray(animation.source_indices, dtype=np.int32),
        )
        manifest["animations"][key] = {
            "label": animation.label,
            "source": animation.source.name,
            "file": f"{key}.npz",
        }
    (cache_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_animation_cache(
    cache_dir: Path,
    source_dir: Path,
) -> dict[str, Animation] | None:
    manifest_path = cache_dir / "manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("signature") != cache_signature(source_dir):
            return None
        animations: dict[str, Animation] = {}
        for key, info in manifest["animations"].items():
            cache_file = cache_dir / info["file"]
            with np.load(cache_file) as cached:
                frames = [
                    Image.fromarray(frame.copy(), "RGBA")
                    for frame in cached["frames"]
                ]
                durations = [int(value) for value in cached["durations"]]
                source_indices = [int(value) for value in cached["source_indices"]]
            animations[key] = Animation(
                key=key,
                label=info["label"],
                source=Path(info["source"]),
                frames=frames,
                durations=durations,
                source_indices=source_indices,
            )
        return animations
    except Exception:
        return None


def premultiplied_bgra(canvas: Image.Image) -> bytes:
    rgba = np.asarray(canvas.convert("RGBA"), dtype=np.uint16)
    alpha = rgba[:, :, 3:4]
    premultiplied = (rgba[:, :, :3] * alpha + 127) // 255
    bgra = np.empty((rgba.shape[0], rgba.shape[1], 4), dtype=np.uint8)
    bgra[:, :, 0] = premultiplied[:, :, 2]
    bgra[:, :, 1] = premultiplied[:, :, 1]
    bgra[:, :, 2] = premultiplied[:, :, 0]
    bgra[:, :, 3] = rgba[:, :, 3]
    return bgra.tobytes()


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json_file(path: Path) -> dict[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary_path, path)


def load_ui_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    fonts_dir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    candidates = [
        fonts_dir / ("msyhbd.ttc" if bold else "msyh.ttc"),
        fonts_dir / ("Microsoft YaHei UI Bold.ttf" if bold else "Microsoft YaHei UI.ttf"),
        fonts_dir / ("simhei.ttf" if bold else "simsun.ttc"),
        fonts_dir / "Dengb.ttf" if bold else fonts_dir / "Deng.ttf",
        fonts_dir / ("seguisb.ttf" if bold else "segoeui.ttf"),
        "msyhbd.ttc" if bold else "msyh.ttc",
        "Microsoft YaHei UI Bold.ttf" if bold else "Microsoft YaHei UI.ttf",
        "simhei.ttf" if bold else "simsun.ttc",
        "seguisb.ttf" if bold else "segoeui.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(str(candidate), size)
        except (OSError, TypeError):
            continue
    return ImageFont.load_default()


def wrap_text_by_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
    max_lines: int,
) -> list[str]:
    normalized = " ".join(str(text).replace("\r", " ").replace("\n", " ").split())
    if not normalized:
        return []

    lines: list[str] = []
    current = ""
    for char in normalized:
        candidate = current + char
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if current and bbox[2] - bbox[0] > max_width:
            lines.append(current)
            current = char
            if len(lines) >= max_lines:
                break
        else:
            current = candidate
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) == max_lines and len("".join(lines)) < len(normalized):
        lines[-1] = lines[-1].rstrip(" .。") + "..."
    return lines


def repair_mojibake_text(value: object) -> str:
    text = str(value)
    if not text:
        return ""
    hint_chars = (
        "\u7487",
        "\u934f",
        "\u9350",
        "\u93b7",
        "\u93c9",
        "\u9424",
        "\u59dd",
        "\u6d93",
        "\ufffd",
    )
    if not any(char in text for char in hint_chars):
        return text
    for encoding in ("gbk", "cp936"):
        try:
            repaired = text.encode(encoding).decode("utf-8")
        except UnicodeError:
            continue
        original_cjk = sum("\u4e00" <= char <= "\u9fff" for char in text)
        repaired_cjk = sum("\u4e00" <= char <= "\u9fff" for char in repaired)
        if repaired_cjk >= max(1, original_cjk // 2):
            return repaired
    return text


class PigPet:
    def __init__(
        self,
        animations: dict[str, Animation],
        report_path: Path,
        app_dir: Path,
        status_path: Path,
    ) -> None:
        self.animations = animations
        self.report_path = report_path
        self.app_dir = app_dir
        self.status_path = status_path
        self.mode = "responsive"
        self.frame_index = 0
        self.transient_key: str | None = None
        self.transient_once = False
        self.success_effect_started: float | None = None
        self.dragging = False
        self.mouse_down = False
        self.drag_start_cursor: tuple[int, int] | None = None
        self.drag_start_window: tuple[int, int] | None = None
        self.drag_previous: tuple[str | None, bool, int, float | None] | None = None
        self.drag_can_play_flat = False
        self.permission_request: dict[str, object] | None = None
        self.permission_request_id = ""
        self.permission_button_down: str | None = None
        self.permission_bubble_down = False
        self.permission_buttons: dict[str, tuple[int, int, int, int]] = {}
        self.permission_bubble_rect: tuple[int, int, int, int] | None = None
        self.permission_dir = permission_dir_for_status(self.status_path)
        self.heartbeat_path = heartbeat_path_for_status(self.status_path)
        self.last_heartbeat = 0.0
        self.hwnd: int | None = None
        self.timer_id = 1
        self.wndproc = WNDPROC(self._wndproc)
        self.render_cache: dict[tuple[str, int], bytes] = {}
        self.effects = self._load_effects()
        initial_status = read_status(self.status_path)
        self.bridge_token = ""
        self.bridge_status = "idle"
        self.last_status_poll = 0.0
        self._apply_bridge_payload(initial_status)

    @property
    def current_key(self) -> str:
        if self.permission_request is not None:
            return "question"
        if self.transient_key is not None:
            return self.transient_key
        if self.mode == "responsive":
            return "carrot" if self.bridge_status == "thinking" else "idle"
        return self.mode

    @property
    def current_animation(self) -> Animation:
        return self.animations[self.current_key]

    def _load_effects(self) -> dict[str, Image.Image]:
        result: dict[str, Image.Image] = {}
        effects_dir = self.app_dir / "assets" / "effects"
        for name in ("sparkle", "firework"):
            path = effects_dir / f"{name}.png"
            if path.is_file():
                result[name] = clear_transparent_rgb(Image.open(path).convert("RGBA"))
        return result

    def run(self) -> None:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass

        instance = kernel32.GetModuleHandleW(None)
        window_class = WNDCLASSW()
        window_class.style = CS_DBLCLKS
        window_class.lpfnWndProc = self.wndproc
        window_class.hInstance = instance
        window_class.hCursor = user32.LoadCursorW(None, ctypes.c_void_p(32512))
        window_class.lpszClassName = CLASS_NAME
        if not user32.RegisterClassW(ctypes.byref(window_class)):
            error = ctypes.get_last_error()
            if error != 1410:
                raise ctypes.WinError(error)

        work_area = RECT()
        user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(work_area), 0)
        x = work_area.right - WINDOW_SIZE - 36
        y = work_area.bottom - WINDOW_SIZE - 36

        self.hwnd = user32.CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW,
            CLASS_NAME,
            APP_NAME,
            WS_POPUP,
            x,
            y,
            WINDOW_SIZE,
            WINDOW_SIZE,
            None,
            None,
            instance,
            None,
        )
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())

        user32.ShowWindow(self.hwnd, SW_SHOW)
        self._write_heartbeat(force=True)
        self._render_current()
        self._schedule_current()

        message = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))

    def _schedule_current(self) -> None:
        if self.hwnd is None:
            return
        user32.KillTimer(self.hwnd, self.timer_id)
        duration = self.current_animation.durations[self.frame_index]
        user32.SetTimer(self.hwnd, self.timer_id, duration, None)

    def _write_heartbeat(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self.last_heartbeat < HEARTBEAT_INTERVAL_SECONDS:
            return
        self.last_heartbeat = now
        payload: dict[str, object] = {
            "app": APP_NAME,
            "pid": os.getpid(),
            "updated_at": utc_timestamp(),
            "status_path": str(self.status_path),
            "current_key": self.current_key,
        }
        if self.hwnd is not None:
            payload["hwnd"] = int(self.hwnd)
            position = RECT()
            if user32.GetWindowRect(self.hwnd, ctypes.byref(position)):
                payload["window_rect"] = [
                    int(position.left),
                    int(position.top),
                    int(position.right),
                    int(position.bottom),
                ]
            payload["window_visible"] = bool(user32.IsWindowVisible(self.hwnd))
        try:
            write_json_atomic(self.heartbeat_path, payload)
        except OSError:
            pass

    def _switch_visual(self, key: str | None, once: bool = False) -> None:
        self.transient_key = key
        self.transient_once = once
        self.frame_index = 0
        self.render_cache.clear()
        self._render_current()
        self._schedule_current()

    def _bridge_status_age_seconds(self) -> float:
        try:
            return max(0.0, time.time() - self.status_path.stat().st_mtime)
        except OSError:
            return float("inf")

    def _is_fresh_thinking_status(self, payload: dict[str, object]) -> bool:
        return (
            payload.get("status") == "thinking"
            and self._bridge_status_age_seconds() <= THINKING_STATUS_STALE_SECONDS
        )

    def _is_fresh_permission_status(self, payload: dict[str, object]) -> bool:
        return (
            payload.get("status") == "permission"
            and self._bridge_status_age_seconds() <= PERMISSION_STATUS_STALE_SECONDS
        )

    def _permission_request_path(self, request_id: str) -> Path:
        return self.permission_dir / f"{request_id}.request.json"

    def _permission_response_path(self, request_id: str) -> Path:
        return self.permission_dir / f"{request_id}.response.json"

    def _permission_request_expired(self, payload: dict[str, object]) -> bool:
        expires_at = str(payload.get("expires_at", ""))
        if not expires_at:
            return False
        try:
            deadline = datetime.fromisoformat(expires_at)
        except ValueError:
            return False
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) >= deadline.astimezone(timezone.utc)

    def _clear_permission_request(self) -> bool:
        previous_key = self.current_key
        self.permission_request = None
        self.permission_request_id = ""
        self.permission_button_down = None
        self.permission_bubble_down = False
        self.permission_buttons = {}
        self.permission_bubble_rect = None
        if previous_key == "question":
            self.frame_index = 0
            self.render_cache.clear()
            self._render_current()
            self._schedule_current()
            return True
        return False

    def _sync_permission_request(self, payload: dict[str, object]) -> bool:
        request_id = str(payload.get("permission_request_id", ""))
        if not request_id:
            return self._clear_permission_request()

        response_path = self._permission_response_path(request_id)
        if response_path.is_file():
            return self._clear_permission_request()

        request = read_json_file(self._permission_request_path(request_id))
        if request is None or self._permission_request_expired(request):
            return self._clear_permission_request()

        previous_key = self.current_key
        self.permission_request = request
        self.permission_request_id = request_id
        self.bridge_status = "idle"
        self.transient_key = None
        self.transient_once = False
        self.success_effect_started = None
        if previous_key != self.current_key or self.frame_index >= len(self.current_animation.frames):
            self.frame_index = 0
            self.render_cache.clear()
            self._render_current()
            self._schedule_current()
            return True
        return False

    def _set_bridge_status(self, status: str) -> bool:
        previous_key = self.current_key
        self.bridge_status = "thinking" if status == "thinking" else "idle"
        if self.bridge_status == "thinking" and self.transient_key == "jump":
            self.transient_key = None
            self.transient_once = False
            self.success_effect_started = None
            self.render_cache.clear()
        if (
            self.mode == "responsive"
            and self.transient_key is None
            and previous_key != self.current_key
        ):
            self._switch_visual(None)
            return True
        return False

    def _start_success_animation(self) -> bool:
        self.bridge_status = "idle"
        self.success_effect_started = time.monotonic()
        self._switch_visual("jump", once=True)
        return True

    def _apply_bridge_payload(self, payload: dict[str, object]) -> bool:
        token = str(payload.get("token", ""))
        status = str(payload.get("status", "idle"))
        if not token:
            self._clear_permission_request()
            return self._set_bridge_status("idle")
        if status == "permission":
            self.bridge_token = token
            if self._is_fresh_permission_status(payload):
                return self._sync_permission_request(payload)
            self._clear_permission_request()
            return self._set_bridge_status("idle")
        if token == self.bridge_token:
            if self.permission_request is not None:
                return self._clear_permission_request()
            if self.bridge_status == "thinking" and status == "thinking":
                if not self._is_fresh_thinking_status(payload):
                    return self._set_bridge_status("idle")
            return False
        self.bridge_token = token
        self._clear_permission_request()
        if status == "success":
            return self._start_success_animation()

        if self._is_fresh_thinking_status(payload):
            return self._set_bridge_status("thinking")

        return self._set_bridge_status("idle")

    def _poll_bridge(self, force: bool = False) -> bool:
        if self.dragging:
            return False
        now = time.monotonic()
        if not force and now - self.last_status_poll < STATUS_POLL_INTERVAL_SECONDS:
            return False
        self.last_status_poll = now
        return self._apply_bridge_payload(read_status(self.status_path))

    def _advance(self) -> None:
        self._write_heartbeat()
        if self._poll_bridge():
            return
        animation = self.current_animation
        self.frame_index += 1
        if self.frame_index >= len(animation.frames):
            self.frame_index = 0
            if self.transient_key is not None and self.transient_once:
                self.transient_key = None
                self.transient_once = False
                self.success_effect_started = None
                self.render_cache.clear()
        self._render_current()
        self._schedule_current()

    def _select_mode(self, mode: str) -> None:
        self.mode = mode
        self.transient_key = None
        self.transient_once = False
        self.success_effect_started = None
        self.frame_index = 0
        self.render_cache.clear()
        self._poll_bridge(force=True)
        self._render_current()
        self._schedule_current()

    def _effect_variant(
        self,
        name: str,
        size: int,
        opacity: float,
    ) -> Image.Image | None:
        source = self.effects.get(name)
        if source is None or size <= 0 or opacity <= 0:
            return None
        ratio = source.height / source.width
        variant = source.resize(
            (size, max(1, round(size * ratio))),
            Image.Resampling.LANCZOS,
        )
        if opacity < 0.999:
            alpha = np.asarray(variant.getchannel("A"), dtype=np.float32)
            alpha = np.uint8(np.clip(alpha * opacity, 0, 255))
            variant.putalpha(Image.fromarray(alpha, "L"))
        return variant

    def _composite_success_effects(self, canvas: Image.Image) -> None:
        if self.success_effect_started is None:
            return
        elapsed = time.monotonic() - self.success_effect_started
        if elapsed < 0 or elapsed > SUCCESS_EFFECT_DURATION_SECONDS:
            return
        progress = elapsed / SUCCESS_EFFECT_DURATION_SECONDS
        fade = min(1.0, progress / 0.18) * min(1.0, (1.0 - progress) / 0.28)
        effect_dx = BODY_ANCHOR_X - 230
        effect_dy = BODY_ANCHOR_BOTTOM - 390
        firework_size = round(34 + 28 * min(1.0, progress / 0.42))
        firework = self._effect_variant("firework", firework_size, fade * 0.82)
        if firework is not None:
            canvas.alpha_composite(
                firework,
                (
                    300 + effect_dx - firework.width // 2,
                    282 + effect_dy - firework.height // 2,
                ),
            )

        sparkles = [
            (154 + effect_dx, 266 + effect_dy, 19, 0.00),
            (279 + effect_dx, 235 + effect_dy, 15, 0.13),
            (184 + effect_dx, 224 + effect_dy, 12, 0.26),
        ]
        for center_x, center_y, base_size, phase in sparkles:
            local = (progress - phase) / max(0.01, 1.0 - phase)
            if local < 0 or local > 1:
                continue
            pulse = math.sin(math.pi * local)
            sparkle = self._effect_variant(
                "sparkle",
                round(base_size * (0.6 + 0.55 * pulse)),
                fade * pulse,
            )
            if sparkle is not None:
                canvas.alpha_composite(
                    sparkle,
                    (
                        center_x - sparkle.width // 2,
                        center_y - sparkle.height // 2,
                    ),
                )

    def _composite_permission_bubble(self, canvas: Image.Image) -> None:
        request = self.permission_request
        if request is None:
            self.permission_buttons = {}
            self.permission_bubble_rect = None
            return

        def draw_centered_text(
            button_rect: tuple[int, int, int, int],
            text: str,
            fill: tuple[int, int, int, int],
            offset: int,
        ) -> None:
            center = (
                (button_rect[0] + button_rect[2]) / 2,
                (button_rect[1] + button_rect[3]) / 2 + offset,
            )
            try:
                draw.text(center, text, fill=fill, font=button_font, anchor="mm")
            except TypeError:
                bbox = draw.textbbox((0, 0), text, font=button_font)
                text_x = center[0] - (bbox[2] - bbox[0]) / 2
                text_y = center[1] - (bbox[3] - bbox[1]) / 2 - bbox[1]
                draw.text((text_x, text_y), text, fill=fill, font=button_font)

        draw = ImageDraw.Draw(canvas, "RGBA")
        title_font = load_ui_font(18, bold=True)
        body_font = load_ui_font(14)
        button_font = load_ui_font(15, bold=True)

        tool_name = str(request.get("tool_name", "Codex"))
        summary = str(request.get("summary", "Codex 正在请求权限"))
        tool_name = repair_mojibake_text(tool_name)
        summary = repair_mojibake_text(summary)
        detail = f"{tool_name}: {summary}" if tool_name else summary
        lines = wrap_text_by_width(draw, detail, body_font, 248, 4)

        left = 262
        top = 160
        right = 558
        line_height = 20
        button_height = 32
        button_bottom_padding = 16
        bubble_height = max(
            138,
            58 + line_height * max(1, len(lines)) + button_height + button_bottom_padding,
        )
        bottom = min(348, top + bubble_height)
        rect = (left, top, right, bottom)
        self.permission_bubble_rect = rect

        shadow = (left + 3, top + 4, right + 3, bottom + 4)
        draw.rounded_rectangle(shadow, radius=18, fill=(0, 0, 0, 82))
        pointer = [(396, bottom - 2), (424, bottom - 2), (410, bottom + 22)]
        pointer_shadow = [(x + 2, y + 3) for x, y in pointer]
        draw.polygon(pointer_shadow, fill=(0, 0, 0, 62))
        draw.rounded_rectangle(
            rect,
            radius=18,
            fill=(255, 250, 244, 242),
            outline=(236, 70, 142, 235),
            width=3,
        )
        draw.polygon(pointer, fill=(255, 250, 244, 242))
        draw.line((398, bottom - 3, 422, bottom - 3), fill=(255, 250, 244, 255), width=4)

        draw.text((left + 14, top + 12), "Codex 请求权限", fill=(48, 40, 42, 255), font=title_font)
        text_y = top + 42
        for line in lines:
            draw.text((left + 18, text_y), line, fill=(76, 67, 70, 255), font=body_font)
            text_y += line_height

        button_top = bottom - button_height - button_bottom_padding
        allow_rect = (left + 38, button_top, left + 130, button_top + button_height)
        deny_rect = (right - 130, button_top, right - 38, button_top + button_height)
        self.permission_buttons = {"allow": allow_rect, "deny": deny_rect}

        pressed = self.permission_button_down
        for action, button_rect, label, fill, outline, text_fill in [
            ("allow", allow_rect, "允许", (94, 199, 123, 255), (69, 174, 99, 255), (255, 255, 255, 255)),
            ("deny", deny_rect, "拒绝", (255, 237, 242, 255), (236, 70, 142, 230), (198, 47, 112, 255)),
        ]:
            offset = 1 if pressed == action else 0
            draw.rounded_rectangle(
                (
                    button_rect[0],
                    button_rect[1] + offset,
                    button_rect[2],
                    button_rect[3] + offset,
                ),
                radius=16,
                fill=fill,
                outline=outline,
                width=3,
            )
            draw_centered_text(button_rect, label, text_fill, offset)

    def _frame_bytes(self, key: str, index: int) -> bytes:
        has_dynamic_effects = (
            key == "jump"
            and self.success_effect_started is not None
        )
        has_permission_ui = self.permission_request is not None
        cache_key = (key, index)
        if not has_dynamic_effects and not has_permission_ui:
            cached = self.render_cache.get(cache_key)
            if cached is not None:
                return cached
        frame = self.animations[key].frames[index]
        canvas = Image.new("RGBA", (WINDOW_SIZE, WINDOW_SIZE), (0, 0, 0, 0))
        x = (WINDOW_SIZE - frame.width) // 2
        y = (WINDOW_SIZE - frame.height) // 2
        canvas.alpha_composite(frame, (x, y))
        if has_dynamic_effects:
            self._composite_success_effects(canvas)
        if has_permission_ui:
            self._composite_permission_bubble(canvas)
        result = premultiplied_bgra(canvas)
        if not has_dynamic_effects and not has_permission_ui:
            self.render_cache[cache_key] = result
        return result

    def _render_current(self) -> None:
        if self.hwnd is None:
            return
        pixels = self._frame_bytes(self.current_key, self.frame_index)
        screen_dc = user32.GetDC(None)
        memory_dc = gdi32.CreateCompatibleDC(screen_dc)

        bitmap_info = BITMAPINFO()
        bitmap_info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bitmap_info.bmiHeader.biWidth = WINDOW_SIZE
        bitmap_info.bmiHeader.biHeight = -WINDOW_SIZE
        bitmap_info.bmiHeader.biPlanes = 1
        bitmap_info.bmiHeader.biBitCount = 32
        bitmap_info.bmiHeader.biCompression = BI_RGB

        bits = ctypes.c_void_p()
        bitmap = gdi32.CreateDIBSection(
            memory_dc,
            ctypes.byref(bitmap_info),
            DIB_RGB_COLORS,
            ctypes.byref(bits),
            None,
            0,
        )
        old_bitmap = gdi32.SelectObject(memory_dc, bitmap)
        ctypes.memmove(bits, pixels, len(pixels))

        position = RECT()
        user32.GetWindowRect(self.hwnd, ctypes.byref(position))
        destination = POINT(position.left, position.top)
        source = POINT(0, 0)
        size = SIZE(WINDOW_SIZE, WINDOW_SIZE)
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)

        user32.UpdateLayeredWindow(
            self.hwnd,
            screen_dc,
            ctypes.byref(destination),
            ctypes.byref(size),
            memory_dc,
            ctypes.byref(source),
            0,
            ctypes.byref(blend),
            ULW_ALPHA,
        )

        gdi32.SelectObject(memory_dc, old_bitmap)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(None, screen_dc)

    def _cursor_window_position(self) -> tuple[int, int] | None:
        if self.hwnd is None:
            return None
        cursor = POINT()
        window = RECT()
        user32.GetCursorPos(ctypes.byref(cursor))
        user32.GetWindowRect(self.hwnd, ctypes.byref(window))
        return (cursor.x - window.left, cursor.y - window.top)

    @staticmethod
    def _point_in_rect(point: tuple[int, int], rect: tuple[int, int, int, int] | None) -> bool:
        if rect is None:
            return False
        x, y = point
        left, top, right, bottom = rect
        return left <= x <= right and top <= y <= bottom

    def _hit_permission_button(self, point: tuple[int, int]) -> str | None:
        for action, rect in self.permission_buttons.items():
            if self._point_in_rect(point, rect):
                return action
        return None

    def _write_permission_decision(self, decision: str) -> None:
        if not self.permission_request_id or decision not in {"allow", "deny"}:
            return
        response_path = self._permission_response_path(self.permission_request_id)
        payload: dict[str, object] = {
            "request_id": self.permission_request_id,
            "decision": decision,
            "updated_at": utc_timestamp(),
            "source": "pig-pet",
        }
        if decision == "deny":
            payload["message"] = "Denied from GooglePiggy Desktop Pet."
        try:
            write_json_atomic(response_path, payload)
        except OSError:
            return
        self._clear_permission_request()

    def _restore_after_drag(
        self,
        previous: tuple[str | None, bool, int, float | None],
    ) -> None:
        (
            self.transient_key,
            self.transient_once,
            self.frame_index,
            self.success_effect_started,
        ) = previous
        self.render_cache.clear()
        self._poll_bridge(force=True)
        self._render_current()
        self._schedule_current()

    def _handle_left_button_down(self) -> None:
        if self.hwnd is None:
            return
        window_point = self._cursor_window_position()
        if self.permission_request is not None and window_point is not None:
            action = self._hit_permission_button(window_point)
            if action is not None:
                self.permission_button_down = action
                self.permission_bubble_down = True
                user32.SetCapture(self.hwnd)
                self._render_current()
                return
            if self._point_in_rect(window_point, self.permission_bubble_rect):
                self.permission_bubble_down = True
                user32.SetCapture(self.hwnd)
                return
        start = POINT()
        window = RECT()
        user32.GetCursorPos(ctypes.byref(start))
        user32.GetWindowRect(self.hwnd, ctypes.byref(window))
        self.mouse_down = True
        self.dragging = False
        self.drag_start_cursor = (start.x, start.y)
        self.drag_start_window = (window.left, window.top)
        self.drag_previous = (
            self.transient_key,
            self.transient_once,
            self.frame_index,
            self.success_effect_started,
        )
        self.drag_can_play_flat = (
            self.mode == "responsive"
            and self.transient_key is None
            and self.bridge_status != "thinking"
        )
        user32.SetCapture(self.hwnd)

    def _handle_mouse_move(self, wparam: int) -> None:
        if self.permission_button_down is not None:
            self._render_current()
            return
        if self.permission_bubble_down:
            return
        if (
            self.hwnd is None
            or not self.mouse_down
            or not (wparam & MK_LBUTTON)
            or self.drag_start_cursor is None
            or self.drag_start_window is None
        ):
            return
        cursor = POINT()
        user32.GetCursorPos(ctypes.byref(cursor))
        start_x, start_y = self.drag_start_cursor
        delta_x = cursor.x - start_x
        delta_y = cursor.y - start_y
        if not self.dragging:
            if (
                abs(delta_x) < DRAG_THRESHOLD_PIXELS
                and abs(delta_y) < DRAG_THRESHOLD_PIXELS
            ):
                return
            self.dragging = True
            self.success_effect_started = None
            self._switch_visual("left")

        window_x, window_y = self.drag_start_window
        user32.SetWindowPos(
            self.hwnd,
            None,
            window_x + delta_x,
            window_y + delta_y,
            0,
            0,
            SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE,
        )

    def _handle_left_button_up(self) -> None:
        if self.permission_button_down is not None or self.permission_bubble_down:
            action = self.permission_button_down
            self.permission_button_down = None
            self.permission_bubble_down = False
            user32.ReleaseCapture()
            point = self._cursor_window_position()
            if action is not None and point is not None and self._hit_permission_button(point) == action:
                self._write_permission_decision(action)
            else:
                self._render_current()
            return
        if not self.mouse_down:
            return
        was_dragging = self.dragging
        previous = self.drag_previous
        can_play_flat = self.drag_can_play_flat
        self.mouse_down = False
        self.dragging = False
        self.drag_start_cursor = None
        self.drag_start_window = None
        self.drag_previous = None
        self.drag_can_play_flat = False
        user32.ReleaseCapture()

        if was_dragging and previous is not None:
            self._restore_after_drag(previous)
        elif can_play_flat:
            self._switch_visual("flat", once=True)

    def _cancel_mouse_drag(self) -> None:
        if not self.mouse_down:
            return
        previous = self.drag_previous
        was_dragging = self.dragging
        self.mouse_down = False
        self.dragging = False
        self.drag_start_cursor = None
        self.drag_start_window = None
        self.drag_previous = None
        self.drag_can_play_flat = False
        self.permission_button_down = None
        self.permission_bubble_down = False
        if was_dragging and previous is not None:
            self._restore_after_drag(previous)

    def _show_menu(self) -> None:
        if self.hwnd is None:
            return
        menu = user32.CreatePopupMenu()
        entries = [
            (100, "状态互动（Codex）", "responsive"),
            (101, "预览：呼吸待机", "idle"),
            (102, "预览：左拱", "left"),
            (103, "预览：猪追胡萝卜", "carrot"),
            (104, "预览：跳跳猪", "jump"),
            (105, "预览：躺平", "flat"),
            (106, "预览：疑问猪", "question"),
        ]
        for command, label, mode in entries:
            flags = MF_STRING | (MF_CHECKED if self.mode == mode else 0)
            user32.AppendMenuW(menu, flags, command, label)
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        autostart_label = "关闭开机自启动" if is_autostart_enabled() else "开启开机自启动"
        user32.AppendMenuW(menu, MF_STRING, 150, autostart_label)
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, 199, "退出猪猪桌宠")

        cursor = POINT()
        user32.GetCursorPos(ctypes.byref(cursor))
        user32.SetForegroundWindow(self.hwnd)
        command = user32.TrackPopupMenu(
            menu,
            TPM_RETURNCMD | TPM_NONOTIFY | TPM_RIGHTBUTTON,
            cursor.x,
            cursor.y,
            0,
            self.hwnd,
            None,
        )
        user32.DestroyMenu(menu)
        if command == 199:
            user32.DestroyWindow(self.hwnd)
        elif command == 150:
            set_autostart(not is_autostart_enabled(), self.app_dir)
        elif 100 <= command <= 106:
            self._select_mode(entries[command - 100][2])

    def _wndproc(self, hwnd: int, message: int, wparam: int, lparam: int) -> int:
        if message == WM_TIMER:
            self._advance()
            return 0
        if message in (WM_LBUTTONDOWN, WM_LBUTTONDBLCLK):
            self._handle_left_button_down()
            return 0
        if message == WM_MOUSEMOVE:
            self._handle_mouse_move(wparam)
            return 0
        if message == WM_LBUTTONUP:
            self._handle_left_button_up()
            return 0
        if message == WM_RBUTTONUP:
            self._show_menu()
            return 0
        if message == WM_DESTROY:
            user32.KillTimer(hwnd, self.timer_id)
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, message, wparam, lparam)


def build_animations(source_dir: Path) -> dict[str, Animation]:
    sources = identify_sources(source_dir)
    left = load_animation("left", "左拱", sources["left"], False)
    flat = load_animation("flat", "躺平", sources["flat"], False)
    return {
        "idle": make_idle_breathing_animation(flat),
        "left": left,
        "carrot": load_animation("carrot", "猪追胡萝卜", sources["carrot"], True),
        "jump": load_animation("jump", "跳跳猪", sources["jump"], False),
        "flat": flat,
        "question": load_animation("question", "疑问猪", sources["question"], False),
    }


def visible_bbox_edge_run(frame: Image.Image, side: str) -> int:
    bbox = frame.getbbox()
    if bbox is None:
        return 0
    alpha = np.array(frame.convert("RGBA"))[:, :, 3]
    x = bbox[0] if side == "left" else bbox[2] - 1
    rows = np.flatnonzero(alpha[:, x] > 16)
    if rows.size == 0:
        return 0
    longest = current = 1
    for previous, row in zip(rows, rows[1:]):
        if int(row) == int(previous) + 1:
            current += 1
            longest = max(longest, current)
        else:
            current = 1
    return longest


def write_qa(animations: dict[str, Animation], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    contact_cell = 230
    label_height = 22
    contact_sheet = Image.new(
        "RGB",
        (8 * contact_cell, len(animations) * (contact_cell + label_height)),
        (245, 245, 245),
    )
    contact_draw = ImageDraw.Draw(contact_sheet)
    report = {
        "ok": True,
        "window_size": [WINDOW_SIZE, WINDOW_SIZE],
        "target_body_width": TARGET_BODY_WIDTH,
        "body_anchor": [BODY_ANCHOR_X, BODY_ANCHOR_BOTTOM],
        "jump_max_horizontal_travel": JUMP_MAX_HORIZONTAL_TRAVEL,
        "left_hump_speed_multiplier": LEFT_HUMP_SPEED_MULTIPLIER,
        "right_hump_repair_padding": RIGHT_HUMP_REPAIR_PADDING,
        "right_hump_max_cap_width": RIGHT_HUMP_MAX_CAP_WIDTH,
        "idle_breath_frames": IDLE_BREATH_FRAMES,
        "idle_breath_duration_ms": IDLE_BREATH_DURATION_MS,
        "idle_breath_max_squash": IDLE_BREATH_MAX_SQUASH,
        "animations": [],
    }
    transition_endpoint_errors: list[float] = []
    for animation in animations.values():
        visible_clearances: list[tuple[int, int, int, int]] = []
        visible_boxes: list[tuple[int, int, int, int]] = []
        rendered_canvases: list[Image.Image] = []
        for frame in animation.frames:
            canvas = Image.new("RGBA", (WINDOW_SIZE, WINDOW_SIZE), (0, 0, 0, 0))
            canvas.alpha_composite(
                frame,
                ((WINDOW_SIZE - frame.width) // 2, (WINDOW_SIZE - frame.height) // 2),
            )
            rendered_canvases.append(canvas)
            bbox = canvas.getbbox()
            if bbox is not None:
                visible_boxes.append(bbox)
                visible_clearances.append(
                    (bbox[0], bbox[1], WINDOW_SIZE - bbox[2], WINDOW_SIZE - bbox[3])
                )
        minimum_visible_clearance = min(
            min(clearance) for clearance in visible_clearances
        )
        body_boxes = [
            pig_body_bbox(
                frame,
                isolate_center_component=(animation.key == "carrot"),
            )
            for frame in rendered_canvases
        ]
        first_body_box = body_boxes[0]
        first_body_center = [
            round((first_body_box[0] + first_body_box[2]) / 2, 1),
            first_body_box[3],
        ]
        last_body_box = body_boxes[-1]
        last_body_center = [
            round((last_body_box[0] + last_body_box[2]) / 2, 1),
            last_body_box[3],
        ]
        for endpoint in (first_body_center, last_body_center):
            transition_endpoint_errors.extend(
                [
                    abs(endpoint[0] - BODY_ANCHOR_X),
                    abs(endpoint[1] - BODY_ANCHOR_BOTTOM),
                ]
            )
        body_centers_x = [(box[0] + box[2]) / 2 for box in body_boxes]
        face_edge = "left" if animation.key == "left" else "right"
        face_edge_runs = [
            visible_bbox_edge_run(frame, face_edge)
            for frame in rendered_canvases
        ]
        report["animations"].append(
            {
                "key": animation.key,
                "label": animation.label,
                "source": str(animation.source),
                "frames": len(animation.frames),
                "durations_ms": animation.durations,
                "total_duration_ms": animation.total_duration,
                "source_indices": animation.source_indices,
                "first_body_bbox": list(first_body_box),
                "first_body_width": first_body_box[2] - first_body_box[0],
                "first_body_anchor": first_body_center,
                "last_body_anchor": last_body_center,
                "transition_endpoint_delta": [
                    round(last_body_center[0] - first_body_center[0], 1),
                    last_body_center[1] - first_body_center[1],
                ],
                "body_center_horizontal_span": round(
                    max(body_centers_x) - min(body_centers_x), 1
                ),
                "face_edge": face_edge,
                "max_visible_bbox_face_edge_run": max(face_edge_runs),
                "max_visible_size": [
                    max(box[2] - box[0] for box in visible_boxes),
                    max(box[3] - box[1] for box in visible_boxes),
                ],
                "minimum_visible_pixel_edge_clearance": minimum_visible_clearance,
                "all_frames_fit": minimum_visible_clearance > 0,
            }
        )
        report["ok"] = report["ok"] and minimum_visible_clearance > 0

        rendered_canvases[0].save(
            output_dir / f"{animation.key}.gif",
            save_all=True,
            append_images=rendered_canvases[1:],
            duration=animation.durations,
            loop=0,
            disposal=2,
            optimize=False,
        )

        sample_indices = sorted(
            set(round(index * (len(rendered_canvases) - 1) / 7) for index in range(8))
        )
        row = list(animations).index(animation.key)
        for column, index in enumerate(sample_indices):
            checker = Image.new("RGB", (contact_cell, contact_cell), (255, 255, 255))
            checker_draw = ImageDraw.Draw(checker)
            square = 14
            for y in range(0, contact_cell, square):
                for x in range(0, contact_cell, square):
                    if (x // square + y // square) % 2:
                        checker_draw.rectangle(
                            (x, y, x + square - 1, y + square - 1),
                            fill=(210, 210, 210),
                        )
            sample = rendered_canvases[index].resize(
                (contact_cell, contact_cell), Image.Resampling.LANCZOS
            )
            checker.paste(sample, (0, 0), sample)
            x = column * contact_cell
            y = row * (contact_cell + label_height)
            contact_sheet.paste(checker, (x, y))
            contact_draw.text(
                (x + 5, y + contact_cell + 4),
                f"{animation.label} frame {index}",
                fill=(0, 0, 0),
            )

    maximum_endpoint_error = max(transition_endpoint_errors, default=0.0)
    report["maximum_transition_endpoint_anchor_error"] = maximum_endpoint_error
    report["all_transition_endpoints_aligned"] = maximum_endpoint_error <= 1.0
    report["ok"] = report["ok"] and report["all_transition_endpoints_aligned"]

    (output_dir / "qa-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    contact_sheet.save(output_dir / "contact-sheet.png")
    print(json.dumps(report, ensure_ascii=False, indent=2))


def log_exception(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(traceback.format_exc(), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--status-file", type=Path)
    parser.add_argument("--qa-only", action="store_true")
    parser.add_argument(
        "--bridge-event",
        choices=["idle", "thinking", "success", "error", "permission"],
    )
    parser.add_argument("--bridge-message", default="")
    parser.add_argument("--permission-request-id", default="")
    parser.add_argument("--enable-autostart", action="store_true")
    parser.add_argument("--disable-autostart", action="store_true")
    args = parser.parse_args()

    app_dir = application_dir()
    qa_dir = app_dir / "qa"
    try:
        status_path = (
            args.status_file.expanduser().resolve()
            if args.status_file
            else default_status_path()
        )
        if args.bridge_event:
            write_status(
                args.bridge_event,
                source="pig-pet-cli",
                event="manual",
                message=args.bridge_message,
                permission_request_id=args.permission_request_id,
                path=status_path,
            )
            return
        if args.enable_autostart or args.disable_autostart:
            set_autostart(args.enable_autostart, app_dir)
            return

        write_json_atomic(
            heartbeat_path_for_status(status_path),
            {
                "app": APP_NAME,
                "pid": os.getpid(),
                "updated_at": utc_timestamp(),
                "status_path": str(status_path),
                "phase": "starting",
            },
        )

        source_dir = (
            args.source_dir.expanduser().resolve()
            if args.source_dir
            else default_source_dir(app_dir).resolve()
        )
        cache_dir = app_dir / "cache"
        if args.qa_only:
            animations = build_animations(source_dir)
            save_animation_cache(animations, cache_dir, source_dir)
            write_qa(animations, qa_dir)
            return
        animations = load_animation_cache(cache_dir, source_dir)
        if animations is None:
            animations = build_animations(source_dir)
            save_animation_cache(animations, cache_dir, source_dir)
        mutex = acquire_single_instance()
        if mutex is None:
            return
        PigPet(
            animations,
            qa_dir / "qa-report.json",
            app_dir,
            status_path,
        ).run()
    except Exception:
        log_exception(app_dir / "pig-pet-error.log")
        if not args.qa_only:
            ctypes.windll.user32.MessageBoxW(
                None,
                f"猪猪桌宠启动失败。请查看：\n{app_dir / 'pig-pet-error.log'}",
                "猪猪桌宠",
                0x10,
            )
        raise


if __name__ == "__main__":
    main()
