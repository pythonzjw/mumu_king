"""
全局配置（540×960 分辨率）
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

# MuMu 12 默认 ADB 端口候选：16384 起，每多一个实例 +32
MUMU_CANDIDATE_PORTS = [16384, 16416, 16448, 16480, 16512, 16544, 16576, 16608]

# === 延迟配置（秒） ===
LOOP_INTERVAL = 1.0          # 主循环每次截图间隔（从 0.5 调到 1.0 降频减负载）
BATTLE_WAIT = 2.0            # 战斗中等待
ENTER_WAIT = 1.5             # 点进入按钮后等加载
SETTLE_WAIT = 1.0            # 点结算确定后等
SETTLE_DOUBLE_KW   = "双倍"  # 结算页双倍奖励按钮关键字
SETTLE_DOUBLE_ROI  = (100, 780, 280, 880)  # 左下双倍按钮搜索区
SETTLE_DOUBLE_WAIT = 1.0     # 点双倍后等是否进广告
SKILL_SELECT_DELAY = 0.3     # 技能选择后延迟

# === 图像识别配置 ===
MATCH_THRESHOLD = 0.8        # 模板匹配阈值（0~1，越高越严格）
# PERFECT_CLEAR 单独阈值
# 模板取「100% 圆点黑实心 + 通关奖励」整两行字
# - 未通关页文字相同只是圆点白空心 → 0.88（不能误识）
# - 3 宝箱全领（绿勾覆盖）状态 → 0.945（v0.5.15 必须能识别，否则卡关）
# 0.93 落在中间，离两端各 ~0.05 安全距离
PERFECT_CLEAR_THRESHOLD = 0.93

# === 游戏状态枚举（字符串，便于日志可读）===
class GameState:
    HOME = "HOME"                  # 主页/进入战斗按钮可见
    BATTLE = "BATTLE"              # 战斗进行中
    SKILL_SELECT = "SKILL_SELECT"  # 技能选择弹窗
    SETTLE = "SETTLE"              # 战斗胜利/失败的「确定」按钮（同位置同样式）
    PERFECT_CLEAR = "PERFECT_CLEAR"  # 完美通关页（红色「完美通关」印章 + 3 个金边宝箱）
    REWARD_POPUP = "REWARD_POPUP"  # 「获得奖励」金字（结算 + 宝箱奖励 通用）
    BUY_STAMINA = "BUY_STAMINA"    # 体力不足时的「购买体力」弹窗
    WHEEL = "WHEEL"                # 战斗中击杀 boss 后的轮盘选技能弹窗
    AD = "AD"                      # 广告页（右上角有「X 秒｜跳过」/「关闭」）
    UNKNOWN = "UNKNOWN"

# === 默认技能优先级（substring 匹配，越靠前越优先）===
DEFAULT_SKILL_PRIORITY = [
    "解锁冰锥", "解锁电磁网", "分裂", "首次",
    "冰锥", "冰霜", "额外", "爆炸",
    "滚木", "火球", "聚焦", "伤害", "穿透",
]

# === 技能卡 OCR ROI（540×960 基准，OCR 实测：3 张卡顶部 y=342，x ≈ 95/270/444）===
SKILL_CARD_ROIS = [
    (42,  322, 162, 667),   # 左卡
    (200, 322, 340, 667),   # 中卡
    (380, 322, 510, 667),   # 右卡
]

# === 完美通关页：模板识别 + 点 3 个宝箱 ===
# 3 个宝箱中心点（540×960，原 1080 是 (295,990)/(525,990)/(755,990)，等比缩放再校）
CHEST_POSITIONS = [
    (148, 495),    # 左宝箱
    (263, 495),    # 中宝箱
    (378, 495),    # 右宝箱
]
CHEST_WAIT = 1.8   # 1.0 → 1.8：等中间宝箱弹奖励的动画延迟，避免下一轮太早跳过
# 「获得奖励」弹窗外的安全点击点
# v0.5.17：(270, 30) 在账号栏 hero 头像/用户名上方，多次点可能误打开账号面板
# 改到右上角 uid 右上的空白角落：uid:19414744 实测覆盖 (400-516, 18-36)
# (525, 8) 在 uid 右边 + 上方边角，离任何可点元素 ≥10px，绝对安全
REWARD_OUTSIDE = (525, 8)
# 完美通关三宝箱处理完后的左滑：从 (x1,y1) 滑到 (x2,y2)，毫秒
SWIPE_LEFT_FROM = (450, 480)
SWIPE_LEFT_TO = (90, 480)
SWIPE_LEFT_DURATION_MS = 400

# === 左上角体力数字 OCR ROI（"5/33" 格式，OCR 实测中心 (191, 66)）===
STAMINA_ROI = (140, 40, 240, 90)
# 体力为 0 时等待时间（秒）：30 分钟
STAMINA_ZERO_WAIT_SECONDS = 2 * 3600   # 2 小时（30 分钟 → 2 小时）

# === 底部 tab 坐标（540 宽 / 5 等分，y=945 实测）===
TAB_SHOP = (54, 945)
TAB_EQUIPMENT = (162, 945)
TAB_BATTLE = (270, 945)
TAB_CASTLE = (378, 945)
TAB_CHALLENGE = (486, 945)

# === 装备页按钮（OCR 实测 图 08）===
ONE_KEY_UPGRADE_BTN = (339, 836)   # 「一键升级」按钮 — 新增
ONE_KEY_MERGE_BTN   = (463, 836)   # 「一键合成」按钮
MERGE_BTN           = (466, 672)   # 一键合成弹窗内的「合成」按钮
# 「一键升级」弹窗内的「确定」OCR 实测 (395, 556) — 但用 OCR 找更稳，不固定坐标
# 各步等待
TAB_SWITCH_WAIT     = 1.5
MERGE_DIALOG_WAIT   = 1.5
MERGE_REWARD_WAIT   = 2.0
UPGRADE_DIALOG_WAIT = 1.0
UPGRADE_CONFIRM_KW  = "确定"
UPGRADE_CONFIRM_ROI = (250, 500, 540, 610)   # 弹窗中下区域

# === 红点检测（底部 tab 上方红色感叹号）===
REDOT_TPL = "redot.png"
REDOT_MATCH_THRESHOLD = 0.75
# HSV 实测红点中心：SHOP(95,871) / EQUIPMENT(203,871) / CASTLE(419,871)，皆 25×25
# ROI 给 ±25px 容差
REDOT_ROIS = {
    "SHOP":           (70,  850, 130, 905),
    "EQUIPMENT":      (178, 850, 238, 905),
    "CASTLE":         (394, 850, 454, 905),
    # HOME 顶部图标红点不在这里：用 recognizer.find_home_icon 模板匹配带红 ! 的图标
}

# === 商店日常 ===
SHOP_ENTER_WAIT         = 1.5
# OCR 扫「免费」范围（避顶部账号栏 y<90、底部 tab 栏 y>875）
SHOP_OCR_ROI            = (0, 90, 540, 875)
SHOP_SWIPE_UP_FROM      = (270, 750)
SHOP_SWIPE_UP_TO        = (270, 300)
SHOP_SWIPE_DURATION_MS  = 600
SHOP_MAX_SWIPE          = 12
# 连续 N 次上滑都没新「免费」才退商店（容忍金币商城/资源商城屏 OCR 抖动）
SHOP_MAX_EMPTY_SWIPE    = 3
# 进商店后先下滑 N 次重置到顶部（游戏切 tab 不会自动滚顶）
SHOP_RESET_TO_TOP_TIMES = 4
SHOP_SWIPE_DOWN_FROM    = (270, 300)
SHOP_SWIPE_DOWN_TO      = (270, 750)
SHOP_KEYWORD_FREE       = "免费"
SHOP_AD_BLOCKLIST       = ("立即下载", "下载详情", "安装")
SHOP_AFTER_TAP_WAIT     = 1.5
SHOP_REWARD_CLOSE_WAIT  = 0.6
SHOP_CONFIRM_KW         = "确定"
SHOP_CONFIRM_ROI        = (125, 550, 415, 700)   # 屏幕中下区域，「确定」按钮位置
SHOP_CONFIRM_POLL       = 3   # 6 → 3 缩短轮询，更快兜底点空白（适配「无确定按钮」礼包变种）

# === 城堡日常 ===
CASTLE_ENTER_WAIT        = 1.5
# 「获取秘卷」按钮搜索区（OCR 实测 图 9 命中 (193, 694)）
CASTLE_GET_SCROLL_ROI    = (30, 650, 300, 770)
CASTLE_GET_SCROLL_KW     = "秘卷"
# 「秘研」按钮搜索区（OCR 实测 图 9 命中 (361, 695)）
CASTLE_MIYAN_BTN_ROI     = (280, 650, 510, 770)
CASTLE_MIYAN_BTN_KW      = "秘研"
# 进城堡后的左上「秘研」图标搜索区（OCR 实测 图 11 命中 (52, 191)）
CASTLE_MIYAN_ICON_ROI    = (0, 125, 125, 250)
CASTLE_POPUP_WAIT        = 1.2
# 「点击屏幕继续」提示搜索区
CASTLE_CONTINUE_HINT_ROI = (0, 725, 540, 850)
CASTLE_CONTINUE_HINT     = "点击屏幕继续"
CASTLE_CONTINUE_POLL     = 8
SCREEN_CENTER            = (270, 480)

# === 广告子流程 ===
# 「关闭/跳过」OCR 扫描区。实测两种样式：
#   小按钮在 (492, 62)（早期广告）；大按钮在 (313, 189) 附近（图 23/24 那种大椭圆）
# ROI 扩大到覆盖两种位置
ADS_SKIP_ROI         = (160, 40, 540, 250)
ADS_KEYWORDS         = ("关闭",)   # 只识别关闭，跳过阶段不动以确保奖励发放
# 超时兜底坐标：依次试小按钮 + 大按钮位置
ADS_FALLBACK_TAPS    = [(492, 62), (400, 185)]
ADS_TIMEOUT_SEC      = 60
ADS_POLL_INTERVAL    = 1.0
ADS_AFTER_CLOSE_WAIT = 1.5

# === Boss 轮盘弹窗底部「跳过」按钮（OCR 实测 (264, 905)）===
WHEEL_SKIP_BTN       = (264, 905)

# === AD 广告页识别（detect_state 末尾兜底 OCR）===
# 右上角小 ROI 找以下关键字任一命中 → 视为广告页
AD_DETECT_ROI        = (160, 40, 540, 250)         # 跟 ADS_SKIP_ROI 共用
AD_DETECT_KEYWORDS   = ("跳过", "关闭")            # 单字「秒」太通用，不用


# === UNKNOWN 主动脱困 ===
UNKNOWN_RESCUE_OCR_AT    = 3
UNKNOWN_RESCUE_TAB_DELTA = 3
UNKNOWN_RESCUE_KEYWORDS  = ("确定", "关闭", "取消", "我知道了", "返回", "跳过")
UNKNOWN_RESCUE_ROI       = (0, 90, 540, 875)

# === HOME 顶部图标入口（坐标由 recognizer.find_home_icon 动态返回，不写死） ===

# === 战令日常 ===
BATTLE_ORDER_WALL_TAB        = (175, 194)
BATTLE_ORDER_WALL_REDOT_ROI  = (150, 165, 215, 210)
BATTLE_ORDER_CLAIM_BTN       = (430, 912)
BATTLE_ORDER_ENTER_WAIT      = 1.5
BATTLE_ORDER_CLAIM_WAIT      = 0.8

# === 活动日常 ===
ACTIVITY_CLAIM_ROI    = (300, 200, 540, 875)
ACTIVITY_CLAIM_KW     = "领取"
ACTIVITY_ENTER_WAIT   = 1.5
ACTIVITY_AFTER_CLAIM  = 0.8

# === 限时活动日常 ===
TIMED_ACTIVITY_SIGN_KW    = "签到"
TIMED_ACTIVITY_SIGN_ROI   = (300, 240, 540, 875)
TIMED_ACTIVITY_ENTER_WAIT = 1.5
TIMED_ACTIVITY_AFTER_SIGN = 0.8
# 找不到签到时下滑找：从 (270, 700) 滑到 (270, 300)，最多 5 次
TIMED_ACTIVITY_SCROLL_FROM     = (270, 700)
TIMED_ACTIVITY_SCROLL_TO       = (270, 300)
TIMED_ACTIVITY_SCROLL_DUR_MS   = 400
TIMED_ACTIVITY_SCROLL_TIMES    = 5

# === 七日狂欢日常 ===
SEVEN_DAY_CHALLENGE_TAB       = (190, 285)
SEVEN_DAY_GIFT_TAB            = (360, 285)
# 实测 sub-tab 右上小红点位置：挑战 (247, 273) / 好礼 (415, 273)
SEVEN_DAY_CHALLENGE_REDOT_ROI = (220, 260, 280, 295)
SEVEN_DAY_GIFT_REDOT_ROI      = (390, 260, 450, 295)
SEVEN_DAY_CLAIM_ROI           = (300, 280, 540, 875)
SEVEN_DAY_CLAIM_KW            = "领取"
SEVEN_DAY_FREE_ROI            = (300, 280, 540, 560)
SEVEN_DAY_FREE_KW             = "免费"
SEVEN_DAY_ENTER_WAIT          = 1.5
SEVEN_DAY_AFTER_TAP           = 0.8

# === 城堡工坊日常 ===
WORKSHOP_TAB_BTN             = (265, 838)
WORKSHOP_FASHI_TAB_BTN       = (85, 838)
WORKSHOP_COLLECT_TPL         = "workshop_collect_btn.png"
WORKSHOP_UPGRADE_KW          = "升级"
WORKSHOP_UPGRADE_ROI         = (0, 380, 220, 875)
WORKSHOP_CONFIRM_ROI         = (300, 610, 540, 710)
WORKSHOP_CONFIRM_KW          = "确定"
WORKSHOP_RESET_TO_TOP_TIMES  = 3
WORKSHOP_SCROLL_DOWN_FROM    = (270, 450)
WORKSHOP_SCROLL_DOWN_TO      = (270, 700)
WORKSHOP_SCROLL_UP_FROM      = (270, 700)
WORKSHOP_SCROLL_UP_TO        = (270, 450)
WORKSHOP_SCROLL_DUR_MS       = 400
WORKSHOP_SCROLL_TIMES        = 5
WORKSHOP_ENTER_WAIT          = 1.2
WORKSHOP_AFTER_UPGRADE       = 1.0
WORKSHOP_POPUP_WAIT          = 1.5
WORKSHOP_AFTER_COLLECT       = 0.8

# === debug 截图环形覆盖 ===
DEBUG_MAX_STEP_FILES     = 5000
