"""
游戏状态识别 + 技能卡 OCR
- 模板匹配：detect_state / find_*_button
- OCR：ocr_skill_cards 识别 3 张技能卡文字
- 模板缺失时抛 RecognizeError，让用户先放图
"""
import os
import threading
from functools import lru_cache

import cv2
import numpy as np

from config import (
    TEMPLATES_DIR, MATCH_THRESHOLD, PERFECT_CLEAR_THRESHOLD, GameState,
    REDOT_TPL, REDOT_ROIS, REDOT_MATCH_THRESHOLD,
    AD_DETECT_ROI, AD_DETECT_KEYWORDS,
    WORKSHOP_COLLECT_TPL,
)

# OCR 全局锁：多 worker 共用 GPU（DirectML）时同时推理会 native 崩溃
# 用锁串行化 OCR 调用；GPU 单次推理 ~10ms，3 worker 串行 30ms 几乎无感
_OCR_LOCK = threading.Lock()


class RecognizeError(RuntimeError):
    """模板缺失 / OCR 模型加载失败 / 截图无效"""
    pass


# === 模板文件名约定（用户需把对应截图放进 templates/）===
TPL_ENTER = "enter_button.png"          # 主页/大厅的「进入游戏」按钮
TPL_BATTLE = "battle_indicator.png"     # 战斗中独有的 UI（顶栏宝箱图标）
TPL_SKILL_TITLE = "skill_select_title.png"  # 技能选择弹窗（底部「刷新」按钮）
TPL_SETTLE = "confirm_button.png"       # 战斗胜利/失败结算页的「确定」按钮（同位置同样式）
TPL_PERFECT = "perfect_clear_seal.png"  # 完美通关页：红色「完美通关」印章
TPL_REWARD = "reward_popup.png"         # 金色「获得奖励」金字（结算后 / 宝箱奖励 通用）
TPL_BUY_STAMINA = "buy_stamina_title.png"  # 「购买体力」黑底白字标题
TPL_WHEEL = "wheel_close_hint.png"      # 击杀 boss 后的轮盘弹窗
TPL_BATTLE_TAB = "battle_tab_active.png"  # 底部「战斗」tab 选中态（验证切 tab 成功）


@lru_cache(maxsize=16)
def _load_template(name):
    path = os.path.join(TEMPLATES_DIR, name)
    if not os.path.exists(path):
        raise RecognizeError(f"模板缺失: {path}")
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        raise RecognizeError(f"模板无法读取: {path}")
    return img


def _match(screen, tpl_name):
    """在 screen 上匹配模板，返回 (score, center_xy)。模板缺失抛 RecognizeError"""
    tpl = _load_template(tpl_name)
    h, w = tpl.shape[:2]
    if screen.shape[0] < h or screen.shape[1] < w:
        return 0.0, None
    res = cv2.matchTemplate(screen, tpl, cv2.TM_CCOEFF_NORMED)
    _, score, _, max_loc = cv2.minMaxLoc(res)
    cx = max_loc[0] + w // 2
    cy = max_loc[1] + h // 2
    return float(score), (cx, cy)


def _try_match(screen, tpl_name, threshold=MATCH_THRESHOLD):
    """安全匹配：模板缺失返回 (0.0, None)，不抛错（用于状态识别时跳过未准备好的模板）"""
    try:
        return _match(screen, tpl_name)
    except RecognizeError:
        return 0.0, None


def detect_state(screen, ocr=None):
    """识别当前游戏状态。
    优先级：BUY_STAMINA > REWARD_POPUP > WHEEL > PERFECT_CLEAR > SKILL_SELECT > SETTLE > BATTLE > HOME > AD > UNKNOWN
    - BUY_STAMINA 最前：覆盖 HOME 画面的弹窗
    - REWARD_POPUP 第二前：金色「获得奖励」金字
    - WHEEL 在 BATTLE 前：战斗中弹的，battle_indicator 仍可能匹配
    - PERFECT_CLEAR 在 SKILL_SELECT 之前：完美通关页底部也是「进入游戏」按钮
    - SETTLE 在 BATTLE 前：战斗胜利/失败的「确定」按钮
    - AD 在 HOME 之后、UNKNOWN 之前：模板都没命中时 OCR 兜底找广告关键字
      （传 ocr 参数才启用 AD 识别；不传 ocr 旧调用保持纯模板匹配兼容）
    """
    score_buy, _ = _try_match(screen, TPL_BUY_STAMINA)
    if score_buy >= MATCH_THRESHOLD:
        return GameState.BUY_STAMINA

    score_reward, _ = _try_match(screen, TPL_REWARD)
    if score_reward >= MATCH_THRESHOLD:
        return GameState.REWARD_POPUP

    score_wheel, _ = _try_match(screen, TPL_WHEEL)
    if score_wheel >= MATCH_THRESHOLD:
        return GameState.WHEEL

    score_perfect, _ = _try_match(screen, TPL_PERFECT)
    if score_perfect >= PERFECT_CLEAR_THRESHOLD:
        return GameState.PERFECT_CLEAR

    score_skill, _ = _try_match(screen, TPL_SKILL_TITLE)
    if score_skill >= MATCH_THRESHOLD:
        return GameState.SKILL_SELECT

    score_settle, _ = _try_match(screen, TPL_SETTLE)
    if score_settle >= MATCH_THRESHOLD:
        return GameState.SETTLE

    score_battle, _ = _try_match(screen, TPL_BATTLE)
    if score_battle >= MATCH_THRESHOLD:
        return GameState.BATTLE

    score_enter, _ = _try_match(screen, TPL_ENTER)
    if score_enter >= MATCH_THRESHOLD:
        return GameState.HOME

    # AD 兜底：所有模板都没命中时 OCR 扫右上角找广告关键字
    if ocr is not None:
        for kw in AD_DETECT_KEYWORDS:
            hits = ocr_find_text(screen, kw, AD_DETECT_ROI, ocr)
            if hits:
                return GameState.AD

    return GameState.UNKNOWN


def all_template_scores(screen):
    """返回所有模板的匹配得分，用于 UNKNOWN 状态诊断"""
    names = [
        ("enter", TPL_ENTER),
        ("battle", TPL_BATTLE),
        ("skill", TPL_SKILL_TITLE),
        ("settle", TPL_SETTLE),
        ("perfect", TPL_PERFECT),
        ("reward", TPL_REWARD),
        ("buy", TPL_BUY_STAMINA),
        ("wheel", TPL_WHEEL),
    ]
    result = {}
    for label, tpl in names:
        score, _ = _try_match(screen, tpl)
        result[label] = score
    return result


def find_enter_button(screen):
    score, pos = _try_match(screen, TPL_ENTER)
    return pos if score >= MATCH_THRESHOLD else None


def find_settle_button(screen):
    score, pos = _try_match(screen, TPL_SETTLE)
    return pos if score >= MATCH_THRESHOLD else None


def is_battle_tab_active(screen):
    """战斗 tab 是否处于选中态（剑图标 + 高亮背景）
    用于 _force_back_to_battle 验证 tap TAB_BATTLE 是否真的切走
    """
    score, _ = _try_match(screen, TPL_BATTLE_TAB)
    return score >= MATCH_THRESHOLD


# === 技能卡 OCR ===
# 不用全局单例：多 worker 共用一个 cnocr 会序列化、互相阻塞、且非线程安全
# 改为工厂函数，每个 worker 自己 make_ocr() 持有独立实例


def _ensure_directml_priority():
    """让 cnocr 优先用 DirectML（GPU）provider。cnocr 默认 get_default_ort_providers
    只识别 CUDA + CPU；如果装了 onnxruntime-directml，把 DmlExecutionProvider 加最前面。
    需要 patch 多个模块的本地副本（recognizer / ppocr.utility / detector），
    因为它们都已 from .utils import get_default_ort_providers 取走了原引用。
    幂等，多 worker 安全。
    """
    try:
        import onnxruntime as ort
        from cnocr import utils as cnocr_utils

        if getattr(cnocr_utils, "_dml_patched", False):
            return
        available = ort.get_available_providers()

        def patched():
            providers = []
            if "DmlExecutionProvider" in available:
                providers.append("DmlExecutionProvider")  # GPU 优先
            if "CUDAExecutionProvider" in available:
                providers.append("CUDAExecutionProvider")
            if "CPUExecutionProvider" in available:
                providers.append("CPUExecutionProvider")
            if not providers:
                providers = available
            return providers

        # patch 源头
        cnocr_utils.get_default_ort_providers = patched
        # patch 已 from .utils import 取走的各副本
        for modname in ("cnocr.recognizer", "cnocr.ppocr.utility"):
            try:
                import importlib
                m = importlib.import_module(modname)
                if hasattr(m, "get_default_ort_providers"):
                    m.get_default_ort_providers = patched
            except Exception:
                pass
        # cnstd 也吃这一套；如果装了
        try:
            from cnstd import utils as cnstd_utils
            if hasattr(cnstd_utils, "get_default_ort_providers"):
                cnstd_utils.get_default_ort_providers = patched
            for modname in ("cnstd.ppocr.utility", "cnstd.yolov7.consts"):
                try:
                    import importlib
                    m = importlib.import_module(modname)
                    if hasattr(m, "get_default_ort_providers"):
                        m.get_default_ort_providers = patched
                except Exception:
                    pass
        except ImportError:
            pass

        cnocr_utils._dml_patched = True
    except Exception:
        # 任何失败静默回退到 cnocr 默认行为（CPU）
        pass


def make_ocr():
    """新建一个 cnocr 实例（每个 worker 独立持有，避免线程间阻塞）。
    自动启用 DirectML GPU 加速（如装了 onnxruntime-directml）。
    """
    _ensure_directml_priority()
    from cnocr import CnOcr
    return CnOcr()


def ocr_skill_cards(screen, card_rois, ocr):
    """对 card_rois 列表里每张卡跑 OCR，返回 [(cx, cy, text), ...]
    card_rois: [(x1, y1, x2, y2), ...]，长度 3。坐标基于截图分辨率
    ocr: cnocr 实例（由调用方提供，避免共享）
    text 为空字符串表示该卡 OCR 失败
    多 worker 同时调 DirectML 会 native 崩溃，用 _OCR_LOCK 串行
    """
    results = []
    for x1, y1, x2, y2 in card_rois:
        crop = screen[y1:y2, x1:x2]
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        text = ""
        try:
            with _OCR_LOCK:
                lines = ocr.ocr(crop)
            text = "".join(line["text"] for line in lines)
        except Exception:
            text = ""
        results.append((cx, cy, text))
    return results


def read_stamina(screen, roi, ocr):
    """OCR 左上角体力数字（如 "30/31"），返回 (current, max)；失败返回 (None, None)。
    多 worker 同时调 DirectML 会 native 崩溃，用 _OCR_LOCK 串行
    """
    import re
    x1, y1, x2, y2 = roi
    crop = screen[y1:y2, x1:x2]
    try:
        with _OCR_LOCK:
            lines = ocr.ocr(crop)
        text = "".join(line["text"] for line in lines)
    except Exception:
        return None, None
    m = re.search(r"(\d+)\s*/\s*(\d+)", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


def pick_skill_by_priority(cards, priority):
    """按 priority 关键字列表挨个匹配 cards 文本，返回第一个命中的 (cx, cy, keyword, text)。
    没命中返回 None。"""
    for keyword in priority:
        if not keyword:
            continue
        for cx, cy, text in cards:
            if keyword in text:
                return cx, cy, keyword, text
    return None


# === 红点检测 ===

def detect_redot_tabs(screen):
    """识别底部 3 个 tab 上方是否有红色感叹号，返回命中 tab 名集合
    返回值为 {"SHOP", "EQUIPMENT", "CASTLE"} 的子集；模板缺失抛 RecognizeError
    """
    tpl = _load_template(REDOT_TPL)  # 缺失抛 RecognizeError
    th, tw = tpl.shape[:2]
    hits = set()
    for tab_name, (x1, y1, x2, y2) in REDOT_ROIS.items():
        # 边界保护：ROI 落到截图外就跳过
        if x2 > screen.shape[1] or y2 > screen.shape[0]:
            continue
        crop = screen[y1:y2, x1:x2]
        if crop.shape[0] < th or crop.shape[1] < tw:
            continue
        res = cv2.matchTemplate(crop, tpl, cv2.TM_CCOEFF_NORMED)
        _, score, _, _ = cv2.minMaxLoc(res)
        if score >= REDOT_MATCH_THRESHOLD:
            hits.add(tab_name)
    return hits


# === 通用 OCR 找文本 ===

def _line_center(line, roi_offset):
    """从 cnocr 一行结果取中心点 (cx, cy)，加上 ROI 左上角偏移转回全图坐标
    cnocr line 结构：{"text": str, "score": float, "position": ndarray(4,2)}
    """
    try:
        pos = line.get("position")
        if pos is None:
            return None
        # position 是 4 个点 [(x1,y1),(x2,y1),(x2,y2),(x1,y2)]
        pos = np.asarray(pos)
        cx = float(pos[:, 0].mean()) + roi_offset[0]
        cy = float(pos[:, 1].mean()) + roi_offset[1]
        return int(cx), int(cy)
    except Exception:
        return None


def ocr_find_text(screen, keyword, roi, ocr, blocklist=None):
    """在 roi 内 OCR，找出所有文本包含 keyword 的行
    - roi: (x1, y1, x2, y2) 全图坐标
    - blocklist: 若 OCR 整屏文本含 blocklist 任一关键字 → 视为非目标页面，整体返回 []
    - 返回 [(cx, cy, text), ...]，坐标已加回 roi 偏移；按 cy 升序
    多 worker 并发 GPU 走 _OCR_LOCK 串行
    """
    x1, y1, x2, y2 = roi
    crop = screen[y1:y2, x1:x2]
    try:
        with _OCR_LOCK:
            lines = ocr.ocr(crop)
    except Exception:
        return []
    if not lines:
        return []

    # blocklist：整屏文本若含禁忌词则丢弃（防误识广告页里的「免费」）
    if blocklist:
        full_text = "".join(line.get("text", "") for line in lines)
        for bad in blocklist:
            if bad and bad in full_text:
                return []

    hits = []
    for line in lines:
        text = line.get("text", "")
        if keyword not in text:
            continue
        center = _line_center(line, (x1, y1))
        if center is None:
            continue
        cx, cy = center
        hits.append((cx, cy, text))
    hits.sort(key=lambda h: h[1])  # 按 y 升序
    return hits


# === HOME 顶部图标识别（带红 ! 模板）===
# 4 张图标模板从「有红 ! 」状态裁出 → 没红 ! 时分数自动跌破 0.8 → 视为无需点
# 比 redot.png 通用模板更可靠（小红 ! ROI 太小匹配不上）
HOME_ICON_TPLS = {
    "BATTLE_ORDER":   "icon_battle_order.png",
    "ACTIVITY":       "icon_activity.png",
    "TIMED_ACTIVITY": "icon_timed_activity.png",
    "SEVEN_DAY":      "icon_seven_day.png",
}


def find_home_icon(screen, tpl_name, threshold=MATCH_THRESHOLD):
    """模板匹配 HOME 顶部图标，返回 (cx, cy) 中心或 None
    模板缺失返回 None（不抛错，避免缺一个图标整个日常都崩）
    """
    try:
        tpl = _load_template(tpl_name)
    except RecognizeError:
        return None
    h, w = tpl.shape[:2]
    if screen.shape[0] < h or screen.shape[1] < w:
        return None
    res = cv2.matchTemplate(screen, tpl, cv2.TM_CCOEFF_NORMED)
    _, score, _, max_loc = cv2.minMaxLoc(res)
    if score < threshold:
        return None
    return (max_loc[0] + w // 2, max_loc[1] + h // 2)


def find_workshop_collect_buttons(screen):
    """全屏查找所有活跃「领取」按钮（模板匹配），返回 [(cx, cy), ...] 按 cy 升序
    模板缺失抛 RecognizeError；未找到返回 []
    """
    tpl = _load_template(WORKSHOP_COLLECT_TPL)
    th, tw = tpl.shape[:2]
    if screen.shape[0] < th or screen.shape[1] < tw:
        return []
    res = cv2.matchTemplate(screen, tpl, cv2.TM_CCOEFF_NORMED)
    locs = np.where(res >= MATCH_THRESHOLD)
    positions = []
    prev_cy = -999
    for pt in sorted(zip(*locs[::-1]), key=lambda p: p[1]):
        cx = pt[0] + tw // 2
        cy = pt[1] + th // 2
        if cy - prev_cy > th * 0.5:
            positions.append((cx, cy))
            prev_cy = cy
    return positions


def is_in_shop_page(screen, ocr):
    """粗判当前是否还在商店（或类似带底部 tab 栏的游戏内页）。
    判定：底部 tab 区 OCR 能识别到「战斗」或「商店」字样 → 视为在 tab 页内
    广告页底部 tab 不可见 → 返回 False

    自适应分辨率：取截图底部 ~85px 作为 ROI，避免硬编码 y 坐标
    （540×960 下 tab 文字 y=945；1080×1920 下 y=1890；都覆盖）
    """
    h, w = screen.shape[:2]
    bottom = max(0, h - 85)
    crop = screen[bottom:h, 0:w]
    try:
        with _OCR_LOCK:
            lines = ocr.ocr(crop)
    except Exception:
        return False
    text = "".join(line.get("text", "") for line in lines)
    return ("战斗" in text) or ("商店" in text)
