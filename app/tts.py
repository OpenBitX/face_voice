"""TTS 客户端。

优先调用 Fish Audio；若 key 无效或出错，自动回落到免费的 Microsoft Edge TTS。
这样 demo 在没有可用 Fish key 时也能立刻跑起来。
"""

from __future__ import annotations

import asyncio
import io
import os
from dataclasses import dataclass
from typing import Iterator

import edge_tts
import requests


FISH_TTS_URL = "https://api.fish.audio/v1/tts"

# Edge TTS 里几个有趣的中文声音 —— 可换其它：
#   zh-CN-YunxiNeural   云希  少年男声，活泼
#   zh-CN-YunyangNeural 云扬  热情男声
#   zh-CN-XiaoyiNeural  晓伊  可爱女声
#   zh-CN-XiaoxiaoNeural 晓晓 情感丰富
DEFAULT_EDGE_VOICE = "zh-CN-YunxiNeural"


@dataclass(slots=True)
class TTSConfig:
    fish_api_key: str = ""
    fish_model: str = "s1"
    fish_reference_id: str | None = None
    fmt: str = "mp3"
    edge_voice: str = DEFAULT_EDGE_VOICE

    @classmethod
    def from_env(cls) -> "TTSConfig":
        return cls(
            fish_api_key=os.getenv("FISH_API_KEY", "").strip(),
            fish_reference_id=(os.getenv("FISH_REFERENCE_ID", "").strip() or None),
            fish_model=os.getenv("FISH_MODEL", "s1").strip() or "s1",
            edge_voice=os.getenv("EDGE_VOICE", DEFAULT_EDGE_VOICE).strip()
                or DEFAULT_EDGE_VOICE,
        )


class TTSError(Exception):
    pass


# ---------------- Fish Audio ----------------

def _fish_synthesize(text: str, cfg: TTSConfig) -> bytes:
    if not cfg.fish_api_key:
        raise TTSError("no fish key")
    headers = {
        "Authorization": f"Bearer {cfg.fish_api_key}",
        "Content-Type": "application/json",
        "model": cfg.fish_model,
    }
    body: dict = {
        "text": text,
        "format": cfg.fmt,
        "mp3_bitrate": 128,
        "normalize": True,
        "latency": "normal",
        "chunk_length": 200,
    }
    if cfg.fish_reference_id:
        body["reference_id"] = cfg.fish_reference_id

    resp = requests.post(FISH_TTS_URL, headers=headers, json=body, timeout=60)
    if resp.status_code != 200:
        raise TTSError(f"fish {resp.status_code}: {resp.text[:200]}")
    ct = resp.headers.get("content-type", "")
    # Fish Audio 出错时会回 JSON；正常是 audio/*
    if "application/json" in ct or resp.content[:1] == b"{":
        raise TTSError(f"fish returned non-audio: {resp.text[:200]}")
    return resp.content


# ---------------- Edge TTS (fallback) ----------------

async def _edge_synthesize_async(text: str, voice: str) -> bytes:
    communicate = edge_tts.Communicate(text, voice)
    buf = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    return buf.getvalue()


def _edge_synthesize(text: str, cfg: TTSConfig) -> bytes:
    return asyncio.run(_edge_synthesize_async(text, cfg.edge_voice))


# ---------------- Public API ----------------

def synthesize(text: str, cfg: TTSConfig) -> tuple[bytes, str]:
    """返回 (mp3_bytes, backend_name)，自动降级。"""
    if cfg.fish_api_key:
        try:
            return _fish_synthesize(text, cfg), "fish"
        except TTSError as e:
            print(f"[tts] fish failed, falling back to edge-tts: {e}")
    return _edge_synthesize(text, cfg), "edge"


def synthesize_stream(text: str, cfg: TTSConfig) -> Iterator[bytes]:
    """流式：对浏览器 <audio> 友好。为了简单，整体合成后一次 yield。

    （Fish Audio 的 REST 其实可以流式拿，但错误处理复杂；demo 里用整段的更稳。）
    """
    audio, _ = synthesize(text, cfg)
    yield audio
