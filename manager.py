"""
多实例协调器
- 启动前 adb start-server + 检查每个 serial 在线
- 每个 serial 起一个 Worker daemon 线程
- 统一处理 stop
"""
import threading

from adb import AdbClient, start_server, connect, AdbError
from worker import Worker


class BotManager:
    def __init__(self, adb_path, serials, skill_priority, log_fn, debug=False,
                 banned_skill_keywords=None):
        self.adb_path = adb_path
        # 保留 serials 字段名；接受任意格式（127.0.0.1:16384 / emulator-5554 / 313d4194）
        self.serials = list(serials)
        self.skill_priority = list(skill_priority)
        self.banned_skill_keywords = list(banned_skill_keywords or [])
        self.log_fn = log_fn
        self.debug = debug
        self.workers = []
        self.threads = []

    def _log(self, msg):
        self.log_fn(f"[manager] {msg}")

    def start(self):
        """启动所有 worker。返回成功启动的 serial 列表。
        不再跑 adb devices 拉全设备列表（避免影响雷电/手机等其他 adb 用户）；
        每个 MuMu serial 用 adb connect 试一次，连上就启动 worker。"""
        try:
            start_server(self.adb_path)
        except AdbError as e:
            self._log(f"adb start-server 失败: {e}")
            return []

        started = []
        for serial in self.serials:
            serial = str(serial).strip()
            if not serial:
                continue
            # 只对 127.0.0.1:port 形式的 serial 主动 connect；其他形式直接尝试
            if serial.startswith("127.0.0.1:"):
                if not connect(self.adb_path, serial):
                    self._log(f"跳过连不上的设备: {serial}")
                    continue
            client = AdbClient(self.adb_path, serial)
            worker = Worker(
                adb_client=client,
                name=serial,
                log_fn=self.log_fn,
                skill_priority=self.skill_priority,
                banned_skill_keywords=self.banned_skill_keywords,
                debug=self.debug,
            )
            t = threading.Thread(target=worker.run, daemon=True)
            t.start()
            self.workers.append(worker)
            self.threads.append(t)
            started.append(serial)
        self._log(f"已启动 {len(started)} 个实例: {started}")
        return started

    def stop(self):
        """停止所有 worker"""
        for w in self.workers:
            w.running = False
        # 不强制 join，留给上层决定是否等
        self._log("已通知所有 worker 停止")

    def is_running(self):
        return any(t.is_alive() for t in self.threads)
