"""
筛选条件处理模块
处理日期选择、下拉框筛选、每页条数等操作
"""

import time
from typing import List, Optional

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from utils.logger import get_logger

logger = get_logger()


class FilterHandler:
    """筛选条件处理器"""

    def __init__(self, page: Page, config: dict):
        self.page = page
        self.config = config

    def set_date(self, date_str: str):
        """
        设置日期输入框（格式：YYYY-MM-DD）

        页面使用 Element UI 的 el-date-editor，日期标签「日期」与输入框在同一 el-form-item 内。
        通过定位包含「日期」的表单项再取 input，避免误匹配或结构差异导致定位失败。

        Args:
            date_str: 目标日期，必须为 YYYY-MM-DD 格式（如 2025-06-01）
        """
        logger.info("设置日期: %s", date_str)
        try:
            # 等待查询区域加载（日期控件在筛选表单内）
            self.page.wait_for_selector(".el-form-item, .el-date-editor, [class*='query']", timeout=10000)
            time.sleep(0.5)

            date_input = None

            # 优先：Element UI 表单项 - 包含「日期」文字的那一项内的 input
            try:
                form_item = self.page.locator(".el-form-item").filter(has_text="日期").first
                candidate = form_item.locator(".el-date-editor input, input").first
                if candidate.is_visible(timeout=3000):
                    date_input = candidate
            except Exception:
                pass

            if date_input is None:
                for selector in [
                    'input[placeholder*="日期"]',
                    'input[placeholder*="date"]',
                    'input[type="date"]',
                    '.el-date-editor input',
                ]:
                    try:
                        candidate = self.page.locator(selector).first
                        if candidate.is_visible(timeout=2000):
                            date_input = candidate
                            break
                    except Exception:
                        continue

            if date_input is None:
                # 最后回退：通过「日期」标签找父级再找 input（可能结构不同）
                label = self.page.locator("text=日期").first
                date_input = label.locator("xpath=ancestor::*[.//input][1]//input").first

            # 点击聚焦后清空并输入，严格使用 YYYY-MM-DD
            date_input.click(timeout=10000)
            time.sleep(0.5)
            date_input.press("Control+a")
            date_input.fill(date_str)
            time.sleep(0.3)
            date_input.press("Enter")
            time.sleep(0.5)

            logger.info("日期已设置为: %s", date_str)

        except Exception as e:
            logger.error("设置日期失败 [%s]: %s", date_str, e)
            raise

    def get_dropdown_options(self, dropdown_label: str) -> List[str]:
        """
        获取指定下拉框的所有选项。

        节点名称等下拉框选项可能由接口请求加载，需先点击/聚焦触发请求，
        再等待下拉列表出现后采集选项。

        Args:
            dropdown_label: 下拉框标签（如：节点名称、断面名称、机组名称等）

        Returns:
            选项文本列表
        """
        logger.info("获取下拉选项: %s", dropdown_label)
        options = []

        try:
            dropdown = self._find_dropdown(dropdown_label)
            if dropdown is None:
                logger.warning("未找到下拉框: %s", dropdown_label)
                return options

            # 点击展开，触发可能存在的异步加载（如节点名称）
            dropdown.click(timeout=10000)
            time.sleep(0.5)

            # 等待下拉列表出现（选项可能由请求加载后渲染）
            try:
                self.page.wait_for_selector(
                    ".el-select-dropdown__item, .el-select-dropdown .el-select-dropdown__list",
                    state="visible",
                    timeout=10000,
                )
            except Exception:
                pass
            time.sleep(1)

            option_selectors = [
                ".el-select-dropdown__item",
                ".el-dropdown-menu__item",
                "li.el-select-dropdown__item",
                ".ant-select-item-option",
            ]

            for sel in option_selectors:
                try:
                    items = self.page.locator(sel).all()
                    if items:
                        for item in items:
                            text = (item.text_content() or "").strip()
                            if text and text != "全部":
                                options.append(text)
                        break
                except Exception:
                    continue

            self.page.keyboard.press("Escape")
            time.sleep(0.5)

            logger.info("下拉选项 [%s]: 共 %d 个", dropdown_label, len(options))

        except Exception as e:
            logger.error("获取下拉选项失败 [%s]: %s", dropdown_label, e)

        return options

    def select_dropdown_option(self, dropdown_label: str, option_text: str):
        """
        选择下拉框中的指定选项。

        节点名称等选项可能需先点击触发加载，再等待列表出现后点击目标项。

        Args:
            dropdown_label: 下拉框标签
            option_text: 要选择的选项文本
        """
        logger.info("选择下拉选项: %s = %s", dropdown_label, option_text)
        try:
            dropdown = self._find_dropdown(dropdown_label)
            if dropdown is None:
                logger.warning("未找到下拉框: %s", dropdown_label)
                return

            dropdown.click(timeout=10000)
            time.sleep(0.5)

            # 等待下拉列表出现（异步加载的选项）
            try:
                self.page.wait_for_selector(
                    ".el-select-dropdown__item",
                    state="visible",
                    timeout=10000,
                )
            except Exception:
                pass
            time.sleep(0.5)

            option_found = False
            for sel in [".el-select-dropdown__item", "li.el-select-dropdown__item"]:
                items = self.page.locator(sel).all()
                for item in items:
                    if (item.text_content() or "").strip() == option_text:
                        item.click()
                        option_found = True
                        break
                if option_found:
                    break

            if not option_found:
                self.page.locator(f"text={option_text}").first.click()

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
                    element = self.page.locator(sel).first
                    if element.is_visible():
                        # 找到后点击旁边的下拉框
                        dropdown = element.locator(".. >> select, .. >> .el-input__inner").first
                        dropdown.click()
                        time.sleep(0.5)

                        # 选择目标条数
                        self.page.locator(f"text={size}").first.click()
                        time.sleep(1)
                        logger.info("已设置每页 %d 条", size)
                        return
                except Exception:
                    continue

            # 回退方案：直接查找带条数的 select
            selects = self.page.locator("select").all()
            for sel in selects:
                options = sel.locator("option").all()
                for opt in options:
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
                    btn = self.page.locator(sel).first
                    if btn.is_visible():
                        btn.click()
                        time.sleep(2)
                        self.page.wait_for_load_state("networkidle", timeout=15000)
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
        根据标签文本查找对应的下拉框元素。

        节点名称等为 el-select，标签「节点名称」与控件在同一 el-form-item 内，
        选项可能需点击后才通过请求加载。

        Args:
            label: 标签文本（如：节点名称、断面名称）

        Returns:
            下拉框元素（Locator）或 None
        """
        try:
            # 策略1：Element UI 表单项 - 包含该标签的那一项内的 .el-select 或 input
            form_item = self.page.locator(".el-form-item").filter(has_text=label).first
            dropdown = form_item.locator(
                ".el-select .el-input__inner, .el-input__inner, select"
            ).first
            if dropdown.is_visible(timeout=3000):
                return dropdown
        except Exception:
            pass

        try:
            # 策略2：标签旁边的 select/input
            label_el = self.page.locator(f"text={label}").first
            if label_el.is_visible(timeout=3000):
                parent = label_el.locator("..")
                dropdown = parent.locator(
                    "select, .el-select .el-input__inner, .el-input__inner"
                ).first
                if dropdown.is_visible(timeout=2000):
                    return dropdown
        except Exception:
            pass

        try:
            # 策略3：placeholder / aria-label
            for sel in [
                f'[placeholder*="{label}"]',
                f'[aria-label*="{label}"]',
                f'select[name*="{label}"]',
            ]:
                el = self.page.locator(sel).first
                if el.is_visible(timeout=2000):
                    return el
        except Exception:
            pass

        return None
