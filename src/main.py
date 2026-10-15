# -*- coding: utf-8 -*-
"""Edge TTS 语音生成工具 - 便携版

基于 edge-tts (微软 Edge 在线语音合成) 的桌面可视化工具。
直接调用 edge_tts Python API，打包后完全自包含，无需目标机器安装任何依赖。
"""
import asyncio
import json
import os
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.request
from importlib import metadata
from tkinter import ttk, filedialog, messagebox

import edge_tts

APP_TITLE = "Edge TTS 语音生成工具"
APP_VERSION = "1.0.0"

FONT_NAME = "Microsoft YaHei UI"
COLOR_BG = "#f4f5f7"
COLOR_PANEL = "#ffffff"
COLOR_ACCENT = "#2563eb"
COLOR_ACCENT_HOVER = "#1d4ed8"
COLOR_ACCENT_DISABLED = "#9db8f0"
COLOR_TEXT = "#1f2937"
COLOR_TEXT_SUB = "#6b7280"
COLOR_BORDER = "#e2e5ea"

DEFAULT_TEXT = "请注意，当前通道拥挤，请缓慢通行，注意安全！"
DEFAULT_VOICE = "zh-CN-YunxiNeural"
DEFAULT_FILENAME = "broadcast.mp3"

# 离线兜底预设（联网加载在线列表前的初始选项）
PRESET_VOICES = [
    ("zh-CN-YunxiNeural", "男声 · 阳光"),
    ("zh-CN-XiaoxiaoNeural", "女声 · 温柔自然"),
    ("zh-CN-YunyangNeural", "男声 · 新闻播报"),
    ("zh-CN-YunjianNeural", "男声 · 浑厚有力"),
    ("zh-CN-XiaoyiNeural", "女声 · 活泼"),
    ("zh-CN-YunxiaNeural", "男声 · 少年音"),
    ("zh-CN-liaoning-XiaobeiNeural", "女声 · 东北话"),
    ("zh-CN-shaanxi-XiaoniNeural", "女声 · 陕西话"),
    ("zh-TW-HsiaoChenNeural", "女声 · 台湾腔"),
    ("zh-TW-YunJheNeural", "男声 · 台湾腔"),
    ("zh-HK-HiuMaanNeural", "女声 · 粤语"),
    ("zh-HK-WanLungNeural", "男声 · 粤语"),
    ("en-US-AriaNeural", "Female · English"),
    ("en-US-GuyNeural", "Male · English"),
    ("en-US-JennyNeural", "Female · English"),
]

GENDER_CN = {"Male": "男声", "Female": "女声"}


def _version_tuple(v):
    """将语义版本号转为可比较的整数元组，非数字段忽略"""
    return tuple(int(x) for x in v.split(".") if x.isdigit())


def app_base_dir():
    """获取程序所在目录（兼容 PyInstaller 打包后的 exe 与源码运行）"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def config_path():
    """配置文件：优先保存在程序目录（便携模式），无权限时退回用户目录"""
    p = os.path.join(app_base_dir(), "config.json")
    try:
        with open(p, "a", encoding="utf-8"):
            pass
        return p
    except OSError:
        return os.path.join(os.path.expanduser("~"), ".edge_tts_voice_tool.json")


class ToolTip:
    """简单悬停提示"""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _event):
        if self.tip is not None:
            return
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            self.tip, text=self.text, justify="left", bg="#374151", fg="white",
            font=(FONT_NAME, 9), padx=8, pady=5, wraplength=320,
        )
        label.pack()

    def _hide(self, _event):
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE}  v{APP_VERSION}")
        self.geometry("980x940")
        self.minsize(900, 820)
        self.configure(bg=COLOR_BG)

        self._voice_map = {}          # 显示文本 -> ShortName
        self._all_voice_values = []   # 全部语音显示文本
        self._generating = False
        self._last_output = None
        self._status_anim_id = None

        self._init_style()
        self._build_ui()
        self._load_config()
        self._load_voices_async()
        self._check_update_async()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ 样式
    def _init_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure(".", background=COLOR_BG, foreground=COLOR_TEXT, font=(FONT_NAME, 9))
        style.configure("TFrame", background=COLOR_BG)
        style.configure("Panel.TFrame", background=COLOR_PANEL)
        style.configure("TLabel", background=COLOR_BG, foreground=COLOR_TEXT)
        style.configure("Panel.TLabel", background=COLOR_PANEL)
        style.configure("Sub.TLabel", foreground=COLOR_TEXT_SUB, background=COLOR_BG, font=(FONT_NAME, 8))
        style.configure("PanelSub.TLabel", foreground=COLOR_TEXT_SUB, background=COLOR_PANEL, font=(FONT_NAME, 8))
        style.configure("Title.TLabel", font=(FONT_NAME, 15, "bold"), background=COLOR_BG)
        style.configure("ParamName.TLabel", font=(FONT_NAME, 9, "bold"), background=COLOR_PANEL)
        style.configure("Status.TLabel", foreground=COLOR_TEXT_SUB, background=COLOR_BG)

        style.configure("TLabelframe", background=COLOR_PANEL, borderwidth=1,
                        relief="solid", bordercolor=COLOR_BORDER)
        style.configure("TLabelframe.Label", background=COLOR_PANEL,
                        foreground=COLOR_TEXT, font=(FONT_NAME, 9, "bold"))

        style.configure("TButton", background=COLOR_PANEL, borderwidth=1,
                        relief="solid", bordercolor=COLOR_BORDER, padding=(12, 6))
        style.map("TButton", background=[("active", "#eef1f6")])

        style.configure("Accent.TButton", background=COLOR_ACCENT, foreground="white",
                        borderwidth=0, font=(FONT_NAME, 10, "bold"), padding=(20, 8))
        style.map("Accent.TButton",
                  background=[("disabled", COLOR_ACCENT_DISABLED), ("active", COLOR_ACCENT_HOVER)],
                  foreground=[("disabled", "#eef2ff")])

        style.configure("TEntry", fieldbackground="white", borderwidth=1,
                        relief="solid", bordercolor=COLOR_BORDER, padding=3)
        style.map("TEntry", bordercolor=[("focus", COLOR_ACCENT)])

        style.configure("TCombobox", fieldbackground="white", background="white",
                        borderwidth=1, bordercolor=COLOR_BORDER, padding=3,
                        arrowcolor=COLOR_TEXT, selectbackground="#dbeafe",
                        selectforeground=COLOR_TEXT)
        style.map("TCombobox", bordercolor=[("focus", COLOR_ACCENT)])
        self.option_add("*TCombobox*Listbox.font", (FONT_NAME, 9))
        self.option_add("*TCombobox*Listbox.background", "white")
        self.option_add("*TCombobox*Listbox.selectBackground", COLOR_ACCENT)

        style.configure("Param.Horizontal.TScale", troughcolor="#e5e7eb",
                        background=COLOR_PANEL, borderwidth=0, lightcolor=COLOR_ACCENT,
                        darkcolor=COLOR_ACCENT, sliderthickness=16, groovewidth=4)

    # ------------------------------------------------------------------ 界面
    def _build_ui(self):
        # 顶部标题
        header = ttk.Frame(self)
        header.pack(fill="x", padx=24, pady=(18, 6))
        ttk.Label(header, text=APP_TITLE, style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="微软 Edge 在线语音合成 · 生成 MP3",
                  style="Sub.TLabel").pack(side="left", padx=(12, 0), pady=(6, 0))
        ttk.Label(header, text=f"v{APP_VERSION}", style="Sub.TLabel").pack(side="right")

        # 文本输入区
        text_frame = ttk.Labelframe(self, text="  文本内容  ", padding=12)
        text_frame.pack(fill="x", padx=24, pady=(8, 10))
        self.text_input = tk.Text(text_frame, height=6, wrap="word", font=(FONT_NAME, 10),
                                  relief="solid", borderwidth=1, highlightthickness=1,
                                  highlightbackground=COLOR_BORDER, highlightcolor=COLOR_ACCENT,
                                  padx=8, pady=6, undo=True)
        self.text_input.pack(fill="x")
        bottom = ttk.Frame(text_frame, style="Panel.TFrame")
        bottom.pack(fill="x", pady=(6, 0))
        self.char_count = ttk.Label(bottom, text="0 字", style="PanelSub.TLabel")
        self.char_count.pack(side="left")
        clear_btn = ttk.Button(bottom, text="清空", width=6, command=self._clear_text)
        clear_btn.pack(side="right")
        self.text_input.bind("<KeyRelease>", lambda e: self._update_count())
        self.text_input.bind("<<Paste>>", lambda e: self.after(10, self._update_count))

        # 参数设置区
        param_frame = ttk.Labelframe(self, text="  参数设置  ", padding=12)
        param_frame.pack(fill="x", padx=24, pady=(0, 10))
        param_frame.columnconfigure(1, weight=1)

        # 语音选择
        ttk.Label(param_frame, text="语音", style="ParamName.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 12))
        self.voice_var = tk.StringVar()
        self.voice_combo = ttk.Combobox(param_frame, textvariable=self.voice_var,
                                        state="normal", font=(FONT_NAME, 9))
        self.voice_combo.grid(row=0, column=1, sticky="ew")
        self.voice_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_voice_desc())
        self.voice_combo.bind("<KeyRelease>", self._filter_voices)
        ToolTip(self.voice_combo, "支持输入关键字实时过滤，如输入 zh-CN 或 云希；"
                                 "也可手动输入完整语音名称后直接生成")
        self.voice_reload_btn = ttk.Button(param_frame, text="刷新列表", width=9,
                                           command=self._load_voices_async)
        self.voice_reload_btn.grid(row=0, column=2, padx=(10, 0))
        self.voice_desc = ttk.Label(param_frame, text="正在加载语音列表...",
                                    style="PanelSub.TLabel")
        self.voice_desc.grid(row=1, column=1, sticky="w", pady=(4, 0))

        # 三个滑块参数
        self.rate_scale, self.rate_var = self._make_param_row(
            param_frame, 2, "语速", -100, 200, -5, "%",
            "朗读速度：-100% 最慢 ~ +200% 最快，0% 为正常语速。\n示例：-5% 表示放慢 5%。", step=1)
        self.volume_scale, self.volume_var = self._make_param_row(
            param_frame, 4, "音量", -100, 100, 0, "%",
            "音量：-100% 静音 ~ +100% 最大，0% 为原始音量。", step=1)
        self.pitch_scale, self.pitch_var = self._make_param_row(
            param_frame, 6, "音调", -50, 50, 0, "Hz",
            "音调：-50Hz ~ +50Hz，正值更清脆，负值更低沉。", step=1)
        param_frame.rowconfigure(7, weight=1)

        # 输出设置区
        out_frame = ttk.Labelframe(self, text="  输出设置  ", padding=12)
        out_frame.pack(fill="x", padx=24, pady=(0, 10))
        out_frame.columnconfigure(1, weight=1)
        ttk.Label(out_frame, text="文件名", style="ParamName.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 12))
        self.filename_var = tk.StringVar(value=DEFAULT_FILENAME)
        ttk.Entry(out_frame, textvariable=self.filename_var).grid(row=0, column=1, sticky="ew")
        ttk.Label(out_frame, text=".mp3 输出（未写扩展名自动补全）", style="PanelSub.TLabel").grid(
            row=1, column=1, sticky="w", pady=(4, 0))
        ttk.Label(out_frame, text="保存目录", style="ParamName.TLabel").grid(
            row=2, column=0, sticky="w", padx=(12, 12), pady=(10, 0))
        self.outdir_var = tk.StringVar(value=app_base_dir())
        ttk.Entry(out_frame, textvariable=self.outdir_var).grid(row=2, column=1, sticky="ew", pady=(10, 0))
        ttk.Button(out_frame, text="浏览...", width=9, command=self._choose_dir).grid(
            row=2, column=2, padx=(10, 0), pady=(10, 0))

        # 操作按钮
        action_frame = ttk.Frame(self)
        action_frame.pack(fill="x", padx=24, pady=(0, 4))
        self.generate_btn = ttk.Button(action_frame, text="▶  生成语音", style="Accent.TButton",
                                       command=self._start_generate)
        self.generate_btn.pack(side="left")
        self.listen_btn = ttk.Button(action_frame, text="🔊  试听", state="disabled",
                                     command=self._play_last)
        self.listen_btn.pack(side="left", padx=(12, 0))
        self.open_btn = ttk.Button(action_frame, text="📂  打开位置", state="disabled",
                                   command=self._open_last_dir)
        self.open_btn.pack(side="left", padx=(12, 0))

        # 状态栏
        status_frame = ttk.Frame(self)
        status_frame.pack(fill="x", padx=24, pady=(4, 8))
        self.status_var = tk.StringVar(value="就绪 · 语音列表加载中...")
        ttk.Label(status_frame, textvariable=self.status_var, style="Status.TLabel").pack(side="left")

        # 参数说明区（内容多时内部滚动）
        self.help_frame = ttk.Labelframe(self, text="  参数说明  ", padding=(12, 8))
        self.help_frame.pack(fill="both", expand=True, padx=24, pady=(0, 18))

        help_canvas = tk.Canvas(self.help_frame, highlightthickness=0,
                                bg=COLOR_PANEL, height=180)
        help_scroll = ttk.Scrollbar(self.help_frame, orient="vertical",
                                    command=help_canvas.yview)
        help_canvas.configure(yscrollcommand=help_scroll.set)
        help_scroll.pack(side="right", fill="y")
        help_canvas.pack(side="left", fill="both", expand=True)
        help_inner = ttk.Frame(help_canvas, style="Panel.TFrame")
        help_win_id = help_canvas.create_window((0, 0), window=help_inner, anchor="nw")

        help_rows = [
            ("语音", "微软 Edge 浏览器在线 TTS 语音，共 300+ 种。名称格式：区域-语言-名称Neural，"
                     "如 zh-CN-YunxiNeural（云希 · 阳光男声）。下拉框支持关键字过滤，也可直接输入名称。"),
            ("语速", "朗读速度，范围 -100%（最慢）至 +200%（最快），0% 为正常语速。示例：-5% 表示放慢 5%。"),
            ("音量", "范围 -100%（静音）至 +100%（最大），0% 为原始音量。"),
            ("音调", "范围 -50Hz 至 +50Hz，正值更清脆，负值更低沉。"),
            ("输出", "MP3 格式（24kHz / 48kbps / 单声道），由微软服务端合成。"),
            ("网络", "语音合成调用微软在线服务，生成时需保持网络连接。"),
            ("便携", "所有参数自动保存到程序目录 config.json；单文件 exe 可直接拷贝到其他 Windows "
                     "电脑使用，无需安装 Python。"),
        ]
        for i, (name, desc) in enumerate(help_rows):
            ttk.Label(help_inner, text=name, style="ParamName.TLabel").grid(
                row=i, column=0, sticky="nw", padx=(0, 12))
            ttk.Label(help_inner, text=desc, style="PanelSub.TLabel", wraplength=740,
                      justify="left").grid(row=i, column=1, sticky="w", pady=1)
        help_inner.columnconfigure(1, weight=1)

        def _help_on_canvas_configure(event):
            help_canvas.itemconfigure(help_win_id, width=event.width)
            help_canvas.configure(scrollregion=help_canvas.bbox("all"))
        help_canvas.bind("<Configure>", _help_on_canvas_configure)
        help_inner.bind("<Configure>",
                        lambda e: help_canvas.configure(scrollregion=help_canvas.bbox("all")))

        def _help_wheel(event):
            help_canvas.yview_scroll(int(-event.delta / 120), "units")
        help_canvas.bind("<Enter>", lambda e: help_canvas.bind_all("<MouseWheel>", _help_wheel))
        help_canvas.bind("<Leave>", lambda e: help_canvas.unbind_all("<MouseWheel>"))

        self._update_count()

    def _make_param_row(self, parent, row, name, lo, hi, default, unit, tip, step=1):
        """创建一行参数：名称 + 滑块 + 数值输入框（双向联动）"""
        label = ttk.Label(parent, text=name, style="ParamName.TLabel")
        label.grid(row=row, column=0, sticky="w", padx=(0, 12))
        ToolTip(label, tip)

        var = tk.StringVar(value=f"{default:+d}{unit}")

        scale = ttk.Scale(parent, from_=lo, to=hi, orient="horizontal",
                          style="Param.Horizontal.TScale")
        scale.set(default)
        scale.grid(row=row, column=1, sticky="ew", pady=(6 if row > 0 else 12, 0))

        entry = ttk.Entry(parent, width=9, textvariable=var, justify="center")
        entry.grid(row=row, column=2, padx=(12, 0), pady=(6 if row > 0 else 12, 0))
        ToolTip(entry, tip)

        def fmt(v):
            return f"{int(v):+d}{unit}"

        def clamp(v):
            if v is None or v == "":
                return default
            try:
                n = int(float(re.sub(r"[^\d.+-]", "", str(v)) or default))
            except ValueError:
                return default
            return max(lo, min(hi, n))

        def on_scale(_event=None):
            var.set(fmt(scale.get()))

        def on_entry(_event=None):
            v = clamp(var.get())
            var.set(fmt(v))
            scale.set(v)

        scale.configure(command=on_scale)
        entry.bind("<Return>", on_entry)
        entry.bind("<FocusOut>", on_entry)
        ToolTip(scale, tip)

        parent.rowconfigure(row + 1, pad=2)
        return scale, var

    # ------------------------------------------------------------------ 工具
    def _update_count(self):
        self.char_count.configure(text=f"{len(self.text_input.get('1.0', 'end').strip())} 字")

    def _clear_text(self):
        self.text_input.delete("1.0", "end")
        self._update_count()

    def _choose_dir(self):
        d = filedialog.askdirectory(initialdir=self.outdir_var.get() or app_base_dir())
        if d:
            self.outdir_var.set(os.path.normpath(d))

    def _set_status(self, text, anim=False):
        if self._status_anim_id:
            self.after_cancel(self._status_anim_id)
            self._status_anim_id = None
        if anim:
            self._anim_base = text
            self._anim_dots = 0
            self._animate_status()
        else:
            self.status_var.set(text)

    def _animate_status(self):
        self._anim_dots = (self._anim_dots + 1) % 4
        self.status_var.set(self._anim_base + "." * self._anim_dots)
        self._status_anim_id = self.after(400, self._animate_status)

    def _check_update_async(self):
        """启动时异步检查 edge-tts 是否有新版本（旧版可能被微软鉴权拒绝）"""

        def worker():
            try:
                local = metadata.version("edge-tts")
                with urllib.request.urlopen(
                    "https://pypi.org/pypi/edge-tts/json", timeout=5
                ) as resp:
                    latest = json.load(resp)["info"]["version"]
                if _version_tuple(local) < _version_tuple(latest):
                    self.after(0, lambda: self._on_update_available(local, latest))
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _on_update_available(self, local, latest):
        self._set_status(f"提示：edge-tts 有新版本（{local} → {latest}），"
                         f"旧版可能被微软鉴权拒绝，建议升级")

    @staticmethod
    def _is_auth_403(msg):
        """判断异常是否为微软鉴权 403（Sec-MS-GEC 算法版本过期）"""
        return "403" in msg and "Invalid response status" in msg

    # ------------------------------------------------------------------ 语音列表
    def _fill_preset_voices(self):
        values = []
        for sn, desc in PRESET_VOICES:
            display = f"{sn}   ·  {desc}"
            self._voice_map[display] = sn
            values.append(display)
        self._all_voice_values = values
        self.voice_combo["values"] = values
        self._refresh_voice_desc()

    def _load_voices_async(self):
        self.voice_reload_btn.configure(state="disabled")
        self.voice_desc.configure(text="正在加载语音列表...")

        def worker():
            try:
                voices = asyncio.run(edge_tts.list_voices())
                # 中文语音置顶，其余按区域排序
                voices.sort(key=lambda v: (0 if v["ShortName"].lower().startswith("zh") else 1,
                                           v["Locale"], v["ShortName"]))
                values = []
                vmap = {}
                for v in voices:
                    g = GENDER_CN.get(v.get("Gender", ""), v.get("Gender", ""))
                    display = f"{v['ShortName']}   ·  {g} · {v.get('LocaleName', v['Locale'])}"
                    vmap[display] = v["ShortName"]
                    values.append(display)
                self.after(0, lambda: self._on_voices_loaded(values, vmap))
            except Exception as exc:  # 网络失败时保留预设列表
                msg = str(exc)
                self.after(0, lambda: self._on_voices_failed(msg))

        threading.Thread(target=worker, daemon=True).start()

    def _on_voices_loaded(self, values, vmap):
        self._voice_map = vmap
        self._all_voice_values = values
        self.voice_combo["values"] = values
        cur = self.voice_var.get()
        if not cur or cur not in vmap:
            # 保留用户自定义输入，否则落到默认语音
            if DEFAULT_VOICE in vmap.values():
                for d, sn in vmap.items():
                    if sn == DEFAULT_VOICE:
                        self.voice_var.set(d)
                        break
        self._refresh_voice_desc()
        self.voice_reload_btn.configure(state="normal")
        self._set_status(f"就绪 · 已加载 {len(values)} 个语音")

    def _on_voices_failed(self, msg):
        self._fill_preset_voices()
        self.voice_reload_btn.configure(state="normal")
        if self._is_auth_403(msg):
            self.voice_desc.configure(text="在线列表加载失败：微软鉴权算法已升级，edge-tts 版本过旧（403）")
            if getattr(sys, "frozen", False):
                hint = "请下载使用本工具的最新版本"
            else:
                hint = "请执行 pip install --upgrade edge-tts 后重启"
            self._set_status(f"语音列表加载失败（403 鉴权过期）· {hint}")
        else:
            self.voice_desc.configure(text="在线列表加载失败，已使用预设语音（检查网络后可点“刷新列表”重试）")
            self._set_status(f"就绪 · 语音列表加载失败：{msg}")

    def _filter_voices(self, event):
        if event.keysym in ("Up", "Down", "Return", "Escape", "Tab", "Left", "Right",
                            "Home", "End", "Shift_L", "Shift_R", "Control_L", "Control_R"):
            return
        typed = self.voice_var.get().strip().lower()
        if not typed:
            self.voice_combo["values"] = self._all_voice_values
        else:
            self.voice_combo["values"] = [d for d in self._all_voice_values if typed in d.lower()]
        if self.voice_combo["values"]:
            self.voice_combo.event_generate("<Down>")
            self.after(30, lambda: self.voice_combo.event_generate("<Escape>"))

    def _refresh_voice_desc(self):
        display = self.voice_var.get().strip()
        sn = self._voice_map.get(display)
        if sn is None:
            sn = display.split()[0] if display else ""
        if not sn:
            self.voice_desc.configure(text="请选择或输入语音名称")
            return
        self.voice_desc.configure(text=f"当前语音：{sn}")

    def _current_voice(self):
        display = self.voice_var.get().strip()
        sn = self._voice_map.get(display)
        return sn if sn else (display.split()[0] if display else "")

    # ------------------------------------------------------------------ 生成
    def _start_generate(self):
        if self._generating:
            return
        text = self.text_input.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning(APP_TITLE, "请先输入要转换的文本内容。")
            return
        voice = self._current_voice()
        if not voice:
            messagebox.showwarning(APP_TITLE, "请选择或输入语音名称，例如 zh-CN-YunxiNeural。")
            return

        filename = self.filename_var.get().strip() or DEFAULT_FILENAME
        if not filename.lower().endswith(".mp3"):
            filename += ".mp3"
        filename = re.sub(r'[\\/:*?"<>|]', "_", filename)
        out_dir = self.outdir_var.get().strip() or app_base_dir()
        out_path = os.path.join(out_dir, filename)

        if os.path.exists(out_path):
            if not messagebox.askyesno(APP_TITLE, f"文件已存在，是否覆盖？\n\n{out_path}"):
                return

        rate = f"{max(-100, min(200, self._int_val(self.rate_var, '%'))):+d}%"
        volume = f"{max(-100, min(100, self._int_val(self.volume_var, '%'))):+d}%"
        pitch = f"{max(-50, min(50, self._int_val(self.pitch_var, 'Hz'))):+d}Hz"

        self._save_config()

        self._generating = True
        self._set_ui_generating(True)
        self._set_status("正在生成语音", anim=True)
        t0 = time.time()

        def worker():
            async def run():
                communicate = edge_tts.Communicate(text, voice, rate=rate,
                                                   volume=volume, pitch=pitch)
                await communicate.save(out_path)

            try:
                asyncio.run(run())
                cost = time.time() - t0
                self.after(0, lambda: self._on_generate_ok(out_path, cost))
            except Exception as exc:
                msg = str(exc)
                self.after(0, lambda: self._on_generate_fail(msg))

        threading.Thread(target=worker, daemon=True).start()

    def _int_val(self, var, unit):
        try:
            return int(re.sub(r"[^\d+-]", "", var.get()))
        except (ValueError, TypeError):
            return int(0)

    def _set_ui_generating(self, busy):
        self.generate_btn.configure(state="disabled" if busy else "normal")
        self.voice_reload_btn.configure(state="disabled" if busy else "normal")
        if busy:
            self.listen_btn.configure(state="disabled")
            self.open_btn.configure(state="disabled")

    def _on_generate_ok(self, path, cost):
        self._generating = False
        self._set_ui_generating(False)
        self._last_output = path
        self.listen_btn.configure(state="normal")
        self.open_btn.configure(state="normal")
        size_kb = os.path.getsize(path) / 1024
        self._set_status(f"生成完成：{os.path.basename(path)}（{size_kb:.0f} KB，耗时 {cost:.1f} 秒）")
        self._auto_play(path)

    def _on_generate_fail(self, msg):
        self._generating = False
        self._set_ui_generating(False)
        self._set_status("生成失败")
        if self._is_auth_403(msg):
            if getattr(sys, "frozen", False):
                hint = ("微软在线语音鉴权算法已升级，程序内置的 edge-tts 版本过旧被拒绝（403）。\n\n"
                        "请下载使用本工具的最新版本。")
            else:
                hint = ("微软在线语音鉴权算法已升级，已安装的 edge-tts 版本过旧被拒绝（403）。\n\n"
                        "请在命令行执行：pip install --upgrade edge-tts\n"
                        "升级后重启本程序即可恢复。")
            messagebox.showerror(APP_TITLE, f"语音生成失败：\n\n{hint}")
        else:
            messagebox.showerror(APP_TITLE, f"语音生成失败：\n\n{msg}\n\n"
                                            f"常见原因：网络未连接、语音名称无效。")

    def _auto_play(self, path):
        """生成后自动打开系统播放器试听"""
        try:
            os.startfile(path)  # noqa - Windows 专用
        except OSError:
            pass

    def _play_last(self):
        if self._last_output and os.path.exists(self._last_output):
            os.startfile(self._last_output)  # noqa - Windows 专用

    def _open_last_dir(self):
        if self._last_output and os.path.exists(self._last_output):
            subprocess.Popen(f'explorer /select,"{os.path.normpath(self._last_output)}"')

    # ------------------------------------------------------------------ 配置
    def _save_config(self):
        cfg = {
            "text": self.text_input.get("1.0", "end").rstrip("\n"),
            "voice": self._current_voice(),
            "rate": self.rate_var.get(),
            "volume": self.volume_var.get(),
            "pitch": self.pitch_var.get(),
            "filename": self.filename_var.get(),
            "outdir": self.outdir_var.get(),
        }
        try:
            with open(config_path(), "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def _load_config(self):
        try:
            with open(config_path(), "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except (OSError, json.JSONDecodeError):
            cfg = {}

        self.text_input.delete("1.0", "end")
        self.text_input.insert("1.0", cfg.get("text", DEFAULT_TEXT))
        voice = cfg.get("voice", DEFAULT_VOICE)
        matched = [d for d, sn in self._voice_map.items() if sn == voice]
        self.voice_var.set(matched[0] if matched else voice)
        self._refresh_voice_desc()
        for key, var in (("rate", self.rate_var), ("volume", self.volume_var), ("pitch", self.pitch_var)):
            if key in cfg:
                var.set(cfg[key])
                # 同步滑块
                scale = {"rate": self.rate_scale, "volume": self.volume_scale,
                         "pitch": self.pitch_scale}[key]
                unit = "Hz" if key == "pitch" else "%"
                try:
                    scale.set(int(re.sub(r"[^\d+-]", "", cfg[key])))
                except (ValueError, TypeError):
                    var.set(f"{0:+d}{unit}")
        if "filename" in cfg:
            self.filename_var.set(cfg["filename"])
        if "outdir" in cfg and os.path.isdir(cfg["outdir"]):
            self.outdir_var.set(cfg["outdir"])

    def _on_close(self):
        self._save_config()
        self.destroy()


def main():
    App().mainloop()


if __name__ == "__main__":
    main()