"""
单实例自动化循环（540×960 完整版 main-full）
- 状态机：HOME → BATTLE → SKILL_SELECT → REWARD_POPUP → HOME
- 体力归零时在 30 分钟等待窗口内做完所有有红点的日常（商店 / 装备升级合成 / 城堡秘研）
- PERFECT_CLEAR 由 _handle_home 内 OCR 「完美通关」4 字触发
"""
import os
import sys
import time
import re
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
    TAB_SHOP, TAB_EQUIPMENT, TAB_BATTLE, TAB_CASTLE, TAB_CHALLENGE,
    ONE_KEY_UPGRADE_BTN, ONE_KEY_MERGE_BTN, MERGE_BTN,
    TAB_SWITCH_WAIT, MERGE_DIALOG_WAIT, MERGE_REWARD_WAIT,
    UPGRADE_DIALOG_WAIT, UPGRADE_CONFIRM_KW, UPGRADE_CONFIRM_ROI,
    MERGE_BTN_KW, MERGE_BTN_ROI,
    SHOP_ENTER_WAIT, SHOP_OCR_ROI,
    SHOP_SWIPE_UP_FROM, SHOP_SWIPE_UP_TO, SHOP_SWIPE_DURATION_MS,
    SHOP_SWIPE_DOWN_FROM, SHOP_SWIPE_DOWN_TO, SHOP_RESET_TO_TOP_TIMES,
    SHOP_MAX_SWIPE, SHOP_MAX_EMPTY_SWIPE, SHOP_KEYWORD_FREE, SHOP_AD_BLOCKLIST,
    SHOP_AFTER_TAP_WAIT, SHOP_AFTER_SCROLL_WAIT, SHOP_REWARD_CLOSE_WAIT,
    SHOP_CONFIRM_KW, SHOP_CONFIRM_ROI, SHOP_CONFIRM_POLL,
    CASTLE_ENTER_WAIT, CASTLE_GET_SCROLL_ROI, CASTLE_GET_SCROLL_KW,
    CASTLE_MIYAN_BTN_ROI, CASTLE_MIYAN_BTN_KW,
    CASTLE_MIYAN_ICON_ROI, CASTLE_POPUP_WAIT,
    CASTLE_CONTINUE_HINT_ROI, CASTLE_CONTINUE_HINT, CASTLE_CONTINUE_POLL,
    SCREEN_CENTER,
    ADS_SKIP_ROI, ADS_KEYWORDS, ADS_FALLBACK_TAPS,
    ADS_TIMEOUT_SEC, ADS_POLL_INTERVAL, ADS_AFTER_CLOSE_WAIT,
    ADS_PROGRESS_KEYWORDS, ADS_PAUSE_CHECK_SEC, ADS_RESUME_TAP,
    AD_DETECT_UNKNOWN_AT,
    WHEEL_SKIP_BTN,
    UNKNOWN_RESCUE_OCR_AT, UNKNOWN_RESCUE_TAB_DELTA,
    UNKNOWN_RESCUE_KEYWORDS, UNKNOWN_RESCUE_ROI,
    LAUNCH_GAME_KW, LAUNCH_GAME_ROI, LAUNCH_GAME_POS, LAUNCH_GAME_MAX_TPL_SCORE,
    DEBUG_MAX_STEP_FILES,
    BATTLE_ORDER_WALL_TAB, BATTLE_ORDER_WALL_REDOT_ROI,
    BATTLE_ORDER_CLAIM_BTN,
    BATTLE_ORDER_ENTER_WAIT, BATTLE_ORDER_CLAIM_WAIT,
    ACTIVITY_CLAIM_ROI, ACTIVITY_CLAIM_KW,
    ACTIVITY_ENTER_WAIT, ACTIVITY_AFTER_CLAIM, ACTIVITY_HOME_FALLBACK,
    TIMED_ACTIVITY_SIGN_KW, TIMED_ACTIVITY_SIGN_ROI,
    TIMED_ACTIVITY_ENTER_WAIT, TIMED_ACTIVITY_AFTER_SIGN, TIMED_ACTIVITY_HOME_FALLBACK,
    TIMED_ACTIVITY_SCROLL_FROM, TIMED_ACTIVITY_SCROLL_TO,
    TIMED_ACTIVITY_SCROLL_DUR_MS, TIMED_ACTIVITY_SCROLL_TIMES,
    TIMED_ACTIVITY_AFTER_SCROLL_WAIT,
    SEVEN_DAY_CHALLENGE_TAB, SEVEN_DAY_GIFT_TAB, SEVEN_DAY_HOME_FALLBACK,
    SEVEN_DAY_TAB_POSITIONS,
    SEVEN_DAY_CLAIM_ROI, SEVEN_DAY_CLAIM_KW,
    SEVEN_DAY_FREE_ROI, SEVEN_DAY_FREE_KW,
    SEVEN_DAY_ENTER_WAIT, SEVEN_DAY_AFTER_TAP, SEVEN_DAY_PAGE_WAIT,
    SEVEN_DAY_REWARD_CLOSE, SEVEN_DAY_RESCAN_ROUNDS,
    CLAIM_EMPTY_RECHECK, CLAIM_SKIP_KEYWORDS,
    WORKSHOP_TAB_BTN, WORKSHOP_FASHI_TAB_BTN,
    WORKSHOP_UPGRADE_KW, WORKSHOP_UPGRADE_ROI,
    WORKSHOP_CONFIRM_ROI, WORKSHOP_CONFIRM_KW,
    WORKSHOP_RESET_TO_TOP_TIMES,
    WORKSHOP_SCROLL_DOWN_FROM, WORKSHOP_SCROLL_DOWN_TO,
    WORKSHOP_SCROLL_UP_FROM, WORKSHOP_SCROLL_UP_TO,
    WORKSHOP_SCROLL_DUR_MS, WORKSHOP_SCROLL_TIMES,
    WORKSHOP_ENTER_WAIT, WORKSHOP_AFTER_UPGRADE,
    WORKSHOP_POPUP_WAIT, WORKSHOP_AFTER_COLLECT,
    CASTLE_SPELL_TARGET_TPLS, CASTLE_SPELL_MATCH_THRESHOLD,
    CASTLE_SPELL_SEARCH_ROI,
    CASTLE_SPELL_RESET_TO_TOP_TIMES, CASTLE_SPELL_SCROLL_TIMES,
    CASTLE_SPELL_SCROLL_DOWN_FROM, CASTLE_SPELL_SCROLL_DOWN_TO,
    CASTLE_SPELL_SCROLL_UP_FROM, CASTLE_SPELL_SCROLL_UP_TO,
    CASTLE_SPELL_SCROLL_DUR_MS, CASTLE_SPELL_AFTER_TAP, CASTLE_SPELL_POPUP_WAIT,
    CASTLE_SPELL_UPGRADE_KW, CASTLE_SPELL_UPGRADE_ROI, CASTLE_SPELL_CONFIRM_ROI,
    CHALLENGE_BRANCH_ENTER_TPL, CHALLENGE_BRANCH_CARD_TPL,
    CHALLENGE_MATCH_THRESHOLD, CHALLENGE_TAB_WAIT, CHALLENGE_ENTER_WAIT,
    CHALLENGE_MAX_SECONDS, CHALLENGE_REWARD_CLOSE,
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
    find_home_icon, HOME_ICON_TPLS, find_back_button, find_template,
)


class Worker:
    def __init__(self, adb_client, name, log_fn, skill_priority, debug=False,
                 banned_skill_keywords=None):
        self.adb = adb_client
        self.name = name              # 用于日志前缀
        self.log_fn = log_fn
        self.skill_priority = list(skill_priority)
        self.banned_skill_keywords = list(banned_skill_keywords or [])
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
        self.log(f"[技能] 优先级: {self.skill_priority}")
        self.log(f"[技能] 禁选: {self.banned_skill_keywords}")
        self.log("[ocr] 加载中...")
        self.ocr = make_ocr()
        self.log("[ocr] 加载完成，开始识别")
        while self.running:
            try:
                screen = self.adb.screencap()
                # 默认不跑广告 OCR 兜底；连续 UNKNOWN 后再跑，减少空场景 OCR CPU
                state = detect_state(screen, self.ocr, detect_ad=False)
                if state == GameState.UNKNOWN and self.unknown_count + 1 >= AD_DETECT_UNKNOWN_AT:
                    state = detect_state(screen, self.ocr, detect_ad=True)
                self.log(f"状态: {state}")
                if self.debug and state not in (GameState.HOME, GameState.BATTLE, GameState.UNKNOWN):
                    self._save_debug(screen, f"_{str(state).lower()}")

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
        banned = [re.sub(r"\s+", "", kw) for kw in self.banned_skill_keywords if kw]
        selectable_cards = cards
        if banned:
            selectable_cards = []
            for card in cards:
                _, _, text = card
                norm_text = re.sub(r"\s+", "", text or "")
                hit_banned = next((kw for kw in banned if kw in norm_text), None)
                if hit_banned:
                    self.log(f"[技能选择] 跳过禁选「{hit_banned}」→ {text}")
                else:
                    selectable_cards.append(card)
            if not selectable_cards:
                self.log("[技能选择] 3 张都命中禁选关键字，回退允许全部，避免卡死")
                selectable_cards = cards
        self.log("[技能选择] 可选卡: " + " | ".join(t or "(空)" for _, _, t in selectable_cards))

        hit = pick_skill_by_priority(selectable_cards, self.skill_priority)
        if hit:
            cx, cy, kw, text = hit
            self.log(f"命中 '{kw}' → 选「{text}」({cx},{cy})")
            self.adb.tap(cx, cy)
        else:
            cx, cy, text = selectable_cards[0]
            self.log(f"无关键字命中，点第一张「{text}」({cx},{cy})")
            self.adb.tap(cx, cy)
        self._sleep(SKILL_SELECT_DELAY)

    def _handle_settle(self, screen):
        """战斗胜利/失败结算页：有双倍次数就看广告；0/3 时直接确认"""
        db_hits = ocr_find_text(screen, SETTLE_DOUBLE_KW, SETTLE_DOUBLE_ROI, self.ocr)
        if db_hits:
            cx, cy, text = db_hits[0]
            norm = re.sub(r"\s+", "", text).replace("／", "/")
            if re.search(r"0/3", norm):
                self.log(f"[结算] 双倍次数已用完「{text.strip()}」，直接确认")
            else:
                self.log(f"[结算] 点双倍奖励「{text.strip()}」({cx},{cy})")
                self.adb.tap(cx, cy)
                self._sleep(SETTLE_DOUBLE_WAIT)
                try:
                    screen2 = self.adb.screencap()
                except AdbError:
                    screen2 = screen
                state2 = detect_state(screen2, self.ocr)
                # 真进广告时通常识别为 AD；部分广告模板/OCR 失败会是 UNKNOWN。
                # 如果仍能看到结算「确认」按钮，说明双倍没进去，不要等待 60s 广告超时。
                if state2 == GameState.AD or (
                    state2 == GameState.UNKNOWN and find_settle_button(screen2) is None
                ):
                    self.log("[结算] 进入广告，等待关闭")
                    self._watch_ad()
                    self._sleep(ADS_AFTER_CLOSE_WAIT)
                    try:
                        screen = self.adb.screencap()
                    except AdbError:
                        pass
                else:
                    self.log(f"[结算] 点双倍未进广告 (state={state2})，直接确认")
                    screen = screen2

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

        # 兜底：这些日常入口/红点偶发模板漏识别，体力等待窗口内固定扫一遍，内部无可领会自行退出
        home_icons.setdefault("ACTIVITY", ACTIVITY_HOME_FALLBACK)
        home_icons.setdefault("TIMED_ACTIVITY", TIMED_ACTIVITY_HOME_FALLBACK)
        home_icons.setdefault("SEVEN_DAY", SEVEN_DAY_HOME_FALLBACK)

        self.log(f"红点 tab: {sorted(tabs)} + HOME 图标/兜底: {sorted(home_icons)}，开始串行做")
        # 底部 tab 日常
        if "SHOP" in tabs:
            self._do_shop_daily()
        # 装备日常固定执行一次：无红点时一键升级/合成无事可做也能安全退出
        if "EQUIPMENT" not in tabs:
            self.log("[装备] 未检测到红点，仍固定执行一次防漏")
        self._do_equipment_daily()
        # 挑战支线：每个体力等待窗口固定尝试一次，未解锁/未匹配到入口会自动跳过
        self._do_challenge_branch_once()
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
        """前提：已在装备 tab。点一键合成 → 点合成弹窗 → 关 2 次奖励
        v0.5.22 OCR 兜底找「合成」按钮（位置可能因游戏 UI 微调）
        """
        self.log(f"点一键合成 {ONE_KEY_MERGE_BTN}")
        self.adb.tap(*ONE_KEY_MERGE_BTN)
        self._sleep(MERGE_DIALOG_WAIT)
        # OCR 在弹窗 ROI 找精确「合成」二字按钮
        hit_pos = None
        try:
            screen = self.adb.screencap()
            hits = ocr_find_text(screen, MERGE_BTN_KW, MERGE_BTN_ROI, self.ocr)
            # 精确匹配「合成」（排除「一键合成」「合成材料」等）
            for cx, cy, text in hits:
                if text.strip() == MERGE_BTN_KW:
                    hit_pos = (cx, cy)
                    break
        except AdbError:
            pass
        if hit_pos:
            self.log(f"[装备] OCR 找到合成按钮 {hit_pos}")
            self.adb.tap(*hit_pos)
        else:
            self.log(f"[装备] OCR 未找到合成按钮，回退固定坐标 {MERGE_BTN}")
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
        self._force_back_to_battle()
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
            self._sleep(SHOP_AFTER_SCROLL_WAIT)
        self.log(f"[商店] 已下滑 {SHOP_RESET_TO_TOP_TIMES} 次重置到顶部")

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
                self._sleep(SHOP_AFTER_SCROLL_WAIT)
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
                if not self._watch_ad():
                    self.log("[商店] 广告未确认关闭，结束商店日常防止乱点")
                    break
                self._sleep(ADS_AFTER_CLOSE_WAIT)

            # 关「获得奖励」礼包弹窗：必须点中间的「确定」按钮
            self._dismiss_shop_reward()
        else:
            self.log(f"[商店] 达到上滑上限 {SHOP_MAX_SWIPE} 轮，结束")

        self.log(f"切回战斗 tab {TAB_BATTLE}")
        self.adb.tap(*TAB_BATTLE)
        self._sleep(TAB_SWITCH_WAIT)
        self._force_back_to_battle()
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
        # 再做法术书指定技能升级（仅匹配用户确认的 4 个模板）
        self._do_castle_spellbook_upgrade()

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
            ad_closed = self._watch_ad()
            self._sleep(ADS_AFTER_CLOSE_WAIT)
            if ad_closed:
                # 关「获得秘卷」提示弹窗：点屏幕中心 + 点空白冗余
                self.log(f"[城堡] 点屏幕中心 {SCREEN_CENTER} 关秘卷提示")
                self.adb.tap(*SCREEN_CENTER)
                self._sleep(0.8)
                self.adb.tap(*REWARD_OUTSIDE)
                self._sleep(0.6)
            else:
                self.log("[城堡] 广告未确认关闭，跳过秘卷提示点击防止暂停广告")
        else:
            self.log("[城堡] 未找到「获取秘卷」按钮，跳过广告环节")

        # 3. 强切回战斗 tab（带验证 + 关残留弹窗重试）
        self._force_back_to_battle()
        self.log("=== 城堡日常结束 ===")

    def _has_redot(self, screen, roi, debug_label=None):
        """红点检测双保险 + 可选 debug 日志
        - HSV 像素 ≥ 80（强信号，HOME/战令大红!）→ 直接通过
        - HSV 像素 ≥ 15（弱信号，七日狂欢小圆点 ~61px）→ 模板验证 score ≥ 0.6
        - 模板加载失败 → 回退纯 HSV（阈值 25）
        debug_label: 不为空时打日志（便于调试看实际 HSV px / 模板 score）
        """
        x1, y1, x2, y2 = roi
        if x2 > screen.shape[1] or y2 > screen.shape[0]:
            if debug_label: self.log(f"[redot/{debug_label}] ROI 越界")
            return False
        crop = screen[y1:y2, x1:x2]
        if crop.size == 0:
            return False
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        m1 = cv2.inRange(hsv, (0, 120, 120), (10, 255, 255))
        m2 = cv2.inRange(hsv, (170, 120, 120), (180, 255, 255))
        n = cv2.countNonZero(cv2.bitwise_or(m1, m2))
        if n >= 80:
            if debug_label: self.log(f"[redot/{debug_label}] HSV={n}px 强信号 ✓")
            return True
        if n >= 15:
            try:
                tpl = _load_template("red_dot.png")
            except Exception:
                ok = n >= 25
                if debug_label: self.log(f"[redot/{debug_label}] HSV={n}px 无模板回退 → {ok}")
                return ok
            if crop.shape[0] >= tpl.shape[0] and crop.shape[1] >= tpl.shape[1]:
                res = cv2.matchTemplate(crop, tpl, cv2.TM_CCOEFF_NORMED)
                _, score, _, _ = cv2.minMaxLoc(res)
                ok = score >= 0.6
                if debug_label: self.log(f"[redot/{debug_label}] HSV={n}px tpl={score:.2f} → {ok}")
                return ok
        if debug_label: self.log(f"[redot/{debug_label}] HSV={n}px 弱信号不足")
        return False

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

    def _find_castle_spell_targets(self, screen):
        """在当前法术书屏幕查找用户确认的指定技能模板，返回 [(tpl, cx, cy, score)]。"""
        hits = []
        x1, y1, x2, y2 = CASTLE_SPELL_SEARCH_ROI
        x1 = max(0, x1); y1 = max(0, y1)
        x2 = min(screen.shape[1], x2); y2 = min(screen.shape[0], y2)
        crop = screen[y1:y2, x1:x2]
        if crop.size == 0:
            return hits
        for tpl_name in CASTLE_SPELL_TARGET_TPLS:
            try:
                tpl = _load_template(tpl_name)
            except RecognizeError:
                self.log(f"[法术书] 模板缺失，跳过: {tpl_name}")
                continue
            th, tw = tpl.shape[:2]
            if crop.shape[0] < th or crop.shape[1] < tw:
                continue
            res = cv2.matchTemplate(crop, tpl, cv2.TM_CCOEFF_NORMED)
            _, score, _, max_loc = cv2.minMaxLoc(res)
            if score >= CASTLE_SPELL_MATCH_THRESHOLD:
                hits.append((tpl_name, x1 + max_loc[0] + tw // 2, y1 + max_loc[1] + th // 2, float(score)))
        hits.sort(key=lambda h: (h[2], h[1]))
        return hits

    def _upgrade_castle_spell_detail(self, tpl_name):
        """法术书技能详情页：先点「升级」，再点「确定」；找不到就安全关闭详情。"""
        upgrade_hit = None
        for _ in range(3):
            if not self.running:
                return False
            try:
                screen = self.adb.screencap()
            except AdbError:
                return False
            hits = ocr_find_text(screen, CASTLE_SPELL_UPGRADE_KW, CASTLE_SPELL_UPGRADE_ROI, self.ocr)
            usable = [(cx, cy, text) for cx, cy, text in hits if CASTLE_SPELL_UPGRADE_KW in re.sub(r"\s+", "", text or "")]
            if usable:
                upgrade_hit = usable[0]
                break
            self._sleep(0.5)

        if not upgrade_hit:
            self.log(f"[法术书] {tpl_name} 详情页未找到「升级」，关闭详情")
            self.adb.tap(*REWARD_OUTSIDE)
            self._sleep(0.5)
            return False

        ux, uy, text = upgrade_hit
        self.log(f"[法术书] 点「{text.strip()}」({ux},{uy})")
        self.adb.tap(ux, uy)
        self._sleep(CASTLE_SPELL_AFTER_TAP)

        confirmed = False
        for _ in range(3):
            if not self.running:
                break
            try:
                screen = self.adb.screencap()
            except AdbError:
                break
            confirm_hits = ocr_find_text(screen, WORKSHOP_CONFIRM_KW, CASTLE_SPELL_CONFIRM_ROI, self.ocr)
            if confirm_hits:
                ccx, ccy, ctext = confirm_hits[0]
                self.log(f"[法术书] 点「{ctext.strip()}」({ccx},{ccy})")
                self.adb.tap(ccx, ccy)
                self._sleep(CASTLE_SPELL_AFTER_TAP)
                confirmed = True
                break
            self._sleep(0.5)

        if not confirmed:
            self.log(f"[法术书] {tpl_name} 未找到二次「确定」，按已点升级处理")
        # 确保回到法术书列表，避免下一轮误在详情页滑动/匹配
        self.adb.tap(*REWARD_OUTSIDE)
        self._sleep(0.5)
        return True

    def _do_castle_spellbook_upgrade(self):
        """法术书指定技能升级：回到顶部后逐屏寻找 4 个固定模板，只点命中的目标技能。"""
        self.log("[法术书] 开始指定技能升级")
        self.adb.tap(*WORKSHOP_FASHI_TAB_BTN)
        self._sleep(WORKSHOP_ENTER_WAIT)

        # 先手指向下滑，确保从顶部开始扫
        for _ in range(CASTLE_SPELL_RESET_TO_TOP_TIMES):
            self.adb.swipe(*CASTLE_SPELL_SCROLL_DOWN_FROM, *CASTLE_SPELL_SCROLL_DOWN_TO,
                            CASTLE_SPELL_SCROLL_DUR_MS)
            self._sleep(0.3)
        self.log("[法术书] 已重置到顶部")

        handled = set()
        for scroll_idx in range(CASTLE_SPELL_SCROLL_TIMES + 1):
            if not self.running:
                break
            try:
                screen = self.adb.screencap()
            except AdbError:
                break

            hits = self._find_castle_spell_targets(screen)
            if hits:
                self.log("[法术书] 当前屏命中: " + ", ".join(
                    f"{tpl}@({cx},{cy})/{score:.2f}" for tpl, cx, cy, score in hits
                ))
            for tpl_name, cx, cy, _ in hits:
                key = (tpl_name, cx // 30, cy // 30)
                if key in handled:
                    continue
                self.log(f"[法术书] 点目标技能 {tpl_name} ({cx},{cy})")
                self.adb.tap(cx, cy)
                handled.add(key)
                self._sleep(CASTLE_SPELL_POPUP_WAIT)
                self._upgrade_castle_spell_detail(tpl_name)

            if scroll_idx < CASTLE_SPELL_SCROLL_TIMES:
                self.adb.swipe(*CASTLE_SPELL_SCROLL_UP_FROM, *CASTLE_SPELL_SCROLL_UP_TO,
                                CASTLE_SPELL_SCROLL_DUR_MS)
                self._sleep(0.8)
        self.log("[法术书] 指定技能升级结束")

    def _do_challenge_branch_once(self):
        """挑战支线：挑战页模板命中才进入；只打支线，不碰道具大师。"""
        self.log("=== 挑战支线开始 ===")
        self._force_back_to_battle()
        self.adb.tap(*TAB_CHALLENGE)
        self._sleep(CHALLENGE_TAB_WAIT)

        try:
            screen = self.adb.screencap()
        except AdbError as e:
            self.log(f"[挑战] 截图失败: {e}")
            self._force_back_to_battle()
            return

        pos = find_template(screen, CHALLENGE_BRANCH_ENTER_TPL, CHALLENGE_MATCH_THRESHOLD)
        if pos is None:
            # 整卡模板只是确认是否在支线页面；入口按钮没命中就不乱点
            card_pos = find_template(screen, CHALLENGE_BRANCH_CARD_TPL, CHALLENGE_MATCH_THRESHOLD)
            self.log(f"[挑战] 未匹配到支线进入游戏按钮，跳过 (card={card_pos})")
            self._force_back_to_battle()
            self.log("=== 挑战支线结束 ===")
            return

        self.log(f"[挑战] 点支线进入游戏 {pos}")
        self.adb.tap(*pos)
        self._sleep(CHALLENGE_ENTER_WAIT)

        deadline = time.time() + CHALLENGE_MAX_SECONDS
        enter_deadline = time.time() + 30
        entered_battle = False
        unknown = 0
        while time.time() < deadline and self.running:
            try:
                screen = self.adb.screencap()
            except AdbError:
                self._sleep(1.0)
                continue

            # 已打完回到挑战页：不再点进入，直接回战斗
            if entered_battle and find_template(screen, CHALLENGE_BRANCH_CARD_TPL, CHALLENGE_MATCH_THRESHOLD):
                self.log("[挑战] 已回到支线页，切回战斗")
                break
            if entered_battle and ocr_find_text(screen, "支线关卡", (0, 90, 540, 360), self.ocr):
                self.log("[挑战] OCR 已回到支线页，切回战斗")
                break

            if self._handle_challenge_reward_or_complete(screen):
                break

            state = detect_state(screen, self.ocr, detect_ad=False)
            if state == GameState.UNKNOWN and unknown + 1 >= AD_DETECT_UNKNOWN_AT:
                state = detect_state(screen, self.ocr, detect_ad=True)
            self.log(f"[挑战] 状态: {state}")

            if state == GameState.BATTLE:
                entered_battle = True
                unknown = 0
                self._handle_battle()
            elif state == GameState.SKILL_SELECT:
                entered_battle = True
                unknown = 0
                self._handle_skill_select(screen)
            elif state == GameState.SETTLE:
                entered_battle = True
                unknown = 0
                self._handle_settle(screen)
            elif state == GameState.REWARD_POPUP:
                self.adb.tap(*CHALLENGE_REWARD_CLOSE)
                self._sleep(0.8)
                break
            elif state == GameState.AD:
                self._handle_ad()
            elif state == GameState.WHEEL:
                self._handle_wheel()
            elif state == GameState.PERFECT_CLEAR:
                # 支线奖励页只点继续，不走主线 3 宝箱逻辑
                self.adb.tap(*CHALLENGE_REWARD_CLOSE)
                self._sleep(0.8)
                break
            elif state == GameState.HOME and entered_battle:
                break
            else:
                if not entered_battle and time.time() >= enter_deadline:
                    self.log("[挑战] 进入战斗超时，跳过本次支线")
                    break
                unknown += 1
                if unknown <= 3 or unknown % 10 == 0:
                    self.log(f"[挑战] 未知等待 ({unknown})")
                self._sleep(1.0)

        if time.time() >= deadline:
            self.log("[挑战] 超时，强制回战斗")
        self._force_back_to_battle()
        self.log("=== 挑战支线结束 ===")

    def _handle_challenge_reward_or_complete(self, screen):
        """挑战奖励页兜底：识别到获得奖励/点击屏幕继续/确认则处理并返回 True。"""
        # 结算页也有「获得奖励」字样，但必须先点底部确认，不能按奖励弹窗处理
        pos = find_settle_button(screen)
        if pos is not None:
            return False
        hits = ocr_find_text(screen, "确认", (150, 760, 390, 900), self.ocr)
        if hits:
            cx, cy, text = hits[0]
            self.log(f"[挑战] 点「{text.strip()}」({cx},{cy})")
            self.adb.tap(cx, cy)
            self._sleep(1.0)
            return False
        for kw in ("获得奖励", "点击屏幕继续"):
            if ocr_find_text(screen, kw, UNKNOWN_RESCUE_ROI, self.ocr):
                self.log(f"[挑战] 检测到「{kw}」，点继续 {CHALLENGE_REWARD_CLOSE}")
                self.adb.tap(*CHALLENGE_REWARD_CLOSE)
                self._sleep(0.8)
                return True
        return False

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
        if screen is not None and self._has_redot(screen, BATTLE_ORDER_WALL_REDOT_ROI, debug_label="城墙"):
            self.log("[战令] 城墙 tab 有红点，进入")
            self.adb.tap(*BATTLE_ORDER_WALL_TAB)
            self._sleep(0.8)
            self.adb.tap(*BATTLE_ORDER_CLAIM_BTN)
            self._sleep(BATTLE_ORDER_CLAIM_WAIT)
            self.adb.tap(*REWARD_OUTSIDE)
            self._sleep(0.5)
        # v0.5.22 用模板匹配点真返回按钮（战令必须点真「返回」才能回上级页面）
        try:
            screen2 = self.adb.screencap()
        except AdbError:
            screen2 = None
        back_pos = find_back_button(screen2) if screen2 is not None else None
        if back_pos:
            self.log(f"[战令] 点返回 {back_pos}")
            self.adb.tap(*back_pos)
        else:
            self.log("[战令] 未找到返回按钮，回退点空白")
            self.adb.tap(*REWARD_OUTSIDE)
        self._sleep(1.0)
        self._force_back_to_battle()
        self.log("=== 战令日常结束 ===")

    def _is_usable_ocr_button(self, text, required_kw, skip_keywords=CLAIM_SKIP_KEYWORDS):
        """判断 OCR 行是否像可点击按钮：包含目标词，且不含已领取/继续领取等干扰词"""
        norm = re.sub(r"\s+", "", text or "")
        if required_kw not in norm:
            return False
        return not any(bad and bad in norm for bad in skip_keywords)

    def _drain_ocr_buttons(self, label, keyword, roi, after_tap, max_rounds=20,
                           empty_recheck=CLAIM_EMPTY_RECHECK,
                           skip_keywords=CLAIM_SKIP_KEYWORDS,
                           close_pos=REWARD_OUTSIDE):
        """反复 OCR 当前页按钮，每次点一个后重新截图，避免动画/奖励弹窗导致漏领"""
        clicked = 0
        empty = 0
        for _ in range(max_rounds):
            if not self.running:
                break
            try:
                screen = self.adb.screencap()
            except AdbError:
                break
            hits = ocr_find_text(screen, keyword, roi, self.ocr)
            usable = [
                (cx, cy, text) for cx, cy, text in hits
                if self._is_usable_ocr_button(text, keyword, skip_keywords)
            ]
            if not usable:
                empty += 1
                if empty >= empty_recheck:
                    break
                self._sleep(0.5)
                continue
            empty = 0
            cx, cy, text = usable[0]
            self.log(f"[{label}] 点「{text.strip()}」({cx},{cy})")
            self.adb.tap(cx, cy)
            clicked += 1
            self._sleep(after_tap)
            self.adb.tap(*close_pos)
            self._sleep(0.5)
        if clicked:
            self.log(f"[{label}] 本轮共点击 {clicked} 个「{keyword}」")
        return clicked

    def _do_activity_daily(self, icon_pos):
        """活动日常：进入活动页 → 领取所有可领 → 关闭"""
        self.log(f"=== 活动日常开始 (入口 {icon_pos}) ===")
        self.adb.tap(*icon_pos)
        self._sleep(ACTIVITY_ENTER_WAIT)
        self._drain_ocr_buttons(
            "活动", ACTIVITY_CLAIM_KW, ACTIVITY_CLAIM_ROI,
            ACTIVITY_AFTER_CLAIM,
        )
        self.adb.tap(*REWARD_OUTSIDE)   # v0.5.18 改用空白处关，避免 X 按钮位置误触 tab
        self._sleep(0.8)
        self._force_back_to_battle()
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
            hits = ocr_find_text(screen, TIMED_ACTIVITY_SIGN_KW, TIMED_ACTIVITY_SIGN_ROI, self.ocr)
            # 找包含「签到」的按钮；逐行排除已签到/未开启等干扰，不用全 ROI blocklist
            for cx, cy, text in hits:
                if self._is_usable_ocr_button(
                    text, TIMED_ACTIVITY_SIGN_KW,
                    skip_keywords=("已签到", "已签", "未开启", "未开起", "继续领取"),
                ):
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
                self._sleep(TIMED_ACTIVITY_AFTER_SCROLL_WAIT)

        if not signed:
            self.log("[限时活动] 全屏遍历没找到「签到」按钮，可能今日已签")
        self.adb.tap(*REWARD_OUTSIDE)   # v0.5.18 改用空白处关
        self._sleep(0.8)
        self._force_back_to_battle()
        self.log("=== 限时活动日常结束 ===")

    def _do_seven_day_daily(self, icon_pos):
        """七日狂欢：多轮复扫 1-7 天红点 + 兜底遍历，避免动画/小红点漏识别导致漏领。"""
        self.log(f"=== 七日狂欢日常开始 (入口 {icon_pos}) ===")
        self.adb.tap(*icon_pos)
        self._sleep(SEVEN_DAY_ENTER_WAIT)

        for scan_round in range(SEVEN_DAY_RESCAN_ROUNDS):
            if not self.running:
                break
            try:
                screen = self.adb.screencap()
            except AdbError:
                break

            days_with_redot = []
            for idx, (tx, ty) in enumerate(SEVEN_DAY_TAB_POSITIONS, start=1):
                # 红点实测偏高，扩大 ROI；小红点漏识别时后面仍会遍历兜底
                roi = (max(0, tx), 145, min(screen.shape[1], tx + 55), 205)
                if self._has_redot(screen, roi, debug_label=f"7day-第{idx}天"):
                    days_with_redot.append(idx)

            ordered_days = list(days_with_redot)
            ordered_days += [d for d in range(1, len(SEVEN_DAY_TAB_POSITIONS) + 1) if d not in ordered_days]
            if days_with_redot:
                self.log(f"[七日狂欢] 第{scan_round+1}轮红点天: {days_with_redot}；随后遍历其余天防漏")
            else:
                self.log(f"[七日狂欢] 第{scan_round+1}轮红点未命中，兜底遍历 1-7 天")

            clicked_this_round = 0
            for day in ordered_days:
                if not self.running:
                    break
                tx, ty = SEVEN_DAY_TAB_POSITIONS[day - 1]
                self.log(f"[七日狂欢] 切第{day}天 tab ({tx},{ty})")
                self.adb.tap(tx, ty)
                self._sleep(SEVEN_DAY_PAGE_WAIT)

                self.adb.tap(*SEVEN_DAY_CHALLENGE_TAB)
                self._sleep(SEVEN_DAY_PAGE_WAIT)
                clicked_this_round += self._drain_ocr_buttons(
                    f"七日狂欢/第{day}天/挑战",
                    SEVEN_DAY_CLAIM_KW,
                    SEVEN_DAY_CLAIM_ROI,
                    SEVEN_DAY_AFTER_TAP,
                    close_pos=SEVEN_DAY_REWARD_CLOSE,
                )

                self.adb.tap(*SEVEN_DAY_GIFT_TAB)
                self._sleep(SEVEN_DAY_PAGE_WAIT)
                clicked_this_round += self._drain_ocr_buttons(
                    f"七日狂欢/第{day}天/好礼",
                    SEVEN_DAY_FREE_KW,
                    SEVEN_DAY_FREE_ROI,
                    SEVEN_DAY_AFTER_TAP,
                    max_rounds=3,
                    skip_keywords=("已领取", "已领"),
                    close_pos=SEVEN_DAY_REWARD_CLOSE,
                )

            if clicked_this_round <= 0:
                self.log("[七日狂欢] 本轮没有任何可领取项，结束复扫")
                break
            self.log(f"[七日狂欢] 第{scan_round+1}轮领取 {clicked_this_round} 个，继续复扫")

        self.adb.tap(*SEVEN_DAY_REWARD_CLOSE)
        self._sleep(0.8)
        self._force_back_to_battle()
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
        # 收紧条件：必须没有任何游戏内模板高分，且只在图标文字小 ROI 内命中，避免游戏中心/广告页误点
        scores = all_template_scores(screen)
        max_tpl_score = max(scores.values()) if scores else 0.0
        if (max_tpl_score < LAUNCH_GAME_MAX_TPL_SCORE and
                ocr_find_text(screen, LAUNCH_GAME_KW, LAUNCH_GAME_ROI, self.ocr)):
            self.log(f"[识别] 模拟器主页候选，点游戏图标「{LAUNCH_GAME_KW}」{LAUNCH_GAME_POS}")
            self.adb.tap(*LAUNCH_GAME_POS)
            self._sleep(8.0)
            try:
                screen2 = self.adb.screencap()
                state2 = detect_state(screen2, self.ocr, detect_ad=False)
                self.log(f"[识别] 启动后状态: {state2}")
            except AdbError:
                pass
            return

        if self.unknown_count <= 3 or self.unknown_count % 10 == 0:
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
        """看广告：右上角小 ROI 持续 OCR 等「关闭」出现 → 点。
        识别到跳过/秒时只等待；疑似暂停时点一次中心恢复播放；未确认关闭返回 False。
        """
        deadline = time.time() + timeout
        progress_seen_since = None
        resume_tapped = False
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
            has_progress = False
            for kw in ADS_PROGRESS_KEYWORDS:
                if ocr_find_text(screen, kw, ADS_SKIP_ROI, self.ocr):
                    has_progress = True
                    break
            if has_progress:
                if progress_seen_since is None:
                    progress_seen_since = time.time()
                if time.time() - progress_seen_since >= ADS_PAUSE_CHECK_SEC and not resume_tapped:
                    self.log(f"[广告] 疑似暂停，点中心恢复播放 {ADS_RESUME_TAP}")
                    self.adb.tap(*ADS_RESUME_TAP)
                    resume_tapped = True
                # 仍在广告进度页，继续等待关闭
            else:
                progress_seen_since = None
            self._sleep(ADS_POLL_INTERVAL)
        self.log(f"[广告] 超时 {timeout}s，未确认关闭，跳过后续点击")
        return False
