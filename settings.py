"""
GUI 设置持久化：exe 同目录的 settings.json
- adb_path / serials / priority / banned_skill_keywords / debug
- 加载失败/文件缺失静默回退到默认值
"""
import json
import os
import sys


def _settings_path():
    base = (os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
            else os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "settings.json")


def load():
    """读 settings.json；不存在/损坏返回 {}"""
    path = _settings_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save(data):
    """覆写 settings.json；写失败静默忽略（不该因写设置失败影响主流程）"""
    path = _settings_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
