# 山西电力交易平台爬虫

自动化爬取**山西电力交易中心电力交易平台（SXPX）**电力现货市场信息披露数据的 Python 爬虫脚本。

---

## 目录

- [功能概述](#功能概述)
- [支持的数据类别](#支持的数据类别)
- [环境要求](#环境要求)
- [安装步骤](#安装步骤)
- [快速开始](#快速开始)
- [命令行参数](#命令行参数)
- [配置文件说明](#配置文件说明)
- [数据存储结构](#数据存储结构)
- [项目结构](#项目结构)
- [模块说明](#模块说明)
- [常见问题](#常见问题)
- [注意事项](#注意事项)

---

## 功能概述

- **连接已有浏览器**：通过 CDP 连接到已登录的 Chrome，无需重复登录
- **自动化浏览器操作**：基于 Playwright + Chrome，完整模拟用户操作
- **多页面数据爬取**：支持 18 种数据类别的自动化爬取
- **智能导出**：优先使用页面"导出"功能，回退到 HTML 表格解析
- **日期迭代**：支持按日逐日爬取指定日期范围的数据
- **下拉筛选**：自动获取并遍历下拉选项（节点、断面、机组等）
- **分页处理**：自动处理分页和滚动加载
- **增量更新**：自动跳过已爬取日期，仅抓取新数据
- **出清概况解析**：使用正则表达式结构化解析长文本出清概况数据
- **数据质量校验**：内置数据完整性和质量检查
- **定时调度**：支持按小时间隔定时执行
- **详细日志**：全流程日志记录，支持文件滚动

---

## 支持的数据类别

### 现货出清结果
| 数据类别 | 下拉筛选 | 分页 | 导出方式 |
|---------|---------|------|---------|
| 实时市场出清概况 | 无 | 有 | 原样导出 |
| 日前市场出清概况 | 无 | 有 | 原样导出 |
| 日前备用总量 | 无 | 无 | 原样导出 |

### 现货实时数据
| 数据类别 | 下拉筛选 | 分页 | 导出方式 |
|---------|---------|------|---------|
| 实时各时段出清现货电量 | 无 | 无 | 原样导出 |
| 实时备用总量 | 无 | 无 | 原样导出 |
| 实时节点边际电价 | 节点名称 | 无 | 导出 |
| 实时输电断面约束及阻塞 | 断面名称 | 无 | 原样导出 |
| 断面约束情况及影子价格 | 断面名称 | 无 | 原样导出 |
| 重要通道实际输电情况 | 断面名称 | 无 | 原样导出 |

### 现货日前信息
| 数据类别 | 下拉筛选 | 分页 | 导出方式 |
|---------|---------|------|---------|
| 抽蓄电站水位 | 无 | 无 | 原样导出 |
| 断面约束 | 无 | 有 | 原样导出 |
| 日前联络线计划 | 联络线名称 | 无 | 原样导出 |
| 输变电设备检修计划 | 无 | 有 | 原样导出 |
| 输电通道可用容量 | 通道名称 | 有 | 原样导出 |
| 日前机组开机安排 | 机组名称 | 无 | 导出 |
| 日前节点边际电价 | 节点名称 | 无 | 导出 |

### 综合查询
| 数据类别 | 下拉筛选 | 分页 | 导出方式 |
|---------|---------|------|---------|
| 节点分配因子 | 无 | 有 | 原样导出 |

---

## 环境要求

- **Python**：3.9 及以上
- **操作系统**：Windows / macOS / Linux
- **网络**：需能访问 `https://pmos.sx.sgcc.com.cn`
- **Chrome 浏览器**：需已安装 Google Chrome（用于 CDP 连接模式）
- **Playwright**：Python 包（`pip install playwright`），用于浏览器自动化

---

## 安装步骤

### 1. 克隆或下载项目

```bash
cd /path/to/your/workspace
# 如果是 git 仓库
git clone <repo-url>
cd crawler
```

### 2. 创建虚拟环境（推荐）

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 4. 安装 Playwright 浏览器

```bash
playwright install chromium
```

> 首次安装 Playwright 浏览器可能需要几分钟时间，也会自动下载所需系统依赖。
> 如果使用 CDP 连接模式（默认），Playwright 不会启动新浏览器，但仍需安装以提供运行时依赖。

---

## 快速开始

### 前置步骤：启动 Chrome（CDP 连接模式）

脚本默认通过 **Chrome DevTools Protocol (CDP)** 连接到已打开且已登录的 Chrome 浏览器，而非启动新浏览器。使用前需：

**1. 以远程调试模式启动 Chrome：**

```bash
# Linux 服务器
google-chrome --remote-debugging-port=9222

# macOS
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222

# Windows
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
```

**2. 在 Chrome 中手动完成操作：**
- 打开 `https://pmos.sx.sgcc.com.cn`
- 完成登录认证
- 确认已进入系统首页（能看到左侧菜单栏）

**3. 保持 Chrome 运行，然后执行爬虫脚本。**

> **重要提示：**
> - Chrome 必须带 `--remote-debugging-port=9222` 参数启动，否则脚本无法连接
> - 如果 Chrome 已在运行但没带该参数，需关闭后重新启动
> - 脚本结束后只断开连接，**不会关闭 Chrome 和已打开的页面**
> - CDP 端口号可在 `config.yaml` 的 `browser.cdp_url` 中修改

### 1. 查看可用任务

```bash
python main.py --list-tasks
```

输出示例：
```
可用爬取任务:
------------------------------------------------------------
  [启用] 现货出清结果 > 实时市场出清概况
  [启用] 现货出清结果 > 日前市场出清概况
  [启用] 现货出清结果 > 日前备用总量
  [启用] 现货实时数据 > 实时各时段出清现货电量
  ...
共 18 个任务
```

### 2. 爬取所有已启用任务（使用默认日期范围）

```bash
python main.py
```

### 3. 爬取指定任务

```bash
# 爬取单个任务
python main.py --task 日前备用总量

# 爬取多个任务（逗号分隔）
python main.py --task "日前备用总量,断面约束,实时备用总量"
```

### 4. 指定日期范围

```bash
python main.py --start 2025-06-01 --end 2025-06-30
```

### 5. 组合使用

```bash
python main.py --task 实时节点边际电价 --start 2025-06-01 --end 2025-06-03
```

### 6. 数据质量校验

```bash
python main.py --validate
```

### 7. 定时调度模式

```bash
python main.py --schedule
```

---

## 命令行参数

| 参数 | 说明 | 默认值 | 示例 |
|------|------|--------|------|
| `--config` | 配置文件路径 | `config.yaml` | `--config prod.yaml` |
| `--task` | 指定任务名称（逗号分隔） | 全部已启用任务 | `--task 日前备用总量` |
| `--start` | 起始日期 | 配置文件中的值 | `--start 2025-06-01` |
| `--end` | 结束日期 | 当天日期 | `--end 2025-06-30` |
| `--validate` | 仅执行数据质量校验 | - | `--validate` |
| `--schedule` | 以定时调度模式运行 | - | `--schedule` |
| `--list-tasks` | 列出所有可用任务 | - | `--list-tasks` |

---

## 配置文件说明

配置文件为 `config.yaml`，主要配置项：

### 浏览器设置

```yaml
browser:
  # 连接模式: "connect"(连接已有Chrome) / "launch"(启动新浏览器)
  mode: "connect"
  cdp_url: "http://localhost:9222"  # CDP 连接地址
  target_url_pattern: "pmos.sx.sgcc.com.cn"  # 匹配目标标签页的 URL 关键词
  headless: false        # 仅 launch 模式：是否无头模式
  slow_mo: 300           # 仅 launch 模式：操作间隔（毫秒）
  timeout: 30000         # 全局超时（毫秒）
  download_dir: "./data/exports"  # 导出文件下载目录
```

| 配置项 | 说明 | 默认值 |
|-------|------|--------|
| `mode` | `"connect"`: 通过 CDP 连接已有 Chrome；`"launch"`: 启动新 Chromium | `"connect"` |
| `cdp_url` | Chrome 远程调试地址 | `"http://localhost:9222"` |
| `target_url_pattern` | 用于查找目标标签页的 URL 关键词 | `"pmos.sx.sgcc.com.cn"` |
| `headless` | 仅 launch 模式生效，是否无头运行 | `false` |
| `slow_mo` | 仅 launch 模式生效，操作间隔（毫秒） | `300` |
| `timeout` | 全局超时（毫秒） | `30000` |

### 日期范围

```yaml
date_range:
  start_date: "2025-01-01"  # 起始日期
  end_date: ""               # 留空表示到当天
```

### 请求控制（反爬）

```yaml
request:
  page_interval: 2       # 翻页间隔（秒）
  query_interval: 3      # 查询间隔（秒）
  date_interval: 2       # 日期迭代间隔（秒）
  retry_times: 3         # 失败重试次数
  retry_interval: 5      # 重试间隔（秒）
```

### 任务开关

每个任务均可单独启用/禁用：

```yaml
tasks:
  日前备用总量:
    enabled: true          # 设为 false 可禁用此任务
    category: "现货出清结果"
    has_export: true
    has_dropdown: false
    has_pagination: false
    export_type: "原样导出"
```

---

## 数据存储结构

```
data/
├── exports/                          # 原始导出文件
├── 现货出清结果/
│   ├── 实时市场出清概况_2025-06-01.csv
│   ├── 日前市场出清概况_2025-06-01.csv
│   └── 日前备用总量_2025-06-01.csv
├── 现货实时数据/
│   ├── 实时各时段出清现货电量_2025-06-01.csv
│   ├── 实时节点边际电价_2025-06-01_1206008004.csv
│   ├── 实时输电断面约束及阻塞_2025-06-01_洪善主变.csv
│   └── ...
├── 现货日前信息/
│   ├── 断面约束_2025-06-01.csv
│   ├── 日前机组开机安排_2025-06-01_220kV思安光伏电站.csv
│   ├── 日前节点边际电价_2025-06-01_1206008004.csv
│   └── ...
└── 综合查询/
    └── 节点分配因子_2025-06-01.csv
```

### CSV 文件命名规则

```
{数据类别}_{日期}_{筛选条件}.csv
```

示例：
- `日前备用总量_2025-06-01.csv`
- `实时节点边际电价_2025-06-01_1206008004.csv`
- `日前机组开机安排_2025-06-01_220kV思安光伏电站.csv`
- `断面约束_2025-06-01.csv`

---

## 项目结构

```
crawler/
├── main.py                    # 主入口脚本
├── config.yaml                # 配置文件
├── requirements.txt           # Python 依赖
├── README.md                  # 使用说明文档
├── crawler/                   # 爬虫核心模块
│   ├── __init__.py
│   ├── browser.py             # 浏览器管理（Playwright）
│   ├── navigator.py           # 页面导航（左侧菜单/Tab 切换）
│   ├── filter_handler.py      # 筛选条件（日期/下拉框/每页条数）
│   ├── export_handler.py      # 导出处理（原样导出/导出按钮）
│   ├── pagination.py          # 分页与滚动加载
│   ├── data_extractor.py      # HTML 表格数据提取
│   └── page_crawler.py        # 页面爬取逻辑编排
├── storage/                   # 数据存储
│   ├── __init__.py
│   └── csv_storage.py         # CSV 文件存储管理
├── utils/                     # 工具模块
│   ├── __init__.py
│   ├── logger.py              # 日志管理
│   ├── parser.py              # 出清概况文本解析
│   └── validator.py           # 数据质量校验
├── data/                      # 数据输出目录（运行后自动创建）
└── logs/                      # 日志目录（运行后自动创建）
```

---

## 模块说明

### `crawler/browser.py` - 浏览器管理
- 支持两种工作模式：
  - **connect 模式**（默认）：通过 CDP 连接到已打开且已登录的 Chrome，脚本结束只断开连接
  - **launch 模式**：启动全新 Chromium 实例，支持 headless/headed 切换
- 自动查找包含目标 URL 的标签页
- 上下文管理器（with 语句）自动管理生命周期

### `crawler/navigator.py` - 页面导航
- 侧边栏使用 **el-tree（树形控件）** 而非 el-menu，通过 `span[title="..."]` 属性精确匹配菜单项
- 点击 `.el-tree-node__content` 触发展开，检查 `aria-expanded` 属性避免误触 toggle
- 导航失败时自动保存诊断截图到 `./logs/`
- 支持内容区 Tab 切换
- 特殊处理综合查询的多级菜单导航

### `crawler/filter_handler.py` - 筛选条件
- 设置日期输入框
- 获取和选择下拉选项
- 设置每页显示条数
- 点击查询按钮

### `crawler/export_handler.py` - 导出处理
- 查找并点击「原样导出」或「导出」按钮
- 通过 Playwright 下载事件捕获文件
- 自动命名保存导出文件

### `crawler/pagination.py` - 分页处理
- 获取总页数
- 翻页（下一页/跳转到指定页）
- 滚动加载（无分页控件时）

### `crawler/data_extractor.py` - 数据提取
- 从 HTML 解析表格（BeautifulSoup + lxml）
- 提取表头和数据行
- 备用 JavaScript 提取方案
- 提取「最新更新日期」

### `crawler/page_crawler.py` - 页面爬取
- 编排完整的爬取流程
- 日期迭代 + 下拉选项遍历
- 优先导出 → 回退表格解析
- 分页提取
- 出清概况特殊解析
- 数据清洗和保存
- 自动重试机制

### `utils/parser.py` - 出清概况解析
- 正则表达式提取长文本中的各项指标
- 支持负荷、电价、机组数、容量等多种指标
- 批量处理

### `utils/validator.py` - 数据校验
- 非空检查
- 必填字段检查
- 数值范围检查
- 日期连续性检查
- CSV 文件质量校验

---

## 常见问题

### Q: 无法连接到 Chrome？

**错误信息：** `无法连接到 Chrome，请确认...`

检查以下几点：
1. Chrome 是否已启动，且带 `--remote-debugging-port=9222` 参数
2. 如果 Chrome 已在运行但没带该参数，需**完全关闭**后重新启动
3. `config.yaml` 中 `cdp_url` 地址是否正确
4. 确认端口未被防火墙阻挡

```bash
# 验证 CDP 是否可用
curl http://localhost:9222/json/version
```

### Q: 连接成功但找不到目标标签页？

**错误信息：** `未找到包含「pmos.sx.sgcc.com.cn」的标签页`

- 确认 Chrome 中已打开 `https://pmos.sx.sgcc.com.cn` 并完成登录
- 检查 `config.yaml` 中 `target_url_pattern` 是否与实际 URL 匹配

### Q: 侧边栏菜单展开失败？

导航失败时会自动保存诊断截图到 `./logs/debug_*.png`，检查截图可快速定位问题：
- 如果截图显示**登录页面** → Chrome 未登录或连接到了错误的标签页
- 如果截图显示**首页但菜单未展开** → 可能是选择器或等待时间问题

### Q: 浏览器启动失败（launch 模式）？
确保已执行 `playwright install chromium` 安装浏览器。如果在 Linux 服务器上运行，可能需要安装系统依赖：
```bash
playwright install-deps chromium
```

### Q: 页面加载超时？
- 检查网络是否能访问 `https://pmos.sx.sgcc.com.cn`
- 增大 `config.yaml` 中的 `browser.timeout` 值
- 增大 `request.query_interval` 等间隔参数

### Q: 导出文件下载失败？
- 检查 `browser.download_dir` 目录是否有写权限
- 部分页面可能无导出按钮，爬虫会自动回退到表格解析

### Q: 如何只爬取特定日期的数据？
```bash
python main.py --start 2025-06-15 --end 2025-06-15
```

### Q: 如何断点续爬？
爬虫内置增量更新机制。如果某日数据的 CSV 文件已存在，会自动跳过。直接重新运行即可从中断处继续。

### Q: 如何调试特定页面？
1. 将 `logging.level` 设为 `DEBUG`
2. 使用 `--task` 参数只运行目标任务
3. 检查 `./logs/debug_*.png` 诊断截图

---

## 注意事项

1. **Chrome 启动方式**：必须使用 `--remote-debugging-port=9222` 参数启动 Chrome，否则脚本无法连接。已在运行的 Chrome（无该参数）需关闭后重新启动
2. **登录状态**：脚本不处理登录流程，需在 Chrome 中手动完成登录并进入系统首页后再运行脚本
3. **脚本不关闭浏览器**：connect 模式下脚本结束只断开 CDP 连接，Chrome 和所有标签页保持不变
4. **侧边栏结构**：左侧导航栏使用 Element UI 的 **el-tree（树形控件）**，菜单项通过 `span[title="..."]` 属性定位，如果网站前端改版，选择器可能需要更新
5. **诊断截图**：导航失败时会自动保存截图到 `./logs/debug_*.png`，便于远程调试
6. **合规使用**：请遵守目标网站的 robots.txt 和使用条款，合理控制爬取频率
7. **反爬策略**：脚本已内置合理的请求间隔，请勿将间隔调得过低
8. **网络环境**：需确保运行环境能正常访问山西电力交易平台
9. **数据准确性**：建议定期使用 `--validate` 进行数据质量检查
10. **存储空间**：长期大量爬取需注意磁盘空间，单日全量数据约 10-50MB

---

## License

本项目仅供学习和研究使用，使用者需自行遵守相关法律法规和网站使用条款。
