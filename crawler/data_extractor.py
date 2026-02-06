"""
数据提取模块
从 HTML 表格中提取结构化数据
"""

import re
import time
from typing import Dict, List, Optional, Tuple

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout
from bs4 import BeautifulSoup

from utils.logger import get_logger

logger = get_logger()


class DataExtractor:
    """HTML 表格数据提取器"""

    def __init__(self, page: Page):
        self.page = page

    def extract_table(self, table_index: int = 0) -> Tuple[List[str], List[Dict]]:
        """
        提取页面中指定序号的表格数据

        Args:
            table_index: 表格索引（页面可能有多个表格）

        Returns:
            (表头列表, 数据行列表)
        """
        logger.info("正在提取表格数据 (表格索引: %d)...", table_index)

        try:
            # 等待表格出现
            self.page.wait_for_selector("table", timeout=10000)
            time.sleep(1)

            # 获取页面 HTML
            html = self.page.content()
            soup = BeautifulSoup(html, "lxml")

            # 查找所有表格
            tables = soup.find_all("table")
            if not tables:
                logger.warning("页面中未找到表格")
                return [], []

            if table_index >= len(tables):
                logger.warning(
                    "表格索引 %d 超出范围 (共 %d 个表格)",
                    table_index, len(tables)
                )
                return [], []

            table = tables[table_index]
            headers, rows = self._parse_table(table)

            logger.info("提取完成: %d 列, %d 行", len(headers), len(rows))
            return headers, rows

        except PlaywrightTimeout:
            logger.error("等待表格超时")
            return [], []
        except Exception as e:
            logger.error("提取表格数据失败: %s", e)
            return [], []

    def extract_all_tables(self) -> List[Tuple[List[str], List[Dict]]]:
        """
        提取页面中所有表格的数据

        Returns:
            [(表头列表, 数据行列表), ...]
        """
        try:
            html = self.page.content()
            soup = BeautifulSoup(html, "lxml")
            tables = soup.find_all("table")

            results = []
            for i, table in enumerate(tables):
                headers, rows = self._parse_table(table)
                if headers:
                    results.append((headers, rows))
                    logger.debug("表格 %d: %d 列, %d 行", i, len(headers), len(rows))

            return results

        except Exception as e:
            logger.error("提取所有表格失败: %s", e)
            return []

    def _parse_table(self, table) -> Tuple[List[str], List[Dict]]:
        """
        解析单个 table 元素

        Args:
            table: BeautifulSoup table 元素

        Returns:
            (表头列表, 数据行字典列表)
        """
        headers = []
        rows = []

        # 提取表头
        thead = table.find("thead")
        if thead:
            header_row = thead.find("tr")
            if header_row:
                for th in header_row.find_all(["th", "td"]):
                    text = th.get_text(strip=True)
                    headers.append(text)
        else:
            # 没有 thead，尝试第一行作为表头
            first_row = table.find("tr")
            if first_row:
                cells = first_row.find_all(["th", "td"])
                for cell in cells:
                    text = cell.get_text(strip=True)
                    headers.append(text)

        if not headers:
            return [], []

        # 提取数据行
        tbody = table.find("tbody")
        data_rows = tbody.find_all("tr") if tbody else table.find_all("tr")[1:]

        for tr in data_rows:
            cells = tr.find_all(["td", "th"])
            if len(cells) == 0:
                continue

            row_data = {}
            for i, cell in enumerate(cells):
                if i < len(headers):
                    key = headers[i]
                else:
                    key = f"列{i + 1}"
                row_data[key] = cell.get_text(strip=True)

            # 过滤掉全空行
            if any(v for v in row_data.values()):
                rows.append(row_data)

        return headers, rows

    def extract_update_time(self) -> Optional[str]:
        """
        提取页面上的「最新更新日期」

        Returns:
            更新时间字符串，未找到返回 None
        """
        try:
            # 查找「最新更新日期」文本
            selectors = [
                'text=/最新更新日期/',
                'text=/更新时间/',
                'text=/最新更新/',
            ]

            for sel in selectors:
                try:
                    el = self.page.locator(sel).first
                    if el.is_visible():
                        text = el.text_content().strip()
                        # 提取日期时间
                        match = re.search(
                            r"(\d{4}[-/]\d{2}[-/]\d{2}\s*\d{2}:\d{2}:\d{2})", text
                        )
                        if match:
                            return match.group(1)
                        # 尝试只匹配日期
                        match = re.search(r"(\d{4}[-/]\d{2}[-/]\d{2})", text)
                        if match:
                            return match.group(1)
                except Exception:
                    continue

            return None

        except Exception as e:
            logger.debug("提取更新时间失败: %s", e)
            return None

    def extract_table_via_js(self) -> Tuple[List[str], List[Dict]]:
        """
        通过 JavaScript 直接从 DOM 提取表格数据（备用方案）

        Returns:
            (表头列表, 数据行字典列表)
        """
        try:
            result = self.page.evaluate("""
                () => {
                    const table = document.querySelector('table');
                    if (!table) return { headers: [], rows: [] };

                    const headers = [];
                    const headerRow = table.querySelector('thead tr') || table.querySelector('tr');
                    if (headerRow) {
                        headerRow.querySelectorAll('th, td').forEach(cell => {
                            headers.push(cell.textContent.trim());
                        });
                    }

                    const rows = [];
                    const tbody = table.querySelector('tbody');
                    const dataRows = tbody ? tbody.querySelectorAll('tr') :
                        Array.from(table.querySelectorAll('tr')).slice(1);

                    dataRows.forEach(tr => {
                        const row = {};
                        tr.querySelectorAll('td').forEach((cell, i) => {
                            const key = i < headers.length ? headers[i] : `列${i + 1}`;
                            row[key] = cell.textContent.trim();
                        });
                        rows.push(row);
                    });

                    return { headers, rows };
                }
            """)

            headers = result.get("headers", [])
            rows = result.get("rows", [])
            logger.info("JS提取完成: %d 列, %d 行", len(headers), len(rows))
            return headers, rows

        except Exception as e:
            logger.error("JS提取表格失败: %s", e)
            return [], []
