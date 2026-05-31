"""
全局配置
"""
import os
import sys

# 项目根目录（兼容 PyInstaller 打包后的路径）
if getattr(sys, "frozen", False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 模板图片目录
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

# === ADB 配置 ===
# 默认用 MuMu 自带 adb.exe，避免与雷电 / Android SDK / 手机调试用的 adb 冲突
# （冲突会触发 server 版本不一致 → kill 重启 → 所有 adb 连接瞬断）
# GUI 可改
ADB_PATH = r"C:\Program Files\Netease\MuMuPlayer-12.0\shell\adb.exe"

# === 延迟配置（秒） ===
LOOP_INTERVAL = 0.5          # 主循环每次截图间隔
BATTLE_WAIT = 2.0            # 战斗中等待
ENTER_WAIT = 1.5             # 点进入按钮后等加载
SETTLE_WAIT = 1.0            # 点结算确定后等
SKILL_SELECT_DELAY = 0.3     # 技能选择后延迟

# === 图像识别配置 ===
MATCH_THRESHOLD = 0.8        # 模板匹配阈值（0~1，越高越严格）

# === 游戏状态枚举（字符串，便于日志可读）===
class GameState:
    HOME = "HOME"                  # 主页/进入战斗按钮可见
    BATTLE = "BATTLE"              # 战斗进行中
    SKILL_SELECT = "SKILL_SELECT"  # 技能选择弹窗
    SETTLE = "SETTLE"              # 战斗结算/确定按钮（含失败页）
    PERFECT_CLEAR = "PERFECT_CLEAR"  # 完美通关页（红色印章 + 三个金边宝箱）
    REWARD_POPUP = "REWARD_POPUP"  # 点宝箱后弹的「获得奖励」弹窗
    UNKNOWN = "UNKNOWN"

# === 默认技能优先级（substring 匹配，越靠前越优先）===
DEFAULT_SKILL_PRIORITY = [
    "冰锥", "冰霜", "电磁网", "额外", "分裂",
    "爆炸", "滚木", "火球", "聚焦", "伤害", "穿透",
]

# === 技能卡 OCR ROI ===
# 3 张卡的位置 (x1, y1, x2, y2)，坐标基于 1080x1920 设备截图分辨率
# ROI 包含黑底白字标题 + 图标 + 描述文字三段，OCR 拼起来与 priority 关键字匹配
SKILL_CARD_ROIS = [
    (85,  645, 325,  1335),  # 左卡
    (420, 645, 660,  1335),  # 中卡
    (755, 645, 995,  1335),  # 右卡
]

# === 完美通关页：三个宝箱中心点（按顺序点击）===
CHEST_POSITIONS = [
    (295, 990),
    (525, 990),
    (755, 990),
]
# 点宝箱后等待时间（秒）：1s 内若没出现 REWARD_POPUP 视为该宝箱未点亮，跳下一个
CHEST_WAIT = 1.0
# 「获得奖励」弹窗外的安全点击点（顶部账号栏下方空白处，避开 tab 栏与按钮）
REWARD_OUTSIDE = (540, 400)
# 完美通关三宝箱处理完后的左滑：从 (x1,y1) 滑到 (x2,y2)，毫秒
SWIPE_LEFT_FROM = (900, 960)
SWIPE_LEFT_TO = (180, 960)
SWIPE_LEFT_DURATION_MS = 400
