"""
tkinter GUI
- adb 路径 / 设备扫描 + 勾选 / 技能优先级 / debug 开关
- 多路日志合并显示
"""
import re
import tkinter as tk
from tkinter import scrolledtext, messagebox
import threading

from config import ADB_PATH, DEFAULT_SKILL_PRIORITY, MUMU_CANDIDATE_PORTS
import settings


# 设备分类规则
# MuMu Player 12: 127.0.0.1:16384 / 16416 / 16448 ...
# 其他模拟器（雷电/夜神/逍遥/MuMu 6 老 emulator-console）: emulator-XXXX 或其他端口
# 物理设备：纯字母数字 ID（如 313d4194）
_RE_LOOPBACK = re.compile(r"^127\.0\.0\.1:(\d+)$")
_MUMU_TCP_PORTS = set(MUMU_CANDIDATE_PORTS)


def classify_serial(serial):
    """返回 ('mumu' | 'emulator' | 'physical', 是否默认勾选, 备注文字)"""
    s = serial.strip()
    m = _RE_LOOPBACK.match(s)
    if m:
        port = int(m.group(1))
        if port in _MUMU_TCP_PORTS:
            return "mumu", True, ""
        return "emulator", False, ""
    if s.startswith("emulator-"):
        # 雷电 / 夜神 / MuMu 6 老 emulator-console 都长这样
        # 默认不勾，警告用户这通常不是 MuMu 12
        return "emulator", False, "⚠ 通常是雷电/夜神，不是 MuMu 12"
    return "physical", False, ""


CATEGORY_LABEL = {
    "mumu": "MuMu 模拟器",
    "emulator": "其他模拟器 / 老 MuMu",
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
        # 加载持久化设置（不存在则空 dict）
        self.settings = settings.load()
        self._build_ui()
        self._restore_from_settings()

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

    def _restore_from_settings(self):
        """从 settings 恢复 adb 路径 / 优先级 / debug / 上次勾选过的 serial"""
        if "adb_path" in self.settings:
            self.adb_var.set(self.settings["adb_path"])
        if "priority" in self.settings:
            p = self.settings["priority"]
            if isinstance(p, list) and p:
                self.priority_var.set(", ".join(p))
        if "debug" in self.settings:
            self.debug_var.set(bool(self.settings["debug"]))
        # 上次勾选过的 serial：以"手动加入"方式预填，用户不扫描也能直接开始
        last_serials = self.settings.get("serials", [])
        for s in last_serials:
            if s and s not in self.device_vars:
                var = tk.BooleanVar(value=True)
                self.device_vars[s] = var
                tk.Checkbutton(
                    self.devices_frame, text=f"{s} (上次)", variable=var, anchor="w",
                ).pack(fill="x", padx=15)

    def _save_settings(self):
        """把当前 GUI 状态存到 settings.json"""
        settings.save({
            "adb_path": self.adb_var.get().strip(),
            "priority": [s.strip() for s in self.priority_var.get().split(",") if s.strip()],
            "debug": self.debug_var.get(),
            "serials": self._selected_serials(),
        })

    # ============================================================
    # 设备扫描 + 勾选
    # ============================================================

    def _scan_devices(self):
        """点「扫描」：先 connect MuMu 候选端口让其注册到 adb server，再 adb devices"""
        self.scan_status.config(text="扫描中...", fg="gray")

        def _do():
            adb_path = self.adb_var.get().strip()
            self._append_log(f"[scan] 用 adb: {adb_path}")
            from adb import start_server, list_devices, connect, AdbError
            try:
                start_server(adb_path)
            except AdbError as e:
                self._append_log(f"[scan] start-server 失败: {e}")
                self.root.after(0, lambda: self.scan_status.config(
                    text="adb 路径无效，请改 adb.exe 路径", fg="red"))
                return

            # 主动 connect MuMu 12 默认端口，让它出现在 adb devices 里
            connected = []
            for port in MUMU_CANDIDATE_PORTS:
                hp = f"127.0.0.1:{port}"
                if connect(adb_path, hp):
                    connected.append(hp)
            if connected:
                self._append_log(f"[scan] 已 connect MuMu 端口: {connected}")
            else:
                self._append_log(f"[scan] MuMu 候选端口 {MUMU_CANDIDATE_PORTS} 都连不上（可能 MuMu 没开/端口不在候选）")

            try:
                serials = list_devices(adb_path)
            except AdbError as e:
                self._append_log(f"[scan] adb devices 失败: {e}")
                self.root.after(0, lambda: self.scan_status.config(
                    text=f"扫描失败: {e}", fg="red"))
                return
            self._append_log(f"[scan] 扫到 {len(serials)} 个原始设备: {serials}")

            # 同一物理设备可能以多个 serial 出现（如 MuMu 同时绑 16384 和 7555）
            # 用 ro.serialno 等硬件属性合并，每组留一个最优 serial（优先 MuMu 16384 槽位）
            from adb import get_device_id
            merged = self._merge_duplicate_serials(adb_path, serials, get_device_id)
            if len(merged) != len(serials):
                self._append_log(f"[scan] 合并后 {len(merged)} 个唯一设备: {merged}")
            self.root.after(0, lambda: self._render_devices(merged))

        threading.Thread(target=_do, daemon=True).start()

    def _merge_duplicate_serials(self, adb_path, serials, get_id_fn):
        """同一硬件设备多 serial → 留一个最优。优先级：MuMu 16xxx > 7555 > emulator-* > 其他"""
        def priority(s):
            # 数字越小越优先
            cat, _, _ = classify_serial(s)
            if cat == "mumu":
                m = _RE_LOOPBACK.match(s)
                if m:
                    port = int(m.group(1))
                    return (0, -port)  # 高端口（16xxx）优先
                return (1, 0)
            if cat == "emulator":
                return (2, 0)
            return (3, 0)

        groups = {}  # device_id → [serial,...]
        unknowns = []  # 拿不到 device_id 的（保留原样不合并）
        for s in serials:
            did = get_id_fn(adb_path, s)
            if did:
                groups.setdefault(did, []).append(s)
            else:
                unknowns.append(s)

        result = []
        for did, ss in groups.items():
            ss.sort(key=priority)
            best = ss[0]
            result.append(best)
            if len(ss) > 1:
                self._append_log(f"[scan] 合并 {ss} → 保留 {best}（设备 ID: {did[:20]}）")
        result.extend(unknowns)
        return result

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
            cat, default_check, note = classify_serial(s)
            groups[cat].append((s, default_check, note))

        for cat in ["mumu", "emulator", "physical"]:
            items = groups[cat]
            if not items:
                continue
            color = "red" if cat == "physical" else "black"
            tk.Label(
                self.devices_frame, text=CATEGORY_LABEL[cat],
                anchor="w", fg=color, font=("", 10, "bold"),
            ).pack(fill="x", pady=(4, 0))
            for s, default_check, note in items:
                # 优先用旧勾选；否则用分类默认
                checked = old_checked.get(s, default_check)
                var = tk.BooleanVar(value=checked)
                self.device_vars[s] = var
                row = tk.Frame(self.devices_frame)
                row.pack(fill="x", padx=15)
                tk.Checkbutton(row, text=s, variable=var, anchor="w").pack(side="left")
                if note:
                    tk.Label(row, text=note, fg="red", anchor="w").pack(side="left", padx=(8, 0))

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
        import os
        adb_path = self.adb_var.get().strip()
        if not os.path.exists(adb_path):
            messagebox.showerror(
                "adb.exe 路径无效",
                f"找不到 adb.exe：\n{adb_path}\n\n"
                "请在「adb.exe 路径」里填正确路径（一般是 MuMu 安装目录下的 adb.exe）",
            )
            return
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

        # 持久化当前设置，下次启动自动恢复
        self._save_settings()

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
