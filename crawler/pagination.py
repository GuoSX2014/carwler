"""
分页处理模块
处理表格的分页控件和滚动加载

注意：分页控件在 iframe 内部，需要通过 self.ctx 指向正确的 Frame 上下文。
"""

import time
from typing import Optional, Union

from playwright.sync_api import Page, Frame, TimeoutError as PlaywrightTimeout

from utils.logger import get_logger

logger = get_logger()


class PaginationHandler:
    """分页处理器"""

    def __init__(self, page: Page, config: dict):
        self.page = page
        # ctx 指向实际操作 DOM 的上下文（Frame 或 Page）
        self.ctx: Union[Page, Frame] = page
        self.config = config
        self.page_interval = config.get("request", {}).get("page_interval", 2)

    def get_total_pages(self) -> int:
        """
        获取总页数

        Returns:
            总页数，如果无法获取返回 1
        """
        try:
            # 方式1：查找 "/N" 样式的总页数显示
            pager_selectors = [
                ".el-pagination__total",
                ".el-pager li:last-child",
                'text=/\\/\\d+/',
            ]

            for sel in pager_selectors:
                try:
                    el = self.ctx.locator(sel).first
                    if el.is_visible():
                        text = el.text_content().strip()
                        # 提取数字
                        import re
                        nums = re.findall(r"\d+", text)
                        if nums:
                            return int(nums[-1])
                except Exception:
                    continue

            # 方式2：查找页码输入框旁边的总页数
            try:
                total_text = self.ctx.locator('text=/\\/\\s*\\d+/').first
                if total_text.is_visible():
                    text = total_text.text_content()
                    import re
                    match = re.search(r"/\s*(\d+)", text)
                    if match:
                        return int(match.group(1))
            except Exception:
                pass

            logger.debug("未找到总页数，默认为 1 页")
            return 1

        except Exception as e:
            logger.warning("获取总页数失败: %s", e)
            return 1

    def has_next_page(self) -> bool:
        """
        检查是否有下一页

        Returns:
            是否有下一页
        """
        try:
            next_selectors = [
                'button:has-text("下一页")',
                ".el-pagination .btn-next",
                'text=下一页',
                "button.btn-next",
            ]

            for sel in next_selectors:
                try:
                    btn = self.ctx.locator(sel).first
                    if btn.is_visible():
                        # 检查按钮是否禁用
                        disabled = btn.get_attribute("disabled")
                        is_disabled = btn.locator(".is-disabled").count() > 0
                        has_disabled_class = "disabled" in (
                            btn.get_attribute("class") or ""
                        )
                        if disabled is not None or is_disabled or has_disabled_class:
                            return False
                        return True
                except Exception:
                    continue

            return False

        except Exception:
            return False

    def go_next_page(self) -> bool:
        """
        翻到下一页

        Returns:
            是否成功翻页
        """
        try:
            next_selectors = [
                'button:has-text("下一页")',
                ".el-pagination .btn-next",
                'text=下一页',
                "button.btn-next",
            ]

            for sel in next_selectors:
                try:
                    btn = self.ctx.locator(sel).first
                    if btn.is_visible() and btn.is_enabled():
                        btn.click()
                        time.sleep(self.page_interval)
                        try:
                            self.ctx.wait_for_load_state(
                                "networkidle", timeout=10000
                            )
                        except Exception:
                            pass
                        logger.debug("已翻到下一页")
                        return True
                except Exception:
                    continue

            logger.debug("无法翻到下一页")
            return False

        except Exception as e:
            logger.warning("翻页失败: %s", e)
            return False

    def go_to_page(self, page_num: int) -> bool:
        """
        跳转到指定页码

        Args:
            page_num: 目标页码

        Returns:
            是否成功跳转
        """
        try:
            # 查找页码输入框
            page_input_selectors = [
                ".el-pagination .el-input__inner",
                'input[type="number"]',
                ".el-pager .number",
            ]

            for sel in page_input_selectors:
                try:
                    inp = self.ctx.locator(sel).first
                    if inp.is_visible():
                        inp.click()
                        inp.fill(str(page_num))
                        inp.press("Enter")
                        time.sleep(self.page_interval)
                        try:
                            self.ctx.wait_for_load_state(
                                "networkidle", timeout=10000
                            )
                        except Exception:
                            pass
                        logger.debug("已跳转到第 %d 页", page_num)
                        return True
                except Exception:
                    continue

            logger.warning("无法跳转到第 %d 页", page_num)
            return False

        except Exception as e:
            logger.warning("页码跳转失败: %s", e)
            return False

    def scroll_to_load_all(self, container_selector: Optional[str] = None):
        """
        滚动加载所有数据（针对无分页但有滚动条的表格）

        Args:
            container_selector: 滚动容器选择器
        """
        logger.info("开始滚动加载数据...")

        scroll_target = container_selector or "table"
        previous_height = 0
        max_attempts = 50
        attempts = 0

        while attempts < max_attempts:
            try:
                # 获取当前滚动高度（在 iframe 内执行）
                current_height = self.ctx.evaluate(f"""
                    () => {{
                        const el = document.querySelector('{scroll_target}');
                        if (el) {{
                            el.parentElement.scrollTop = el.parentElement.scrollHeight;
                            return el.parentElement.scrollHeight;
                        }}
                        return document.documentElement.scrollHeight;
                    }}
                """)

                if current_height == previous_height:
                    break

                previous_height = current_height
                time.sleep(1)
                attempts += 1

            except Exception as e:
                logger.warning("滚动加载出错: %s", e)
                break

        logger.info("滚动加载完成 (尝试 %d 次)", attempts)
