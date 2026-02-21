# Image Harvester v2

`Image Harvester v2` 是一个面向“图集页”的可续跑图片采集器，核心模式是：

1. 根据 `url_template` 逐页抓取 HTML。
2. 用 CSS 选择器提取图片 URL（按 DOM 顺序）。
3. 从已提取 URL 中解析“序号种子”（如 `001.jpg`），并按页面上限扩展到完整序列。
4. 下载图片并将任务状态写入 SQLite，支持中断后继续。
5. 为每个页面输出 `metadata.json`。

## 功能特性

- 序号扩展下载：不会只停留在页面当前展示的少量图片。
- 上限控制：默认以页面上限（`sequence_count_selector`）作为完成标准。
- 断点续跑：`jobs/pages/images/events` 全量状态入库。
- 失败可追踪：页面、图片级状态和最近事件可回看。
- 每页元数据：输出下载摘要、文件哈希、失败原因等。
- TUI 操作界面：启动任务、查看历史、监控进度与失败样本。
- 可选 Playwright：支持 JS 页面抓取，或作为 requests 的回退引擎。

## 环境要求

- Python `>= 3.14`（来自 `pyproject.toml`）
- `pip`
- 可选：Chromium（仅在使用 Playwright 时）

## 安装

安装基础依赖（仅核心库）：

```bash
pip install -e .
```

安装 TUI（推荐）：

```bash
pip install -e ".[tui]"
```

安装 Playwright 支持：

```bash
pip install -e ".[playwright]"
playwright install chromium
```

安装开发依赖（测试）：

```bash
pip install -e ".[dev]"
```

一次安装常用组合：

```bash
pip install -e ".[tui,playwright,dev]"
```

## 启动方式

TUI 启动：

```bash
harvester-tui
# 或
python -m image_harvester
```

当前版本以 TUI 为主入口，暂未提供独立命令行参数式 `run` 子命令。

## TUI 能力

- 左侧表单配置任务并启动。
- 启动时自动回填最近一次任务配置。
- 若最近任务状态是 `running`，会自动续跑。
- 右侧实时展示：
  - 任务列表（历史）
  - 任务统计（页面/图片）
  - 页面状态
  - 事件流
  - 失败样本
- 快捷键：
  - `r` 刷新
  - `q` 退出（运行中会二次确认）

## 配置项说明

`RunConfig` 字段如下（含默认值）：

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `url_template` | 无 | 页面 URL 模板，必须包含 `{num}` 占位符。 |
| `start_num` | 无 | 起始页码，`>= 0`。 |
| `end_num` | `None` | 结束页码；为空时按失败阈值停止。 |
| `selector` | `div.gallerypic img` | 图片 URL 提取用 CSS 选择器。 |
| `output_dir` | `data/downloads` | 图片与每页 `metadata.json` 输出目录。 |
| `state_db` | `data/state.sqlite3` | SQLite 状态库路径。 |
| `engine` | `requests` | 页面抓取引擎：`requests` 或 `playwright`。 |
| `resume` | `true` | 是否断点续跑。`false` 会重置同 `job_id` 历史状态。 |
| `page_timeout_sec` | `20.0` | 页面请求超时秒数。 |
| `image_timeout_sec` | `30.0` | 图片请求超时秒数。 |
| `image_retries` | `3` | 单张图片失败重试次数。 |
| `page_retries` | `2` | 页面抓取失败重试次数。 |
| `request_delay_sec` | `0.2` | 请求间隔秒数。 |
| `stop_after_consecutive_page_failures` | `5` | 当 `end_num=None` 时，连续页面失败达到阈值即停止。 |
| `playwright_fallback` | `false` | `engine=requests` 且解析到 0 图时，尝试 Playwright 回退抓取。 |
| `sequence_count_selector` | `#tishi p span` | 页面“图集上限”提取选择器。 |
| `sequence_require_upper_bound` | `true` | 该字段会进入任务标识；当前版本默认要求上限。 |
| `sequence_probe_after_upper_bound` | `false` | 达到上限后是否探测下一张（仅记录事件，不纳入下载清单）。 |

## 关键行为说明

- 序号种子要求 URL 路径匹配 `.../<数字>.<后缀>`，例如 `001.jpg`。
- 页面上限缺失时会标记该页 `failed_fetch`（并记录事件 `sequence_upper_bound_missing`）。
- 若在达到上限前出现下载失败，该页会标记为 `failed_fetch`（事件 `sequence_incomplete_failed`）。
- 当 `end_num=None` 时，页面状态为 `failed_fetch` 或 `no_images` 都会计入“连续失败”。
- 目录命名：
  - 页面目录固定为 6 位页码（如 `000001`）。
  - 图片文件名使用 URL basename 的安全化版本。

## 输出结构

默认输出示例：

```text
data/
  downloads/
    000001/
      001.jpg
      002.jpg
      metadata.json
    000002/
      ...
  state.sqlite3
```

`metadata.json` 包含：

- 页面信息：`job_id`、`page_num`、`page_url`、`source_id`、`selector`、`engine`
- 图片明细：`index`、`url`、`local_path`、`status`、`http_status`、`sha256`、`error` 等
- 汇总：`total_count`、`success_count`、`failed_count`、`duration_sec`、`status`

## 任务状态

- 任务级：`running` / `completed` / `failed`
- 页面级：`pending` / `running` / `completed` / `completed_with_failures` / `no_images` / `failed_fetch`
- 图片级：`pending` / `running` / `completed` / `failed`

SQLite 表结构（自动初始化）：

- `jobs`
- `pages`
- `images`
- `events`

## 代码调用示例（无 TUI）

```python
from pathlib import Path

from image_harvester.config import compute_job_id, run_config_json
from image_harvester.fetchers import RequestsFetcher
from image_harvester.models import RunConfig
from image_harvester.pipeline import ImageHarvesterPipeline
from image_harvester.state import StateStore

cfg = RunConfig(
    url_template="https://example.com/gallery/{num}.html",
    start_num=1,
    end_num=10,
    output_dir=Path("data/downloads"),
    state_db=Path("data/state.sqlite3"),
)

store = StateStore(cfg.state_db)
try:
    pipeline = ImageHarvesterPipeline(
        config=cfg,
        store=store,
        fetcher=RequestsFetcher(),
    )
    summary = pipeline.run(
        job_id=compute_job_id(cfg),
        config_json=run_config_json(cfg),
    )
    print(summary)
finally:
    store.close()
```

## 开发与测试

运行测试：

```bash
pytest
```

建议先安装：

```bash
pip install -e ".[dev]"
```

## 注意事项

- 请仅采集你有权访问和下载的内容，并遵守目标站点的服务条款与法律法规。
- 若目标站点反爬严格，可适当提高 `request_delay_sec`、调整超时与重试，或启用 Playwright。
