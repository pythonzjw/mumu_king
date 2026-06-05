"""
单实例自动化循环（540×960 完整版 main-full）
- 状态机：HOME → BATTLE → SKILL_SELECT → REWARD_POPUP → HOME
- 体力归零时在 30 分钟等待窗口内做完所有有红点的日常（商店 / 装备升级合成 / 城堡秘研）
- PERFECT_CLEAR 由 _handle_home 内 OCR 「完美通关」4 字触发
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
    SETTLE_WAIT, SETTLE_DOUBLE_KW, SETTLE_DOUBLE_ROI, SETTLE_DOUBLE_WAIT,
    SKILL_SELECT_DELAY, SKILL_CARD_ROIS,
    CHEST_POSITIONS, CHEST_WAIT, REWARD_OUTSIDE,
    SWIPE_LEFT_FROM, SWIPE_LEFT_TO, SWIPE_LEFT_DURATION_MS,
    STAMINA_ROI, STAMINA_ZERO_WAIT_SECONDS,
    TAB_SHOP, TAB_EQUIPMENT, TAB_BATTLE, TAB_CASTLE,
    ONE_KEY_UPGRADE_BTN, ONE_KEY_MERGE_BTN, MERGE_BTN,
    TAB_SWITCH_WAIT, MERGE_DIALOG_WAIT, MERGE_REWARD_WAIT,
    UPGRADE_DIALOG_WAIT, UPGRADE_CONFIRM_KW, UPGRADE_CONFIRM_ROI,
    SHOP_ENTER_WAIT, SHOP_OCR_ROI,
    SHOP_SWIPE_UP_FROM, SHOP_SWIPE_UP_TO, SHOP_SWIPE_DURATION_MS,
    SHOP_SWIPE_DOWN_FROM, SHOP_SWIPE_DOWN_TO, SHOP_RESET_TO_TOP_TIMES,
    SHOP_MAX_SWIPE, SHOP_MAX_EMPTY_SWIPE, SHOP_KEYWORD_FREE, SHOP_AD_BLOCKLIST,
    SHOP_AFTER_TAP_WAIT, SHOP_REWARD_CLOSE_WAIT,
    SHOP_CONFIRM_KW, SHOP_CONFIRM_ROI, SHOP_CONFIRM_POLL,
    CASTLE_ENTER_WAIT, CASTLE_GET_SCROLL_ROI, CASTLE_GET_SCROLL_KW,
    CASTLE_MIYAN_BTN_ROI, CASTLE_MIYAN_BTN_KW,
    CASTLE_MIYAN_ICON_ROI, CASTLE_POPUP_WAIT,
    CASTLE_CONTINUE_HINT_ROI, CASTLE_CONTINUE_HINT, CASTLE_CONTINUE_POLL,
    SCREEN_CENTER,
    ADS_SKIP_ROI, ADS_KEYWORDS, ADS_FALLBACK_TAPS,
    ADS_TIMEOUT_SEC, ADS_POLL_INTERVAL, ADS_AFTER_CLOSE_WAIT,
    WHEEL_SKIP_BTN,
    UNKNOWN_RESCUE_OCR_AT, UNKNOWN_RESCUE_TAB_DELTA,
    UNKNOWN_RESCUE_KEYWORDS, UNKNOWN_RESCUE_ROI,
    DEBUG_MAX_STEP_FILES,
    BATTLE_ORDER_WALL_TAB, BATTLE_ORDER_WALL_REDOT_ROI,
    BATTLE_ORDER_CLAIM_BTN,
    BATTLE_ORDER_ENTER_WAIT, BATTLE_ORDER_CLAIM_WAIT,
    ACTIVITY_CLAIM_ROI, ACTIVITY_CLAIM_KW,
    ACTIVITY_ENTER_WAIT, ACTIVITY_AFTER_CLAIM,
    TIMED_ACTIVITY_SIGN_KW, TIMED_ACTIVITY_SIGN_ROI,
    TIMED_ACTIVITY_ENTER_WAIT, TIMED_ACTIVITY_AFTER_SIGN,
    TIMED_ACTIVITY_SCROLL_FROM, TIMED_ACTIVITY_SCROLL_TO,
    TIMED_ACTIVITY_SCROLL_DUR_MS, TIMED_ACTIVITY_SCROLL_TIMES,
    SEVEN_DAY_CHALLENGE_TAB, SEVEN_DAY_GIFT_TAB,
    SEVEN_DAY_TAB_POSITIONS,
    SEVEN_DAY_CLAIM_ROI, SEVEN_DAY_CLAIM_KW,
    SEVEN_DAY_FREE_ROI, SEVEN_DAY_FREE_KW,
    SEVEN_DAY_ENTER_WAIT, SEVEN_DAY_AFTER_TAP,
    WORKSHOP_TAB_BTN, WORKSHOP_FASHI_TAB_BTN,
    WORKSHOP_UPGRADE_KW, WORKSHOP_UPGRADE_ROI,
    WORKSHOP_CONFIRM_ROI, WORKSHOP_CONFIRM_KW,
    WORKSHOP_RESET_TO_TOP_TIMES,
    WORKSHOP_SCROLL_DOWN_FROM, WORKSHOP_SCROLL_DOWN_TO,
    WORKSHOP_SCROLL_UP_FROM, WORKSHOP_SCROLL_UP_TO,
    WORKSHOP_SCROLL_DUR_MS, WORKSHOP_SCROLL_TIMES,
    WORKSHOP_ENTER_WAIT, WORKSHOP_AFTER_UPGRADE,
    WORKSHOP_POPUP_WAIT, WORKSHOP_AFTER_COLLECT,
    REDOT_MATCH_THRESHOLD,
)
from adb import AdbError
from recognizer import (
    detect_state, find_enter_button, find_settle_button,
    is_battle_tab_active,
    ocr_skill_cards, pick_skill_by_priority, read_stamina,
    all_template_scores, make_ocr, RecognizeError,
    detect_redot_tabs, ocr_find_text, is_in_shop_page,
    find_workshop_collect_buttons, _load_template,
    find_home_icon, HOME_ICON_TPLS,
)


class Worker:
    def __init__(self, adb_client, name, log_fn, skill_priority, debug=False):
        self.adb = adb_client
        self.name = name              # 用于日志前缀
        self.log_fn = log_fn
        self.skill_priority = list(skill_priority)
        self.debug = debug
        self.running = True
        self.unknown_count = 0
        self.max_unknown = 20
        self.step_count = 0
        # 完美通关页已点的宝箱数（0~3）；点完 3 个后左滑回原页面
        self.chests_clicked = 0
        # OCR 实例：run() 第一行 lazy 创建，多 worker 并行加载
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
        # 环形覆盖防磁盘膨胀
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
        self.log("[ocr] 加载中...")
        self.ocr = make_ocr()
        self.log("[ocr] 加载完成，开始识别")
        while self.running:
            try:
                screen = self.adb.screencap()
                self._save_debug(screen)
                state = detect_state(screen, self.ocr)
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
                elif state == GameState.AD:
                    self.unknown_count = 0
                    self._handle_ad()
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
        # 1. 体力检测：0 就跑日常 + 等 30 分钟
        cur, mx = read_stamina(screen, STAMINA_ROI, self.ocr)
        if cur is not None:
            self.log(f"体力 {cur}/{mx}")
            if cur <= 0:
                mins = STAMINA_ZERO_WAIT_SECONDS // 60
                self.log(f"体力为 0，{mins} 分钟等待内做日常")
                self._do_dailies_within_window(STAMINA_ZERO_WAIT_SECONDS)
                return

        # 2. 普通进入战斗（PERFECT_CLEAR 由 detect_state 模板识别，不在此 OCR 查）
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
        # 防御：战斗技能卡必含「解锁/学习/伤害/次」之一（如「解锁脉冲激光」「奥术飞弹子弹+1」）
        # 城堡法术书页只有名字+Lv.X，不含这些 → 跳过避免误点法术书（如「火球术」）
        combined = " ".join(t for _, _, t in cards)
        if not any(kw in combined for kw in ("解锁", "学习", "伤害", "次", "+")):
            self.log(f"[技能选择] 防御命中 — 3 卡文本不像战斗技能 ({combined[:40]}...)，跳过")
            return
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
        """战斗胜利/失败结算页：先尝试「双倍奖励」看广告 → 再点确认"""
        # 1. 找「双倍」按钮（左下，有次数限制 0/3）
        db_hits = ocr_find_text(screen, SETTLE_DOUBLE_KW, SETTLE_DOUBLE_ROI, self.ocr)
        if db_hits:
            cx, cy, text = db_hits[0]
            self.log(f"[结算] 点双倍奖励「{text.strip()}」({cx},{cy})")
            self.adb.tap(cx, cy)
            self._sleep(SETTLE_DOUBLE_WAIT)
            # 验证是否真进了广告页（次数用完点了无反应不会进）
            try:
                screen2 = self.adb.screencap()
            except AdbError:
                screen2 = screen
            state2 = detect_state(screen2, self.ocr)
            if state2 == GameState.AD or not is_battle_tab_active(screen2):
                # 真进广告
                self.log("[结算] 进入广告，等待关闭")
                self._watch_ad()
                self._sleep(ADS_AFTER_CLOSE_WAIT)
                try:
                    screen = self.adb.screencap()
                except AdbError:
                    pass
            else:
                self.log(f"[结算] 点双倍未进广告 (state={state2})，可能次数用完，跳过")
                screen = screen2

        # 2. 点「确认」按钮（原逻辑）
        pos = find_settle_button(screen)
        if pos is None:
            self.log("未定位结算确定按钮")
            return
        self.log(f"点结算确定 ({pos[0]},{pos[1]})")
        self.adb.tap(pos[0], pos[1])
        self._sleep(SETTLE_WAIT)

    def _handle_perfect_clear(self):
        """完美通关页：依次点 3 个宝箱。
        点第 3 个宝箱后直接内联关奖励弹窗 + 左滑，不依赖主循环重新检测模板。
        保留顶部分支作为安全兜底（正常路径不走这里）。
        """
        if self.chests_clicked >= len(CHEST_POSITIONS):
            self.log("3 个宝箱已处理，左滑到下一关")
            self.adb.swipe(*SWIPE_LEFT_FROM, *SWIPE_LEFT_TO, SWIPE_LEFT_DURATION_MS)
            self.chests_clicked = 0
            self._sleep(1.0)
            return
        idx = self.chests_clicked
        cx, cy = CHEST_POSITIONS[idx]
        self.log(f"点宝箱 {idx + 1}/{len(CHEST_POSITIONS)} ({cx},{cy})")
        self.adb.tap(cx, cy)
        self._sleep(0.3)
        self.adb.tap(cx, cy)
        self.chests_clicked += 1
        self._sleep(CHEST_WAIT)
        # ★ 第3个宝箱点完后直接处理，不依赖主循环重新识别模板
        if self.chests_clicked >= len(CHEST_POSITIONS):
            self._sleep(1.0)
            self.adb.tap(*REWARD_OUTSIDE)
            self._sleep(0.8)
            self.adb.tap(*REWARD_OUTSIDE)
            self._sleep(0.5)
            self.log("3 个宝箱全部处理，左滑到下一关")
            self.adb.swipe(*SWIPE_LEFT_FROM, *SWIPE_LEFT_TO, SWIPE_LEFT_DURATION_MS)
            self.chests_clicked = 0
            self._sleep(1.0)

    def _handle_reward_popup(self):
        """金色「获得奖励」金字（结算/宝箱/商店通用）→ 点弹窗外安全点关闭"""
        x, y = REWARD_OUTSIDE
        self.log(f"获得奖励弹窗，点弹窗外 ({x},{y}) 关闭")
        self.adb.tap(x, y)
        self._sleep(0.6)

    def _handle_buy_stamina(self):
        """体力不足弹「购买体力」→ 关弹窗 → 30 分钟等待窗口内做日常"""
        x, y = REWARD_OUTSIDE
        self.log(f"购买体力弹窗，点空白 ({x},{y}) 关闭")
        self.adb.tap(x, y)
        self._sleep(0.8)
        mins = STAMINA_ZERO_WAIT_SECONDS // 60
        self.log(f"{mins} 分钟等待内做日常")
        self._do_dailies_within_window(STAMINA_ZERO_WAIT_SECONDS)

    def _handle_wheel(self):
        """战斗中击杀 boss 后弹的轮盘 → 优先点底部「跳过」按钮，兜底点空白"""
        sx, sy = WHEEL_SKIP_BTN
        self.log(f"轮盘弹窗，点底部跳过 ({sx},{sy})")
        self.adb.tap(sx, sy)
        self._sleep(0.6)
        # 兜底：万一跳过按钮位置不对（不同弹窗变种）再点空白
        self.adb.tap(*REWARD_OUTSIDE)
        self._sleep(0.4)

    def _handle_ad(self):
        """主循环识别到广告页（detect_state 返回 AD）→ 调用 _watch_ad 等关闭"""
        self.log("识别到广告页，等待关闭...")
        self._watch_ad()
        self._sleep(ADS_AFTER_CLOSE_WAIT)

    # === 体力归零日常调度 ===

    def _do_dailies_within_window(self, total_wait_seconds):
        """在 total_wait_seconds 窗口内做完日常，剩余时间 sleep
        日常用时 >= 窗口时不再 sleep
        """
        start = time.time()
        self._do_all_dailies_with_redot()
        elapsed = time.time() - start
        remaining = max(0.0, total_wait_seconds - elapsed)
        self.log(f"日常用时 {elapsed:.0f}s，剩余等待 {remaining:.0f}s")
        if remaining > 0:
            self._sleep(remaining)

    def _do_all_dailies_with_redot(self):
        """截图 → 看红点 → 把有红点的全部串行做一遍
        - 底部 tab（商店/装备/城堡）：detect_redot_tabs 模板匹配
        - HOME 顶部图标（战令/活动/限时活动/七日狂欢）：find_home_icon 匹配带红 ! 的图标模板
          → 没红 ! 时模板分数自动跌破阈值 → 不点
        每个日常内部自带"无事可做就退出"，误触发也不会卡
        """
        try:
            screen = self.adb.screencap()
        except AdbError as e:
            self.log(f"日常截图失败: {e}")
            return
        # 底部 tab 红点
        try:
            tabs = detect_redot_tabs(screen)
        except RecognizeError as e:
            self.log(f"红点模板缺失: {e}")
            tabs = set()
        # HOME 顶部图标红点（带红 ! 模板）
        home_icons = {}
        for name, tpl in HOME_ICON_TPLS.items():
            pos = find_home_icon(screen, tpl)
            if pos is not None:
                home_icons[name] = pos

        if not tabs and not home_icons:
            self.log("无红点，跳过日常")
            return
        self.log(f"红点 tab: {sorted(tabs)} + HOME 图标: {sorted(home_icons)}，开始串行做")
        # 底部 tab 日常
        if "SHOP" in tabs:
            self._do_shop_daily()
        if "EQUIPMENT" in tabs:
            self._do_equipment_daily()
        if "CASTLE" in tabs:
            self._do_castle_daily()
        # HOME 顶部图标日常（找到带红 ! 的才做）
        if "BATTLE_ORDER" in home_icons:
            self._do_battle_order_daily(home_icons["BATTLE_ORDER"])
        if "ACTIVITY" in home_icons:
            self._do_activity_daily(home_icons["ACTIVITY"])
        if "TIMED_ACTIVITY" in home_icons:
            self._do_timed_activity_daily(home_icons["TIMED_ACTIVITY"])
        if "SEVEN_DAY" in home_icons:
            self._do_seven_day_daily(home_icons["SEVEN_DAY"])
        self.log("=== 全部日常处理完 ===")

    # === 装备日常：一键升级 → 一键合成 ===

    def _do_one_key_upgrade(self):
        """前提：已在装备 tab。点一键升级 → OCR 找弹窗「确定」点 → 等关闭"""
        self.log(f"点一键升级 {ONE_KEY_UPGRADE_BTN}")
        self.adb.tap(*ONE_KEY_UPGRADE_BTN)
        self._sleep(UPGRADE_DIALOG_WAIT)
        # OCR 找弹窗里的「确定」按钮
        try:
            screen = self.adb.screencap()
        except AdbError:
            return
        hits = ocr_find_text(screen, UPGRADE_CONFIRM_KW, UPGRADE_CONFIRM_ROI, self.ocr)
        if hits:
            cx, cy, text = hits[0]
            self.log(f"点升级弹窗「{text.strip()}」({cx},{cy})")
            self.adb.tap(cx, cy)
            self._sleep(1.0)
        else:
            self.log("[装备] 一键升级无弹窗或OCR未命中确定，跳过")

    def _do_one_key_merge(self):
        """前提：已在装备 tab。点一键合成 → 点合成弹窗 → 关 2 次奖励"""
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
        """装备 tab 红点日常：切装备 → 一键升级 → 一键合成 → 切回战斗"""
        self.log("=== 装备日常开始 ===")
        self.adb.tap(*TAB_EQUIPMENT)
        self._sleep(TAB_SWITCH_WAIT)
        self._do_one_key_upgrade()
        self._do_one_key_merge()
        self.log(f"切回战斗 tab {TAB_BATTLE}")
        self.adb.tap(*TAB_BATTLE)
        self._sleep(TAB_SWITCH_WAIT)
        self.log("=== 装备日常结束 ===")

    # === 商店日常 ===

    def _do_shop_daily(self):
        """商店红点日常：扫描全屏「免费」按钮 → 点 → 看广告 → 关奖励 → 上滑 → 重复
        直到上滑后两轮签名一致（到底）或达上限
        """
        self.log("=== 商店日常开始 ===")
        self.adb.tap(*TAB_SHOP)
        self._sleep(SHOP_ENTER_WAIT)

        # 先下滑 N 次重置到商店顶部（游戏切 tab 不自动滚顶，下次进可能还在底部）
        for _ in range(SHOP_RESET_TO_TOP_TIMES):
            self.adb.swipe(*SHOP_SWIPE_DOWN_FROM, *SHOP_SWIPE_DOWN_TO, SHOP_SWIPE_DURATION_MS)
            self._sleep(0.3)
        self.log(f"[商店] 已下滑 {SHOP_RESET_TO_TOP_TIMES} 次重置到顶部")
        self._sleep(0.5)

        clicked = set()
        prev_swipe_signature = None
        empty_swipe_count = 0    # 连续上滑后扫不到「免费」的次数，>= SHOP_MAX_EMPTY_SWIPE 才退
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
                self.log(f"[商店] 第 {round_idx+1} 轮本屏无新「免费」，上滑")
                self.adb.swipe(*SHOP_SWIPE_UP_FROM, *SHOP_SWIPE_UP_TO, SHOP_SWIPE_DURATION_MS)
                self._sleep(1.0)
                try:
                    screen2 = self.adb.screencap()
                except AdbError:
                    break
                hits2 = ocr_find_text(
                    screen2, SHOP_KEYWORD_FREE, SHOP_OCR_ROI, self.ocr,
                    blocklist=SHOP_AD_BLOCKLIST,
                )
                clicked.clear()  # 新视野，清空 clicked
                cur_sig = frozenset((h[0] // 40, h[1] // 40) for h in hits2)
                # 两次上滑后 OCR 签名完全相同 = 真到底了
                if cur_sig and cur_sig == prev_swipe_signature:
                    self.log("[商店] 上滑后 OCR 与上次完全一致，已到底，结束")
                    break
                prev_swipe_signature = cur_sig
                # 空上滑容忍：连续 N 次都扫不到「免费」才退，避免金币/资源商城屏 OCR 抖动误退
                if not hits2:
                    empty_swipe_count += 1
                    self.log(f"[商店] 上滑后无「免费」({empty_swipe_count}/{SHOP_MAX_EMPTY_SWIPE})")
                    if empty_swipe_count >= SHOP_MAX_EMPTY_SWIPE:
                        self.log(f"[商店] 连续 {SHOP_MAX_EMPTY_SWIPE} 次空上滑，结束")
                        break
                else:
                    empty_swipe_count = 0   # 这次扫到了，重置计数
                continue

            cx, cy, text = new_hits[0]
            self.log(f"[商店] 点「{text.strip()}」({cx},{cy})")
            self.adb.tap(cx, cy)
            clicked.add((cx // 40, cy // 40))
            self._sleep(SHOP_AFTER_TAP_WAIT)

            # 点完判断是否进了广告
            try:
                screen3 = self.adb.screencap()
            except AdbError:
                continue
            if not is_in_shop_page(screen3, self.ocr):
                self.log("[商店] 进入广告，等待关闭")
                self._watch_ad()
                self._sleep(ADS_AFTER_CLOSE_WAIT)

            # 关「获得奖励」礼包弹窗：必须点中间的「确定」按钮
            self._dismiss_shop_reward()
        else:
            self.log(f"[商店] 达到上滑上限 {SHOP_MAX_SWIPE} 轮，结束")

        self.log(f"切回战斗 tab {TAB_BATTLE}")
        self.adb.tap(*TAB_BATTLE)
        self._sleep(TAB_SWITCH_WAIT)
        self.log("=== 商店日常结束 ===")

    def _dismiss_shop_reward(self):
        """关商店礼包弹窗：OCR 找「确定」按钮点击"""
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

    # === 城堡日常 ===

    def _do_castle_daily(self):
        """城堡红点日常：切城堡 → 工坊日常 → 点左上「秘研」图标 → 获取秘卷（看广告）→
        关广告 → 点屏幕中心关秘卷领取提示 → 切回战斗 tab
        """
        self.log("=== 城堡日常开始 ===")
        self.adb.tap(*TAB_CASTLE)
        self._sleep(CASTLE_ENTER_WAIT)
        # 先做工坊日常（升级 + 领取）
        self._do_castle_workshop()

        # 1. 点左上「秘研」图标弹出操作框
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

        # 2. 点「获取秘卷」按钮 → 看广告 → 点屏幕中心关秘卷提示
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
            # 关「获得秘卷」提示弹窗：点屏幕中心 + 点空白冗余
            self.log(f"[城堡] 点屏幕中心 {SCREEN_CENTER} 关秘卷提示")
            self.adb.tap(*SCREEN_CENTER)
            self._sleep(0.8)
            self.adb.tap(*REWARD_OUTSIDE)
            self._sleep(0.6)
        else:
            self.log("[城堡] 未找到「获取秘卷」按钮，跳过广告环节")

        # 3. 强切回战斗 tab（带验证 + 关残留弹窗重试）
        self._force_back_to_battle()
        self.log("=== 城堡日常结束 ===")

    def _has_redot(self, screen, roi):
        """HSV 红色像素计数法检测红点是否存在
        v0.5.16：阈值 50→25 — 七日狂欢 sub-tab 红点是纯小圆点（9×9, 48-52px）
        而战令城墙红点带 !（16×16, 172px）。两种红点尺寸差 4 倍，统一阈值 25 都能覆盖
        正常无红点时为 0 像素，离 25 距离 25px，安全
        """
        x1, y1, x2, y2 = roi
        if x2 > screen.shape[1] or y2 > screen.shape[0]:
            return False
        crop = screen[y1:y2, x1:x2]
        if crop.size == 0:
            return False
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        m1 = cv2.inRange(hsv, (0, 120, 120), (10, 255, 255))
        m2 = cv2.inRange(hsv, (170, 120, 120), (180, 255, 255))
        red_pixels = cv2.countNonZero(cv2.bitwise_or(m1, m2))
        return red_pixels >= 25

    def _do_castle_workshop(self):
        """城堡工坊日常：切工坊 tab → 重置到顶 → 逐屏找领取+升级 → 返回法术书 tab"""
        self.log("[工坊] 切工坊 tab")
        self.adb.tap(*WORKSHOP_TAB_BTN)
        self._sleep(WORKSHOP_ENTER_WAIT)
        # 先下滑重置到顶部
        for _ in range(WORKSHOP_RESET_TO_TOP_TIMES):
            self.adb.swipe(*WORKSHOP_SCROLL_DOWN_FROM, *WORKSHOP_SCROLL_DOWN_TO, WORKSHOP_SCROLL_DUR_MS)
            self._sleep(0.3)
        self.log("[工坊] 已重置到顶部")

        handled_positions = set()
        prev_sig = None

        for scroll_idx in range(WORKSHOP_SCROLL_TIMES + 1):
            if not self.running:
                break
            try:
                screen = self.adb.screencap()
            except AdbError:
                break

            # 1. 找活跃「领取」按钮（模板匹配，区分米黄色活跃/灰色未激活）
            try:
                collect_hits = find_workshop_collect_buttons(screen)
            except RecognizeError:
                collect_hits = []
            for cx, cy in collect_hits:
                key = (cx // 40, cy // 40)
                if key in handled_positions:
                    continue
                self.log(f"[工坊] 点领取 ({cx},{cy})")
                self.adb.tap(cx, cy)
                handled_positions.add(key)
                self._sleep(WORKSHOP_AFTER_COLLECT)
                self.adb.tap(*REWARD_OUTSIDE)
                self._sleep(0.5)

            # 2. 找「升级」按钮（OCR）
            upgrade_hits = ocr_find_text(screen, WORKSHOP_UPGRADE_KW, WORKSHOP_UPGRADE_ROI, self.ocr)
            for cx, cy, _ in upgrade_hits:
                key = (cx // 40, cy // 40)
                if key in handled_positions:
                    continue
                self.log(f"[工坊] 点升级 ({cx},{cy})")
                self.adb.tap(cx, cy)
                handled_positions.add(key)
                self._sleep(WORKSHOP_POPUP_WAIT)
                try:
                    screen2 = self.adb.screencap()
                except AdbError:
                    continue
                confirm_hits = ocr_find_text(screen2, WORKSHOP_CONFIRM_KW, WORKSHOP_CONFIRM_ROI, self.ocr)
                if confirm_hits:
                    ccx, ccy, _ = confirm_hits[0]
                    self.log(f"[工坊] 点确定 ({ccx},{ccy})")
                    self.adb.tap(ccx, ccy)
                    self._sleep(WORKSHOP_AFTER_UPGRADE)
                else:
                    self.log("[工坊] 未找到「确定」，点空白兜底")
                    self.adb.tap(*REWARD_OUTSIDE)
                    self._sleep(0.5)

            # 3. 上滑找更多工坊（最后一轮不滑）
            if scroll_idx < WORKSHOP_SCROLL_TIMES:
                self.adb.swipe(*WORKSHOP_SCROLL_UP_FROM, *WORKSHOP_SCROLL_UP_TO, WORKSHOP_SCROLL_DUR_MS)
                self._sleep(0.8)
                handled_positions.clear()
                try:
                    screen3 = self.adb.screencap()
                except AdbError:
                    break
                try:
                    c_hits = find_workshop_collect_buttons(screen3)
                except RecognizeError:
                    c_hits = []
                u_hits = ocr_find_text(screen3, WORKSHOP_UPGRADE_KW, WORKSHOP_UPGRADE_ROI, self.ocr)
                cur_sig = frozenset(
                    [(cx // 40, cy // 40) for cx, cy in c_hits] +
                    [(cx // 40, cy // 40) for cx, cy, _ in u_hits]
                )
                if cur_sig == prev_sig:
                    self.log("[工坊] 上滑前后画面一致，已到底")
                    break
                prev_sig = cur_sig

        # 返回法术书 tab（城堡主视图）
        self.log("[工坊] 返回法术书 tab")
        self.adb.tap(*WORKSHOP_FASHI_TAB_BTN)
        self._sleep(WORKSHOP_ENTER_WAIT)

    def _do_battle_order_daily(self, icon_pos):
        """战令日常：钻石 tab 一键领取 → 检查城墙 tab 红点 → 返回
        icon_pos: HOME 战令图标动态匹配返回的中心坐标
        """
        self.log(f"=== 战令日常开始 (入口 {icon_pos}) ===")
        self.adb.tap(*icon_pos)
        self._sleep(BATTLE_ORDER_ENTER_WAIT)
        # 钻石 tab（默认），直接点一键领取
        self.adb.tap(*BATTLE_ORDER_CLAIM_BTN)
        self._sleep(BATTLE_ORDER_CLAIM_WAIT)
        self.adb.tap(*REWARD_OUTSIDE)
        self._sleep(0.5)
        # 检查城墙 tab 是否有红点
        try:
            screen = self.adb.screencap()
        except AdbError:
            screen = None
        if screen is not None and self._has_redot(screen, BATTLE_ORDER_WALL_REDOT_ROI):
            self.log("[战令] 城墙 tab 有红点，进入")
            self.adb.tap(*BATTLE_ORDER_WALL_TAB)
            self._sleep(0.8)
            self.adb.tap(*BATTLE_ORDER_CLAIM_BTN)
            self._sleep(BATTLE_ORDER_CLAIM_WAIT)
            self.adb.tap(*REWARD_OUTSIDE)
            self._sleep(0.5)
        self.adb.tap(*REWARD_OUTSIDE)   # v0.5.18 改用空白处关，避免点 BACK 误触 tab
        self._sleep(1.0)
        self.log("=== 战令日常结束 ===")

    def _do_activity_daily(self, icon_pos):
        """活动日常：进入活动页 → 领取所有可领 → 关闭"""
        self.log(f"=== 活动日常开始 (入口 {icon_pos}) ===")
        self.adb.tap(*icon_pos)
        self._sleep(ACTIVITY_ENTER_WAIT)
        for _ in range(10):
            if not self.running:
                break
            try:
                screen = self.adb.screencap()
            except AdbError:
                break
            hits = ocr_find_text(screen, ACTIVITY_CLAIM_KW, ACTIVITY_CLAIM_ROI, self.ocr)
            if not hits:
                break
            cx, cy, _ = hits[0]
            self.log(f"[活动] 点领取 ({cx},{cy})")
            self.adb.tap(cx, cy)
            self._sleep(ACTIVITY_AFTER_CLAIM)
            self.adb.tap(*REWARD_OUTSIDE)
            self._sleep(0.5)
        self.adb.tap(*REWARD_OUTSIDE)   # v0.5.18 改用空白处关，避免 X 按钮位置误触 tab
        self._sleep(0.8)
        self.log("=== 活动日常结束 ===")

    def _do_timed_activity_daily(self, icon_pos):
        """限时活动：进入 → 找「签到」按钮（找不到则下滑找）→ 点一次 → 关闭"""
        self.log(f"=== 限时活动日常开始 (入口 {icon_pos}) ===")
        self.adb.tap(*icon_pos)
        self._sleep(TIMED_ACTIVITY_ENTER_WAIT)

        signed = False
        # 最多下滑 N 次找签到（首屏 + N 屏滚动）
        for scroll_idx in range(TIMED_ACTIVITY_SCROLL_TIMES + 1):
            if not self.running:
                break
            try:
                screen = self.adb.screencap()
            except AdbError:
                break
            hits = ocr_find_text(screen, TIMED_ACTIVITY_SIGN_KW, TIMED_ACTIVITY_SIGN_ROI, self.ocr,
                                  blocklist=("继续领取",))
            # 找精确「签到」按钮（不含「继续领取」/「未开起」等其他文本）
            for cx, cy, text in hits:
                if text.strip() == TIMED_ACTIVITY_SIGN_KW:
                    self.log(f"[限时活动] 点签到 ({cx},{cy})")
                    self.adb.tap(cx, cy)
                    self._sleep(TIMED_ACTIVITY_AFTER_SIGN)
                    self.adb.tap(*REWARD_OUTSIDE)
                    self._sleep(0.5)
                    signed = True
                    break
            if signed:
                break
            # 没找到 → 下滑找下一屏（最后一轮不滑）
            if scroll_idx < TIMED_ACTIVITY_SCROLL_TIMES:
                self.log(f"[限时活动] 第 {scroll_idx+1} 屏没找到签到，下滑")
                self.adb.swipe(*TIMED_ACTIVITY_SCROLL_FROM, *TIMED_ACTIVITY_SCROLL_TO,
                                TIMED_ACTIVITY_SCROLL_DUR_MS)
                self._sleep(0.6)

        if not signed:
            self.log("[限时活动] 全屏遍历没找到「签到」按钮，可能今日已签")
        self.adb.tap(*REWARD_OUTSIDE)   # v0.5.18 改用空白处关
        self._sleep(0.8)
        self.log("=== 限时活动日常结束 ===")

    def _do_seven_day_daily(self, icon_pos):
        """七日狂欢：进入页 → 找 1-7 天哪些有红点 →
        对每个有红点 day：点该 day → 切挑战领所有 → 切好礼点免费 → 关闭

        v0.5.20：按用户描述「看哪天有红点就点哪天进去」实现
        """
        self.log(f"=== 七日狂欢日常开始 (入口 {icon_pos}) ===")
        self.adb.tap(*icon_pos)
        self._sleep(SEVEN_DAY_ENTER_WAIT)

        try:
            screen = self.adb.screencap()
        except AdbError:
            self.adb.tap(*REWARD_OUTSIDE)
            self._sleep(0.8)
            return

        # 找哪几天有红点（红点固定在每个 day tab 右上 ~22px）
        days_with_redot = []
        for idx, (tx, ty) in enumerate(SEVEN_DAY_TAB_POSITIONS, start=1):
            roi = (tx + 8, 184, tx + 38, 215)
            if self._has_redot(screen, roi):
                days_with_redot.append((idx, tx, ty))

        if not days_with_redot:
            self.log("[七日狂欢] 1-7 天都无红点，跳过")
            self.adb.tap(*REWARD_OUTSIDE)
            self._sleep(0.8)
            return

        self.log(f"[七日狂欢] 有红点的天: {[d[0] for d in days_with_redot]}")

        for day, tx, ty in days_with_redot:
            if not self.running:
                break
            self.log(f"[七日狂欢] 切第{day}天 tab ({tx},{ty})")
            self.adb.tap(tx, ty)
            self._sleep(0.6)

            # 切每日挑战 sub-tab → OCR 找领取，循环点
            self.adb.tap(*SEVEN_DAY_CHALLENGE_TAB)
            self._sleep(0.6)
            for _ in range(10):
                if not self.running:
                    break
                try:
                    screen = self.adb.screencap()
                except AdbError:
                    break
                hits = ocr_find_text(screen, SEVEN_DAY_CLAIM_KW, SEVEN_DAY_CLAIM_ROI, self.ocr)
                if not hits:
                    break
                cx, cy, _ = hits[0]
                self.log(f"[七日狂欢/第{day}天/挑战] 点领取 ({cx},{cy})")
                self.adb.tap(cx, cy)
                self._sleep(SEVEN_DAY_AFTER_TAP)
                self.adb.tap(*REWARD_OUTSIDE)
                self._sleep(0.5)

            # 切每日好礼 sub-tab → OCR 找免费，点一次
            self.adb.tap(*SEVEN_DAY_GIFT_TAB)
            self._sleep(0.6)
            try:
                screen = self.adb.screencap()
            except AdbError:
                continue
            hits = ocr_find_text(screen, SEVEN_DAY_FREE_KW, SEVEN_DAY_FREE_ROI, self.ocr)
            if hits:
                cx, cy, _ = hits[0]
                self.log(f"[七日狂欢/第{day}天/好礼] 点免费 ({cx},{cy})")
                self.adb.tap(cx, cy)
                self._sleep(SEVEN_DAY_AFTER_TAP)
                self.adb.tap(*REWARD_OUTSIDE)
                self._sleep(0.5)

        self.adb.tap(*REWARD_OUTSIDE)
        self._sleep(0.8)
        self.log("=== 七日狂欢日常结束 ===")

    def _force_back_to_battle(self):
        """切回战斗 tab。无副作用操作 — 先检查再点击。最多 5 次

        v0.5.10 改：完全去掉 v0.5.8 加的「连点屏幕中心 3 次」
        — SCREEN_CENTER=(270,480) 在城堡法术书页正好是火球术图标位置，
        会触发法术书升级覆盖战斗 tab 导致死循环。
        改用 REWARD_OUTSIDE 顶部账号栏内部空白关弹窗（v0.5.16 上移到 y=30）。
        """
        for attempt in range(5):
            if not self.running:
                return
            # 1. 先截图检查是否已经在战斗 tab
            try:
                screen = self.adb.screencap()
            except AdbError:
                continue
            if is_battle_tab_active(screen):
                self.log(f"切回战斗 tab 成功 (attempt {attempt}, already active)")
                return

            # 2. tap 战斗 tab → 验证
            self.adb.tap(*TAB_BATTLE)
            self._sleep(TAB_SWITCH_WAIT * 1.5)
            try:
                screen = self.adb.screencap()
            except AdbError:
                continue
            if is_battle_tab_active(screen):
                self.log(f"切回战斗 tab 成功 (attempt {attempt} after tap)")
                return
            # 兜底：战斗中/结算等画面无 tab 栏但也算切走
            state = detect_state(screen, self.ocr)
            if state in (GameState.BATTLE, GameState.SETTLE,
                         GameState.PERFECT_CLEAR, GameState.REWARD_POPUP):
                self.log(f"切回战斗 tab 成功 (state={state})")
                return

            # 3. 未切走 → 点顶部安全空白关弹窗（不点屏幕中心避免误触法术书等）
            self.log(f"[切回战斗 {attempt+1}/5] 未切走 (state={state})，点顶部空白")
            self.adb.tap(*REWARD_OUTSIDE)   # (270, 200) 账号栏下方安全空白
            self._sleep(0.5)
            # 也试 OCR 找弹窗「确定/关闭」
            for kw in ("确定", "关闭"):
                hits = ocr_find_text(screen, kw, UNKNOWN_RESCUE_ROI, self.ocr)
                if hits:
                    cx, cy, _ = hits[0]
                    self.log(f"[切回战斗] 点弹窗「{kw}」({cx},{cy})")
                    self.adb.tap(cx, cy)
                    self._sleep(0.5)
                    break
        self.log("[切回战斗] 5 次都失败，留给 UNKNOWN 脱困逻辑")

    # === UNKNOWN 脱困 ===

    def _handle_unknown(self, screen):
        """连续 UNKNOWN 时主动脱困
        - 前置识别 1：15 关通关礼包弹窗 → 点空白关
        - 前置识别 2：模拟器主页（OCR 命中「正中靶心」）→ 点游戏图标启动
        - 1~2 次：仅打印日志
        - 3 次：OCR 找「确定/关闭/...」按钮点击
        - 6 次：仍 UNKNOWN，点战斗 tab 强行回首页
        - 20 次：重置 count 重来
        """
        # 前置识别 1：15 关通关礼包弹窗 → 点空白关
        if ocr_find_text(screen, "通关礼包", UNKNOWN_RESCUE_ROI, self.ocr):
            self.log("[识别] 15 关通关礼包弹窗，点空白关闭")
            self.adb.tap(270, 50)
            self._sleep(0.5)
            self.adb.tap(530, 200)
            self._sleep(0.5)
            return

        # 前置识别 2：模拟器主页 → 点游戏图标启动
        if ocr_find_text(screen, "正中靶心", (0, 350, 540, 420), self.ocr):
            self.log("[识别] 模拟器主页，点游戏图标「正中靶心」(334, 382)")
            self.adb.tap(334, 382)
            self._sleep(8.0)
            return

        if self.unknown_count <= 3 or self.unknown_count % 10 == 0:
            scores = all_template_scores(screen)
            score_text = " ".join(f"{k}={v:.2f}" for k, v in scores.items())
            self.log(f"未知状态 ({self.unknown_count}/{self.max_unknown}) 得分: {score_text}")
            if self.debug:
                self._save_debug(screen, "_unknown")

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

        if self.unknown_count == UNKNOWN_RESCUE_OCR_AT + UNKNOWN_RESCUE_TAB_DELTA:
            self.log(f"[脱困] 仍 UNKNOWN，点战斗 tab {TAB_BATTLE} 强行回首页")
            self.adb.tap(*TAB_BATTLE)
            self._sleep(TAB_SWITCH_WAIT)
            return

        if self.unknown_count >= self.max_unknown:
            self.log("连续未知过多，重置计数继续")
            self.unknown_count = 0

    # === 广告子流程 ===

    def _watch_ad(self, timeout=ADS_TIMEOUT_SEC):
        """看广告：右上角小 ROI 持续 OCR 等「关闭」出现 → 点。超时则点固定坐标兜底
        只识别「关闭」，跳过阶段不动以确保奖励发放
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
        self.log(f"[广告] 超时 {timeout}s，依次点 {len(ADS_FALLBACK_TAPS)} 个兜底坐标")
        for x, y in ADS_FALLBACK_TAPS:
            self.adb.tap(x, y)
            self._sleep(1.0)
        return False
