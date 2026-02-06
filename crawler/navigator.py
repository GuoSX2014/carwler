"""
页面导航模块
处理左侧菜单、子菜单的导航和页面切换

导航路径（3层折叠菜单）：
    信息披露 > 分类(如现货实时数据) > 页面(如实时节点边际电价)

关键注意事项：
    - 侧边栏由 Vue 动态渲染，首次加载需等待菜单出现
    - 折叠菜单为 toggle 模式，重复点击会收起，需做状态追踪
    - 菜单展开有动画延迟，需等待子项可见后再继续
    - 侧边栏可能需要滚动才能看到目标菜单项
    - text= 选择器会匹配面包屑等非菜单元素，需限定到侧边栏范围
"""

import time
from typing import Optional

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from utils.logger import get_logger

logger = get_logger()

# 侧边栏选择器：vue-element-admin 模板的侧边栏在 .sidebar-container 内
# 所有菜单操作都限定在此范围，避免误匹配面包屑或其他区域的同名文本
SIDEBAR_SELECTOR = "#app .sidebar-container, #app .el-aside, #app nav"


class Navigator:
    """页面导航器 - 处理左侧栏菜单和内容区 tab 切换"""

    def __init__(self, page: Page, config: dict):
        self.page = page
        self.config = config
        self.query_interval = config.get("request", {}).get("query_interval", 3)
        # 状态追踪：避免重复点击已展开的折叠菜单（再次点击会收起）
        self._info_disclosure_expanded = False
        self._current_category: Optional[str] = None

    def _find_sidebar_menu_item(self, text: str, timeout: int = 15000):
        """
        在侧边栏中查找菜单项

        优先在侧边栏容器中查找，如果侧边栏容器不存在则回退到全局查找。
        使用 get_by_text(exact=True) 精确匹配文本，避免子串误匹配。

        Args:
            text: 菜单项文本
            timeout: 超时时间（毫秒）

        Returns:
            Locator 对象
        """
        # 优先尝试在侧边栏容器中查找
        sidebar = self.page.locator(SIDEBAR_SELECTOR).first
        try:
            sidebar.wait_for(state="attached", timeout=3000)
            item = sidebar.get_by_text(text, exact=True).first
            item.wait_for(state="visible", timeout=timeout)
            return item
        except PlaywrightTimeout:
            pass

        # 回退：全局查找可见的文本元素
        logger.debug("侧边栏容器未找到，回退到全局查找「%s」", text)
        item = self.page.get_by_text(text, exact=True).first
        item.wait_for(state="visible", timeout=timeout)
        return item

    def _click_menu_item(self, text: str, timeout: int = 15000):
        """
        点击侧边栏菜单项（带滚动和等待）

        Args:
            text: 菜单项文本
            timeout: 超时时间（毫秒）
        """
        item = self._find_sidebar_menu_item(text, timeout=timeout)
        # 滚动到视图内，确保侧边栏中被遮挡的菜单项可见
        item.scroll_into_view_if_needed()
        time.sleep(0.3)
        item.click()

    def wait_for_sidebar_ready(self, timeout: int = 20000):
        """
        等待侧边栏菜单渲染完成

        侧边栏由 Vue 动态渲染，在页面首次加载后可能需要额外时间。
        通过等待已知的顶层菜单项（如「信息披露」）出现来判断就绪。

        Args:
            timeout: 超时时间（毫秒）
        """
        logger.info("等待侧边栏菜单加载...")
        try:
            self.page.get_by_text("信息披露", exact=True).first.wait_for(
                state="visible", timeout=timeout
            )
            logger.info("侧边栏菜单已就绪")
        except PlaywrightTimeout:
            logger.warning("等待侧边栏菜单超时 (%dms)，继续尝试导航", timeout)

    def navigate_to_info_disclosure(self):
        """
        展开左侧栏「信息披露」父菜单

        信息披露是所有数据页面的顶层入口，必须先展开才能看到子分类。
        展开后会验证子菜单是否出现，确保操作生效。
        """
        if self._info_disclosure_expanded:
            logger.debug("「信息披露」已展开，跳过点击")
            return

        logger.info("正在展开「信息披露」菜单...")
        try:
            self._click_menu_item("信息披露", timeout=15000)
            # 等待展开动画完成，子菜单项需要时间渲染
            time.sleep(2)

            # 验证展开成功：等待已知的子分类出现
            self._verify_menu_expanded(
                child_texts=["现货出清结果", "现货实时数据", "现货日前信息"],
                parent_name="信息披露",
                timeout=10000,
            )
            self._info_disclosure_expanded = True
            logger.info("已展开「信息披露」")

        except PlaywrightTimeout:
            logger.warning("展开「信息披露」后未找到子菜单，尝试再次点击...")
            # 可能第一次点击实际上收起了已展开的菜单，再点一次
            try:
                self._click_menu_item("信息披露", timeout=5000)
                time.sleep(2)
                self._verify_menu_expanded(
                    child_texts=["现货出清结果", "现货实时数据", "现货日前信息"],
                    parent_name="信息披露",
                    timeout=10000,
                )
                self._info_disclosure_expanded = True
                logger.info("已展开「信息披露」（第二次尝试）")
            except PlaywrightTimeout:
                logger.error("无法展开「信息披露」菜单")
                raise

    def _verify_menu_expanded(self, child_texts: list, parent_name: str,
                               timeout: int = 10000):
        """
        验证菜单展开成功：检查任一已知子项是否可见

        Args:
            child_texts: 期望出现的子菜单文本列表（任一可见即可）
            parent_name: 父菜单名称（用于日志）
            timeout: 超时时间（毫秒）
        """
        # 构建 OR 选择器：任一子项可见即认为展开成功
        selectors = ", ".join(
            f":text-is('{t}')" for t in child_texts
        )
        try:
            self.page.locator(selectors).first.wait_for(
                state="visible", timeout=timeout
            )
        except PlaywrightTimeout:
            raise PlaywrightTimeout(
                f"展开「{parent_name}」后未检测到子菜单项"
            )

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
            self._click_menu_item(category, timeout=15000)
            # 等待展开动画完成
            time.sleep(2)
            self._current_category = category
            logger.info("已展开「%s」", category)
        except PlaywrightTimeout:
            logger.error("未找到分类「%s」菜单", category)
            raise

    def navigate_to_subcategory(self, subcategory: str):
        """
        点击三级子菜单（如：实时市场出清概况、日前备用总量等）

        Args:
            subcategory: 子分类名称
        """
        logger.info("正在点击子菜单「%s」...", subcategory)
        try:
            self._click_menu_item(subcategory, timeout=15000)
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
                self._click_menu_item(part, timeout=10000)
                time.sleep(1.5)
            except PlaywrightTimeout:
                logger.warning("未找到层级「%s」", part)

        # 最后点击目标页面
        try:
            self._click_menu_item(page_name, timeout=10000)
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
