"""Minimal pure-stdlib PNG rasterizer for canvas pages.

Renders stroke point lists onto a white RGB canvas and encodes a valid
PNG (no external dependencies). This is a simplified renderer (decision
C-005): it exists so finalized canvas pages can enter the shared
ingestion layer as real images (§6, §67). NoteSpace's layout-aware PDF
renderer (Phase 4) is a separate, faithful-rendering component.
"""
import struct
import zlib

CANVAS_W = 900
CANVAS_H = 620


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def _plot(buf: bytearray, w: int, h: int, x: int, y: int) -> None:
    if 0 <= x < w and 0 <= y < h:
        idx = (y * w + x) * 3
        buf[idx] = buf[idx + 1] = buf[idx + 2] = 17  # #111827-ish ink


def _draw_line(buf: bytearray, w: int, h: int, x0: float, y0: float, x1: float, y1: float) -> None:
    steps = max(1, int(max(abs(x1 - x0), abs(y1 - y0))))
    for i in range(steps + 1):
        t = i / steps
        x, y = int(x0 + (x1 - x0) * t), int(y0 + (y1 - y0) * t)
        for dx, dy in ((0, 0), (1, 0), (0, 1)):  # ~2px thickness
            _plot(buf, w, h, x + dx, y + dy)


def render_strokes_png(strokes_points: list[list[float]], width: int = CANVAS_W, height: int = CANVAS_H) -> bytes:
    """strokes_points: list of flat [x0,y0,x1,y1,…] arrays in canvas coordinates."""
    buf = bytearray(b"\xff" * (width * height * 3))
    for points in strokes_points:
        for i in range(0, len(points) - 3, 2):
            _draw_line(buf, width, height, points[i], points[i + 1], points[i + 2], points[i + 3])

    raw = b"".join(b"\x00" + bytes(buf[y * width * 3 : (y + 1) * width * 3]) for y in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit RGB
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(raw, 6))
        + _png_chunk(b"IEND", b"")
    )
