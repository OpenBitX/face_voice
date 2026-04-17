#!/usr/bin/env python3
"""
从原视频裁出眼睛区域，**逐帧泛洪填充**去掉外部黑背景，
输出带 alpha 通道的 VP9 WebM（Chrome/Edge/Firefox 原生支持）。

与 colorkey/chromakey 滤镜相比：
  - 只去掉"从边角连通的黑"，眼球里的深色睫毛/瞳孔边缘阴影都不会被误伤
  - 不会产生 VP9+colorkey 常见的边缘锯齿/色散 artifact

用法（项目根目录）：
    uv run python scripts/gen_eyes.py
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections import deque
from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "videos" / "制作说话的眼睛嘴巴视频.mp4"
OUT_WEBM = ROOT / "docs" / "videos" / "eyes.webm"
OUT_MP4 = ROOT / "docs" / "videos" / "eyes.mp4"

# 眼睛区域 y≈15~230，宽 1280
CROP = "crop=1280:220:0:15"
BLACK_THRESHOLD = 30  # max(R,G,B) <= 此值算"黑"
FPS = 24


def run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode(errors="replace")[-2000:])


def flood_fill_alpha(img: Image.Image) -> Image.Image:
    """对单张 RGB 图：边角泛洪黑→透明；眼睛是两个大连通分量，都保留。

    区别于嘴巴 PNG 只保留最大连通分量：眼睛有左右两只，两者都要。
    做法：保留所有面积 >= MIN_KEEP 的连通分量。
    """
    MIN_KEEP = 2000  # 小于此像素数的孤岛 → 视作噪声丢弃

    img = img.convert("RGB")
    W, H = img.size
    px = img.load()
    N = W * H

    is_bg = bytearray(N)

    def idx(x: int, y: int) -> int:
        return y * W + x

    def is_black(x: int, y: int) -> bool:
        r, g, b = px[x, y]
        return max(r, g, b) <= BLACK_THRESHOLD

    # 边角 BFS
    q: deque[tuple[int, int]] = deque()
    for x in range(W):
        for y0 in (0, H - 1):
            if is_black(x, y0) and not is_bg[idx(x, y0)]:
                is_bg[idx(x, y0)] = 1
                q.append((x, y0))
    for y in range(H):
        for x0 in (0, W - 1):
            if is_black(x0, y) and not is_bg[idx(x0, y)]:
                is_bg[idx(x0, y)] = 1
                q.append((x0, y))
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < W and 0 <= ny < H:
                i = idx(nx, ny)
                if not is_bg[i] and is_black(nx, ny):
                    is_bg[i] = 1
                    q.append((nx, ny))

    # 找所有 non-bg 连通分量，保留大的
    keep = bytearray(N)
    visited = bytearray(N)
    for y in range(H):
        for x in range(W):
            i = idx(x, y)
            if is_bg[i] or visited[i]:
                continue
            cells = [i]
            visited[i] = 1
            stack = [(x, y)]
            while stack:
                cx, cy = stack.pop()
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < W and 0 <= ny < H:
                        ni = idx(nx, ny)
                        if not is_bg[ni] and not visited[ni]:
                            visited[ni] = 1
                            cells.append(ni)
                            stack.append((nx, ny))
            if len(cells) >= MIN_KEEP:
                for c in cells:
                    keep[c] = 1

    alpha_bytes = bytes(255 if keep[i] else 0 for i in range(N))
    alpha = Image.frombytes("L", (W, H), alpha_bytes)
    alpha = alpha.filter(ImageFilter.GaussianBlur(radius=0.7))

    r, g, b = img.split()
    return Image.merge("RGBA", (r, g, b, alpha))


def main() -> None:
    if not SRC.exists():
        raise FileNotFoundError(SRC)

    with tempfile.TemporaryDirectory(prefix="eyes_") as tmp:
        tmp_dir = Path(tmp)
        frames_dir = tmp_dir / "frames"
        frames_dir.mkdir()

        print(f"[1/3] 裁剪并抽帧 ({FPS} fps) 到临时目录…")
        run([
            "ffmpeg", "-y", "-i", str(SRC),
            "-vf", CROP,
            "-r", str(FPS),
            str(frames_dir / "f_%04d.png"),
        ])

        pngs = sorted(frames_dir.glob("f_*.png"))
        print(f"[2/3] 逐帧泛洪填充（共 {len(pngs)} 帧）…")
        for i, p in enumerate(pngs, 1):
            rgba = flood_fill_alpha(Image.open(p))
            rgba.save(p)
            if i % 24 == 0 or i == len(pngs):
                print(f"    {i}/{len(pngs)}")

        print("[3/3] 编码 VP9+alpha WebM + 兜底 mp4…")
        run([
            "ffmpeg", "-y", "-framerate", str(FPS),
            "-i", str(frames_dir / "f_%04d.png"),
            "-c:v", "libvpx-vp9",
            "-pix_fmt", "yuva420p",
            "-b:v", "1500k",
            "-crf", "18",
            "-deadline", "good",
            "-cpu-used", "2",
            "-auto-alt-ref", "0",
            "-an",
            str(OUT_WEBM),
        ])
        run([
            "ffmpeg", "-y", "-i", str(SRC),
            "-vf", CROP,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an",
            str(OUT_MP4),
        ])

    print(f"\nDone -> {OUT_WEBM.name} (alpha), {OUT_MP4.name} (fallback)")


if __name__ == "__main__":
    main()
