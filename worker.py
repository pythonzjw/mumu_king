"""
单实例自动化循环
- 状态机：HOME → BATTLE → SKILL_SELECT → SETTLE → HOME
- 每个 Worker 一根 daemon 线程，互不干扰
"""
import os
import sys
import time
import cv2

from config import (
    GameState, LOOP_INTERVAL, BATTLE_WAIT, ENTER_WAIT,
    SETTLE_WAIT, SKILL_SELECT_DELAY, SKILL_CARD_ROIS,
    CHEST_POSITIONS, CHEST_WAIT, REWARD_OUTSIDE,
    SWIPE_LEFT_FROM, SWIPE_LEFT_TO, SWIPE_LEFT_DURATION_MS,
    STAMINA_ROI, STAMINA_ZERO_WAIT_SECONDS,
)
from adb import AdbError
from recognizer import (
    detect_state, find_enter_button, find_settle_button,
    ocr_skill_cards, pick_skill_by_priority, read_stamina,
    all_template_scores, RecognizeError,
)


class Worker:
    def __init__(self, adb_client, name, log_fn, skill_priority, debug=False):
        self.adb = adb_client
        self.name = name              # 用于日志前缀，通常是端口号
        self.log_fn = log_fn
        self.skill_priority = list(skill_priority)
        self.debug = debug
        self.running = True
        self.unknown_count = 0
        self.max_unknown = 20
        self.step_count = 0
        # 完美通关页已点的宝箱数（0~3）；点完 3 个后左滑回原页面，重置为 0
        self.chests_clicked = 0
        if self.debug:
            # PyInstaller --onefile 下 __file__ 指向临时解压目录退出即清，
            # 改用 sys.executable 所在目录；serial 中的 ":" Windows 文件系统不允许，转 "_"
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
        self.step_count += 1
        path = os.path.join(self.debug_dir, f"step_{self.step_count:04d}{suffix}.png")
        cv2.imwrite(path, screen)

    def _sleep(self, sec):
        """可中断 sleep：每 100ms 检查 self.running"""
        end = time.time() + sec
        while time.time() < end and self.running:
            time.sleep(0.1)

    def run(self):
        self.log("启动")
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
                elif state == GameState.SETTLE:
                    self.unknown_count = 0
                    self._handle_settle(screen)
                elif state == GameState.PERFECT_CLEAR:
                    self.unknown_count = 0
                    self._handle_perfect_clear()
                elif state == GameState.REWARD_POPUP:
                    self.unknown_count = 0
                    self._handle_reward_popup()
                else:
                    self.unknown_count += 1
                    # UNKNOWN 时输出各模板得分 + 强制存截图（带 _unknown 后缀）方便诊断
                    if self.unknown_count <= 3 or self.unknown_count % 10 == 0:
                        scores = all_template_scores(screen)
                        score_text = " ".join(f"{k}={v:.2f}" for k, v in scores.items())
                        self.log(f"未知状态 ({self.unknown_count}/{self.max_unknown}) 得分: {score_text}")
                        # 即使没勾 debug 也强制存第 1 张 UNKNOWN 截图（用于诊断）
                        if self.debug:
                            self._save_debug(screen, "_unknown")
                    if self.unknown_count >= self.max_unknown:
                        self.log("连续未知过多，重置计数继续")
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
        # 进按钮前先查体力，0 就等 30 分钟（避免 0 体力点了被弹"体力不足"）
        cur, mx = read_stamina(screen, STAMINA_ROI)
        if cur is not None:
            self.log(f"体力 {cur}/{mx}")
            if cur <= 0:
                mins = STAMINA_ZERO_WAIT_SECONDS // 60
                self.log(f"体力为 0，等待 {mins} 分钟后再检测")
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
        cards = ocr_skill_cards(screen, SKILL_CARD_ROIS)
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

    def _handle_settle(self, screen):
        pos = find_settle_button(screen)
        if pos is None:
            self.log("未定位结算确定按钮")
            return
        self.log(f"点结算确定 ({pos[0]},{pos[1]})")
        self.adb.tap(pos[0], pos[1])
        self._sleep(SETTLE_WAIT)

    def _handle_perfect_clear(self):
        """完美通关页：依次点 3 个宝箱（点不亮 1s 内不弹奖励 → 跳下一个）；
        全部点完后左滑到下一关页面，重置 chests_clicked。
        REWARD_POPUP 由主循环下一轮自动接管，本函数只负责"点击当前 chest"。"""
        if self.chests_clicked >= len(CHEST_POSITIONS):
            self.log(f"3 个宝箱已处理，左滑到下一关 {SWIPE_LEFT_FROM} → {SWIPE_LEFT_TO}")
            self.adb.swipe(*SWIPE_LEFT_FROM, *SWIPE_LEFT_TO, SWIPE_LEFT_DURATION_MS)
            self.chests_clicked = 0
            self._sleep(1.0)
            return
        idx = self.chests_clicked
        cx, cy = CHEST_POSITIONS[idx]
        self.log(f"点宝箱 {idx + 1}/{len(CHEST_POSITIONS)} ({cx},{cy})")
        self.adb.tap(cx, cy)
        self.chests_clicked += 1
        self._sleep(CHEST_WAIT)

    def _handle_reward_popup(self):
        """弹了「获得奖励」→ 点弹窗外安全点关闭，下一轮回 PERFECT_CLEAR 继续"""
        x, y = REWARD_OUTSIDE
        self.log(f"获得奖励弹窗，点弹窗外 ({x},{y}) 关闭")
        self.adb.tap(x, y)
        self._sleep(0.6)
