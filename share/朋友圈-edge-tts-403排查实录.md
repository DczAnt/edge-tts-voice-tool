# 朋友圈图文成品 — edge-tts 403 排查实录

> 事实核对：基于 edge_tts_voice_tool 项目实际排查（2026-10-15，edge-tts 7.2.8→7.3.1）

---

## 一、正文文案（直接复制可发）

用 edge-tts 生成语音，之前好好的，今天突然全部 403？

报错 `WSServerHandshakeError: 403`，代码一行没改。根因：微软悄悄升级了在线语音的鉴权算法 Sec-MS-GEC（v1→v2），旧版 edge-tts 生成的 token 直接被拒。

重点：v2 不是改个版本号前缀——drm.py 从 160 行暴增到 610 行，整套 SHA256 签名重写（篡改轮常量 + 加 CS64 校验和）。想 monkey-patch 前缀绕过？不行，算法本体变了。解法就一句 `pip install --upgrade edge-tts`。

但坑没完：PyInstaller 打的 exe 里 edge-tts 被冻结，pip 升级根本进不去，必须重新打包。于是给工具加了两层自检：启动时异步查 PyPI 落后就预警，运行时识别 403 自动弹升级指引。下次微软再换算法，提示直接指路，不用排查。

**https://github.com/DczAnt/edge-tts-voice-tool**

你的 edge-tts 还能正常生成吗？评论区报个版本号 👇

---

## 二、配图清单（3 张，GitHub Dark 风格，1080×1440 竖版）

| 卡位 | 内容 | 模板 |
|------|------|------|
| **图1 报错钩子卡** | 终端窗口：`WSServerHandshakeError: 403, message='Invalid response status'`；大标题"之前好好的 突然 403"；副题"代码一行没改，微软悄悄换了鉴权算法" | `card1-403-error.html` |
| **图2 v1→v2 对比卡** | v1: 前缀 `1-` / drm.py 160 行 / 普通 SHA256；v2: 前缀 `2-` / drm.py 610 行 / 定制 SHA256 + CS64；底部"monkey-patch 前缀？不行，算法本体变了" | `card2-v1-v2-diff.html` |
| **图3 仓库封面卡** | 三个特性：403 自检 / 版本预警 / 便携 exe；副题"Edge TTS 语音生成工具"；底部地址 `github.com/DczAnt/edge-tts-voice-tool` | `card3-repo-cover.html` |

### 渲染命令（Git Bash）

```bash
EDGE="/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
OUT="E:/AIcomm/edge_tts_voice_tool/share/images"
mkdir -p "$OUT"

"$EDGE" --headless=new --disable-gpu --hide-scrollbars \
  --screenshot="$OUT/card1-403-error.png" --window-size=1080,1440 \
  "file:///E:/AIcomm/edge_tts_voice_tool/share/card1-403-error.html"
"$EDGE" --headless=new --disable-gpu --hide-scrollbars \
  --screenshot="$OUT/card2-v1-v2-diff.png" --window-size=1080,1440 \
  "file:///E:/AIcomm/edge_tts_voice_tool/share/card2-v1-v2-diff.html"
"$EDGE" --headless=new --disable-gpu --hide-scrollbars \
  --screenshot="$OUT/card3-repo-cover.png" --window-size=1080,1440 \
  "file:///E:/AIcomm/edge_tts_voice_tool/share/card3-repo-cover.html"
```

---

## 三、发布技巧

- **发布时间**：工作日 12:00-13:00 或 20:00-22:00（开发者刷朋友圈高峰）
- **折叠区**：前 3 行"之前好好的突然 403？"钩子已在前 3 行，展开率高
- **评论区置顶**（发布后自己评论）：
  > 补充：edge-tts 这个 403 是通病，微软每隔几个月就升级一次 Sec-MS-GEC 算法。已把自检机制开源，启动自动查版本 + 403 自动识别给升级指引。
- **互动回复模板**（有人评论"我也遇到了"时）：
  > 直接 pip install --upgrade edge-tts 就行。如果是 exe 版，edge-tts 被冻结在 exe 里 pip 升级没用，得重新打包或下载新版。

---

## 自检清单

- [x] 前 3 行有钩子（"之前好好的突然 403？"反差在前 3 行）
- [x] GitHub 地址单独成行加粗、倒数第二行
- [x] 数字与排查一致（7.2.8→7.3.1，160→610 行，v1→v2）
- [x] 截图无敏感信息
- [x] 结尾有互动问题（"你的 edge-tts 还能正常生成吗？"）
- [x] 读者能带走至少 1 个知识点（403 根因 + 升级解法 + exe 冻结陷阱）
- [x] 事实核对声明已附