"""FastAPI 服务器 —— 极简版。

/            首页：参考视频作为脸 + 文字输入 + 立即播放 TTS
/tts?text=   返回整段 TTS mp3（Cartesia Sonic，付费）
/face.mp4    参考脸部动画视频（从 docs/videos 提供）
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import cartesia_tts, lipsync, tts


load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"
FACE_VIDEO = ROOT / "docs" / "videos" / "制作说话的眼睛嘴巴视频.mp4"
EYES_VIDEO = ROOT / "docs" / "videos" / "eyes.mp4"
EYES_WEBM = ROOT / "docs" / "videos" / "eyes.webm"

app = FastAPI(title="Talking Face Demo")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/face.mp4")
def face_video():
    if not FACE_VIDEO.exists():
        raise HTTPException(404, "脸部动画视频不存在")
    return FileResponse(FACE_VIDEO, media_type="video/mp4")


@app.get("/eyes.webm")
def eyes_webm():
    """带 alpha 通道的 VP9 WebM（Chrome/Edge/Firefox 原生支持）。"""
    if not EYES_WEBM.exists():
        raise HTTPException(
            404, "eyes.webm 不存在，请跑: uv run python scripts/gen_eyes.py"
        )
    return FileResponse(EYES_WEBM, media_type="video/webm")


@app.get("/eyes.mp4")
def eyes_video():
    """mp4 fallback（Safari 等不支持 VP9 alpha 时用）。"""
    if not EYES_VIDEO.exists():
        raise HTTPException(
            404, "eyes.mp4 不存在，请跑: uv run python scripts/gen_eyes.py"
        )
    return FileResponse(EYES_VIDEO, media_type="video/mp4")


@app.get("/tts")
def tts_endpoint(
    text: str = Query(..., min_length=1, max_length=2000),
    voice_id: str | None = Query(None, description="Cartesia voice id"),
    language: str | None = Query(None, description="zh / en / ja / ...", max_length=8),
    model_id: str | None = Query(None, description="sonic-2 / sonic-3 等"),
):
    cfg = tts.TTSConfig.from_env()
    if voice_id:
        cfg.voice_id = voice_id
    if language:
        cfg.language = language
    if model_id:
        cfg.model_id = model_id

    try:
        audio, backend = tts.synthesize(text, cfg)
    except Exception as e:
        raise HTTPException(500, f"TTS 失败: {e}")

    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={
            "X-TTS-Backend": backend,
            "X-TTS-Voice": cfg.voice_id,
            "X-TTS-Lang": cfg.language,
            "X-TTS-Model": cfg.model_id,
        },
    )


@app.get("/voices")
def voices_endpoint():
    """返回 Cartesia 精选发音人列表，给前端下拉框用。"""
    return {
        "voices": cartesia_tts.VOICE_POOL,
        "default": cartesia_tts.DEFAULT_VOICE_ID,
        "default_language": cartesia_tts.DEFAULT_LANGUAGE,
        "default_model": cartesia_tts.DEFAULT_MODEL,
    }


class LipsyncRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    voice_id: str | None = None
    language: str | None = None


@app.post("/lipsync")
def lipsync_endpoint(req: LipsyncRequest):
    """高精度 Wav2Lip 唇形同步：TTS → Replicate Wav2Lip → 返回 mp4。典型 30-90s。"""
    if not lipsync.is_available():
        raise HTTPException(
            503,
            "Replicate 未配置，请在 .env 里填 REPLICATE_API_TOKEN "
            "(https://replicate.com/account/api-tokens)",
        )
    if not FACE_VIDEO.exists():
        raise HTTPException(500, "face.mp4 不存在")

    cfg = tts.TTSConfig.from_env()
    if req.voice_id:
        cfg.voice_id = req.voice_id
    if req.language:
        cfg.language = req.language

    try:
        audio, backend = tts.synthesize(req.text, cfg)
    except Exception as e:
        raise HTTPException(500, f"TTS 失败: {e}")

    try:
        video = lipsync.run_wav2lip(FACE_VIDEO.read_bytes(), audio)
    except Exception as e:
        raise HTTPException(500, f"Wav2Lip 失败: {e}")

    return Response(
        content=video,
        media_type="video/mp4",
        headers={"X-TTS-Backend": backend, "X-Lipsync": "replicate-wav2lip"},
    )


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "cartesia_configured": bool(os.getenv("CARTESIA_API_KEY", "").strip()),
        "replicate_configured": lipsync.is_available(),
        "face_video_exists": FACE_VIDEO.exists(),
    }
