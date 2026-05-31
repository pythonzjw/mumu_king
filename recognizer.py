"""
游戏状态识别 + 技能卡 OCR
- 模板匹配：detect_state / find_*_button
- OCR：ocr_skill_cards 识别 3 张技能卡文字
- 模板缺失时抛 RecognizeError，让用户先放图
"""
import os
from functools import lru_cache

import cv2
import numpy as np

from config import TEMPLATES_DIR, MATCH_THRESHOLD, GameState


class RecognizeError(RuntimeError):
    """模板缺失 / OCR 模型加载失败 / 截图无效"""
    pass


# === 模板文件名约定（用户需把对应截图放进 templates/）===
TPL_ENTER = "enter_button.png"          # 主页/大厅的「进入战斗」按钮
TPL_BATTLE = "battle_indicator.png"     # 战斗中独有的 UI 特征（比如左下技能图标 / 血条样式）
TPL_SKILL_TITLE = "skill_select_title.png"  # 技能选择弹窗标题或顶部特征
TPL_SETTLE = "confirm_button.png"       # 结算页的「确定」按钮
TPL_PERFECT = "perfect_clear_seal.png"  # 完美通关页：红色「完美通关」印章
TPL_REWARD = "reward_popup.png"         # 点宝箱后弹的「获得奖励」金字标题


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


def detect_state(screen):
    """识别当前游戏状态。
    优先级：REWARD_POPUP > PERFECT_CLEAR > SKILL_SELECT > SETTLE > BATTLE > HOME > UNKNOWN
    - REWARD_POPUP 必须最前：弹奖励时印章和「进入游戏」按钮都还在画面里
    - PERFECT_CLEAR 比 HOME 前：完美通关页底部也是「进入游戏」按钮
    - SETTLE 在 BATTLE 前：结算页保留战场背景，battle_indicator 也会高分
    """
    score_reward, _ = _try_match(screen, TPL_REWARD)
    if score_reward >= MATCH_THRESHOLD:
        return GameState.REWARD_POPUP

    score_perfect, _ = _try_match(screen, TPL_PERFECT)
    if score_perfect >= MATCH_THRESHOLD:
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

    return GameState.UNKNOWN


def find_enter_button(screen):
    score, pos = _try_match(screen, TPL_ENTER)
    return pos if score >= MATCH_THRESHOLD else None


def find_settle_button(screen):
    score, pos = _try_match(screen, TPL_SETTLE)
    return pos if score >= MATCH_THRESHOLD else None


# === 技能卡 OCR ===
# cnocr 全局单例，多线程共用一个；首次 detect 会触发模型加载（500MB onnx，慢）
_ocr = None


def _get_ocr():
    global _ocr
    if _ocr is None:
        from cnocr import CnOcr
        _ocr = CnOcr()
    return _ocr


def ocr_skill_cards(screen, card_rois):
    """对 card_rois 列表里每张卡跑 OCR，返回 [(cx, cy, text), ...]
    card_rois: [(x1, y1, x2, y2), ...]，长度 3。坐标基于截图分辨率
    text 为空字符串表示该卡 OCR 失败
    """
    ocr = _get_ocr()
    results = []
    for x1, y1, x2, y2 in card_rois:
        crop = screen[y1:y2, x1:x2]
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        text = ""
        try:
            lines = ocr.ocr(crop)
            text = "".join(line["text"] for line in lines)
        except Exception:
            text = ""
        results.append((cx, cy, text))
    return results


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
