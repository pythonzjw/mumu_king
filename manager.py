"""
多实例协调器
- 启动前 adb start-server + 检查每个端口在线
- 每个端口起一个 Worker daemon 线程
- 统一处理 stop
"""
import threading

from adb import AdbClient, start_server, list_devices, AdbError
from worker import Worker


class BotManager:
    def __init__(self, adb_path, ports, skill_priority, log_fn, debug=False):
        self.adb_path = adb_path
        self.ports = list(ports)
        self.skill_priority = list(skill_priority)
        self.log_fn = log_fn
        self.debug = debug
        self.workers = []
        self.threads = []

    def _log(self, msg):
        self.log_fn(f"[manager] {msg}")

    def start(self):
        """启动所有 worker。返回成功启动的端口列表"""
        try:
            start_server(self.adb_path)
        except AdbError as e:
            self._log(f"adb start-server 失败: {e}")
            return []

        try:
            online = set(list_devices(self.adb_path))
        except AdbError as e:
            self._log(f"adb devices 失败: {e}")
            return []

        self._log(f"在线设备: {sorted(online)}")
        started = []
        for port in self.ports:
            serial = port if ":" in str(port) else f"127.0.0.1:{port}"
            if serial not in online:
                self._log(f"跳过离线端口: {serial}")
                continue
            client = AdbClient(self.adb_path, serial)
            worker = Worker(
                adb_client=client,
                name=serial,
                log_fn=self.log_fn,
                skill_priority=self.skill_priority,
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
