"""
tkinter GUI
- adb 路径 / 设备扫描 + 勾选 / 技能优先级 / debug 开关
- 多路日志合并显示
"""
import re
import tkinter as tk
from tkinter import scrolledtext, messagebox
import threading

from config import ADB_PATH, DEFAULT_SKILL_PRIORITY


# 设备分类规则
# MuMu Player 12: 127.0.0.1:16384 / 16416 / 16448 ...
# MuMu Player 6 / X / 老 emulator: emulator-XXXX、127.0.0.1:7555
# 其他模拟器（雷电/夜神/逍遥）: 127.0.0.1:其他端口
# 物理设备：纯字母数字 ID（如 313d4194）
_RE_LOOPBACK = re.compile(r"^127\.0\.0\.1:(\d+)$")
_MUMU_TCP_PORTS = {16384, 16416, 16448, 16480, 16512, 16544, 16576, 16608, 7555}


def classify_serial(serial):
    """返回 ('mumu' | 'emulator' | 'physical', 是否默认勾选)"""
    s = serial.strip()
    m = _RE_LOOPBACK.match(s)
    if m:
        port = int(m.group(1))
        if port in _MUMU_TCP_PORTS:
            return "mumu", True
        return "emulator", False
    if s.startswith("emulator-"):
        # MuMu 12 偶尔也会以 emulator-XXXX 形式出现，归为 mumu 候选但默认不勾，让用户确认
        return "mumu", False
    return "physical", False


CATEGORY_LABEL = {
    "mumu": "MuMu 模拟器",
    "emulator": "其他模拟器",
    "physical": "物理设备（USB 手机等，请谨慎勾选）",
}


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("MuMu 多开战斗自动化")
        self.root.geometry("700x780")
        self.root.resizable(False, False)
        self.manager = None
        # serial → tk.BooleanVar，记录每个设备是否被勾选
        self.device_vars = {}
        self._build_ui()

    def _build_ui(self):
        # adb 路径
        f1 = tk.Frame(self.root, padx=10)
        f1.pack(fill="x", pady=(10, 5))
        tk.Label(f1, text="adb.exe 路径:").pack(anchor="w")
        self.adb_var = tk.StringVar(value=ADB_PATH)
        tk.Entry(f1, textvariable=self.adb_var).pack(fill="x", pady=2)

        # 设备扫描区
        f2 = tk.LabelFrame(self.root, text="设备", padx=8, pady=5)
        f2.pack(fill="x", padx=10, pady=(0, 5))

        f2_top = tk.Frame(f2)
        f2_top.pack(fill="x", pady=(0, 5))
        tk.Button(
            f2_top, text="扫描设备", command=self._scan_devices,
            width=10, bg="#2196F3", fg="white",
        ).pack(side="left")
        self.scan_status = tk.Label(f2_top, text="点「扫描设备」拉取在线设备", fg="gray")
        self.scan_status.pack(side="left", padx=10)

        # 设备列表容器（动态填充三组 checkbox）
        self.devices_frame = tk.Frame(f2)
        self.devices_frame.pack(fill="x")

        # 手动添加（扫描没出现的可在这里加）
        f2_bottom = tk.Frame(f2)
        f2_bottom.pack(fill="x", pady=(8, 0))
        tk.Label(f2_bottom, text="手动添加（serial，例 127.0.0.1:16384）:").pack(anchor="w")
        f2_bot_row = tk.Frame(f2_bottom)
        f2_bot_row.pack(fill="x", pady=2)
        self.manual_var = tk.StringVar()
        tk.Entry(f2_bot_row, textvariable=self.manual_var).pack(side="left", fill="x", expand=True)
        tk.Button(f2_bot_row, text="加入", width=8, command=self._add_manual).pack(side="left", padx=(5, 0))

        # 技能优先级
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

    # ============================================================
    # 设备扫描 + 勾选
    # ============================================================

    def _scan_devices(self):
        """点「扫描」：开线程跑 adb devices，结果回主线程刷新 UI"""
        self.scan_status.config(text="扫描中...", fg="gray")

        def _do():
            adb_path = self.adb_var.get().strip()
            from adb import start_server, list_devices, AdbError
            try:
                start_server(adb_path)
                serials = list_devices(adb_path)
            except AdbError as e:
                self.root.after(0, lambda: self.scan_status.config(
                    text=f"扫描失败: {e}", fg="red"))
                return
            self.root.after(0, lambda: self._render_devices(serials))

        threading.Thread(target=_do, daemon=True).start()

    def _render_devices(self, serials):
        """渲染设备列表（三组 checkbox）。保留旧的勾选状态"""
        old_checked = {s: v.get() for s, v in self.device_vars.items()}

        for w in self.devices_frame.winfo_children():
            w.destroy()
        self.device_vars = {}

        if not serials:
            self.scan_status.config(text="未发现任何设备", fg="orange")
            tk.Label(
                self.devices_frame, anchor="w",
                text="提示：检查 MuMu 是否已开启；若手机连着 USB 调试也会出现在这里",
                fg="gray",
            ).pack(fill="x")
            return

        groups = {"mumu": [], "emulator": [], "physical": []}
        for s in serials:
            cat, default_check = classify_serial(s)
            groups[cat].append((s, default_check))

        for cat in ["mumu", "emulator", "physical"]:
            items = groups[cat]
            if not items:
                continue
            color = "red" if cat == "physical" else "black"
            tk.Label(
                self.devices_frame, text=CATEGORY_LABEL[cat],
                anchor="w", fg=color, font=("", 10, "bold"),
            ).pack(fill="x", pady=(4, 0))
            for s, default_check in items:
                # 优先用旧勾选；否则用分类默认
                checked = old_checked.get(s, default_check)
                var = tk.BooleanVar(value=checked)
                self.device_vars[s] = var
                tk.Checkbutton(
                    self.devices_frame, text=s, variable=var, anchor="w",
                ).pack(fill="x", padx=15)

        self.scan_status.config(
            text=f"发现 {len(serials)} 个设备（已为 MuMu 默认勾选）", fg="green",
        )

    def _add_manual(self):
        """手动添加 serial 到列表（扫描没出现也能加）"""
        s = self.manual_var.get().strip()
        if not s:
            return
        if s in self.device_vars:
            self._append_log(f"[gui] 设备 {s} 已在列表中")
            return
        # 直接加到 devices_frame 下面，不分组
        var = tk.BooleanVar(value=True)
        self.device_vars[s] = var
        tk.Checkbutton(
            self.devices_frame, text=f"{s} (手动)", variable=var, anchor="w",
        ).pack(fill="x", padx=15)
        self.manual_var.set("")

    def _selected_serials(self):
        return [s for s, v in self.device_vars.items() if v.get()]

    # ============================================================
    # 日志 + 状态
    # ============================================================

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

    # ============================================================
    # 启动 / 停止
    # ============================================================

    def _start(self):
        adb_path = self.adb_var.get().strip()
        serials = self._selected_serials()
        if not serials:
            messagebox.showwarning("没有勾选设备", "请先点「扫描设备」并勾选至少一个设备")
            return

        # 物理设备二次确认（避免自动化用户的手机）
        physical = [s for s in serials if classify_serial(s)[0] == "physical"]
        if physical:
            ok = messagebox.askyesno(
                "物理设备警告",
                f"以下设备看起来是物理手机/平板：\n\n{', '.join(physical)}\n\n"
                "脚本会自动点击屏幕，确定要在这些设备上运行吗？",
            )
            if not ok:
                return

        priority_text = self.priority_var.get().strip()
        if priority_text:
            priority = [s.strip() for s in priority_text.split(",") if s.strip()]
        else:
            priority = list(DEFAULT_SKILL_PRIORITY)

        from manager import BotManager
        self.manager = BotManager(
            adb_path=adb_path,
            serials=serials,
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
