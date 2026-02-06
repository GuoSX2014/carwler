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

        通过清空并重新输入日期值，适配大多数日期选择器

        Args:
            date_str: 目标日期（YYYY-MM-DD）
        """
        logger.info("设置日期: %s", date_str)
        try:
            # 尝试定位日期输入框 - 多种可能的选择器
            date_selectors = [
                'input[placeholder*="日期"]',
                'input[placeholder*="date"]',
                'input[type="date"]',
                '.el-date-editor input',
                'input.el-input__inner',
            ]

            date_input = None
            for selector in date_selectors:
                try:
                    # 寻找日期标签旁边的输入框
                    candidate = self.page.locator(selector).first
                    if candidate.is_visible():
                        date_input = candidate
                        break
                except Exception:
                    continue

            if date_input is None:
                # 回退方案：通过"日期"标签定位
                label = self.page.locator("text=日期").first
                date_input = label.locator(".. >> input").first

            # 清空并输入新日期
            date_input.click()
            time.sleep(0.5)

            # 全选并删除现有内容
            date_input.press("Control+a")
            date_input.fill(date_str)
            time.sleep(0.3)

            # 按回车确认
            date_input.press("Enter")
            time.sleep(0.5)

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
            # 定位下拉框
            dropdown = self._find_dropdown(dropdown_label)
            if dropdown is None:
                logger.warning("未找到下拉框: %s", dropdown_label)
                return options

            # 点击展开下拉框
            dropdown.click()
            time.sleep(1)

            # 获取下拉选项列表
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
                            text = item.text_content().strip()
                            if text and text != "全部":
                                options.append(text)
                        break
                except Exception:
                    continue

            # 关闭下拉框（点击空白处）
            self.page.keyboard.press("Escape")
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
            dropdown = self._find_dropdown(dropdown_label)
            if dropdown is None:
                logger.warning("未找到下拉框: %s", dropdown_label)
                return

            dropdown.click()
            time.sleep(1)

            # 在下拉列表中查找并点击目标选项
            option_found = False
            option_selectors = [
                ".el-select-dropdown__item",
                "li.el-select-dropdown__item",
            ]

            for sel in option_selectors:
                items = self.page.locator(sel).all()
                for item in items:
                    if item.text_content().strip() == option_text:
                        item.click()
                        option_found = True
                        break
                if option_found:
                    break

            if not option_found:
                # 尝试直接通过文本点击
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
        根据标签文本查找对应的下拉框元素

        Args:
            label: 标签文本

        Returns:
            下拉框元素（Locator）或 None
        """
        try:
            # 策略1：label 旁边的 select/input
            label_el = self.page.locator(f"text={label}").first
            if label_el.is_visible():
                # 尝试找同级或相邻的下拉框
                parent = label_el.locator("..")
                dropdown = parent.locator(
                    "select, .el-select .el-input__inner, .el-input__inner"
                ).first
                if dropdown.is_visible():
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
                el = self.page.locator(sel).first
                if el.is_visible():
                    return el
        except Exception:
            pass

        return None
