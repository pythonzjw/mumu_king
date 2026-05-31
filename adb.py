"""
ADB 客户端封装
- subprocess 调 adb.exe，截图 / 点击 / 在线检查
- 写死走 config.ADB_PATH（默认 MuMu 自带 adb.exe）避免 server 版本冲突
- 每个 AdbClient 绑定一个 serial（127.0.0.1:port），多实例互不干扰
- Windows 下所有 subprocess 加 CREATE_NO_WINDOW 隐藏 cmd 黑窗
"""
import subprocess
import sys
import numpy as np
import cv2

# Windows 下隐藏 subprocess 弹出的 cmd 黑窗；其他平台是 0（无效果）
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


class AdbError(RuntimeError):
    """adb 命令失败 / 截图解码失败 / 设备离线，由 worker 捕获"""
    pass


class AdbClient:
    def __init__(self, adb_path, serial):
        self.adb_path = adb_path
        self.serial = serial

    def _run(self, args, capture_binary=False, timeout=5):
        """调 adb 子进程；capture_binary=True 用于 screencap（stdout 是 PNG 字节流）"""
        cmd = [self.adb_path] + args
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout,
                creationflags=_NO_WINDOW,
                # capture_binary 时不能 text=True，stdout 必须是 bytes
            )
        except FileNotFoundError:
            raise AdbError(f"找不到 adb.exe: {self.adb_path}")
        except subprocess.TimeoutExpired:
            raise AdbError(f"adb 超时: {' '.join(args)}")
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", errors="ignore").strip()
            raise AdbError(f"adb 失败 ({' '.join(args)}): {err}")
        return proc.stdout if capture_binary else proc.stdout.decode("utf-8", errors="ignore")

    def screencap(self):
        """截图 → BGR numpy array"""
        png_bytes = self._run(
            ["-s", self.serial, "exec-out", "screencap", "-p"],
            capture_binary=True,
            timeout=8,
        )
        if not png_bytes:
            raise AdbError(f"{self.serial} 截图为空")
        arr = np.frombuffer(png_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise AdbError(f"{self.serial} 截图解码失败")
        return img

    def tap(self, x, y):
        """点击 (x, y)，坐标基于截图分辨率（与设备分辨率一致）"""
        self._run(
            ["-s", self.serial, "shell", "input", "tap", str(int(x)), str(int(y))],
            timeout=5,
        )

    def swipe(self, x1, y1, x2, y2, duration_ms=400):
        """滑动 (x1,y1) → (x2,y2)，duration_ms 毫秒"""
        self._run(
            ["-s", self.serial, "shell", "input", "swipe",
             str(int(x1)), str(int(y1)),
             str(int(x2)), str(int(y2)),
             str(int(duration_ms))],
            timeout=5,
        )

    def is_alive(self):
        """检查 self.serial 是否在 adb devices 列表中且 device 状态"""
        out = self._run(["devices"], timeout=5)
        for line in out.splitlines():
            line = line.strip()
            if line.startswith(self.serial) and "device" in line.split():
                return True
        return False


def start_server(adb_path):
    """启动 adb server（避免后续命令各自首次启动竞争）"""
    try:
        subprocess.run(
            [adb_path, "start-server"],
            capture_output=True,
            timeout=10,
            creationflags=_NO_WINDOW,
        )
    except FileNotFoundError:
        raise AdbError(f"找不到 adb.exe: {adb_path}")
    except subprocess.TimeoutExpired:
        raise AdbError("adb start-server 超时")


def connect(adb_path, host_port):
    """adb connect 127.0.0.1:{port}；失败/超时静默返回 False（端口可能没开）"""
    try:
        proc = subprocess.run(
            [adb_path, "connect", host_port],
            capture_output=True,
            timeout=3,
            text=True,
            creationflags=_NO_WINDOW,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        # adb connect 成功输出 "connected to ..." 或 "already connected"
        return "connected" in out.lower()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_device_id(adb_path, serial):
    """用 adb -s serial shell getprop 拿设备真实硬件 ID（用于合并指向同一设备的多个 serial）。
    依次试 ro.serialno / ro.boot.serialno / ro.product.cpu.abi+ro.build.fingerprint，都拿不到返回 ""。
    """
    for prop in ("ro.serialno", "ro.boot.serialno", "ro.build.fingerprint"):
        try:
            proc = subprocess.run(
                [adb_path, "-s", serial, "shell", "getprop", prop],
                capture_output=True, timeout=3, text=True,
                creationflags=_NO_WINDOW,
            )
            val = (proc.stdout or "").strip()
            if val:
                return val
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return ""
    return ""


def list_devices(adb_path):
    """返回 adb devices 列表中所有 'device' 状态的 serial"""
    try:
        proc = subprocess.run(
            [adb_path, "devices"],
            capture_output=True,
            timeout=5,
            text=True,
            creationflags=_NO_WINDOW,
        )
    except FileNotFoundError:
        raise AdbError(f"找不到 adb.exe: {adb_path}")
    except subprocess.TimeoutExpired:
        raise AdbError("adb devices 超时")
    serials = []
    for line in proc.stdout.splitlines()[1:]:  # 跳过表头 "List of devices attached"
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            serials.append(parts[0])
    return serials
