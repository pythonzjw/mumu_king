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
# 启动时自动从下面候选里挑第一个存在的；都不存在则用第一个作为提示
# GUI 可改
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
    return ADB_PATH_CANDIDATES[0]  # 都没找到给第一个，让用户看到再手动改


ADB_PATH = _find_adb()

# MuMu 12 默认 ADB 端口候选：16384 起，每多一个实例 +32
# 扫描时只 connect 这些端口（去掉 7555 避免与 16384 重复指向同一台 MuMu）
MUMU_CANDIDATE_PORTS = [16384, 16416, 16448, 16480, 16512, 16544, 16576, 16608]

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
    BUY_STAMINA = "BUY_STAMINA"    # 体力不足时的「购买体力」弹窗
    WHEEL = "WHEEL"                # 战斗中击杀 boss 后的轮盘选技能弹窗（不参与，点空白关闭）
    UNKNOWN = "UNKNOWN"

# === 默认技能优先级（substring 匹配，越靠前越优先）===
DEFAULT_SKILL_PRIORITY = [
    "解锁冰锥", "解锁电磁网", "分裂", "首次",
    "冰锥", "冰霜", "额外", "爆炸",
    "滚木", "火球", "聚焦", "伤害", "穿透",
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

# === 左上角体力数字 OCR ROI（"30/31" 这种）===
STAMINA_ROI = (245, 80, 530, 165)
# 体力为 0 时等待时间（秒）：30 分钟（游戏体力恢复速度）
STAMINA_ZERO_WAIT_SECONDS = 30 * 60

# === 底部 tab 坐标（1080x1920）===
TAB_SHOP = (108, 1840)
TAB_EQUIPMENT = (324, 1840)
TAB_BATTLE = (540, 1840)
TAB_CASTLE = (756, 1840)
TAB_CHALLENGE = (972, 1840)

# === 装备页：「一键合成」按钮 + 弹窗里的「合成」按钮 ===
ONE_KEY_MERGE_BTN = (885, 1700)
MERGE_BTN = (875, 1335)
# 一键合成流程各步等待（秒）
TAB_SWITCH_WAIT = 1.5
MERGE_DIALOG_WAIT = 1.5
MERGE_REWARD_WAIT = 2.0

# === 红点检测（底部 3 个 tab 上方的红色感叹号）===
REDOT_TPL = "redot.png"
# 比主匹配 0.8 略低，小图易抖
REDOT_MATCH_THRESHOLD = 0.75
# 3 个 tab 上方红点位置（已用 HSV 实测：商店红点 (189,1744)、装备 (405,1743)、城堡 (837,1743)，皆约 52×48）
# 每个 ROI 给 120×100 容差，避免分辨率/UI 微抖
REDOT_ROIS = {
    "SHOP":      (160, 1720, 280, 1820),   # 商店 tab 上方
    "EQUIPMENT": (375, 1720, 495, 1820),   # 装备 tab 上方
    "CASTLE":    (805, 1720, 925, 1820),   # 城堡 tab 上方
}

# === 商店日常 ===
SHOP_ENTER_WAIT         = 1.5
# OCR 扫「免费」的范围：去顶部账号栏（y<180）和底部 tab 栏（y>1750）避免误识 tab 文字
SHOP_OCR_ROI            = (0, 180, 1080, 1750)
SHOP_SWIPE_UP_FROM      = (540, 1500)
SHOP_SWIPE_UP_TO        = (540, 600)
SHOP_SWIPE_DURATION_MS  = 600
SHOP_MAX_SWIPE          = 8                # 上滑硬上限，防死循环
SHOP_KEYWORD_FREE       = "免费"
# OCR 整屏命中以下任一关键字视为广告页，本屏不处理
SHOP_AD_BLOCKLIST       = ("立即下载", "下载详情", "安装")
SHOP_AFTER_TAP_WAIT     = 1.5
# 关「获得奖励/确定」弹窗时点空白的等待
SHOP_REWARD_CLOSE_WAIT  = 0.6
# 商店免费抽完，弹「获得奖励」礼包样式弹窗，必须点中间的「确定」按钮才能关
SHOP_CONFIRM_KW         = "确定"
SHOP_CONFIRM_ROI        = (250, 1100, 830, 1400)   # 屏幕中下区域，「确定」按钮常出现位置
SHOP_CONFIRM_POLL       = 6                          # 每次 0.5s 轮询，最多 3s 等弹窗出现

# === 城堡日常 ===
CASTLE_ENTER_WAIT        = 1.5
# 「获取秘卷」按钮搜索区（用户校准后微调），按图 9 估在底部按钮区左半
CASTLE_GET_SCROLL_ROI    = (60,  1380, 600, 1520)
CASTLE_GET_SCROLL_KW     = "获取秘卷"
# 「秘研」按钮搜索区，按图 9 估在底部按钮区右半
CASTLE_MIYAN_BTN_ROI     = (560, 1380, 1020, 1520)
CASTLE_MIYAN_BTN_KW      = "秘研"
# 「点击屏幕继续」提示搜索区
CASTLE_CONTINUE_HINT_ROI = (0, 1450, 1080, 1700)
CASTLE_CONTINUE_HINT     = "点击屏幕继续"
# 等待「点击屏幕继续」最大轮询次数（每次 0.5s）
CASTLE_CONTINUE_POLL     = 8
SCREEN_CENTER            = (540, 960)

# === 广告子流程 ===
# 右上角 OCR 扫描区（图 3/图 4 中「跳过」「关闭」都在这块）
ADS_SKIP_ROI         = (820, 80, 1080, 260)
ADS_KEYWORDS         = ("关闭",)   # 只点关闭；跳过阶段不动，确保奖励发放
# 超时兜底点击坐标（右上角按钮中心估值）
ADS_FALLBACK_TAP     = (950, 180)
ADS_TIMEOUT_SEC      = 60
ADS_POLL_INTERVAL    = 1.0
ADS_AFTER_CLOSE_WAIT = 1.5
