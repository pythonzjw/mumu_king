"""
单实例自动化循环
- 状态机：HOME → BATTLE → SKILL_SELECT → SETTLE → HOME
- 每个 Worker 一根 daemon 线程，互不干扰
"""
import os
import sys
import time
import cv2
import numpy as np


def _imwrite_unicode(path, img):
    """cv2.imwrite 在 Windows 下不支持中文路径会静默失败；用 imencode + tofile 绕过"""
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
    SETTLE_WAIT, SKILL_SELECT_DELAY, SKILL_CARD_ROIS,
    CHEST_POSITIONS, CHEST_WAIT, REWARD_OUTSIDE,
    SWIPE_LEFT_FROM, SWIPE_LEFT_TO, SWIPE_LEFT_DURATION_MS,
    STAMINA_ROI, STAMINA_ZERO_WAIT_SECONDS,
    TAB_SHOP, TAB_EQUIPMENT, TAB_BATTLE, TAB_CASTLE,
    ONE_KEY_MERGE_BTN, MERGE_BTN,
    TAB_SWITCH_WAIT, MERGE_DIALOG_WAIT, MERGE_REWARD_WAIT,
    SHOP_ENTER_WAIT, SHOP_OCR_ROI,
    SHOP_SWIPE_UP_FROM, SHOP_SWIPE_UP_TO, SHOP_SWIPE_DURATION_MS,
    SHOP_MAX_SWIPE, SHOP_KEYWORD_FREE, SHOP_AD_BLOCKLIST,
    SHOP_AFTER_TAP_WAIT, SHOP_REWARD_CLOSE_WAIT,
    SHOP_CONFIRM_KW, SHOP_CONFIRM_ROI, SHOP_CONFIRM_POLL,
    CASTLE_ENTER_WAIT, CASTLE_GET_SCROLL_ROI, CASTLE_GET_SCROLL_KW,
    CASTLE_MIYAN_BTN_ROI, CASTLE_MIYAN_BTN_KW,
    CASTLE_MIYAN_ICON_ROI, CASTLE_POPUP_WAIT,
    CASTLE_CONTINUE_HINT_ROI, CASTLE_CONTINUE_HINT, CASTLE_CONTINUE_POLL,
    SCREEN_CENTER,
    ADS_SKIP_ROI, ADS_KEYWORDS, ADS_FALLBACK_TAP,
    ADS_TIMEOUT_SEC, ADS_POLL_INTERVAL, ADS_AFTER_CLOSE_WAIT,
    UNKNOWN_RESCUE_OCR_AT, UNKNOWN_RESCUE_TAB_DELTA,
    UNKNOWN_RESCUE_KEYWORDS, UNKNOWN_RESCUE_ROI,
    DEBUG_MAX_STEP_FILES,
)
from adb import AdbError
from recognizer import (
    detect_state, find_enter_button, find_settle_button,
    ocr_skill_cards, pick_skill_by_priority, read_stamina,
    all_template_scores, make_ocr, RecognizeError,
    detect_redot_tabs, ocr_find_text, is_in_shop_page,
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
        # OCR 实例：在 run() 第一行 lazy 创建，让多个 worker 在各自线程并行加载 onnx 模型
        # 避免主线程串行 init 时 3 个 worker 等 30s
        self.ocr = None
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
        # 环形覆盖，避免长时间挂 debug 磁盘膨胀
        self.step_count = (self.step_count + 1) % DEBUG_MAX_STEP_FILES
        path = os.path.join(self.debug_dir, f"step_{self.step_count:04d}{suffix}.png")
        if not _imwrite_unicode(path, screen):
            self.log(f"截图保存失败: {path}")

    def _sleep(self, sec):
        """可中断 sleep：每 100ms 检查 self.running"""
        end = time.time() + sec
        while time.time() < end and self.running:
            time.sleep(0.1)

    def run(self):
        self.log("启动")
        # 在线程内立刻加载 cnocr（多 worker 并行加载，比主线程串行快）
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
                elif state == GameState.SETTLE:
                    self.unknown_count = 0
                    self._handle_settle(screen)
                elif state == GameState.PERFECT_CLEAR:
                    self.unknown_count = 0
                    self._handle_perfect_clear()
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
                    self._handle_unknown(screen)

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
        cur, mx = read_stamina(screen, STAMINA_ROI, self.ocr)
        if cur is not None:
            self.log(f"体力 {cur}/{mx}")
            if cur <= 0:
                mins = STAMINA_ZERO_WAIT_SECONDS // 60
                self.log(f"体力为 0，等待 {mins} 分钟后再检测")
                self._sleep(STAMINA_ZERO_WAIT_SECONDS)
                return
        # 体力够再看红点：有红点就先做日常，本轮不点进入
        if self._check_and_do_daily(screen):
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

    def _handle_buy_stamina(self):
        """体力不足弹「购买体力」→ 关弹窗 → sleep 30 分钟等体力恢复
        合成已下沉到「装备 tab 红点日常」，本函数不再触发合成
        """
        x, y = REWARD_OUTSIDE
        self.log(f"购买体力弹窗，点空白 ({x},{y}) 关闭")
        self.adb.tap(x, y)
        self._sleep(0.8)
        mins = STAMINA_ZERO_WAIT_SECONDS // 60
        self.log(f"等待 {mins} 分钟体力恢复")
        self._sleep(STAMINA_ZERO_WAIT_SECONDS)

    def _handle_wheel(self):
        """战斗中击杀 boss 后弹的轮盘 → 点空白关闭，不参与轮盘选择"""
        x, y = REWARD_OUTSIDE
        self.log(f"轮盘弹窗，点空白 ({x},{y}) 关闭")
        self.adb.tap(x, y)
        self._sleep(0.6)

    # === 红点日常 ===

    def _check_and_do_daily(self, screen):
        """识别底部 tab 红点，命中就执行对应日常；一次只做一项以便尽快回 HOME 重检
        返回 True 表示本轮做了日常（调用方不要再点进入按钮）
        """
        try:
            tabs = detect_redot_tabs(screen)
        except RecognizeError as e:
            self.log(f"红点模板缺失: {e}")
            return False
        if not tabs:
            return False
        self.log(f"检测到红点 tab: {sorted(tabs)}")
        if "SHOP" in tabs:
            self._do_shop_daily()
            return True
        if "EQUIPMENT" in tabs:
            self._do_equipment_daily()
            return True
        if "CASTLE" in tabs:
            self._do_castle_daily()
            return True
        return False

    def _do_one_key_merge(self):
        """前提：已在装备 tab。点一键合成 → 点合成弹窗 → 关 2 次奖励
        不切 tab，由调用方负责切入/切回
        """
        self.log(f"点一键合成 {ONE_KEY_MERGE_BTN}")
        self.adb.tap(*ONE_KEY_MERGE_BTN)
        self._sleep(MERGE_DIALOG_WAIT)
        self.log(f"点合成按钮 {MERGE_BTN}")
        self.adb.tap(*MERGE_BTN)
        self._sleep(MERGE_REWARD_WAIT)
        self.log(f"点空白关合成奖励 {REWARD_OUTSIDE}")
        self.adb.tap(*REWARD_OUTSIDE)
        self._sleep(0.8)
        self.adb.tap(*REWARD_OUTSIDE)
        self._sleep(0.5)

    def _do_equipment_daily(self):
        """装备 tab 红点日常：切装备 → 一键合成 → 切回战斗"""
        self.log("=== 装备日常开始 ===")
        self.adb.tap(*TAB_EQUIPMENT)
        self._sleep(TAB_SWITCH_WAIT)
        self._do_one_key_merge()
        self.log(f"切回战斗 tab {TAB_BATTLE}")
        self.adb.tap(*TAB_BATTLE)
        self._sleep(TAB_SWITCH_WAIT)
        self.log("=== 装备日常结束 ===")

    def _do_shop_daily(self):
        """商店红点日常：扫描全屏「免费」按钮 → 点 → 看广告 → 关奖励 → 上滑 → 重复
        直到上滑后无新「免费」或达到 SHOP_MAX_SWIPE 上限
        """
        self.log("=== 商店日常开始 ===")
        self.adb.tap(*TAB_SHOP)
        self._sleep(SHOP_ENTER_WAIT)

        clicked = set()                # 同一屏内 40px 网格去重；上滑后会清空（新视野）
        prev_swipe_signature = None    # 上滑后 hits 的网格签名，连续两次相同视为到底
        for round_idx in range(SHOP_MAX_SWIPE):
            if not self.running:
                break
            try:
                screen = self.adb.screencap()
            except AdbError as e:
                self.log(f"商店截图失败: {e}")
                break
            if not is_in_shop_page(screen, self.ocr):
                self.log("已不在商店页（可能误入广告），结束商店日常")
                break

            hits = ocr_find_text(
                screen, SHOP_KEYWORD_FREE, SHOP_OCR_ROI, self.ocr,
                blocklist=SHOP_AD_BLOCKLIST,
            )
            new_hits = [h for h in hits if (h[0] // 40, h[1] // 40) not in clicked]

            if not new_hits:
                # 本屏没新「免费」→ 上滑找下一屏 → 清 clicked → 检测到底
                self.log(f"[商店] 第 {round_idx+1} 轮本屏无新「免费」，上滑")
                self.adb.swipe(*SHOP_SWIPE_UP_FROM, *SHOP_SWIPE_UP_TO, SHOP_SWIPE_DURATION_MS)
                self._sleep(1.0)
                try:
                    screen2 = self.adb.screencap()
                except AdbError as e:
                    self.log(f"商店上滑后截图失败: {e}")
                    break
                hits2 = ocr_find_text(
                    screen2, SHOP_KEYWORD_FREE, SHOP_OCR_ROI, self.ocr,
                    blocklist=SHOP_AD_BLOCKLIST,
                )
                # 关键修复：上滑 = 新视野，清空 clicked 重新去重
                clicked.clear()
                # 到底检测：本次上滑后的 hits 签名与上次完全相同 → 页面没动 → 停
                cur_sig = frozenset((h[0] // 40, h[1] // 40) for h in hits2)
                if cur_sig and cur_sig == prev_swipe_signature:
                    self.log("[商店] 上滑后 OCR 与上次完全一致，已到底，结束")
                    break
                prev_swipe_signature = cur_sig
                if not hits2:
                    self.log("[商店] 上滑后无任何「免费」，结束")
                    break
                continue

            cx, cy, text = new_hits[0]
            self.log(f"[商店] 点「{text.strip()}」({cx},{cy})")
            self.adb.tap(cx, cy)
            clicked.add((cx // 40, cy // 40))
            self._sleep(SHOP_AFTER_TAP_WAIT)

            # 点完判断是否进了广告
            try:
                screen3 = self.adb.screencap()
            except AdbError as e:
                self.log(f"商店点击后截图失败: {e}")
                continue
            if not is_in_shop_page(screen3, self.ocr):
                self.log("[商店] 进入广告，等待跳过/关闭")
                self._watch_ad()
                self._sleep(ADS_AFTER_CLOSE_WAIT)

            # 关「获得奖励」礼包弹窗：必须点中间的「确定」按钮，点空白无效
            self._dismiss_shop_reward()
        else:
            self.log(f"[商店] 达到上滑上限 {SHOP_MAX_SWIPE} 轮，结束")

        self.log(f"切回战斗 tab {TAB_BATTLE}")
        self.adb.tap(*TAB_BATTLE)
        self._sleep(TAB_SWITCH_WAIT)
        self.log("=== 商店日常结束 ===")

    def _dismiss_shop_reward(self):
        """关商店免费抽完弹的「获得奖励」礼包弹窗：OCR 找「确定」按钮点击
        礼包样式弹窗点空白无效，必须点中按钮；最多轮询 SHOP_CONFIRM_POLL 次
        找不到兜底点空白 + 屏幕中心，最大限度避免卡死
        """
        for _ in range(SHOP_CONFIRM_POLL):
            if not self.running:
                return
            try:
                screen = self.adb.screencap()
            except AdbError:
                return
            hits = ocr_find_text(screen, SHOP_CONFIRM_KW, SHOP_CONFIRM_ROI, self.ocr)
            if hits:
                cx, cy, text = hits[0]
                self.log(f"[商店] 点「{text.strip()}」({cx},{cy})")
                self.adb.tap(cx, cy)
                self._sleep(SHOP_REWARD_CLOSE_WAIT)
                return
            self._sleep(0.5)
        self.log("[商店] 未找到「确定」按钮，兜底点屏幕中心 + 空白")
        self.adb.tap(*SCREEN_CENTER)
        self._sleep(0.5)
        self.adb.tap(*REWARD_OUTSIDE)
        self._sleep(0.5)

    def _do_castle_daily(self):
        """城堡红点日常：切城堡 → 点左上「秘研」图标弹操作框 → 获取秘卷（看广告）
        → 关奖励 → 秘研 → 点屏幕继续 → 切回战斗
        """
        self.log("=== 城堡日常开始 ===")
        self.adb.tap(*TAB_CASTLE)
        self._sleep(CASTLE_ENTER_WAIT)

        # 1a. 先点左上角「秘研」图标，否则不会出现「获取秘卷/秘研」操作框
        try:
            entry_screen = self.adb.screencap()
        except AdbError as e:
            self.log(f"城堡截图失败: {e}")
            self.adb.tap(*TAB_BATTLE)
            self._sleep(TAB_SWITCH_WAIT)
            return
        icon_hits = ocr_find_text(
            entry_screen, CASTLE_MIYAN_BTN_KW, CASTLE_MIYAN_ICON_ROI, self.ocr,
        )
        if not icon_hits:
            self.log("[城堡] 未找到左上「秘研」图标，跳过日常")
            self.adb.tap(*TAB_BATTLE)
            self._sleep(TAB_SWITCH_WAIT)
            return
        cx, cy, _ = icon_hits[0]
        self.log(f"[城堡] 点左上「秘研」图标 ({cx},{cy})")
        self.adb.tap(cx, cy)
        self._sleep(CASTLE_POPUP_WAIT)

        # 1b. 弹窗里找「获取秘卷」按钮，点击进广告
        try:
            screen = self.adb.screencap()
        except AdbError as e:
            self.log(f"城堡截图失败: {e}")
            self.adb.tap(*TAB_BATTLE)
            self._sleep(TAB_SWITCH_WAIT)
            return

        hits = ocr_find_text(screen, CASTLE_GET_SCROLL_KW, CASTLE_GET_SCROLL_ROI, self.ocr)
        if hits:
            cx, cy, text = hits[0]
            self.log(f"[城堡] 点「{text.strip()}」({cx},{cy})")
            self.adb.tap(cx, cy)
            self._sleep(1.2)
            self._watch_ad()
            self._sleep(ADS_AFTER_CLOSE_WAIT)
            # 关可能弹的奖励
            self.adb.tap(*REWARD_OUTSIDE)
            self._sleep(0.6)
        else:
            self.log("[城堡] 未找到「获取秘卷」按钮，跳过广告环节")

        # 2. 找「秘研」按钮，点击升级
        try:
            screen2 = self.adb.screencap()
        except AdbError as e:
            self.log(f"城堡秘研前截图失败: {e}")
            self.adb.tap(*TAB_BATTLE)
            self._sleep(TAB_SWITCH_WAIT)
            return

        miyan = ocr_find_text(screen2, CASTLE_MIYAN_BTN_KW, CASTLE_MIYAN_BTN_ROI, self.ocr)
        if miyan:
            cx, cy, text = miyan[0]
            self.log(f"[城堡] 点「{text.strip()}」({cx},{cy})")
            self.adb.tap(cx, cy)
            self._sleep(2.0)
            # 等「点击屏幕继续」，最多 4 秒
            for _ in range(CASTLE_CONTINUE_POLL):
                if not self.running:
                    break
                try:
                    s = self.adb.screencap()
                except AdbError:
                    break
                if ocr_find_text(s, CASTLE_CONTINUE_HINT, CASTLE_CONTINUE_HINT_ROI, self.ocr):
                    self.log(f"[城堡] 检测到「{CASTLE_CONTINUE_HINT}」，点屏幕中心")
                    self.adb.tap(*SCREEN_CENTER)
                    self._sleep(0.8)
                    break
                self._sleep(0.5)
            else:
                self.log("[城堡] 未等到「点击屏幕继续」（可能秘卷不足），放弃")
        else:
            self.log("[城堡] 未找到「秘研」按钮")

        self.log(f"切回战斗 tab {TAB_BATTLE}")
        self.adb.tap(*TAB_BATTLE)
        self._sleep(TAB_SWITCH_WAIT)
        self.log("=== 城堡日常结束 ===")

    def _handle_unknown(self, screen):
        """连续 UNKNOWN 时主动脱困，避免脚本卡死在未识别的运营/礼包弹窗
        - 1~2 次：仅打印日志（瞬时画面不介入）
        - 3 次：OCR 找「确定/关闭/取消...」按钮点击，关弹窗
        - 6 次：还 UNKNOWN，点战斗 tab 强行回首页
        - 20 次：重置 count 重来一轮
        脱困后不重置 count，让下一轮主循环自然 detect_state 验证；
        若成功画面变 HOME/BATTLE 等，对应分支会清零 count
        """
        # 日志：第 1~3 次和每 10 次打印模板得分
        if self.unknown_count <= 3 or self.unknown_count % 10 == 0:
            scores = all_template_scores(screen)
            score_text = " ".join(f"{k}={v:.2f}" for k, v in scores.items())
            self.log(f"未知状态 ({self.unknown_count}/{self.max_unknown}) 得分: {score_text}")
            if self.debug:
                self._save_debug(screen, "_unknown")

        # 阶段 1：OCR 找按钮脱困
        if self.unknown_count == UNKNOWN_RESCUE_OCR_AT:
            for kw in UNKNOWN_RESCUE_KEYWORDS:
                hits = ocr_find_text(screen, kw, UNKNOWN_RESCUE_ROI, self.ocr)
                if hits:
                    cx, cy, text = hits[0]
                    self.log(f"[脱困] OCR 找到「{text.strip()}」({cx},{cy})，点击尝试关弹窗")
                    self.adb.tap(cx, cy)
                    self._sleep(1.0)
                    return
            self.log("[脱困] OCR 未找到任何关闭关键字")

        # 阶段 2：仍 UNKNOWN，切战斗 tab 强行回首页
        if self.unknown_count == UNKNOWN_RESCUE_OCR_AT + UNKNOWN_RESCUE_TAB_DELTA:
            self.log(f"[脱困] 仍 UNKNOWN，点战斗 tab {TAB_BATTLE} 强行回首页")
            self.adb.tap(*TAB_BATTLE)
            self._sleep(TAB_SWITCH_WAIT)
            return

        # 阶段 3：达上限重置（与原逻辑一致）
        if self.unknown_count >= self.max_unknown:
            self.log("连续未知过多，重置计数继续")
            self.unknown_count = 0

    def _watch_ad(self, timeout=ADS_TIMEOUT_SEC):
        """看广告子流程：右上角小 ROI 持续 OCR 等「跳过/关闭/X」关键字出现 → 点对应位置
        超时则点固定坐标兜底；返回 True=找到关键字成功点击，False=超时兜底
        """
        deadline = time.time() + timeout
        while time.time() < deadline and self.running:
            try:
                screen = self.adb.screencap()
            except AdbError as e:
                self.log(f"广告截图失败: {e}")
                self._sleep(ADS_POLL_INTERVAL)
                continue
            for kw in ADS_KEYWORDS:
                hits = ocr_find_text(screen, kw, ADS_SKIP_ROI, self.ocr)
                if hits:
                    cx, cy, text = hits[0]
                    self.log(f"[广告] 检测到「{text.strip()}」({cx},{cy})")
                    self.adb.tap(cx, cy)
                    self._sleep(1.0)
                    return True
            self._sleep(ADS_POLL_INTERVAL)
        self.log(f"[广告] 超时 {timeout}s，点兜底坐标 {ADS_FALLBACK_TAP}")
        self.adb.tap(*ADS_FALLBACK_TAP)
        self._sleep(1.0)
        # 「跳过」和「关闭」可能是两步弹窗，再补一次
        self.adb.tap(*ADS_FALLBACK_TAP)
        self._sleep(1.0)
        return False
