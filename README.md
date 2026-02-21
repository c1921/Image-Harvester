# Image Harvester v2

Image Harvester v2 是一个基于 URL 模板的图片下载工具，提供：

- 按页面 DOM 顺序下载图片
- 使用 SQLite 记录状态，支持中断后续跑
- 每页生成独立元数据文件（`metadata.json`）
- CLI 命令：`run`、`status`、`retry-failed`、`export-metadata`
- 可选的 Playwright 抓取引擎

## 快速开始

```bash
pip install -e .
harvester run --url-template "https://example.com/gallery/{num}.html" --start-num 1 --end-num 3
```

## 命令帮助

```bash
harvester run --help
harvester status --help
harvester retry-failed --help
harvester export-metadata --help
```

## 可选 JavaScript 引擎

安装 Playwright 支持：

```bash
pip install -e ".[playwright]"
playwright install chromium
```
