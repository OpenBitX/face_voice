"""Cartesia TTS 客户端（HTTP `/tts/bytes` 端点）。

官方文档：https://docs.cartesia.ai/api-reference/tts/tts-bytes
实时 WebSocket 版见：https://docs.cartesia.ai/get-started/quickstart

对于本 demo，server 端是"整段合成后一次性发给浏览器 <audio>"的模式，
所以用 HTTP `bytes` 端点最直接——一次请求返回整个 mp3 文件流，
Content-Type 天然是 audio/mpeg，浏览器 <audio> 直接可播放。
"""

from __future__ import annotations

import socket
import ssl
import time
from dataclasses import dataclass
from typing import Iterable

import requests


# 官方 bytes 端点
CARTESIA_BYTES_URL = "https://api.cartesia.ai/tts/bytes"
CARTESIA_API_VERSION = "2024-11-13"

# 默认模型与发音人
DEFAULT_MODEL = "sonic-2"
DEFAULT_VOICE_ID = "f786b574-daa5-4673-aa0c-cbe3e8534c02"  # Cartesia 文档示例 voice
DEFAULT_LANGUAGE = "zh"

# 精选发音人池（展示给前端下拉框）。
# Cartesia Sonic 系列是多语言模型，同一个 voice id 可以通过 language 切换语种。
# 这里给出几个官方 Library 里通用的 voice id；你可以在 https://play.cartesia.ai/voices 选自己喜欢的。
VOICE_POOL: list[dict] = [
    {
        "name": "Sonic 默认女声（中文）",
        "voice_id": "f786b574-daa5-4673-aa0c-cbe3e8534c02",
        "language": "zh",
    },
    {
        "name": "Sonic 默认女声（英文）",
        "voice_id": "f786b574-daa5-4673-aa0c-cbe3e8534c02",
        "language": "en",
    },
]


@dataclass(slots=True)
class CartesiaCredentials:
    api_key: str

    def ok(self) -> bool:
        return bool(self.api_key)


class CartesiaTTSError(RuntimeError):
    """Cartesia 合成失败时抛出。"""


_RETRIABLE_NET_ERRORS: tuple[type[BaseException], ...] = (
    socket.timeout,
    TimeoutError,
    ConnectionResetError,
    ConnectionAbortedError,
    ssl.SSLEOFError,
    ssl.SSLError,
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    OSError,
)


def synthesize(
    text: str,
    creds: CartesiaCredentials,
    *,
    voice_id: str = DEFAULT_VOICE_ID,
    model_id: str = DEFAULT_MODEL,
    language: str = DEFAULT_LANGUAGE,
    speed: str | float = "normal",
    sample_rate: int = 44100,
    bit_rate: int = 128000,
    timeout: float = 60.0,
    retries: int = 3,
) -> bytes:
    """调用 Cartesia `/tts/bytes`，返回整段 mp3 字节。"""
    if not creds.ok():
        raise CartesiaTTSError("Cartesia 凭证未配置：需要 CARTESIA_API_KEY")

    text = (text or "").strip()
    if not text:
        raise CartesiaTTSError("文本为空")

    headers = {
        "Cartesia-Version": CARTESIA_API_VERSION,
        "X-API-Key": creds.api_key,
        "Content-Type": "application/json",
    }

    body: dict = {
        "model_id": model_id,
        "transcript": text,
        "voice": {"mode": "id", "id": voice_id},
        "output_format": {
            "container": "mp3",
            "sample_rate": sample_rate,
            "bit_rate": bit_rate,
        },
        "language": language,
    }

    if speed not in (None, "normal", 1.0):
        body["speed"] = speed

    last_exc: Exception | None = None
    for attempt in range(max(1, retries)):
        try:
            resp = requests.post(
                CARTESIA_BYTES_URL,
                headers=headers,
                json=body,
                timeout=timeout,
            )
        except _RETRIABLE_NET_ERRORS as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(0.8 * (attempt + 1))
                continue
            raise CartesiaTTSError(
                f"连接 Cartesia 失败（重试 {retries} 次仍失败）：{exc}"
            ) from exc

        if resp.status_code != 200:
            ct = resp.headers.get("content-type", "")
            detail = resp.text[:300] if "json" in ct or "text" in ct else "<binary>"
            raise CartesiaTTSError(
                f"Cartesia 返回 HTTP {resp.status_code}: {detail}"
            )

        ct = resp.headers.get("content-type", "")
        if resp.content[:1] == b"{" or "application/json" in ct:
            raise CartesiaTTSError(
                f"Cartesia 返回非音频内容（可能是错误报文）：{resp.text[:300]}"
            )

        return resp.content

    raise CartesiaTTSError(
        f"未知错误（重试 {retries} 次仍失败）：{last_exc}"
    ) from last_exc


def synthesize_iter(
    text: str,
    creds: CartesiaCredentials,
    **kwargs,
) -> Iterable[bytes]:
    """流式分片返回（当前实现整段合成后单次 yield）。"""
    yield synthesize(text, creds, **kwargs)
