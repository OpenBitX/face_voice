#!/usr/bin/env python3
"""
从面部视频提取 9 个嘴型 PNG（A-H + X），把**外部纯黑背景**转为真正的 alpha 透明。

关键算法：从四个边角做"泛洪填充"(flood fill)，只把外部连通的黑色像素
设为透明，嘴唇缝/牙齿间隙的"内部阴影"即使很暗也不会被误伤。

用法（项目根目录）：
    uv run python scripts/gen_mouths.py
"""

from __future__ import annotations

import subprocess
from collections import deque
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
VIDEO = ROOT / "docs" / "videos" / "制作说话的眼睛嘴巴视频.mp4"
MOUTHS = ROOT / "static" / "mouths"

CROP_VF = "crop=900:450:190:200,scale=500:250"

SHAPES: list[tuple[str, float, str]] = [
    ("A", 2.00, "双唇完全闭合 —— M/B/P / 静默"),
    ("B", 0.25, "上下齿微分开 —— K/S/T/EH"),
    ("C", 2.50, "中等张开带笑意 —— AE 诶"),
    ("D", 1.00, "大椭圆完全张开 —— AA 啊"),
    ("E", 4.00, "收圆中度张开 —— AO 哦"),
    ("F", 5.50, "唇极度收拢小圆口 —— UW 呜"),
    ("G", 5.75, "上齿压下唇内侧 —— F/V 唇齿音"),
    ("H", 0.75, "嘴半张下齿突出 —— L 舌上顶"),
    ("X", 2.00, "休息态（同 A）"),
]

# 判定"这个像素算背景黑"的阈值：max(R,G,B) <= BLACK_THRESHOLD
# 用于泛洪填充，不是最终 alpha 判定
BLACK_THRESHOLD = 30


def resolve_video() -> Path:
    """
    兼容 Windows 下的中文文件名乱码问题：
    - 优先使用仓库约定的 VIDEO 路径
    - 否则回退到 docs/videos 下“最大”的 mp4（通常就是源素材）
    """
    if VIDEO.exists():
        return VIDEO
    videos_dir = ROOT / "docs" / "videos"
    mp4s = sorted(videos_dir.glob("*.mp4"), key=lambda p: p.stat().st_size, reverse=True)
    if not mp4s:
        raise FileNotFoundError(f"未找到视频文件: {videos_dir}/*.mp4")
    return mp4s[0]


def probe_duration(video: Path) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout)[-1500:])
    try:
        return float(r.stdout.strip())
    except ValueError as e:
        raise RuntimeError(f"无法解析视频时长: {r.stdout!r}") from e


def extract_frame(ts: float, out: Path) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(ts),
        "-i", str(resolve_video()),
        "-vframes", "1",
        "-vf", CROP_VF,
        str(out),
    ]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode(errors="replace")[-1500:])


def remove_outer_black(path: Path) -> None:
    """两步抠图：
      1) BFS 从顶边 + 左右列播种（跳过底边）：外部连通黑 → 透明。
         跳过底边的原因：底边靠近下巴皮肤的过渡区，若从底边播种会把下巴误判为
         背景侵蚀掉；底部背景黑会经由左/右侧路径自然被填充，不影响整体效果。
      2) 丢弃像素数 < 图像总像素 3% 的小碎片（孤立噪点/伪影）。
         不再只保留"最大块"，以防止下巴在某些帧被切成次大块后被误删。
    """
    img = Image.open(path).convert("RGB")
    W, H = img.size
    px = img.load()
    N = W * H

    is_bg = bytearray(N)  # 1 = 外部透明背景

    def idx(x: int, y: int) -> int:
        return y * W + x

    def is_black(x: int, y: int) -> bool:
        r, g, b = px[x, y]
        return max(r, g, b) <= BLACK_THRESHOLD

    # ── step 1: BFS，仅从顶边 + 左右列播种，不播种底边 ──
    # 原因：底边靠近下巴皮肤过渡区，从底边播种会把下巴区域误判为背景侵蚀掉。
    # 底部黑色背景可通过左/右侧黑色区域与顶部连通后自然被填充。
    q: deque[tuple[int, int]] = deque()
    for x in range(W):
        # 只播种顶边（y=0），不播种底边（y=H-1）
        if is_black(x, 0) and not is_bg[idx(x, 0)]:
            is_bg[idx(x, 0)] = 1
            q.append((x, 0))
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

    # ── step 2: 保留所有"足够大"的连通块，只丢掉小碎片 ──
    # 原本只保留最大块会把下巴（若被底边 BFS 切断后变成次大块）一并丢弃。
    # 改为：保留像素数 >= 图像总像素 3% 的连通块。
    MIN_KEEP = max(200, int(N * 0.03))
    component = bytearray(N)  # 0=未访问, 1=保留, 2=小碎块
    for y in range(H):
        for x in range(W):
            i = idx(x, y)
            if is_bg[i] or component[i]:
                continue
            cells = [i]
            component[i] = 2
            stack = [(x, y)]
            while stack:
                cx, cy = stack.pop()
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < W and 0 <= ny < H:
                        ni = idx(nx, ny)
                        if not is_bg[ni] and not component[ni]:
                            component[ni] = 2
                            cells.append(ni)
                            stack.append((nx, ny))
            if len(cells) >= MIN_KEEP:
                for c in cells:
                    component[c] = 1  # 足够大 → 保留

    # ── 构建 alpha：保留块 = 不透明 ──
    alpha_bytes = bytes(255 if component[i] == 1 else 0 for i in range(N))
    alpha = Image.frombytes("L", (W, H), alpha_bytes)
    alpha = alpha.filter(ImageFilter.GaussianBlur(radius=0.8))

    r, g, b = img.split()
    out = Image.merge("RGBA", (r, g, b, alpha))
    out.save(path)


def _frame_features(rgb: Image.Image) -> dict[str, float]:
    """
    在裁剪后 500x250 的嘴部图上提取简单特征，用于“自动选帧”。
    只需要相对排序稳定即可，不追求严格口腔语义识别。
    """
    im = rgb.convert("RGB")
    W, H = im.size
    # 取嘴部中心区域，减少皮肤/阴影的干扰
    x0, x1 = int(W * 0.18), int(W * 0.82)
    y0, y1 = int(H * 0.28), int(H * 0.90)
    crop = im.crop((x0, y0, x1, y1))
    # 口腔洞检测再收紧到中心 ROI，避免嘴角/唇线暗部把 bbox 撑满
    cw, ch = crop.size
    ix0, ix1 = int(cw * 0.25), int(cw * 0.75)
    iy0, iy1 = int(ch * 0.35), int(ch * 0.92)
    inner = crop.crop((ix0, iy0, ix1, iy1))

    g = inner.convert("L")
    px = inner.load()
    gx = g.load()
    w, h = inner.size
    n = w * h

    # 背景（纯黑）掩码
    bg = 0
    # “口腔洞”= 非背景、非常暗且 RGB 都低（排除嘴唇红色/皮肤阴影）
    hole = 0
    teeth = 0
    teeth_upper = 0
    teeth_lower = 0
    hx0, hy0 = w, h
    hx1, hy1 = -1, -1
    for y in range(h):
        for x in range(w):
            r, gg, b = px[x, y]
            if max(r, gg, b) <= BLACK_THRESHOLD:
                bg += 1
                continue
            val = gx[x, y]
            # 口腔洞（非常暗且 RGB 都低）
            if val <= 55 and r <= 80 and gg <= 80 and b <= 80:
                hole += 1
                if x < hx0:
                    hx0 = x
                if x > hx1:
                    hx1 = x
                if y < hy0:
                    hy0 = y
                if y > hy1:
                    hy1 = y

    fg = max(1, n - bg)
    hole_ratio = hole / fg

    if hx1 >= hx0 and hy1 >= hy0:
        hole_w = (hx1 - hx0 + 1) / w
        hole_h = (hy1 - hy0 + 1) / h
        roundness = (hole_h / max(1e-6, hole_w))
        # 牙齿只在口腔洞附近统计（扩一圈），避免把皮肤高光算成牙齿
        pad = 14
        rx0 = max(0, hx0 - pad)
        rx1 = min(w - 1, hx1 + pad)
        ry0 = max(0, hy0 - pad)
        ry1 = min(h - 1, hy1 + pad)
        midy = (ry0 + ry1) // 2
        for y in range(ry0, ry1 + 1):
            for x in range(rx0, rx1 + 1):
                r, gg, b = px[x, y]
                if max(r, gg, b) <= BLACK_THRESHOLD:
                    continue
                val = gx[x, y]
                if val >= 170 and abs(r - gg) <= 30 and abs(gg - b) <= 30:
                    teeth += 1
                    if y <= midy:
                        teeth_upper += 1
                    else:
                        teeth_lower += 1
    else:
        hole_w = 0.0
        hole_h = 0.0
        roundness = 0.0
        teeth = teeth_upper = teeth_lower = 0

    teeth_ratio = teeth / fg
    teeth_upper_ratio = teeth_upper / max(1, teeth)
    teeth_lower_ratio = teeth_lower / max(1, teeth)
    return {
        "hole_ratio": hole_ratio,
        "teeth_ratio": teeth_ratio,
        "hole_w": hole_w,
        "hole_h": hole_h,
        "roundness": roundness,
        "teeth_upper_ratio": teeth_upper_ratio,
        "teeth_lower_ratio": teeth_lower_ratio,
    }


def _score(shape: str, f: dict[str, float]) -> float:
    """
    为每类嘴型打分：分数越高越符合。
    这是启发式规则，目标是选出“相对更像”的帧。
    """
    hole = f["hole_ratio"]
    teeth = f["teeth_ratio"]
    hw = f["hole_w"]
    hh = f["hole_h"]
    rnd = f["roundness"]
    t_up = f["teeth_upper_ratio"]
    t_low = f["teeth_lower_ratio"]

    if shape in ("A", "X"):
        # 闭嘴：开口暗区最小，牙齿几乎不可见
        return -(hole * 12.0 + teeth * 6.0)

    if shape == "D":
        # 最大张口：暗区高度/面积最大（黑洞明显）
        return hole * 10.0 + hh * 4.0 - teeth * 0.2

    if shape == "C":
        # 中等张开 + 露齿：dark 中等偏上，teeth 也明显
        return teeth * 7.0 + hole * 3.0 - abs(hole - 0.10) * 10.0

    if shape == "B":
        # 微张带缝 + 露齿：teeth 明显，但 dark 不宜太大
        return teeth * 8.0 - abs(hole - 0.04) * 14.0

    if shape == "F":
        # 极度收圆小圆口：开口存在但宽度小，roundness 高
        return rnd * 4.5 - hw * 9.0 - abs(hole - 0.05) * 14.0 - teeth * 6.0

    if shape == "E":
        # 收圆中度张开：roundness 中高，dark 中等
        return rnd * 3.2 - hw * 6.5 - abs(hole - 0.08) * 12.0 - teeth * 5.0

    if shape == "G":
        # F/V：露齿但开口不大（更像“牙压唇”的亮带）
        must_teeth_penalty = 0.0 if teeth >= 0.01 else 50.0
        return (
            teeth * 10.0
            + t_up * 2.5
            - t_low * 2.0
            - abs(hole - 0.01) * 22.0
            - must_teeth_penalty
        )

    if shape == "H":
        # L：通常开口不算最大，但下齿/口腔可见（用“有一定 dark 且 teeth 适中”近似）
        return hole * 6.0 + teeth * 3.0 + t_low * 1.5 - abs(hole - 0.07) * 10.0

    return 0.0


def auto_pick_timestamps(video: Path) -> dict[str, float]:
    """
    采样视频全程，自动为 A-H/X 挑选最像的时间戳。
    结果是确定性的（同一视频、同一参数下）。
    """
    duration = probe_duration(video)
    # 采样步长：视频短（~8s），用较密采样提高命中率
    step = 0.05
    # 避免首尾转场
    t0, t1 = max(0.0, 0.1), max(0.0, duration - 0.1)

    shapes = ["A", "B", "C", "D", "E", "F", "G", "H"]
    candidates: list[tuple[float, dict[str, float]]] = []

    with TemporaryDirectory() as td:
        tmp = Path(td)
        # 遍历候选时间
        i = 0
        t = t0
        while t <= t1 + 1e-6:
            out = tmp / f"cand_{i:04d}.png"
            extract_frame(t, out)
            rgb = Image.open(out).convert("RGB")
            f = _frame_features(rgb)
            candidates.append((t, f))
            i += 1
            t += step

    # 为每个形状预计算 top 候选（越多越稳，但也更慢；这里候选池本身很小）
    ranked: dict[str, list[tuple[float, float]]] = {}
    for s in shapes:
        lst = []
        for ts, f in candidates:
            lst.append((_score(s, f), ts))
        lst.sort(reverse=True, key=lambda x: x[0])
        ranked[s] = lst[:80]

    # 带约束的贪心分配：优先挑“最难挑”的形状，避免全挤到同一帧
    order = ["D", "F", "E", "A", "B", "C", "G", "H"]
    min_sep = 0.15
    picked_ts: dict[str, float] = {}
    used: list[float] = []
    for s in order:
        chosen = None
        for _sc, ts in ranked[s]:
            if all(abs(ts - u) >= min_sep for u in used):
                chosen = ts
                break
        if chosen is None:
            # 退化：实在找不到满足间隔的，就选最高分（允许冲突）
            chosen = ranked[s][0][1]
        picked_ts[s] = chosen
        used.append(chosen)

    # X 复用 A（按 README 规范）
    picked_ts["X"] = picked_ts["A"]
    return picked_ts


def main() -> None:
    video = resolve_video()

    MOUTHS.mkdir(parents=True, exist_ok=True)
    for old in MOUTHS.glob("shape-*.png"):
        old.unlink()

    # 优先自动选帧；如果你想手工固定某些时间戳，可以直接改 SHAPES
    picked = auto_pick_timestamps(video)
    for letter, _ts, desc in SHAPES:
        ts = float(picked.get(letter, _ts))
        png = MOUTHS / f"shape-{letter}.png"
        print(f"  [抽帧] shape-{letter}.png  t={ts}s  {desc}")
        extract_frame(ts, png)
        remove_outer_black(png)

    print(f"\nDone! {len(SHAPES)} transparent PNGs -> {MOUTHS}/")


if __name__ == "__main__":
    main()
