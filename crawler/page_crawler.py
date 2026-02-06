"""
页面爬取模块
针对不同页面类型的具体爬取逻辑
"""

import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from playwright.sync_api import Page

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

        # 设置每页条数（如果支持）
        if has_page_size:
            try:
                self.filter_handler.set_page_size(50)
            except Exception:
                logger.warning("设置每页条数失败，使用默认值")

        # 获取下拉选项
        dropdown_options = []
        if has_dropdown:
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

        支持自动重试
        """
        for attempt in range(1, self.retry_times + 1):
            try:
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

        # 2. 设置下拉选项
        if dropdown_label and dropdown_value:
            self.filter_handler.select_dropdown_option(dropdown_label, dropdown_value)

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
