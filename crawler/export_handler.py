"""
导出处理模块
处理「原样导出」和「导出」按钮的点击和文件下载
"""

import os
import time
import glob as glob_module
from typing import Optional

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from utils.logger import get_logger

logger = get_logger()


class ExportHandler:
    """导出功能处理器"""

    def __init__(self, page: Page, config: dict):
        self.page = page
        self.config = config
        self.download_dir = os.path.abspath(
            config.get("browser", {}).get("download_dir", "./data/exports")
        )
        os.makedirs(self.download_dir, exist_ok=True)

    def try_export(self, export_type: str = "原样导出",
                    task_name: str = "", date_str: str = "",
                    extra_label: str = "") -> Optional[str]:
        """
        尝试点击导出按钮并下载文件

        Args:
            export_type: 导出按钮文本（"原样导出" 或 "导出"）
            task_name: 任务名称（用于文件命名）
            date_str: 日期字符串
            extra_label: 额外标签（如节点名称等）

        Returns:
            下载文件路径，失败返回 None
        """
        logger.info("尝试导出: %s [%s]", export_type, task_name)

        try:
            # 查找导出按钮
            export_btn = self._find_export_button(export_type)
            if export_btn is None:
                logger.warning("未找到「%s」按钮", export_type)
                return None

            # 记录下载前的文件列表
            before_files = set(os.listdir(self.download_dir))

            # 使用 Playwright 的下载事件处理
            with self.page.expect_download(timeout=30000) as download_info:
                export_btn.click()

            download = download_info.value

            # 构造目标文件名
            suffix = os.path.splitext(download.suggested_filename)[1] or ".csv"
            safe_task = task_name.replace("/", "_").replace("\\", "_")
            safe_extra = extra_label.replace("/", "_").replace("\\", "_") if extra_label else ""

            if safe_extra:
                filename = f"{safe_task}_{date_str}_{safe_extra}{suffix}"
            else:
                filename = f"{safe_task}_{date_str}{suffix}"

            filepath = os.path.join(self.download_dir, filename)

            # 保存文件
            download.save_as(filepath)
            logger.info("导出文件已保存: %s", filepath)
            return filepath

        except PlaywrightTimeout:
            logger.warning("导出超时，可能按钮不可用或无数据 [%s]", task_name)
            return None
        except Exception as e:
            logger.error("导出失败 [%s]: %s", task_name, e)
            return None

    def _find_export_button(self, export_type: str):
        """
        查找导出按钮

        Args:
            export_type: 按钮文本

        Returns:
            按钮元素或 None
        """
        # 按优先级尝试多种选择器
        selectors = [
            f'button:has-text("{export_type}")',
            f'a:has-text("{export_type}")',
            f'span:has-text("{export_type}")',
            f'text={export_type}',
        ]

        for sel in selectors:
            try:
                btn = self.page.locator(sel).first
                if btn.is_visible():
                    return btn
            except Exception:
                continue

        # 回退：查找包含"导出"文字的按钮
        try:
            btns = self.page.locator("button").all()
            for btn in btns:
                text = btn.text_content().strip()
                if export_type in text or "导出" in text:
                    return btn
        except Exception:
            pass

        return None

    def is_export_available(self, export_type: str = "原样导出") -> bool:
        """
        检查导出按钮是否可用

        Args:
            export_type: 按钮文本

        Returns:
            是否可用
        """
        btn = self._find_export_button(export_type)
        if btn is None:
            return False
        try:
            return btn.is_visible() and btn.is_enabled()
        except Exception:
            return False
