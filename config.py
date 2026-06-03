"""
全局配置（540×960 最简版 main-simple）

只做：战斗循环 + 选技能 + 体力不足等 30 分钟
不做：红点日常 / 商店 / 装备升级合成 / 城堡秘研 / 完美通关 / 广告
"""
import os
import sys

if getattr(sys, "frozen", False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

# === ADB 配置 ===
import os as _os

ADB_PATH_CANDIDATES = [
    r"C:\Program Files\Netease\MuMuPlayer-12.0\shell\adb.exe",
    r"C:\Program Files\Netease\MuMu\nx_main\adb.exe",
    r"C:\Program Files\MuMuPlayer\nx_main\adb.exe",
    r"E:\应用\工具\MuMuPlayer\nx_main\adb.exe",
    r"D:\Program Files\Netease\MuMuPlayer-12.0\shell\adb.exe",
    r"D:\MuMuPlayer\nx_main\adb.exe",
]


def _find_adb():
    for p in ADB_PATH_CANDIDATES:
        if _os.path.exists(p):
            return p
    return ADB_PATH_CANDIDATES[0]


ADB_PATH = _find_adb()
MUMU_CANDIDATE_PORTS = [16384, 16416, 16448, 16480, 16512, 16544, 16576, 16608]

# === 延迟配置（秒） ===
LOOP_INTERVAL = 1.0
BATTLE_WAIT = 2.0
ENTER_WAIT = 1.5
SKILL_SELECT_DELAY = 0.3

# === 图像识别 ===
MATCH_THRESHOLD = 0.8

# === 游戏状态枚举 ===
class GameState:
    HOME = "HOME"
    BATTLE = "BATTLE"
    SKILL_SELECT = "SKILL_SELECT"
    REWARD_POPUP = "REWARD_POPUP"   # 金色「获得奖励」金字（结算 + 宝箱 通用）
    BUY_STAMINA = "BUY_STAMINA"
    WHEEL = "WHEEL"
    UNKNOWN = "UNKNOWN"

# === 默认技能优先级 ===
DEFAULT_SKILL_PRIORITY = [
    "解锁冰锥", "解锁电磁网", "分裂", "首次",
    "冰锥", "冰霜", "额外", "爆炸",
    "滚木", "火球", "聚焦", "伤害", "穿透",
]

# === 技能卡 OCR ROI（540×960）===
SKILL_CARD_ROIS = [
    (42,  322, 162, 667),
    (200, 322, 340, 667),
    (380, 322, 510, 667),
]

# === 「获得奖励」弹窗外的安全点击点 ===
REWARD_OUTSIDE = (270, 200)

# === 左上角体力 OCR ROI（"5/33" 格式）===
STAMINA_ROI = (140, 40, 240, 90)
STAMINA_ZERO_WAIT_SECONDS = 30 * 60   # 体力为 0 等 30 分钟

# === debug 截图环形覆盖 ===
DEBUG_MAX_STEP_FILES = 5000
