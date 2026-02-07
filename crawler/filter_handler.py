"""
筛选条件处理模块
处理日期选择、下拉框筛选、每页条数等操作

注意：页面内容（日期输入框、下拉框、查询按钮等）通常在 iframe 内部，
需要通过 self.ctx 指向正确的 Frame 上下文才能找到元素。
self.page 保留对主页面 Page 的引用，用于 keyboard 等仅 Page 支持的操作。
"""

import time
from typing import List, Optional, Union

from playwright.sync_api import Page, Frame, TimeoutError as PlaywrightTimeout

from utils.logger import get_logger

logger = get_logger()


class FilterHandler:
    """筛选条件处理器"""

    def __init__(self, page: Page, config: dict):
        self.page = page
        # ctx 指向实际操作 DOM 的上下文（Frame 或 Page）
        # 默认为 page，在检测到 iframe 后会被替换为 iframe 的 Frame
        self.ctx: Union[Page, Frame] = page
        self.config = config

    def _wait_for_filters_ready(self):
        """
        等待筛选区域渲染完成。

        不同页面可能使用不同的前端框架：
        - Element UI 页面：使用 .el-form-item, .el-date-editor 等类
        - 其他页面（如抽蓄电站水位）：使用标准 HTML input, button 等

        处理两种异常：
        - PlaywrightTimeout: 超时但 Frame 仍有效，可以继续尝试
        - 其他异常（如 Frame was detached）: Frame 失效，需要抛出让上层重试
        """
        try:
            # 先尝试 Element UI 选择器
            self.ctx.wait_for_selector(
                ".el-form-item, .el-date-editor, .el-select, .el-input",
                timeout=10000,
            )
            return
        except PlaywrightTimeout:
            pass
        except Exception as e:
            err_msg = str(e)
            if "detached" in err_msg.lower():
                logger.error("iframe 已 detached，需要重新检测: %s", err_msg)
                raise
            logger.warning("等待筛选区域时出现异常: %s", e)
            return

        # Element UI 选择器未匹配，尝试通用选择器（适配非 Element UI 页面）
        try:
            self.ctx.wait_for_selector(
                "input, select, button, form, table",
                timeout=10000,
            )
            logger.debug("通过通用选择器检测到筛选区域")
        except PlaywrightTimeout:
            logger.warning("筛选区域未在预期时间出现（Element UI 和通用选择器均未匹配）")
        except Exception as e:
            err_msg = str(e)
            if "detached" in err_msg.lower():
                logger.error("iframe 已 detached，需要重新检测: %s", err_msg)
                raise
            logger.warning("等待筛选区域时出现异常: %s", e)

    def _find_form_item(self, label: str):
        """根据标签文本查找对应的表单项容器"""
        # 策略1：el-form-item 容器
        try:
            form_item = self.ctx.locator(".el-form-item").filter(
                has_text=label
            ).first
            if form_item and form_item.is_visible():
                return form_item
        except Exception:
            pass

        # 策略2：通过 label 文本向上查找 el-form-item 祖先
        try:
            label_el = self.ctx.locator(f"text={label}").first
            if label_el.is_visible():
                return label_el.locator(
                    "xpath=ancestor::div[contains(@class,'el-form-item')][1]"
                )
        except Exception:
            pass

        # 策略3：label 的直接父级（有些页面不使用 el-form-item）
        try:
            label_el = self.ctx.locator(f"text={label}").first
            if label_el.is_visible():
                return label_el.locator("..")
        except Exception:
            pass

        return None

    @staticmethod
    def _pick_visible_input(container, selectors: List[str]):
        """在容器内按顺序选择第一个可见输入框"""
        for sel in selectors:
            try:
                candidate = container.locator(sel).first
                if candidate and candidate.is_visible():
                    return candidate
            except Exception:
                continue
        return None

    def set_date(self, date_str: str):
        """
        设置日期输入框（格式：YYYY-MM-DD）

        适配多种页面类型：
        - Element UI DatePicker 页面（如：实时节点边际电价等）
        - 普通文本输入框页面（如：抽蓄电站水位等）

        通过多种策略查找日期输入框，优先尝试 Element UI 选择器，
        回退到通用选择器。

        Args:
            date_str: 目标日期（YYYY-MM-DD）
        """
        logger.info("设置日期: %s", date_str)
        try:
            self._wait_for_filters_ready()

            date_input = None

            # 策略1：通过"日期"标签定位其旁边的日期输入框（Element UI）
            form_item = self._find_form_item("日期")
            if form_item is not None:
                date_input = self._pick_visible_input(
                    form_item,
                    [
                        ".el-date-editor input",
                        ".el-date-editor .el-input__inner",
                        'input[placeholder*="日期"]',
                        'input[placeholder*="date"]',
                        ".el-input__inner",
                        "input",
                    ],
                )

            # 策略2：全局查找 Element UI 日期控件
            if date_input is None:
                date_input = self._pick_visible_input(
                    self.ctx,
                    [
                        ".el-date-editor input",
                        ".el-date-editor .el-input__inner",
                        'input[placeholder*="日期"]',
                        'input[placeholder*="date"]',
                        'input[type="date"]',
                    ],
                )

            # 策略3：通过标签文本查找附近的 input（适配非 Element UI 页面）
            if date_input is None:
                for label_text in ["日期", "运行日期", "查询日期", "选择日期", "日"]:
                    try:
                        label_el = self.ctx.locator(f"text={label_text}").first
                        if label_el and label_el.is_visible():
                            # 向上遍历父级，查找附近的 input
                            for level in range(1, 6):
                                ancestor = label_el
                                for _ in range(level):
                                    ancestor = ancestor.locator("..")
                                try:
                                    inp = ancestor.locator("input").first
                                    if inp and inp.is_visible():
                                        date_input = inp
                                        logger.debug(
                                            "通过标签「%s」+ 父级(level=%d)找到日期输入框",
                                            label_text, level,
                                        )
                                        break
                                except Exception:
                                    continue
                            if date_input is not None:
                                break
                    except Exception:
                        continue

            # 策略4：查找值包含日期格式的 input（当前页面已有日期值）
            if date_input is None:
                try:
                    inputs = self.ctx.locator("input").all()
                    for inp in inputs:
                        try:
                            if inp.is_visible():
                                val = inp.input_value().strip()
                                # 检查值是否类似日期格式 YYYY-MM-DD
                                if val and len(val) == 10 and val[4] == "-" and val[7] == "-":
                                    date_input = inp
                                    logger.debug("通过已有日期值找到日期输入框: %s", val)
                                    break
                        except Exception:
                            continue
                except Exception:
                    pass

            if date_input is None:
                raise RuntimeError("未找到日期输入框")

            # 点击日期输入框
            date_input.click()
            time.sleep(0.5)

            # 全选已有内容，输入新日期
            date_input.press("Control+a")
            time.sleep(0.1)
            date_input.fill(date_str)
            time.sleep(0.3)

            # 验证输入值，如果 fill 不生效则用 JS 直接赋值
            try:
                current = date_input.input_value().strip()
                if current != date_str:
                    logger.debug("fill 输入未生效 (%s)，使用 JS 赋值", current)
                    self.ctx.evaluate(
                        """([el, val]) => {
                            el.value = val;
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                        }""",
                        [date_input.element_handle(), date_str],
                    )
            except Exception:
                pass

            # 按回车确认
            try:
                date_input.press("Enter")
            except Exception:
                pass
            time.sleep(0.3)

            # 按 Escape 关闭日期面板（如果还在显示）
            try:
                self.page.keyboard.press("Escape")
            except Exception:
                pass
            time.sleep(0.5)

            # 点击页面空白处确保日期面板关闭
            try:
                self.ctx.locator("body").click(position={"x": 0, "y": 0})
            except Exception:
                pass
            time.sleep(0.3)

            logger.info("日期已设置为: %s", date_str)

        except Exception as e:
            logger.error("设置日期失败 [%s]: %s", date_str, e)
            raise

    def _find_active_dropdown_panel(self):
        """
        找到当前打开的（可见的）el-select 下拉面板。

        Element UI 的下拉面板 .el-select-dropdown.el-popper 挂载在 body 上，
        页面上可能存在多个面板（如节点名称下拉、分页条数下拉等），
        但同一时刻只有一个是可见的（正在展开的那个）。

        Returns:
            可见的下拉面板 Locator，未找到返回 None
        """
        try:
            panels = self.ctx.locator(".el-select-dropdown.el-popper").all()
            for panel in panels:
                try:
                    if panel.is_visible():
                        return panel
                except Exception:
                    continue
        except Exception:
            pass
        return None

    def _open_dropdown_panel(self, dropdown_label: str):
        """
        打开指定标签的下拉框面板，并等待面板出现。

        Element UI 的 el-select 下拉面板是独立 DOM 节点，
        挂载在 <body> 上（不在 el-select 内部），需要通过
        可见性检查来定位当前打开的面板。

        Args:
            dropdown_label: 下拉框标签

        Returns:
            下拉输入框 Locator

        Raises:
            RuntimeError: 未找到下拉框
        """
        dropdown = self._find_dropdown(dropdown_label)
        if dropdown is None:
            raise RuntimeError(f"未找到下拉框: {dropdown_label}")

        # 先关闭可能已打开的面板
        try:
            self.page.keyboard.press("Escape")
            time.sleep(0.5)
        except Exception:
            pass

        # 确保所有面板都已关闭
        for _ in range(5):
            if self._find_active_dropdown_panel() is None:
                break
            time.sleep(0.3)

        # 点击打开下拉面板
        dropdown.click()
        time.sleep(0.8)

        # 等待目标下拉面板出现（通过检测可见面板）
        panel = None
        for attempt in range(3):
            # 检查是否有面板变为可见
            panel = self._find_active_dropdown_panel()
            if panel:
                # 确认面板中有选项
                try:
                    item_count = panel.locator(".el-select-dropdown__item").count()
                    if item_count > 0:
                        logger.debug("下拉面板已出现，包含 %d 个选项", item_count)
                        break
                except Exception:
                    pass

            if attempt < 2:
                # 重试：再次点击下拉框
                logger.debug("下拉面板未出现，重试点击... (第%d次)", attempt + 2)
                try:
                    # 先关闭可能打开的其他面板
                    self.page.keyboard.press("Escape")
                    time.sleep(0.3)
                except Exception:
                    pass
                dropdown.click()
                time.sleep(1.5)

        if panel is None or not panel.is_visible():
            logger.warning("下拉面板仍未出现，尝试使用 JavaScript 触发")
            # 最后手段：通过 JS 点击 el-select 容器触发展开
            try:
                self.ctx.evaluate("""(inputEl) => {
                    const selectEl = inputEl.closest('.el-select');
                    if (selectEl) {
                        const input = selectEl.querySelector('.el-input__inner');
                        if (input) {
                            input.click();
                            input.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                            input.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                        }
                    }
                }""", dropdown.element_handle())
                time.sleep(1.5)
                panel = self._find_active_dropdown_panel()
            except Exception as e:
                logger.debug("JS 触发下拉面板失败: %s", e)

        if panel is None:
            logger.warning("下拉面板最终未能打开")

        return dropdown

    def _close_dropdown_panel(self):
        """关闭当前打开的下拉面板"""
        try:
            self.page.keyboard.press("Escape")
        except Exception:
            pass
        time.sleep(0.3)

    def _collect_visible_dropdown_items(self) -> List[str]:
        """
        从当前打开的下拉面板中收集所有选项文本。

        关键：页面上可能存在多个下拉面板（如节点名称、分页条数等），
        必须只从当前打开（可见）的面板中收集选项，避免混入其他面板的内容。

        Element UI 的 el-select 下拉面板可能包含可滚动列表，
        但所有选项 DOM 节点都存在（非虚拟滚动），可以一次性获取。

        Returns:
            选项文本列表
        """
        options = []
        try:
            # 关键修复：仅从当前打开的可见面板中收集选项
            panel = self._find_active_dropdown_panel()
            if panel is None:
                logger.warning("未找到可见的下拉面板，无法收集选项")
                return options

            # 优先取 span 内文本（更精确），回退到 li 自身文本
            items = panel.locator(".el-select-dropdown__item").all()
            for item in items:
                try:
                    # 优先读 span 子元素的文本
                    span = item.locator("span").first
                    text = ""
                    try:
                        text = span.text_content().strip()
                    except Exception:
                        text = item.text_content().strip()
                    if text and text != "全部" and text not in options:
                        options.append(text)
                except Exception:
                    continue
        except Exception as e:
            logger.debug("收集下拉选项失败: %s", e)
        return options

    def get_dropdown_options(self, dropdown_label: str) -> List[str]:
        """
        获取指定下拉框的所有选项

        Args:
            dropdown_label: 下拉框标签（如：节点名称、断面名称、机组名称等）

        Returns:
            选项文本列表
        """
        logger.info("获取下拉选项: %s", dropdown_label)
        options = []

        try:
            self._wait_for_filters_ready()

            # 打开下拉面板
            self._open_dropdown_panel(dropdown_label)

            # 收集选项
            options = self._collect_visible_dropdown_items()

            # 关闭面板
            self._close_dropdown_panel()

            logger.info("下拉选项 [%s]: 共 %d 个", dropdown_label, len(options))
            if options:
                logger.info("  前5个: %s%s",
                            options[:5],
                            " ..." if len(options) > 5 else "")

        except Exception as e:
            logger.error("获取下拉选项失败 [%s]: %s", dropdown_label, e)
            self._close_dropdown_panel()

        return options

    def select_dropdown_option(self, dropdown_label: str, option_text: str):
        """
        选择下拉框中的指定选项。

        流程：
        1. 打开下拉面板
        2. 在当前可见面板中找到目标选项
        3. 滚动到可见区域并点击
        4. 等待面板关闭
        5. 验证选择结果

        关键：必须只在当前打开的面板中查找，避免误点击其他面板的选项。

        Args:
            dropdown_label: 下拉框标签
            option_text: 要选择的选项文本
        """
        logger.info("选择下拉选项: %s = %s", dropdown_label, option_text)
        try:
            self._wait_for_filters_ready()

            # 打开下拉面板
            self._open_dropdown_panel(dropdown_label)
            time.sleep(0.3)

            # 关键：找到当前打开的面板，仅在其中查找选项
            panel = self._find_active_dropdown_panel()
            if panel is None:
                self._close_dropdown_panel()
                raise RuntimeError(
                    f"下拉面板未打开，无法选择选项: {option_text}"
                )

            # 在面板中查找目标选项并点击
            option_found = False

            # 策略1：精确匹配 el-select-dropdown__item（限定在当前面板内）
            try:
                items = panel.locator(".el-select-dropdown__item").all()
                for item in items:
                    try:
                        text = item.text_content().strip()
                        if text == option_text:
                            # 滚动到可见区域
                            item.scroll_into_view_if_needed()
                            time.sleep(0.2)
                            item.click()
                            option_found = True
                            logger.debug("通过精确匹配点击选项: %s", option_text)
                            break
                    except Exception:
                        continue
            except Exception as e:
                logger.debug("策略1查找选项失败: %s", e)

            # 策略2：通过 span 子元素的文本精确匹配（限定在当前面板内）
            if not option_found:
                try:
                    items = panel.locator(
                        ".el-select-dropdown__item span"
                    ).all()
                    for item in items:
                        try:
                            text = item.text_content().strip()
                            if text == option_text:
                                parent = item.locator("..")
                                parent.scroll_into_view_if_needed()
                                time.sleep(0.2)
                                parent.click()
                                option_found = True
                                logger.debug("通过span子元素点击选项: %s", option_text)
                                break
                        except Exception:
                            continue
                except Exception as e:
                    logger.debug("策略2查找选项失败: %s", e)

            # 策略3：使用 has-text 精确文本匹配（限定在当前面板内）
            if not option_found:
                try:
                    target = panel.locator(
                        f'.el-select-dropdown__item:has-text("{option_text}")'
                    ).first
                    if target.is_visible():
                        target.scroll_into_view_if_needed()
                        time.sleep(0.2)
                        target.click()
                        option_found = True
                        logger.debug("通过has-text点击选项: %s", option_text)
                except Exception as e:
                    logger.debug("策略3查找选项失败: %s", e)

            if not option_found:
                self._close_dropdown_panel()
                raise RuntimeError(f"未在下拉选项中找到: {option_text}")

            # 等待下拉面板自动关闭（el-select 选中后自动收起）
            time.sleep(0.5)

            logger.info("已选择: %s = %s", dropdown_label, option_text)

        except Exception as e:
            logger.error("选择下拉选项失败 [%s=%s]: %s", dropdown_label, option_text, e)
            self._close_dropdown_panel()
            raise

    def set_page_size(self, size: int = 50):
        """
        设置每页显示条数

        Args:
            size: 每页条数（10/20/30/40/50）
        """
        logger.info("设置每页条数: %d", size)
        try:
            # 查找每页条数下拉框
            page_size_selectors = [
                "text=每页条数",
                "text=每页展示",
                ".el-pagination .el-select",
            ]

            for sel in page_size_selectors:
                try:
                    element = self.ctx.locator(sel).first
                    if element.is_visible():
                        # 找到后点击旁边的下拉框
                        dropdown = element.locator(".. >> select, .. >> .el-input__inner").first
                        dropdown.click()
                        time.sleep(0.5)

                        # 选择目标条数
                        self.ctx.locator(f"text={size}").first.click()
                        time.sleep(1)
                        logger.info("已设置每页 %d 条", size)
                        return
                except Exception:
                    continue

            # 回退方案：直接查找带条数的 select
            selects = self.ctx.locator("select").all()
            for sel in selects:
                opts = sel.locator("option").all()
                for opt in opts:
                    if str(size) in opt.text_content():
                        sel.select_option(str(size))
                        time.sleep(1)
                        logger.info("已设置每页 %d 条", size)
                        return

            logger.warning("未找到每页条数选择器")

        except Exception as e:
            logger.error("设置每页条数失败: %s", e)

    def click_query_button(self):
        """点击「查询」按钮"""
        logger.info("点击「查询」按钮")
        try:
            query_selectors = [
                'button:has-text("查询")',
                'button:has-text("查 询")',
                "text=查询",
                ".query-btn",
                'button[type="primary"]',
            ]

            for sel in query_selectors:
                try:
                    btn = self.ctx.locator(sel).first
                    if btn.is_visible():
                        btn.click()
                        time.sleep(2)
                        try:
                            self.ctx.wait_for_load_state("networkidle", timeout=15000)
                        except Exception:
                            pass
                        logger.info("查询已执行")
                        return
                except Exception:
                    continue

            logger.warning("未找到查询按钮")

        except Exception as e:
            logger.error("点击查询按钮失败: %s", e)
            raise

    def _find_dropdown(self, label: str):
        """
        根据标签文本查找对应的下拉框输入元素。

        Element UI el-select 的典型 DOM 结构：
          <div class="el-form-item">
            <label>节点名称</label>
            <div class="el-form-item__content">
              <div class="el-select">
                <div class="el-input">
                  <input class="el-input__inner" placeholder="请选择">
                  <span class="el-input__suffix">
                    <i class="el-select__caret el-input__icon el-icon-arrow-up"></i>
                  </span>
                </div>
              </div>
            </div>
          </div>

        点击 .el-input__inner 或 .el-select 容器都可以打开下拉面板。

        Args:
            label: 标签文本

        Returns:
            下拉框输入元素（Locator）或 None
        """
        # 策略1：通过表单项容器查找
        try:
            form_item = self._find_form_item(label)
            if form_item is not None:
                # 优先找 el-select 的 input
                dropdown = self._pick_visible_input(
                    form_item,
                    [
                        ".el-select .el-input__inner",
                        ".el-select input",
                        "input[role='combobox']",
                        "select",
                        ".el-input__inner",
                    ],
                )
                if dropdown is not None:
                    logger.debug("通过表单项容器找到下拉框: %s", label)
                    return dropdown
        except Exception:
            pass

        # 策略2：通过标签文本 + 紧邻的 el-select 查找
        try:
            label_el = self.ctx.locator(f"text={label}").first
            if label_el.is_visible():
                # 向上找父级容器，在其中寻找 el-select
                for level in range(1, 5):
                    ancestor = label_el
                    for _ in range(level):
                        ancestor = ancestor.locator("..")
                    try:
                        select_input = ancestor.locator(
                            ".el-select .el-input__inner"
                        ).first
                        if select_input.is_visible():
                            logger.debug(
                                "通过标签祖先(level=%d)找到下拉框: %s",
                                level, label,
                            )
                            return select_input
                    except Exception:
                        continue
        except Exception:
            pass

        # 策略3：直接查找 placeholder / aria-label 匹配的输入框
        try:
            selectors = [
                f'[aria-label*="{label}"]',
                f'[placeholder*="{label}"]',
                f'select[name*="{label}"]',
            ]
            for sel in selectors:
                el = self.ctx.locator(sel).first
                if el.is_visible():
                    logger.debug("通过属性选择器找到下拉框: %s", label)
                    return el
        except Exception:
            pass

        # 策略4：通过标签文本找到相邻的 input
        try:
            label_el = self.ctx.locator(f"text={label}").first
            if label_el.is_visible():
                parent = label_el.locator("..")
                dropdown = parent.locator(
                    "select, .el-select .el-input__inner, .el-input__inner"
                ).first
                if dropdown.is_visible():
                    logger.debug("通过标签直接父级找到下拉框: %s", label)
                    return dropdown
        except Exception:
            pass

        logger.warning("所有策略均未找到下拉框: %s", label)
        return None
