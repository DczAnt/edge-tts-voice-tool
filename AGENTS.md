# AGENTS.md — Edge TTS 语音生成工具开发入口

> 本文档供 AI 开发助手快速上手，涵盖架构、命令、陷阱与约定。

## 项目概述

基于 `edge-tts`（微软 Edge 在线语音合成）的 Windows 桌面 GUI 工具（tkinter），输入文字一键生成 MP3。
单文件 `src/main.py`，可 PyInstaller 打包为便携 exe。

## 技术栈

- **语言**：Python 3.10+（开发环境 3.13）
- **GUI**：tkinter / ttk（标准库，无额外 UI 框架）
- **核心依赖**：`edge-tts>=7.3.1`（在线 TTS）、`aiohttp`（edge-tts 依赖）
- **打包**：`pyinstaller>=6.0`（onefile + windowed）
- **平台**：Windows 10/11（用到 `os.startfile`）

## 开发命令

```bash
# 安装依赖
pip install -r requirements.txt

# 源码运行
python src/main.py

# 语法检查
python -m py_compile src/main.py

# 重新打包 exe（产物 dist/EdgeTTS_VoiceTool.exe）
pyinstaller --clean --onefile --windowed --name EdgeTTS_VoiceTool \
    --distpath dist --workpath build --specpath build src/main.py
# 或直接：build.bat（注意末尾有 pause + explorer，自动化场景用上面的裸命令）
```

## 目录结构

```
src/main.py          # 全部逻辑（GUI + edge-tts 调用 + 自检），单文件
build.bat            # 打包脚本
requirements.txt     # edge-tts>=7.3.1, pyinstaller>=6.0
config.json          # 运行时自动生成（gitignore），保存用户参数
dist/                # exe 交付物（gitignore）
build/               # PyInstaller 中间产物（gitignore）
```

## 架构要点

### 核心类 `App(tk.Tk)`（src/main.py）

单文件单类，所有 GUI 与逻辑集中于此。关键区域：

| 区域 | 方法 | 说明 |
|------|------|------|
| 语音列表加载 | `_load_voices_async` / `_on_voices_loaded` / `_on_voices_failed` | 后台线程调 `edge_tts.list_voices()`，失败回退预设列表；403 时给针对性提示 |
| 语音生成 | `_start_generate` → worker 线程 → `_on_generate_ok` / `_on_generate_fail` | `edge_tts.Communicate().save()`，403 识别后区分源码/exe 给升级指引 |
| 版本自检 | `_check_update_async` / `_on_update_available` | 启动时 daemon 线程查 PyPI JSON，落后则状态栏提示 |
| 403 识别 | `_is_auth_403(msg)`（静态方法） | 匹配 `"403" in msg and "Invalid response status" in msg` |
| 参数说明区 | `_build_ui` 末尾 Canvas+Scrollbar | 可滚动，滚轮通过 Enter/Leave bind_all 局部生效 |

### 数据流

```
用户输入文本/参数 → _start_generate → 后台线程 asyncio.run(Communicate.save)
  → 成功: _on_generate_ok → 自动试听
  → 失败: _on_generate_fail → _is_auth_403? 针对性提示 : 通用错误
```

### 配置持久化

`config.json` 保存文本/语音/语速/音量/音调/文件名/输出目录，启动时 `_load_config` 恢复，关闭/生成时 `_save_config` 写入。
路径优先程序目录（便携模式），无权限退回 `~/.edge_tts_voice_tool.json`。

## 已知陷阱（重要）

### 1. edge-tts 403 — 微软定期升级 Sec-MS-GEC 鉴权算法

**现象**：`WSServerHandshakeError: 403, message='Invalid response status'`，"之前可用突然报错"。
**根因**：微软不定期升级 Sec-MS-GEC 算法版本（已观察 v1→v2），旧版 edge-tts 的 token 被拒绝。v2 不只是改前缀，是整套签名算法重写（定制 SHA256 + CS64 校验）。
**修复**：`pip install --upgrade edge-tts`。**不要**尝试 monkey-patch 前缀，算法本体已变。
**预防**：`requirements.txt` 下限已收紧到 `>=7.3.1`；工具内置启动版本检查 + 运行时 403 识别。
**再次遇到时**：第一步直接升级 edge-tts 并测试，勿先排查本地代码。

### 2. PyInstaller exe 内 edge-tts 被冻结

`--onefile` 打包后 edge-tts 及依赖被嵌入 exe。**pip 升级 edge-tts 不影响已打包的 exe**。
修复 exe 的 403 必须**重新打包**。`_is_auth_403` 在 exe 模式（`sys.frozen`）下提示"下载最新版"而非"pip 升级"。

### 3. 参数说明区滚轮绑定

Canvas 滚轮用 `bind_all("<MouseWheel>")`，会全局拦截。为避免影响文本输入框滚动，仅在鼠标 Enter Canvas 时 bind_all、Leave 时 unbind_all。
**改动注意**：若新增其他需要滚轮的区域，勿与该机制冲突。

### 4. 在线服务依赖

语音列表加载和生成都需要网络。离线时语音列表回退 `PRESET_VOICES`（硬编码 15 个常用语音），生成则直接报错。

## 代码约定

- **单文件架构**：所有逻辑在 `src/main.py`，不拆模块（便携工具规模不需要）
- **无第三方 UI 框架**：仅 tkinter/ttk，样式通过 `ttk.Style` 集中配置
- **后台任务**：网络调用（list_voices / Communicate.save / PyPI 查询）一律放 daemon 线程，通过 `self.after(0, callback)` 回主线程更新 UI
- **异常处理**：后台线程 catch Exception 后转主线程弹窗，不在线程内直接操作 UI
- **配色常量**：`COLOR_*` 集中定义在文件顶部，勿散落硬编码
- **无注释**：代码自解释，仅在非显而易见处加简短注释
- **中文界面**：所有用户可见文案用简体中文

## 修改检查清单

改动后务必验证：

1. `python -m py_compile src/main.py` — 语法
2. 源码运行生成一条语音 — 功能正常
3. 若改了 UI 布局 — GUI smoke test（创建 App → update_idletasks → 检查 winfo 尺寸 → destroy）
4. 若改了打包相关 — 重新 `pyinstaller` 打包确认 exe 可启动