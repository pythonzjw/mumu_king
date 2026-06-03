"""
单实例自动化循环（540×960 最简版 main-simple）
- 只跑：HOME → BATTLE → SKILL_SELECT → REWARD_POPUP → HOME 主循环
- 体力归零：关弹窗 → sleep 30 分钟（不做任何日常）
- 不做：商店 / 装备 / 城堡 / 红点 / 完美通关
"""
import os
import sys
import time
import cv2


def _imwrite_unicode(path, img):
    try:
        ok, buf = cv2.imencode(".png", img)
        if ok:
            buf.tofile(path)
            return True
    except Exception:
        pass
    return False

from config import (
    GameState, LOOP_INTERVAL, BATTLE_WAIT, ENTER_WAIT,
    SKILL_SELECT_DELAY, SKILL_CARD_ROIS,
    REWARD_OUTSIDE,
    STAMINA_ROI, STAMINA_ZERO_WAIT_SECONDS,
    DEBUG_MAX_STEP_FILES,
)
from adb import AdbError
from recognizer import (
    detect_state, find_enter_button,
    ocr_skill_cards, pick_skill_by_priority, read_stamina,
    all_template_scores, make_ocr, RecognizeError,
)


class Worker:
    def __init__(self, adb_client, name, log_fn, skill_priority, debug=False):
        self.adb = adb_client
        self.name = name
        self.log_fn = log_fn
        self.skill_priority = list(skill_priority)
        self.debug = debug
        self.running = True
        self.unknown_count = 0
        self.max_unknown = 20
        self.step_count = 0
        self.ocr = None
        if self.debug:
            base = (os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
                    else os.path.dirname(os.path.abspath(__file__)))
            safe_name = self.name.replace(":", "_")
            self.debug_dir = os.path.join(base, "debug_run", safe_name)
            os.makedirs(self.debug_dir, exist_ok=True)

    def log(self, msg):
        ts = time.strftime("%H:%M:%S")
        self.log_fn(f"[{ts}][{self.name}] {msg}")

    def _save_debug(self, screen, suffix=""):
        if not self.debug:
            return
        self.step_count = (self.step_count + 1) % DEBUG_MAX_STEP_FILES
        path = os.path.join(self.debug_dir, f"step_{self.step_count:04d}{suffix}.png")
        if not _imwrite_unicode(path, screen):
            self.log(f"截图保存失败: {path}")

    def _sleep(self, sec):
        """可中断 sleep"""
        end = time.time() + sec
        while time.time() < end and self.running:
            time.sleep(0.1)

    def run(self):
        self.log("启动")
        self.log("[ocr] 加载中...")
        self.ocr = make_ocr()
        self.log("[ocr] 加载完成，开始识别")
        while self.running:
            try:
                screen = self.adb.screencap()
                self._save_debug(screen)
                state = detect_state(screen)
                self.log(f"状态: {state}")

                if state == GameState.HOME:
                    self.unknown_count = 0
                    self._handle_home(screen)
                elif state == GameState.BATTLE:
                    self.unknown_count = 0
                    self._handle_battle()
                elif state == GameState.SKILL_SELECT:
                    self.unknown_count = 0
                    self._handle_skill_select(screen)
                elif state == GameState.REWARD_POPUP:
                    self.unknown_count = 0
                    self._handle_reward_popup()
                elif state == GameState.BUY_STAMINA:
                    self.unknown_count = 0
                    self._handle_buy_stamina()
                elif state == GameState.WHEEL:
                    self.unknown_count = 0
                    self._handle_wheel()
                else:
                    self.unknown_count += 1
                    if self.unknown_count <= 3 or self.unknown_count % 10 == 0:
                        scores = all_template_scores(screen)
                        text = " ".join(f"{k}={v:.2f}" for k, v in scores.items())
                        self.log(f"未知状态 ({self.unknown_count}/{self.max_unknown}) 得分: {text}")
                        if self.debug:
                            self._save_debug(screen, "_unknown")
                    if self.unknown_count >= self.max_unknown:
                        self.log("连续未知过多，重置计数")
                        self.unknown_count = 0

                self._sleep(LOOP_INTERVAL)

            except AdbError as e:
                self.log(f"ADB 错误: {e}")
                self._sleep(2)
            except RecognizeError as e:
                self.log(f"识别错误: {e}")
                self._sleep(2)
            except Exception as e:
                self.log(f"异常: {e}")
                import traceback
                traceback.print_exc()
                self._sleep(2)

        self.log("已停止")

    def _handle_home(self, screen):
        # 体力为 0 就等 30 分钟
        cur, mx = read_stamina(screen, STAMINA_ROI, self.ocr)
        if cur is not None:
            self.log(f"体力 {cur}/{mx}")
            if cur <= 0:
                mins = STAMINA_ZERO_WAIT_SECONDS // 60
                self.log(f"体力为 0，等 {mins} 分钟")
                self._sleep(STAMINA_ZERO_WAIT_SECONDS)
                return
        pos = find_enter_button(screen)
        if pos is None:
            self.log("未定位进入按钮")
            return
        self.log(f"点进入按钮 ({pos[0]},{pos[1]})")
        self.adb.tap(pos[0], pos[1])
        self._sleep(ENTER_WAIT)

    def _handle_battle(self):
        self.log("战斗中，等待...")
        self._sleep(BATTLE_WAIT)

    def _handle_skill_select(self, screen):
        cards = ocr_skill_cards(screen, SKILL_CARD_ROIS, self.ocr)
        for i, (cx, cy, text) in enumerate(cards, 1):
            self.log(f"  技能卡 {i}: {text or '(OCR 失败)'}")
        hit = pick_skill_by_priority(cards, self.skill_priority)
        if hit:
            cx, cy, kw, text = hit
            self.log(f"命中 '{kw}' → 选「{text}」({cx},{cy})")
            self.adb.tap(cx, cy)
        else:
            cx, cy, text = cards[0]
            self.log(f"无关键字命中，点第一张「{text}」({cx},{cy})")
            self.adb.tap(cx, cy)
        self._sleep(SKILL_SELECT_DELAY)

    def _handle_reward_popup(self):
        """金色「获得奖励」金字（结算/宝箱/商店通用）→ 点空白关闭"""
        x, y = REWARD_OUTSIDE
        self.log(f"获得奖励弹窗，点空白 ({x},{y}) 关闭")
        self.adb.tap(x, y)
        self._sleep(0.6)

    def _handle_buy_stamina(self):
        """购买体力弹窗 → 关 → sleep 30 分钟（不做任何日常）"""
        x, y = REWARD_OUTSIDE
        self.log(f"购买体力弹窗，点空白 ({x},{y}) 关闭")
        self.adb.tap(x, y)
        self._sleep(0.8)
        mins = STAMINA_ZERO_WAIT_SECONDS // 60
        self.log(f"等 {mins} 分钟体力恢复")
        self._sleep(STAMINA_ZERO_WAIT_SECONDS)

    def _handle_wheel(self):
        """战斗中击杀 boss 后弹的轮盘 → 点空白关闭"""
        x, y = REWARD_OUTSIDE
        self.log(f"轮盘弹窗，点空白 ({x},{y}) 关闭")
        self.adb.tap(x, y)
        self._sleep(0.6)
