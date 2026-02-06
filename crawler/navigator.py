"""
页面导航模块
处理左侧菜单、子菜单的导航和页面切换
"""

import time
from typing import Optional

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from utils.logger import get_logger

logger = get_logger()


class Navigator:
    """页面导航器 - 处理左侧栏菜单和内容区 tab 切换"""

    def __init__(self, page: Page, config: dict):
        self.page = page
        self.config = config
        self.query_interval = config.get("request", {}).get("query_interval", 3)

    def navigate_to_info_disclosure(self):
        """
        导航到 信息披露 菜单
        点击左侧栏中的「信息披露」展开菜单
        """
        logger.info("正在导航到「信息披露」...")
        try:
            # 查找并点击「信息披露」菜单项
            menu_item = self.page.locator("text=信息披露").first
            menu_item.click()
            time.sleep(1)
            logger.info("已点击「信息披露」")
        except PlaywrightTimeout:
            logger.warning("未找到「信息披露」菜单，尝试直接导航")

    def navigate_to_category(self, category: str):
        """
        导航到一级分类菜单（如：现货出清结果、现货实时数据、现货日前信息、综合查询）

        Args:
            category: 分类名称
        """
        logger.info("正在导航到分类「%s」...", category)
        try:
            # 点击左侧栏中的一级分类
            menu_item = self.page.locator(f"text={category}").first
            menu_item.click()
            time.sleep(1)
            logger.info("已展开「%s」", category)
        except PlaywrightTimeout:
            logger.error("未找到分类「%s」菜单", category)
            raise

    def navigate_to_subcategory(self, subcategory: str):
        """
        导航到二级子菜单（如：实时市场出清概况、日前备用总量等）

        Args:
            subcategory: 子分类名称
        """
        logger.info("正在点击子菜单「%s」...", subcategory)
        try:
            # 点击左侧栏中的子菜单项
            sub_item = self.page.locator(f"text={subcategory}").first
            sub_item.click()
            time.sleep(2)
            self.page.wait_for_load_state("networkidle", timeout=15000)
            logger.info("已导航到「%s」页面", subcategory)
        except PlaywrightTimeout:
            logger.error("未找到子菜单「%s」或页面加载超时", subcategory)
            raise

    def navigate_to_page(self, category: str, page_name: str,
                          subcategory_path: Optional[str] = None):
        """
        完整导航到目标页面

        Args:
            category: 一级分类（现货出清结果/现货实时数据/现货日前信息/综合查询）
            page_name: 页面名称
            subcategory_path: 额外的子分类路径（如 综合查询 下的 供需与约束 > 参数信息）
        """
        logger.info("=" * 60)
        logger.info("导航到: %s > %s", category, page_name)

        # 先点击一级分类
        self.navigate_to_category(category)

        if subcategory_path:
            # 综合查询的特殊导航路径
            self._navigate_comprehensive_query(page_name, subcategory_path)
        else:
            # 普通导航：直接点击子菜单
            self.navigate_to_subcategory(page_name)

        time.sleep(self.query_interval)

    def _navigate_comprehensive_query(self, page_name: str, subcategory_path: str):
        """
        处理综合查询的特殊导航

        综合查询的结构：综合查询 > 供需与约束 > 参数信息 > 节点分配因子
        需要依次展开中间层级
        """
        logger.info("综合查询特殊导航: %s > %s", subcategory_path, page_name)

        # 先点击「综合查询」
        try:
            comp_query = self.page.locator("text=综合查询").first
            comp_query.click()
            time.sleep(1)
        except PlaywrightTimeout:
            pass

        # 解析路径中的中间层级
        parts = [p.strip() for p in subcategory_path.split(">")]
        for part in parts:
            try:
                logger.info("展开: %s", part)
                item = self.page.locator(f"text={part}").first
                item.click()
                time.sleep(1)
            except PlaywrightTimeout:
                logger.warning("未找到层级「%s」", part)

        # 最后点击目标页面
        try:
            target = self.page.locator(f"text={page_name}").first
            target.click()
            time.sleep(2)
            self.page.wait_for_load_state("networkidle", timeout=15000)
            logger.info("已导航到综合查询「%s」", page_name)
        except PlaywrightTimeout:
            logger.error("未找到综合查询目标页「%s」", page_name)
            raise

    def click_tab(self, tab_name: str):
        """
        点击内容区顶部的 tab 标签

        Args:
            tab_name: tab 名称
        """
        logger.info("点击 Tab: %s", tab_name)
        try:
            tab = self.page.locator(f"text={tab_name}").first
            tab.click()
            time.sleep(1.5)
            self.page.wait_for_load_state("networkidle", timeout=10000)
        except PlaywrightTimeout:
            logger.warning("未找到 Tab「%s」", tab_name)

    def wait_for_table(self, timeout: int = 15000):
        """等待表格加载完成"""
        try:
            self.page.wait_for_selector("table", timeout=timeout)
            # 额外等待确保数据渲染
            time.sleep(1)
            logger.debug("表格已加载")
        except PlaywrightTimeout:
            logger.warning("等待表格超时 (%dms)", timeout)
