"""Small generated flag PNG assets for translation overlays."""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

FLAG_FILES = {
    "zh": "cn.png",
    "ja": "jp.png",
    "vi": "vn.png",
    "ko": "kr.png",
    "es": "es.png",
    "hi": "in.png",
}
FLAG_WIDTH = 144
FLAG_HEIGHT = 96
RGBA = tuple[int, int, int, int]


class Canvas:
    """Tiny RGBA drawing helper used to generate flag icons without dependencies."""

    def __init__(self, width: int = FLAG_WIDTH, height: int = FLAG_HEIGHT) -> None:
        self.width = width
        self.height = height
        self.pixels = bytearray(width * height * 4)

    def set_pixel(self, x: int, y: int, color: RGBA) -> None:
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            return
        offset = (y * self.width + x) * 4
        self.pixels[offset : offset + 4] = bytes(color)

    def fill(self, color: RGBA) -> None:
        row = bytes(color) * self.width
        for y in range(self.height):
            start = y * self.width * 4
            self.pixels[start : start + len(row)] = row

    def rect(self, x0: float, y0: float, x1: float, y1: float, color: RGBA) -> None:
        for y in range(max(0, round(y0)), min(self.height, round(y1))):
            for x in range(max(0, round(x0)), min(self.width, round(x1))):
                self.set_pixel(x, y, color)

    def circle(self, cx: float, cy: float, radius: float, color: RGBA) -> None:
        radius_squared = radius * radius
        for y in range(math.floor(cy - radius), math.ceil(cy + radius) + 1):
            for x in range(math.floor(cx - radius), math.ceil(cx + radius) + 1):
                if (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 <= radius_squared:
                    self.set_pixel(x, y, color)

    def circle_outline(self, cx: float, cy: float, radius: float, thickness: float, color: RGBA) -> None:
        outer = radius + thickness / 2
        inner = radius - thickness / 2
        for y in range(math.floor(cy - outer), math.ceil(cy + outer) + 1):
            for x in range(math.floor(cx - outer), math.ceil(cx + outer) + 1):
                distance = math.hypot(x + 0.5 - cx, y + 0.5 - cy)
                if inner <= distance <= outer:
                    self.set_pixel(x, y, color)

    def polygon(self, points: list[tuple[float, float]], color: RGBA) -> None:
        min_x = max(0, math.floor(min(point[0] for point in points)))
        max_x = min(self.width - 1, math.ceil(max(point[0] for point in points)))
        min_y = max(0, math.floor(min(point[1] for point in points)))
        max_y = min(self.height - 1, math.ceil(max(point[1] for point in points)))
        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                if point_in_polygon(x + 0.5, y + 0.5, points):
                    self.set_pixel(x, y, color)

    def rotated_rect(
        self,
        cx: float,
        cy: float,
        width: float,
        height: float,
        angle_degrees: float,
        color: RGBA,
    ) -> None:
        angle = math.radians(angle_degrees)
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        radius = math.hypot(width, height) / 2
        for y in range(math.floor(cy - radius), math.ceil(cy + radius) + 1):
            for x in range(math.floor(cx - radius), math.ceil(cx + radius) + 1):
                dx = x + 0.5 - cx
                dy = y + 0.5 - cy
                local_x = dx * cos_a + dy * sin_a
                local_y = -dx * sin_a + dy * cos_a
                if abs(local_x) <= width / 2 and abs(local_y) <= height / 2:
                    self.set_pixel(x, y, color)

    def line(self, x0: float, y0: float, x1: float, y1: float, thickness: float, color: RGBA) -> None:
        length = math.hypot(x1 - x0, y1 - y0)
        if length <= 0:
            return
        angle = math.degrees(math.atan2(y1 - y0, x1 - x0))
        self.rotated_rect((x0 + x1) / 2, (y0 + y1) / 2, length, thickness, angle, color)


def ensure_flag_assets(assets_folder: Path, *, force: bool = False) -> Path:
    """Create bundled PNG flag icons and return their directory."""

    flag_dir = assets_folder / "flags"
    flag_dir.mkdir(parents=True, exist_ok=True)
    makers = {
        "zh": draw_china,
        "ja": draw_japan,
        "vi": draw_vietnam,
        "ko": draw_south_korea,
        "es": draw_spain,
        "hi": draw_india,
    }
    for key, maker in makers.items():
        path = flag_asset_path(flag_dir, key)
        if force or not path.is_file() or path.stat().st_size == 0:
            write_png(path, maker())
    return flag_dir


def flag_asset_path(flag_dir: Path, language_key: str) -> Path:
    """Return the expected flag asset path for a translation language key."""

    return flag_dir / FLAG_FILES.get(language_key, f"{language_key}.png")


def write_png(path: Path, canvas: Canvas) -> None:
    """Write a Canvas as an RGBA PNG file."""

    raw = bytearray()
    row_width = canvas.width * 4
    for y in range(canvas.height):
        raw.append(0)
        start = y * row_width
        raw.extend(canvas.pixels[start : start + row_width])

    def chunk(kind: bytes, payload: bytes) -> bytes:
        checksum = zlib.crc32(kind + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)

    png = b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            chunk(b"IHDR", struct.pack(">IIBBBBB", canvas.width, canvas.height, 8, 6, 0, 0, 0)),
            chunk(b"IDAT", zlib.compress(bytes(raw), level=9)),
            chunk(b"IEND", b""),
        ]
    )
    path.write_bytes(png)


def point_in_polygon(x: float, y: float, points: list[tuple[float, float]]) -> bool:
    """Return True when a point is inside a polygon."""

    inside = False
    previous_x, previous_y = points[-1]
    for current_x, current_y in points:
        intersects = (current_y > y) != (previous_y > y)
        if intersects:
            slope_x = (previous_x - current_x) * (y - current_y) / (previous_y - current_y) + current_x
            if x < slope_x:
                inside = not inside
        previous_x, previous_y = current_x, current_y
    return inside


def star_points(
    cx: float,
    cy: float,
    outer_radius: float,
    inner_radius: float,
    *,
    rotation_degrees: float = -90,
) -> list[tuple[float, float]]:
    """Return points for a five-point star."""

    points: list[tuple[float, float]] = []
    for index in range(10):
        radius = outer_radius if index % 2 == 0 else inner_radius
        angle = math.radians(rotation_degrees + index * 36)
        points.append((cx + math.cos(angle) * radius, cy + math.sin(angle) * radius))
    return points


def draw_china() -> Canvas:
    canvas = Canvas()
    red = (222, 41, 16, 255)
    yellow = (255, 222, 0, 255)
    canvas.fill(red)
    canvas.polygon(star_points(24, 24, 14, 5.5), yellow)
    small_centers = [(48, 12, -125), (60, 24, -100), (60, 40, -75), (48, 52, -50)]
    for cx, cy, rotation in small_centers:
        canvas.polygon(star_points(cx, cy, 5.5, 2.3, rotation_degrees=rotation), yellow)
    return canvas


def draw_japan() -> Canvas:
    canvas = Canvas()
    canvas.fill((255, 255, 255, 255))
    canvas.circle(72, 48, 27, (188, 0, 45, 255))
    return canvas


def draw_vietnam() -> Canvas:
    canvas = Canvas()
    canvas.fill((218, 37, 29, 255))
    canvas.polygon(star_points(72, 48, 29, 11.5), (255, 255, 0, 255))
    return canvas


def draw_south_korea() -> Canvas:
    canvas = Canvas()
    canvas.fill((255, 255, 255, 255))
    black = (0, 0, 0, 255)
    red = (205, 46, 58, 255)
    blue = (0, 71, 160, 255)
    radius = 22
    for y in range(FLAG_HEIGHT):
        for x in range(FLAG_WIDTH):
            dx = x + 0.5 - 72
            dy = y + 0.5 - 48
            if dx * dx + dy * dy <= radius * radius:
                canvas.set_pixel(x, y, red if dy < 0 else blue)
    canvas.circle(72, 37, radius / 2, red)
    canvas.circle(72, 59, radius / 2, blue)
    draw_trigram(canvas, 39, 24, -34, [True, True, True])
    draw_trigram(canvas, 105, 24, 34, [False, True, False])
    draw_trigram(canvas, 39, 72, 34, [True, False, True])
    draw_trigram(canvas, 105, 72, -34, [False, False, False])
    canvas.circle_outline(72, 48, radius, 1.0, (245, 245, 245, 255))
    return canvas


def draw_trigram(canvas: Canvas, cx: float, cy: float, angle: float, pattern: list[bool]) -> None:
    """Draw one Korean taegeukgi trigram."""

    bar_length = 27
    bar_height = 4.8
    gap = 8.2
    for index, full_bar in enumerate(pattern):
        local_y = (index - 1) * gap
        if full_bar:
            draw_rotated_local_bar(canvas, cx, cy, 0, local_y, bar_length, bar_height, angle)
        else:
            segment = bar_length * 0.42
            draw_rotated_local_bar(canvas, cx, cy, -bar_length * 0.29, local_y, segment, bar_height, angle)
            draw_rotated_local_bar(canvas, cx, cy, bar_length * 0.29, local_y, segment, bar_height, angle)


def draw_rotated_local_bar(
    canvas: Canvas,
    group_cx: float,
    group_cy: float,
    local_x: float,
    local_y: float,
    width: float,
    height: float,
    angle: float,
) -> None:
    angle_rad = math.radians(angle)
    cx = group_cx + local_x * math.cos(angle_rad) - local_y * math.sin(angle_rad)
    cy = group_cy + local_x * math.sin(angle_rad) + local_y * math.cos(angle_rad)
    canvas.rotated_rect(cx, cy, width, height, angle, (0, 0, 0, 255))


def draw_spain() -> Canvas:
    canvas = Canvas()
    red = (198, 11, 30, 255)
    yellow = (255, 196, 0, 255)
    dark_red = (170, 21, 27, 255)
    gold = (255, 215, 0, 255)
    blue = (0, 61, 165, 255)
    white = (245, 245, 245, 255)
    purple = (100, 48, 140, 255)
    canvas.fill(yellow)
    canvas.rect(0, 0, FLAG_WIDTH, FLAG_HEIGHT * 0.25, red)
    canvas.rect(0, FLAG_HEIGHT * 0.75, FLAG_WIDTH, FLAG_HEIGHT, red)

    # A compact, recognizable coat of arms placed toward the hoist side.
    canvas.polygon([(45, 22), (57, 22), (61, 29), (41, 29)], dark_red)
    canvas.rect(40, 29, 62, 33, gold)
    for x in (43, 51, 59):
        canvas.circle(x, 27, 2.2, gold)

    canvas.polygon([(38, 33), (64, 33), (64, 58), (51, 70), (38, 58)], dark_red)
    canvas.polygon([(41, 36), (61, 36), (61, 56), (51, 65), (41, 56)], gold)
    canvas.rect(43, 38, 51, 47, dark_red)
    canvas.rect(51, 38, 59, 47, white)
    canvas.rect(43, 47, 51, 57, gold)
    canvas.rect(51, 47, 59, 57, dark_red)

    canvas.rect(45, 41, 49, 45, gold)
    canvas.rect(44, 39, 50, 41, gold)
    canvas.circle(55, 43, 2.3, purple)
    for x in (44, 47, 50):
        canvas.rect(x, 47, x + 1.4, 57, dark_red)
    canvas.line(53, 52, 57, 48, 1.2, gold)
    canvas.line(53, 48, 57, 52, 1.2, gold)
    canvas.circle(51, 59, 4.4, blue)

    canvas.rect(31, 38, 35, 65, dark_red)
    canvas.rect(30, 36, 36, 39, gold)
    canvas.rect(30, 64, 36, 67, gold)
    canvas.rect(67, 38, 71, 65, dark_red)
    canvas.rect(66, 36, 72, 39, gold)
    canvas.rect(66, 64, 72, 67, gold)
    return canvas


def draw_india() -> Canvas:
    canvas = Canvas()
    canvas.fill((255, 255, 255, 255))
    canvas.rect(0, 0, FLAG_WIDTH, FLAG_HEIGHT / 3, (255, 153, 51, 255))
    canvas.rect(0, FLAG_HEIGHT * 2 / 3, FLAG_WIDTH, FLAG_HEIGHT, (19, 136, 8, 255))
    navy = (0, 0, 128, 255)
    canvas.circle_outline(72, 48, 13, 1.7, navy)
    canvas.circle(72, 48, 2.2, navy)
    for index in range(24):
        angle = 2 * math.pi * index / 24
        canvas.line(72, 48, 72 + math.cos(angle) * 12, 48 + math.sin(angle) * 12, 1.0, navy)
    return canvas
