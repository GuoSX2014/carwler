"""
浏览器管理模块
基于 Playwright 管理 Chromium 浏览器实例
"""

import os
from typing import Optional

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from utils.logger import get_logger

logger = get_logger()


class BrowserManager:
    """浏览器生命周期管理器"""

    def __init__(self, config: dict):
        self.config = config.get("browser", {})
        self.headless = self.config.get("headless", False)
        self.slow_mo = self.config.get("slow_mo", 300)
        self.timeout = self.config.get("timeout", 30000)
        self.download_dir = os.path.abspath(
            self.config.get("download_dir", "./data/exports")
        )
        self.viewport = self.config.get("viewport", {"width": 1920, "height": 1080})

        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    def start(self) -> Page:
        """启动浏览器并返回页面实例"""
        os.makedirs(self.download_dir, exist_ok=True)

        logger.info("正在启动 Chromium 浏览器 (headless=%s)...", self.headless)
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            slow_mo=self.slow_mo,
        )

        self._context = self._browser.new_context(
            viewport=self.viewport,
            accept_downloads=True,
        )
        self._context.set_default_timeout(self.timeout)

        self._page = self._context.new_page()
        logger.info("浏览器启动成功")
        return self._page

    @property
    def page(self) -> Page:
        """获取当前页面"""
        if self._page is None:
            raise RuntimeError("浏览器尚未启动，请先调用 start()")
        return self._page

    @property
    def context(self) -> BrowserContext:
        """获取浏览器上下文"""
        if self._context is None:
            raise RuntimeError("浏览器尚未启动，请先调用 start()")
        return self._context

    def navigate(self, url: str):
        """导航到指定 URL"""
        logger.info("正在导航到: %s", url)
        self.page.goto(url, wait_until="networkidle")
        logger.info("页面加载完成")

    def wait_for_load(self, timeout: Optional[int] = None):
        """等待页面加载完成"""
        t = timeout or self.timeout
        self.page.wait_for_load_state("networkidle", timeout=t)

    def screenshot(self, path: str):
        """截屏保存"""
        self.page.screenshot(path=path)
        logger.debug("截屏已保存: %s", path)

    def close(self):
        """关闭浏览器并释放资源"""
        logger.info("正在关闭浏览器...")
        try:
            if self._page:
                self._page.close()
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception as e:
            logger.warning("关闭浏览器时出错: %s", e)
        finally:
            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None
            logger.info("浏览器已关闭")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
