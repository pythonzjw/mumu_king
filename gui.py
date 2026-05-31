"""
tkinter GUI
- adb 路径 / 端口列表 / 技能优先级 / debug 开关
- 多路日志合并显示
"""
import tkinter as tk
from tkinter import scrolledtext
import threading

from config import ADB_PATH, DEFAULT_SKILL_PRIORITY


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("MuMu 多开战斗自动化")
        self.root.geometry("680x720")
        self.root.resizable(False, False)
        self.manager = None
        self._build_ui()

    def _build_ui(self):
        # adb 路径
        f1 = tk.Frame(self.root, padx=10)
        f1.pack(fill="x", pady=(10, 5))
        tk.Label(f1, text="adb.exe 路径:").pack(anchor="w")
        self.adb_var = tk.StringVar(value=ADB_PATH)
        tk.Entry(f1, textvariable=self.adb_var).pack(fill="x", pady=2)

        # 端口列表（多行）
        f2 = tk.Frame(self.root, padx=10)
        f2.pack(fill="x", pady=(0, 5))
        tk.Label(f2, text="MuMu 端口（每行一个，例 127.0.0.1:16384 或仅写 16384）:").pack(anchor="w")
        self.ports_text = tk.Text(f2, height=4, font=("Consolas", 10))
        self.ports_text.insert("1.0", "127.0.0.1:16384\n")
        self.ports_text.pack(fill="x", pady=2)

        # 技能优先级（默认值预填，可随时改）
        f3 = tk.Frame(self.root, padx=10)
        f3.pack(fill="x", pady=(0, 5))
        tk.Label(f3, text="技能优先级（逗号分隔，越前越优先）:").pack(anchor="w")
        self.priority_var = tk.StringVar(value=", ".join(DEFAULT_SKILL_PRIORITY))
        tk.Entry(f3, textvariable=self.priority_var).pack(fill="x", pady=2)

        # 控制按钮 + debug
        f4 = tk.Frame(self.root, padx=10)
        f4.pack(fill="x", pady=5)
        self.btn_start = tk.Button(
            f4, text="开始", command=self._start, width=10, bg="#4CAF50", fg="white",
        )
        self.btn_start.pack(side="left", padx=(0, 10))
        self.btn_stop = tk.Button(
            f4, text="停止", command=self._stop, width=10, state="disabled",
        )
        self.btn_stop.pack(side="left", padx=(0, 10))
        self.debug_var = tk.BooleanVar(value=False)
        tk.Checkbutton(f4, text="调试模式（保存每步截图）", variable=self.debug_var).pack(side="left")

        # 状态
        f5 = tk.Frame(self.root, padx=10)
        f5.pack(fill="x", pady=5)
        self.status_label = tk.Label(f5, text="状态: 就绪", anchor="w")
        self.status_label.pack(side="left")

        # 日志
        f6 = tk.LabelFrame(self.root, text="运行日志", padx=5, pady=5)
        f6.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.log_text = scrolledtext.ScrolledText(
            f6, state="disabled", font=("Consolas", 9), wrap="word",
        )
        self.log_text.pack(fill="both", expand=True)

    def _append_log(self, text):
        """线程安全日志注入"""
        def _do():
            self.log_text.config(state="normal")
            self.log_text.insert("end", text + "\n")
            self.log_text.see("end")
            self.log_text.config(state="disabled")
        self.root.after(0, _do)

    def _set_status(self, text):
        self.root.after(0, lambda: self.status_label.config(text=f"状态: {text}"))

    def _parse_ports(self):
        """读 ports_text，返回 ['127.0.0.1:16384', ...]"""
        raw = self.ports_text.get("1.0", "end").strip().splitlines()
        result = []
        for line in raw:
            line = line.strip()
            if not line:
                continue
            if ":" not in line:
                line = f"127.0.0.1:{line}"
            result.append(line)
        return result

    def _start(self):
        adb_path = self.adb_var.get().strip()
        ports = self._parse_ports()
        if not ports:
            self._append_log("[gui] 端口列表为空")
            return
        priority_text = self.priority_var.get().strip()
        if priority_text:
            priority = [s.strip() for s in priority_text.split(",") if s.strip()]
        else:
            priority = list(DEFAULT_SKILL_PRIORITY)

        from manager import BotManager
        self.manager = BotManager(
            adb_path=adb_path,
            ports=ports,
            skill_priority=priority,
            log_fn=self._append_log,
            debug=self.debug_var.get(),
        )

        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self._set_status("启动中...")

        threading.Thread(target=self._run_manager, daemon=True).start()

    def _run_manager(self):
        try:
            started = self.manager.start()
            if not started:
                self._set_status("启动失败")
                self.root.after(0, self._on_stopped)
                return
            self._set_status(f"运行中 ({len(started)} 个)")
        except Exception as e:
            self._append_log(f"[gui] 启动异常: {e}")
            self._set_status("启动异常")
            self.root.after(0, self._on_stopped)

    def _stop(self):
        if self.manager:
            self.manager.stop()
            self._set_status("正在停止...")
            # 等线程退出再恢复按钮
            threading.Thread(target=self._wait_stop, daemon=True).start()

    def _wait_stop(self):
        if self.manager:
            for t in self.manager.threads:
                t.join(timeout=5)
        self.root.after(0, self._on_stopped)

    def _on_stopped(self):
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self._set_status("已停止")

    def run(self):
        self.root.mainloop()
