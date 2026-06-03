"""
游戏状态识别 + 技能卡 OCR（main-simple 精简版）
- 模板匹配：detect_state / find_enter_button
- OCR：ocr_skill_cards 识别 3 张技能卡文字
- 模板缺失时抛 RecognizeError
"""
import os
import threading
from functools import lru_cache

import cv2
import numpy as np

from config import TEMPLATES_DIR, MATCH_THRESHOLD, GameState

# OCR 全局锁：多 worker 共用 GPU（DirectML）时同时推理会 native 崩溃
_OCR_LOCK = threading.Lock()


class RecognizeError(RuntimeError):
    """模板缺失 / OCR 模型加载失败 / 截图无效"""
    pass


# === 模板文件名约定 ===
TPL_ENTER = "enter_button.png"          # 主页「进入游戏」按钮
TPL_BATTLE = "battle_indicator.png"     # 战斗中独有 UI（顶栏宝箱图标）
TPL_SKILL_TITLE = "skill_select_title.png"  # 技能选择弹窗
TPL_REWARD = "reward_popup.png"         # 金色「获得奖励」金字（结算 + 宝箱通用）
TPL_BUY_STAMINA = "buy_stamina_title.png"  # 「购买体力」标题
TPL_WHEEL = "wheel_close_hint.png"      # 击杀 boss 后的轮盘


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
    try:
        return _match(screen, tpl_name)
    except RecognizeError:
        return 0.0, None


def detect_state(screen):
    """识别当前游戏状态
    优先级：BUY_STAMINA > REWARD_POPUP > WHEEL > SKILL_SELECT > BATTLE > HOME > UNKNOWN
    """
    if _try_match(screen, TPL_BUY_STAMINA)[0] >= MATCH_THRESHOLD:
        return GameState.BUY_STAMINA
    if _try_match(screen, TPL_REWARD)[0] >= MATCH_THRESHOLD:
        return GameState.REWARD_POPUP
    if _try_match(screen, TPL_WHEEL)[0] >= MATCH_THRESHOLD:
        return GameState.WHEEL
    if _try_match(screen, TPL_SKILL_TITLE)[0] >= MATCH_THRESHOLD:
        return GameState.SKILL_SELECT
    if _try_match(screen, TPL_BATTLE)[0] >= MATCH_THRESHOLD:
        return GameState.BATTLE
    if _try_match(screen, TPL_ENTER)[0] >= MATCH_THRESHOLD:
        return GameState.HOME
    return GameState.UNKNOWN


def all_template_scores(screen):
    """UNKNOWN 状态诊断"""
    names = [
        ("enter", TPL_ENTER),
        ("battle", TPL_BATTLE),
        ("skill", TPL_SKILL_TITLE),
        ("reward", TPL_REWARD),
        ("buy", TPL_BUY_STAMINA),
        ("wheel", TPL_WHEEL),
    ]
    return {label: _try_match(screen, tpl)[0] for label, tpl in names}


def find_enter_button(screen):
    score, pos = _try_match(screen, TPL_ENTER)
    return pos if score >= MATCH_THRESHOLD else None


# === OCR ===

def _ensure_directml_priority():
    """让 cnocr 优先用 DirectML（GPU）provider；幂等，多 worker 安全"""
    try:
        import onnxruntime as ort
        from cnocr import utils as cnocr_utils

        if getattr(cnocr_utils, "_dml_patched", False):
            return
        available = ort.get_available_providers()

        def patched():
            providers = []
            if "DmlExecutionProvider" in available:
                providers.append("DmlExecutionProvider")
            if "CUDAExecutionProvider" in available:
                providers.append("CUDAExecutionProvider")
            if "CPUExecutionProvider" in available:
                providers.append("CPUExecutionProvider")
            if not providers:
                providers = available
            return providers

        cnocr_utils.get_default_ort_providers = patched
        for modname in ("cnocr.recognizer", "cnocr.ppocr.utility"):
            try:
                import importlib
                m = importlib.import_module(modname)
                if hasattr(m, "get_default_ort_providers"):
                    m.get_default_ort_providers = patched
            except Exception:
                pass
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
        pass


def make_ocr():
    """每个 worker 独立持有的 cnocr 实例，自动启用 DirectML"""
    _ensure_directml_priority()
    from cnocr import CnOcr
    return CnOcr()


def ocr_skill_cards(screen, card_rois, ocr):
    """对 card_rois 列表里每张卡跑 OCR，返回 [(cx, cy, text), ...]"""
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
    """OCR 左上角体力数字（如 "5/33"），返回 (current, max)；失败返回 (None, None)"""
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
    """按 priority 关键字列表挨个匹配 cards 文本，返回 (cx, cy, keyword, text)；没命中返回 None"""
    for keyword in priority:
        if not keyword:
            continue
        for cx, cy, text in cards:
            if keyword in text:
                return cx, cy, keyword, text
    return None
