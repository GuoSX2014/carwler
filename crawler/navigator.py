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
        # 状态追踪：避免重复点击已展开的折叠菜单（再次点击会收起）
        self._info_disclosure_expanded = False
        self._current_category: Optional[str] = None

    def navigate_to_info_disclosure(self):
        """
        展开左侧栏「信息披露」父菜单

        信息披露是所有数据页面的顶层入口，必须先展开才能看到子分类。
        使用状态追踪避免重复点击导致菜单收起。
        """
        if self._info_disclosure_expanded:
            logger.debug("「信息披露」已展开，跳过点击")
            return
        logger.info("正在展开「信息披露」菜单...")
        try:
            menu_item = self.page.locator("text=信息披露").first
            menu_item.click()
            time.sleep(1)
            self._info_disclosure_expanded = True
            logger.info("已展开「信息披露」")
        except PlaywrightTimeout:
            logger.warning("未找到「信息披露」菜单，尝试直接导航")

    def navigate_to_category(self, category: str):
        """
        展开二级分类菜单（如：现货出清结果、现货实时数据、现货日前信息、综合查询）

        这些分类是「信息披露」的子菜单，需先展开「信息披露」。
        使用状态追踪避免重复点击导致菜单收起。

        Args:
            category: 分类名称
        """
        if self._current_category == category:
            logger.debug("分类「%s」已展开，跳过点击", category)
            return
        logger.info("正在展开分类「%s」...", category)
        try:
            menu_item = self.page.locator(f"text={category}").first
            menu_item.click()
            time.sleep(1)
            self._current_category = category
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

        实际导航路径（3层）：信息披露 > 分类 > 页面
        例如：信息披露 > 现货出清结果 > 日前备用总量

        Args:
            category: 二级分类（现货出清结果/现货实时数据/现货日前信息/综合查询）
            page_name: 页面名称
            subcategory_path: 额外的子分类路径（如 综合查询 下的 供需与约束 > 参数信息）
        """
        logger.info("=" * 60)
        logger.info("导航到: 信息披露 > %s > %s", category, page_name)

        # 第一步：展开「信息披露」父菜单（所有数据页面的顶层入口）
        self.navigate_to_info_disclosure()

        # 第二步：展开二级分类
        self.navigate_to_category(category)

        # 第三步：点击具体页面
        if subcategory_path:
            # 综合查询的特殊导航路径（多层展开）
            self._navigate_comprehensive_query(page_name, subcategory_path)
        else:
            # 普通导航：直接点击子菜单
            self.navigate_to_subcategory(page_name)

        time.sleep(self.query_interval)

    def _navigate_comprehensive_query(self, page_name: str, subcategory_path: str):
        """
        处理综合查询的特殊导航

        完整路径：信息披露 > 综合查询 > 供需与约束 > 参数信息 > 节点分配因子
        注意：「信息披露」和「综合查询」已由 navigate_to_page 中的
        navigate_to_info_disclosure() 和 navigate_to_category() 展开，
        此处只需处理中间层级和最终目标页面。
        """
        logger.info("综合查询特殊导航: %s > %s", subcategory_path, page_name)

        # 解析路径中的中间层级（不再重复点击「综合查询」）
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
