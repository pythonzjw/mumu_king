# CONTEXT_HANDOFF

## 当前目标
修复结算失败后点确定变慢、保留结算双倍、七日狂欢/商店漏识别，并给技能选择增加 GUI 禁选关键字输入框。

## 已完成
- 结算页 `_handle_settle` 恢复双倍逻辑；OCR 到 `0/3` 时跳过双倍直接确认，有次数时仍点双倍看广告。
- GUI 增加「禁止选择关键字」输入框，逗号分隔；启动后传给 Worker，命中禁选词的卡优先跳过。
- 七日狂欢切第 N 天、切「每日挑战/每日好礼」后统一等待 1s 再截图 OCR。
- 商店每次滑动后统一等待 1s 再识别「免费」。

## 已修改文件
- `config.py`
- `gui.py`
- `main.py`
- `manager.py`
- `worker.py`
- `settings.py`
- `CONTEXT_HANDOFF.md`

## 关键决策
- 结算双倍保留，但 `0/3` 时不点，避免等待广告超时。
- 3 张技能卡都命中禁选词时回退允许全部，避免卡死。
- GUI 禁选关键字会保存到 `settings.json` 的 `banned_skill_keywords`。
- 不新增依赖，不改状态机结构。

## 验证情况
- 已执行：`python3 -m py_compile main.py config.py worker.py recognizer.py adb.py manager.py gui.py settings.py`
- 结果：通过。

## 未完成事项
- 需要实机确认七日狂欢第 5 天「领取」和商店「免费获取」是否稳定点击。

## 下一步
- 如仍漏点，基于实际 debug 截图继续校准 OCR ROI 或改为模板匹配按钮。

## 已知问题
- 禁选关键字默认空列表，需要在 GUI 输入框里按逗号填写。
