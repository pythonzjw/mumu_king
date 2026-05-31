"""
入口
- 默认 GUI
- --nogui 命令行模式：python main.py --nogui --ports=16384,16416 --priority="A,B" --debug
"""
import sys
import time

from config import ADB_PATH, DEFAULT_SKILL_PRIORITY


def _parse_args():
    args = {
        "nogui": False,
        "ports": [],
        "priority": list(DEFAULT_SKILL_PRIORITY),
        "debug": False,
        "adb": ADB_PATH,
    }
    for a in sys.argv[1:]:
        if a == "--nogui":
            args["nogui"] = True
        elif a == "--debug":
            args["debug"] = True
        elif a.startswith("--ports="):
            ports = [s.strip() for s in a.split("=", 1)[1].split(",") if s.strip()]
            args["ports"] = [p if ":" in p else f"127.0.0.1:{p}" for p in ports]
        elif a.startswith("--priority="):
            text = a.split("=", 1)[1]
            args["priority"] = [s.strip() for s in text.split(",") if s.strip()]
        elif a.startswith("--adb="):
            args["adb"] = a.split("=", 1)[1]
    return args


def run_nogui(args):
    if not args["ports"]:
        print("--nogui 模式必须指定 --ports=端口1,端口2,...")
        sys.exit(1)

    from manager import BotManager

    def log_fn(msg):
        print(msg)

    manager = BotManager(
        adb_path=args["adb"],
        ports=args["ports"],
        skill_priority=args["priority"],
        log_fn=log_fn,
        debug=args["debug"],
    )
    started = manager.start()
    if not started:
        print("启动失败，没有可用实例")
        sys.exit(1)

    try:
        while manager.is_running():
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n收到中断，停止")
        manager.stop()
        for t in manager.threads:
            t.join(timeout=5)


def main():
    args = _parse_args()
    if args["nogui"]:
        run_nogui(args)
    else:
        from gui import App
        App().run()


if __name__ == "__main__":
    main()
