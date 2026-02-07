"""
页面爬取模块
针对不同页面类型的具体爬取逻辑

关键设计：
    该平台的页面内容（日期输入框、下拉框、查询/导出按钮、数据表格等）
    都渲染在 iframe 内部，而不是主页面中。
    导航后需检测 iframe 并切换到其 Frame 上下文，否则无法找到任何控件。
"""

import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from playwright.sync_api import Page, Frame

from crawler.navigator import Navigator
from crawler.filter_handler import FilterHandler
from crawler.export_handler import ExportHandler
from crawler.pagination import PaginationHandler
from crawler.data_extractor import DataExtractor
from storage.csv_storage import CsvStorage
from utils.parser import parse_clearing_summary_batch
from utils.logger import get_logger

logger = get_logger()


class PageCrawler:
    """
    通用页面爬取器
    根据任务配置自动选择爬取策略（导出 / 表格解析 / 分页 等）
    """

    def __init__(self, page: Page, config: dict):
        self.page = page
        self.config = config
        self.navigator = Navigator(page, config)
        self.filter_handler = FilterHandler(page, config)
        self.export_handler = ExportHandler(page, config)
        self.pagination = PaginationHandler(page, config)
        self.extractor = DataExtractor(page)
        self.storage = CsvStorage(config)

        self.date_interval = config.get("request", {}).get("date_interval", 2)
        self.retry_times = config.get("request", {}).get("retry_times", 3)
        self.retry_interval = config.get("request", {}).get("retry_interval", 5)

        # 记住当前任务使用的 iframe ID，用于重新检测时优先匹配
        self._current_iframe_id: Optional[str] = None

    # ── iframe 上下文切换 ────────────────────────────────────────

    def _drill_into_nested_iframe(self, frame: Frame) -> Optional[Frame]:
        """
        检查 Frame 内是否包含嵌套的 iframe，如果有则进入最内层。

        该平台部分页面使用 3 层 iframe 嵌套：
        - 主页面 → pxf-settlement-outnetpub iframe → 内层 id="iframe"（FineReport 报表）
        - 内层 iframe 包含实际的表单控件（日期输入框、查询按钮、数据表格）

        FineReport iframe 特征：
        - id="iframe"
        - 包含 .fr-trigger-editor（日期控件）、.fr-form-imgboard（按钮）
        - 或包含 input, button, table 等通用控件

        Args:
            frame: 上一层 iframe 的 Frame 对象

        Returns:
            内层 iframe 的 Frame 对象，如果没有嵌套则返回 None
        """
        try:
            inner_iframes = frame.query_selector_all("iframe")
            for inner_el in inner_iframes:
                try:
                    inner_frame = inner_el.content_frame()
                    if inner_frame:
                        # 检查内层 iframe 是否有实际的表单控件
                        count = inner_frame.locator(
                            "input, button, table, "
                            ".fr-trigger-editor, .fr-form-imgboard, "
                            ".el-date-editor, .el-select, .el-input"
                        ).count()
                        if count > 0:
                            inner_id = inner_el.get_attribute("id") or "unknown"
                            logger.info(
                                "发现嵌套内层 iframe: %s (包含 %d 个表单控件, URL: %s)",
                                inner_id, count,
                                inner_frame.url[:80] if inner_frame.url else "N/A",
                            )
                            return inner_frame
                except Exception:
                    continue
        except Exception as e:
            logger.debug("检查嵌套 iframe 失败: %s", e)
        return None

    def _get_content_frame(self) -> Optional[Frame]:
        """
        检测当前页面中可见的内容 iframe 并返回其 Frame 对象。

        该平台使用 iframe 加载各个功能页面内容：
        - 主页面（self.page）包含侧边栏菜单和 tab 切换
        - 功能页面（日期筛选、表格、导出按钮等）在 iframe 内

        平台存在两种 iframe 结构：
        1. 二层结构：主页面 → 内容 iframe（Element UI 页面，如实时节点边际电价）
        2. 三层结构：主页面 → 中间 iframe → 内层 iframe（FineReport 报表页面）
           中间 iframe 通常 id="pxf-settlement-outnetpub"
           内层 iframe 通常 id="iframe"，包含 FineReport 表单控件

        本方法会自动检测并穿透嵌套结构，返回最内层包含实际控件的 Frame。

        Returns:
            最内层内容 iframe 的 Frame 对象，未找到返回 None
        """
        # 方法0：如果记录了 iframe ID，优先按 ID 查找
        if self._current_iframe_id:
            try:
                target = self.page.query_selector(
                    f'iframe#{self._current_iframe_id}'
                )
                if target and target.is_visible():
                    frame = target.content_frame()
                    if frame:
                        logger.info(
                            "通过已记录ID找到内容区 iframe: %s (URL: %s)",
                            self._current_iframe_id,
                            frame.url[:80] if frame.url else "N/A",
                        )
                        # ★ 检查是否有嵌套的内层 iframe
                        inner = self._drill_into_nested_iframe(frame)
                        if inner:
                            return inner
                        return frame
            except Exception as e:
                logger.debug("通过ID查找iframe失败: %s", e)

        # 方法1：通过 query_selector 找到可见的 iframe 元素
        try:
            iframes = self.page.query_selector_all("iframe")
            for iframe_el in iframes:
                try:
                    if iframe_el.is_visible():
                        frame = iframe_el.content_frame()
                        if frame:
                            iframe_id = iframe_el.get_attribute("id") or "unknown"
                            logger.info(
                                "找到内容区 iframe: %s (URL: %s)",
                                iframe_id,
                                frame.url[:80] if frame.url else "N/A",
                            )
                            # 记住这个 iframe 的 ID
                            self._current_iframe_id = iframe_id

                            # ★ 检查是否有嵌套的内层 iframe（FineReport 三层结构）
                            inner = self._drill_into_nested_iframe(frame)
                            if inner:
                                return inner
                            return frame
                except Exception:
                    continue
        except Exception as e:
            logger.debug("方法1查找iframe失败: %s", e)

        # 方法2：遍历所有 frames，找到有实际内容的非主 frame
        try:
            for frame in self.page.frames:
                if frame == self.page.main_frame:
                    continue
                try:
                    # 检查 frame 内是否有表单控件或按钮
                    # 同时支持 Element UI 和 FineReport 控件
                    count = frame.locator(
                        "button, input, table, "
                        ".el-date-editor, .el-select, .el-input, "
                        ".fr-trigger-editor, .fr-form-imgboard"
                    ).count()
                    if count > 0:
                        logger.info(
                            "找到内容区 frame (方法2): %s",
                            frame.url[:80] if frame.url else "N/A",
                        )
                        return frame
                except Exception:
                    continue
        except Exception as e:
            logger.debug("方法2查找iframe失败: %s", e)

        logger.warning("未检测到内容区 iframe，将使用主页面上下文")
        return None

    def _switch_to_content_frame(self):
        """
        检测 iframe 并将所有 handler 的操作上下文切换到 iframe 内。

        包含重试机制：如果首次只找到外层 iframe（内层尚未加载），
        会等待并重新尝试穿透嵌套 iframe。

        如果未检测到 iframe，handler 将继续使用主页面上下文。
        """
        frame = self._get_content_frame()
        if frame:
            self.filter_handler.ctx = frame
            self.export_handler.ctx = frame
            self.extractor.ctx = frame
            self.pagination.ctx = frame
            logger.info("已将操作上下文切换到 iframe")

            # 检查是否可能还有未加载的内层 iframe
            # 如果当前 frame 没有 FineReport/ElementUI 控件，
            # 但有一个 iframe 子元素，说明内层可能还在加载
            try:
                control_count = frame.locator(
                    "input, .fr-trigger-editor, .el-date-editor"
                ).count()
                inner_iframe_count = len(frame.query_selector_all("iframe"))
                if control_count == 0 and inner_iframe_count > 0:
                    logger.info("外层 iframe 中发现内层 iframe 但控件未加载，等待加载...")
                    for retry in range(5):
                        time.sleep(2)
                        inner = self._drill_into_nested_iframe(frame)
                        if inner:
                            self.filter_handler.ctx = inner
                            self.export_handler.ctx = inner
                            self.extractor.ctx = inner
                            self.pagination.ctx = inner
                            logger.info("内层 iframe 加载完成 (第%d次尝试)", retry + 1)
                            return
                    logger.warning("内层 iframe 未能在预期时间内加载完成")
            except Exception as e:
                logger.debug("检查内层 iframe 加载状态失败: %s", e)
        else:
            # 回退到主页面
            self.filter_handler.ctx = self.page
            self.export_handler.ctx = self.page
            self.extractor.ctx = self.page
            self.pagination.ctx = self.page

    def _is_frame_valid(self) -> bool:
        """
        检查当前 iframe 上下文是否仍然有效（未被 detach）。

        iframe 可能因页面重新渲染、Vue 路由切换等原因被替换，
        此时旧的 Frame 引用变为 detached 状态，所有操作都会失败。

        Returns:
            True 表示 Frame 仍有效，False 表示已 detached
        """
        ctx = self.filter_handler.ctx
        # 如果 ctx 就是 page 本身，不需要检查
        if ctx == self.page:
            return True
        try:
            # 尝试一个轻量操作来验证 Frame 是否仍然有效
            ctx.evaluate("() => document.readyState")
            return True
        except Exception:
            return False

    def _ensure_content_frame(self):
        """
        确保 iframe 上下文有效。如果 Frame 已 detached，则重新检测 iframe。

        该平台的 Vue.js 应用在页面切换或异步加载时，可能会替换 iframe 元素，
        导致之前获取的 Frame 引用失效。此方法在关键操作前调用，
        确保操作上下文始终指向有效的 iframe。
        """
        if self._is_frame_valid():
            return

        logger.warning("检测到 iframe 已 detached，正在重新检测...")

        # 等待一小段时间让页面稳定
        time.sleep(1)

        # 重试多次，因为新的 iframe 可能还在加载中
        for attempt in range(5):
            frame = self._get_content_frame()
            if frame:
                self.filter_handler.ctx = frame
                self.export_handler.ctx = frame
                self.extractor.ctx = frame
                self.pagination.ctx = frame
                logger.info("已重新检测到 iframe 并切换上下文 (第%d次尝试)", attempt + 1)
                return
            logger.debug("第%d次重新检测 iframe 未找到，等待后重试...", attempt + 1)
            time.sleep(2)

        # 最终回退到主页面
        logger.warning("多次重试仍未检测到 iframe，回退到主页面上下文")
        self.filter_handler.ctx = self.page
        self.export_handler.ctx = self.page
        self.extractor.ctx = self.page
        self.pagination.ctx = self.page

    # ── 主流程 ────────────────────────────────────────────────────

    def crawl_task(self, task_name: str, task_config: dict,
                    start_date: str, end_date: str):
        """
        执行单个爬取任务

        Args:
            task_name: 任务名称（如：实时节点边际电价）
            task_config: 任务配置字典
            start_date: 起始日期（YYYY-MM-DD）
            end_date: 结束日期（YYYY-MM-DD）
        """
        if not task_config.get("enabled", True):
            logger.info("任务「%s」已禁用，跳过", task_name)
            return

        logger.info("=" * 70)
        logger.info("开始爬取任务: %s", task_name)
        logger.info("日期范围: %s ~ %s", start_date, end_date)
        logger.info("=" * 70)

        category = task_config.get("category", "")
        subcategory = task_config.get("subcategory", None)
        has_dropdown = task_config.get("has_dropdown", False)
        dropdown_label = task_config.get("dropdown_label", "")
        has_export = task_config.get("has_export", False)
        export_type = task_config.get("export_type", "原样导出")
        has_pagination = task_config.get("has_pagination", False)
        has_page_size = task_config.get("has_page_size", False)
        is_clearing_summary = "出清概况" in task_name

        # 获取已爬取的日期（增量更新）
        existing_dates = self.storage.get_existing_dates(task_name, category)
        logger.info("已有数据日期: %d 天", len(existing_dates))

        # 导航到目标页面
        try:
            self.navigator.navigate_to_page(category, task_name, subcategory)
        except Exception as e:
            logger.error("导航到「%s」失败: %s", task_name, e)
            return

        # ★ 重置 iframe ID 记录（新任务可能使用不同的 iframe）
        self._current_iframe_id = None

        # ★ 关键步骤：导航完成后，检测 iframe 并切换上下文
        self._switch_to_content_frame()

        # 等待内容区完全加载（iframe 内容可能需要较长时间）
        time.sleep(3)

        # ★ 二次确认：iframe 可能在加载过程中被替换，需要重新检测
        self._ensure_content_frame()

        # 设置每页条数（如果支持）
        if has_page_size:
            try:
                self.filter_handler.set_page_size(50)
            except Exception:
                logger.warning("设置每页条数失败，使用默认值")

        # 获取下拉选项（先确保 iframe 上下文有效）
        dropdown_options = []
        if has_dropdown:
            self._ensure_content_frame()
            dropdown_options = self.filter_handler.get_dropdown_options(dropdown_label)
            if not dropdown_options:
                logger.warning("未获取到「%s」的下拉选项，尝试不选择直接查询",
                               dropdown_label)
                dropdown_options = [""]  # 空字符串表示不选择

        # 日期迭代
        date_list = self._generate_date_list(start_date, end_date)
        total_dates = len(date_list)

        for date_idx, date_str in enumerate(date_list):
            # 增量更新检查
            if date_str in existing_dates:
                logger.info("[%d/%d] 跳过已有数据: %s", date_idx + 1, total_dates, date_str)
                continue

            logger.info("[%d/%d] 处理日期: %s", date_idx + 1, total_dates, date_str)

            if has_dropdown and dropdown_options:
                # 对每个下拉选项迭代
                for opt_idx, option in enumerate(dropdown_options):
                    logger.info("  下拉选项 [%d/%d]: %s",
                                opt_idx + 1, len(dropdown_options), option or "(默认)")
                    self._crawl_single(
                        task_name=task_name,
                        task_config=task_config,
                        date_str=date_str,
                        category=category,
                        dropdown_label=dropdown_label,
                        dropdown_value=option,
                        has_export=has_export,
                        export_type=export_type,
                        has_pagination=has_pagination,
                        is_clearing_summary=is_clearing_summary,
                    )
            else:
                self._crawl_single(
                    task_name=task_name,
                    task_config=task_config,
                    date_str=date_str,
                    category=category,
                    dropdown_label="",
                    dropdown_value="",
                    has_export=has_export,
                    export_type=export_type,
                    has_pagination=has_pagination,
                    is_clearing_summary=is_clearing_summary,
                )

            time.sleep(self.date_interval)

        logger.info("任务「%s」完成", task_name)

    def _crawl_single(self, task_name: str, task_config: dict,
                       date_str: str, category: str,
                       dropdown_label: str, dropdown_value: str,
                       has_export: bool, export_type: str,
                       has_pagination: bool,
                       is_clearing_summary: bool):
        """
        执行单次爬取（一个日期 + 一个下拉选项组合）

        支持自动重试，重试前会重新检测 iframe 上下文
        """
        for attempt in range(1, self.retry_times + 1):
            try:
                # ★ 每次尝试前确保 iframe 上下文有效
                self._ensure_content_frame()

                self._do_crawl_single(
                    task_name, task_config, date_str, category,
                    dropdown_label, dropdown_value,
                    has_export, export_type, has_pagination,
                    is_clearing_summary,
                )
                return  # 成功则退出
            except Exception as e:
                logger.error("爬取失败 [%s][%s][%s] 第%d次: %s",
                             task_name, date_str, dropdown_value, attempt, e)
                if attempt < self.retry_times:
                    logger.info("等待 %d 秒后重试...", self.retry_interval)
                    time.sleep(self.retry_interval)
                else:
                    logger.error("已达最大重试次数，跳过此记录")

    def _do_crawl_single(self, task_name: str, task_config: dict,
                          date_str: str, category: str,
                          dropdown_label: str, dropdown_value: str,
                          has_export: bool, export_type: str,
                          has_pagination: bool,
                          is_clearing_summary: bool):
        """实际执行单次爬取的核心逻辑"""

        # 1. 设置日期
        self.filter_handler.set_date(date_str)
        time.sleep(0.5)

        # 2. 设置下拉选项（先选下拉，再点查询）
        if dropdown_label and dropdown_value:
            self.filter_handler.select_dropdown_option(dropdown_label, dropdown_value)
            time.sleep(0.5)

        # 3. 点击查询
        self.filter_handler.click_query_button()
        time.sleep(1)

        # 4. 尝试导出（优先使用导出）
        if has_export:
            filepath = self.export_handler.try_export(
                export_type=export_type,
                task_name=task_name,
                date_str=date_str,
                extra_label=dropdown_value,
            )
            if filepath:
                logger.info("通过导出获取数据成功: %s", filepath)
                return

            logger.info("导出不可用，回退到表格解析")

        # 5. 从表格提取数据
        all_data = []

        if has_pagination:
            # 带分页的提取
            all_data = self._extract_with_pagination(task_name)
        else:
            # 无分页，滚动加载后提取
            self.pagination.scroll_to_load_all()
            headers, rows = self.extractor.extract_table()
            all_data = rows

        if not all_data:
            logger.warning("未提取到数据 [%s][%s][%s]", task_name, date_str, dropdown_value)
            return

        # 6. 特殊处理：出清概况文本解析
        if is_clearing_summary:
            all_data = parse_clearing_summary_batch(all_data)

        # 7. 数据清洗
        all_data = self._clean_data(all_data)

        # 8. 添加更新时间
        update_time = self.extractor.extract_update_time()
        if update_time:
            for row in all_data:
                row["最新更新日期"] = update_time

        # 9. 保存 CSV
        self.storage.save(
            data=all_data,
            task_name=task_name,
            date_str=date_str,
            extra_label=dropdown_value,
            category=category,
        )

    def _extract_with_pagination(self, task_name: str) -> List[Dict]:
        """
        带分页的数据提取

        Args:
            task_name: 任务名称

        Returns:
            所有页的数据
        """
        all_data = []
        total_pages = self.pagination.get_total_pages()
        logger.info("共 %d 页数据", total_pages)

        current_page = 1
        while True:
            logger.info("正在提取第 %d/%d 页...", current_page, total_pages)

            headers, rows = self.extractor.extract_table()
            all_data.extend(rows)

            if current_page >= total_pages:
                break

            if not self.pagination.has_next_page():
                break

            if not self.pagination.go_next_page():
                break

            current_page += 1

        logger.info("分页提取完成: 共 %d 行数据", len(all_data))
        return all_data

    def _clean_data(self, data: List[Dict]) -> List[Dict]:
        """
        基础数据清洗

        - 去除前后空白
        - 转换数字类型
        - 处理缺失值

        Args:
            data: 原始数据

        Returns:
            清洗后的数据
        """
        cleaned = []
        for row in data:
            new_row = {}
            for key, value in row.items():
                if isinstance(value, str):
                    value = value.strip()
                    # 跳过序号列的转换
                    if key == "序号":
                        new_row[key] = value
                        continue
                    # 尝试数值转换
                    if value.replace(".", "", 1).replace("-", "", 1).isdigit():
                        try:
                            if "." in value:
                                value = float(value)
                            else:
                                value = int(value)
                        except (ValueError, TypeError):
                            pass
                new_row[key] = value if value != "" else None
            cleaned.append(new_row)
        return cleaned

    @staticmethod
    def _generate_date_list(start_date: str, end_date: str) -> List[str]:
        """
        生成日期列表（含首尾）

        Args:
            start_date: 起始日期（YYYY-MM-DD）
            end_date: 结束日期（YYYY-MM-DD）

        Returns:
            日期字符串列表
        """
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")

        dates = []
        current = start
        while current <= end:
            dates.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)

        return dates
