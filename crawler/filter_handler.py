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
        """等待筛选区域渲染完成"""
        try:
            self.ctx.wait_for_selector(
                ".el-form-item, .el-date-editor, .el-select, .el-input",
                timeout=10000,
            )
        except PlaywrightTimeout:
            logger.warning("筛选区域未在预期时间出现")

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

        通过清空并重新输入日期值，适配 Element UI DatePicker。
        需要先点击日期输入框打开日期面板，然后修改值并关闭面板。

        Args:
            date_str: 目标日期（YYYY-MM-DD）
        """
        logger.info("设置日期: %s", date_str)
        try:
            self._wait_for_filters_ready()

            date_input = None

            # 策略1：通过"日期"标签定位其旁边的日期输入框
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
                    ],
                )

            # 策略2：全局查找日期控件
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

            if date_input is None:
                raise RuntimeError("未找到日期输入框")

            # 点击日期输入框，打开日期面板
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

            # 定位下拉框
            dropdown = self._find_dropdown(dropdown_label)
            if dropdown is None:
                logger.warning("未找到下拉框: %s", dropdown_label)
                return options

            # 点击展开下拉框
            dropdown.click()
            time.sleep(1)

            # 等待下拉选项出现
            try:
                self.ctx.wait_for_selector(
                    ".el-select-dropdown__item",
                    timeout=5000,
                )
            except PlaywrightTimeout:
                logger.debug("等待下拉选项超时，继续尝试获取")

            # 获取下拉选项列表
            option_selectors = [
                ".el-select-dropdown__item",
                "li.el-select-dropdown__item",
                ".el-dropdown-menu__item",
            ]

            for sel in option_selectors:
                try:
                    items = self.ctx.locator(sel).all()
                    if items:
                        for item in items:
                            try:
                                text = item.text_content().strip()
                                if text and text != "全部":
                                    options.append(text)
                            except Exception:
                                continue
                        if options:
                            break
                except Exception:
                    continue

            # 关闭下拉框
            try:
                self.page.keyboard.press("Escape")
            except Exception:
                pass
            time.sleep(0.5)

            logger.info("下拉选项 [%s]: 共 %d 个", dropdown_label, len(options))

        except Exception as e:
            logger.error("获取下拉选项失败 [%s]: %s", dropdown_label, e)

        return options

    def select_dropdown_option(self, dropdown_label: str, option_text: str):
        """
        选择下拉框中的指定选项

        Args:
            dropdown_label: 下拉框标签
            option_text: 要选择的选项文本
        """
        logger.info("选择下拉选项: %s = %s", dropdown_label, option_text)
        try:
            self._wait_for_filters_ready()

            dropdown = self._find_dropdown(dropdown_label)
            if dropdown is None:
                logger.warning("未找到下拉框: %s", dropdown_label)
                return

            dropdown.click()
            time.sleep(1)

            # 等待下拉选项出现
            try:
                self.ctx.wait_for_selector(
                    ".el-select-dropdown__item",
                    timeout=5000,
                )
            except PlaywrightTimeout:
                pass

            # 在下拉列表中查找并点击目标选项
            option_found = False
            option_selectors = [
                ".el-select-dropdown__item",
                "li.el-select-dropdown__item",
            ]

            for sel in option_selectors:
                try:
                    items = self.ctx.locator(sel).all()
                    for item in items:
                        if item.text_content().strip() == option_text:
                            item.click()
                            option_found = True
                            break
                    if option_found:
                        break
                except Exception:
                    continue

            if not option_found:
                # 尝试直接通过文本点击
                self.ctx.locator(f"text={option_text}").first.click()

            time.sleep(0.5)
            logger.info("已选择: %s", option_text)

        except Exception as e:
            logger.error("选择下拉选项失败 [%s=%s]: %s", dropdown_label, option_text, e)
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
        根据标签文本查找对应的下拉框元素

        Args:
            label: 标签文本

        Returns:
            下拉框元素（Locator）或 None
        """
        try:
            # 策略1：表单项容器内查找
            form_item = self._find_form_item(label)
            if form_item is not None:
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
                    return dropdown
        except Exception:
            pass

        try:
            # 策略2：直接查找 aria-label 或 placeholder
            selectors = [
                f'[aria-label*="{label}"]',
                f'[placeholder*="{label}"]',
                f'select[name*="{label}"]',
            ]
            for sel in selectors:
                el = self.ctx.locator(sel).first
                if el.is_visible():
                    return el
        except Exception:
            pass

        try:
            # 策略3：通过标签文本找到旁边的 input
            label_el = self.ctx.locator(f"text={label}").first
            if label_el.is_visible():
                parent = label_el.locator("..")
                dropdown = parent.locator(
                    "select, .el-select .el-input__inner, .el-input__inner"
                ).first
                if dropdown.is_visible():
                    return dropdown
        except Exception:
            pass

        return None
