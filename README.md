# 会说话的脸 · Talking Face Demo

输入一段中文 → Fish Audio / Edge TTS 合成语音 → 浏览器实时切换真实嘴型截图 PNG，叠在脸部视频上，像物体成精。

---

## 快速启动（3 步）

### 前置要求

| 工具 | 用途 | 安装 |
|------|------|------|
| **uv** | Python 包管理 | `powershell -c "irm https://astral.sh/uv/install.ps1 \| iex"` |
| **ffmpeg** | 仅模式 A（webm 合成）需要 | `winget install Gyan.FFmpeg` |

### 第 1 步：进入目录 & 安装依赖

```powershell
cd C:\Learning\sample\synchronous-github\zingspark\hackathon
uv sync
```

### 第 2 步：配置 API Key（已预填，可跳过）

`.env` 已经有 Fish Audio key，直接用。若需修改：

```powershell
# 打开 .env 编辑即可
notepad .env
```

| 变量 | 说明 | 是否必填 |
|------|------|---------|
| `FISH_API_KEY` | Fish Audio API key | 可选（没有会自动用免费 Edge TTS 兜底） |
| `FISH_REFERENCE_ID` | 声音 ID（去 fish.audio 挑 funny 中文声音） | 可选 |
| `REPLICATE_API_TOKEN` | Replicate token，用于高精度 Wav2Lip | 可选 |

### 第 3 步：启动服务

```powershell
uv run uvicorn app.server:app --reload --port 8000
```

浏览器打开 **<http://localhost:8000>**，点 **▶ 实时说话** 即可。

---

## 页面使用说明

1. **要说的话**：输入中文文本，支持情感标签：
   ```
   [laughing] 哎呦你干嘛~ [excited] 这个苹果居然会说话！
   ```
2. **声音选择**：左侧 select 是 Edge TTS（免费，6 种趣味声音）；右侧填 `reference_id` 可用 Fish Audio 的梗声。
3. **▶ 实时说话（免费）**：TTS 合成 → 浏览器实时切换嘴型 PNG，延迟 < 500 ms。
4. **✨ 高精度唇形（Replicate）**：调用 Wav2Lip 神经网络合成，~30-90 秒，需要 `REPLICATE_API_TOKEN`。

---

## 嘴型方案说明

### 当前方案：截图 PNG 切换（默认）

从源视频 `docs/videos/制作说话的眼睛嘴巴视频.mp4` 抽取 9 帧真实嘴型：

| 文件 | 对应发音 | 说明 |
|------|---------|------|
| `shape-A.png` | M/B/P / 静默 | 双唇完全闭合 |
| `shape-B.png` | K/S/T/EH | 上下齿轻轻分开 |
| `shape-C.png` | AE "诶" | 中等张开带笑意 |
| `shape-D.png` | AA "啊" | 嘴呈大椭圆完全张开 |
| `shape-E.png` | AO "哦" | 双唇收圆中度张开 |
| `shape-F.png` | UW "呜" | 唇极度收拢成小圆口 |
| `shape-G.png` | F/V 唇齿音 | 上齿轻压下唇 |
| `shape-H.png` | L 舌上顶 | 嘴半张舌面突出 |
| `shape-X.png` | 休息态 | 同 A |

浏览器每帧分析音频的 **频谱重心 + RMS + 中频能量**，映射到对应的嘴型 PNG，叠加在脸部视频上。

### 备用方案：振幅几何图形

若 PNG 素材加载失败，自动回落到用 Canvas 画的椭圆嘴（不需要任何素材）。在页面底部可手动切换。

---

## 架构速览

```
浏览器输入文字
    │
    ▼ GET /tts?text=...
FastAPI (app/server.py)
    │
    ├─ Fish Audio TTS REST → mp3
    └─ edge-tts (fallback) → mp3
         │
         ▼ 返回 mp3 给浏览器
浏览器 AudioContext.AnalyserNode
    │ 每帧取 RMS + 频谱重心
    ▼
切换 static/mouths/shape-{A..X}.png
叠加在 face.mp4 视频上方
```

---

## 高精度模式（可选）

`POST /lipsync` → Replicate Wav2Lip → 返回 mp4（约 $0.13 / 次）

需要在 `.env` 填入：
```
REPLICATE_API_TOKEN=你的token
```

---

## 扩展点

- **换脸部视频**：替换 `docs/videos/制作说话的眼睛嘴巴视频.mp4`，然后重新跑 `static/mouths/README.md` 里的 ffmpeg 命令重新截取嘴型 PNG
- **换背景图**：编辑 `static/index.html`，在 `.stage` 里加 `<img>` 作背景层
- **换声音**：去 <https://fish.audio/zh-CN/>「发现」页面，挑有趣的中文声音，URL 末尾就是 `reference_id`
