# 会说话的脸 · Talking Face Demo

输入一段中文 → **Cartesia Sonic TTS** 合成语音 → 浏览器实时切换真实嘴型截图 PNG，叠在脸部视频上，像物体成精。

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

### 第 2 步：配置 Cartesia API Key

仓库根目录已提交 **`.env`**（方便 clone 即用），其中 `CARTESIA_API_KEY` 等为**占位符**，请按下面替换为你自己的 key：

1. 去 <https://play.cartesia.ai/keys> 创建 API Key
2. 编辑 `.env`，把 `PASTE_YOUR_CARTESIA_API_KEY` 换成真实 key；需要高精度唇形时再填 `REPLICATE_API_TOKEN`

**关于 GitHub 推送：**若把含真实 token 的 `.env` 再次 `commit` 并 `push`，GitHub **Push Protection** 通常会拒绝。协作时要么只在本机改 `.env` 不提交，要么使用占位符版本进仓库；切勿把生产密钥写进 Git 历史。

| 变量 | 说明 | 是否必填 |
|------|------|---------|
| `CARTESIA_API_KEY` | Cartesia API Key（`sk_car_...`） | **必填** |
| `CARTESIA_VOICE_ID` | 默认 voice id（见 <https://play.cartesia.ai/voices>） | 可选 |
| `CARTESIA_LANGUAGE` | 默认语言 `zh / en / ja / fr / de / es / pt / ko / hi / it` | 可选，默认 `zh` |
| `CARTESIA_MODEL` | 模型 `sonic-2 / sonic-3` | 可选，默认 `sonic-2` |
| `REPLICATE_API_TOKEN` | Replicate token，用于高精度 Wav2Lip | 可选 |

### 第 3 步：启动服务

```powershell
uv run uvicorn app.server:app --reload --port 8000
```

浏览器打开 **<http://localhost:8000>**，点 **▶ 实时说话** 即可。

---

## 页面使用说明

1. **要说的话**：输入文本，Sonic 系列是多语言模型，同一个 voice 可以切换语言发音
2. **Cartesia voice / 语言**：下拉框切换发音人 id 和语言；想换音色去 <https://play.cartesia.ai/voices> 复制 voice id 到 `.env` 的 `CARTESIA_VOICE_ID`
3. **▶ 实时说话（Cartesia Sonic）**：Cartesia `/tts/bytes` 端点返回 mp3 → 浏览器本地音素分析 → 切嘴型 PNG，延迟 < 500 ms
4. **✨ 高精度唇形（Replicate）**：调用 Wav2Lip 神经网络合成，~30-90 秒，需要 `REPLICATE_API_TOKEN`

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
    ▼ GET /tts?text=...&voice_id=...&language=zh
FastAPI (app/server.py)
    │
    ▼
Cartesia Sonic TTS（HTTP POST /tts/bytes）→ mp3
    │ 网络抖动自动重试（SSL EOF / RST / read timeout）
    ▼
返回 mp3 给浏览器
    │
浏览器 AudioContext.AnalyserNode
    │ 每帧取 RMS + 频谱重心
    ▼
切换 static/mouths/shape-{A..X}.png
叠加在 face.mp4 视频上方
```

---

## 代码结构

| 文件 | 职责 |
|------|------|
| `app/server.py` | FastAPI 路由：`/tts`、`/voices`、`/lipsync`、`/health` |
| `app/cartesia_tts.py` | Cartesia HTTP TTS 客户端（`/tts/bytes` + 网络抖动自动重试） |
| `app/tts.py` | TTS 统一入口（当前唯一后端 = Cartesia） |
| `app/lipsync.py` | 调用 Replicate Wav2Lip |
| `static/index.html` | 前端单页 |

---

## 高精度模式（可选）

`POST /lipsync` → Cartesia TTS → Replicate Wav2Lip → 返回 mp4（约 $0.13 / 次）

需要在 `.env` 填入：

```
REPLICATE_API_TOKEN=你的token
```

---

## 扩展点

- **换脸部视频**：替换 `docs/videos/制作说话的眼睛嘴巴视频.mp4`，然后重新跑 `static/mouths/README.md` 里的 ffmpeg 命令重新截取嘴型 PNG
- **换背景图**：编辑 `static/index.html`，在 `.stage` 里加 `<img>` 作背景层
- **换声音 / 克隆声音**：去 <https://play.cartesia.ai/voices> 浏览 voice library，或用 <https://play.cartesia.ai/> 录一段自己的声音克隆成 voice，复制 voice id 到 `.env` 的 `CARTESIA_VOICE_ID`
- **切换模型**：`.env` 里设 `CARTESIA_MODEL=sonic-3` 换最新更自然的版本
