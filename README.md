# Iran News Monitor Bot

一个基于 Python 的伊朗新闻监控脚本：

- 定时从 NewsAPI 拉取与伊朗相关的英文新闻
- 调用 Anthropic API 将标题和摘要翻译为中文
- 通过 Telegram Bot 推送到指定聊天
- 使用本地 `sent_news.json` 去重，避免重复发送

## 功能说明

- 默认每 10 分钟检查一次新闻
- 默认关键词：`Iran OR Tehran OR IRGC`
- 默认拉取最近 10 条英文新闻
- 启动时会先发送一条机器人上线通知，再执行首次检查

## 运行环境

- Python 3.9+

## 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 配置

1. 复制示例配置：

```bash
cp .env.example .env
```

2. 按实际值填写 `.env`：

```env
TELEGRAM_BOT_TOKEN=你的 Telegram Bot Token
TELEGRAM_CHAT_ID=你的 Telegram Chat ID
ANTHROPIC_API_KEY=你的 Anthropic API Key
NEWS_API_KEY=你的 NewsAPI Key
CHECK_INTERVAL_MINUTES=10
NEWS_QUERY=Iran OR Tehran OR IRGC
NEWS_PAGE_SIZE=10
ANTHROPIC_MODEL=claude-sonnet-4-20250514
```

## 启动

```bash
python3 iran_monitor_bot.py
```

启动后脚本会持续运行，并按 `CHECK_INTERVAL_MINUTES` 设定的周期轮询。

## 主要依赖

- `requests`：请求 NewsAPI、Anthropic API、Telegram Bot API
- `schedule`：定时任务调度
- `python-dotenv`：从 `.env` 加载本地配置

## 生成文件

- `sent_news.json`：已推送新闻的哈希缓存，自动生成

## 注意事项

- `.env` 中包含敏感密钥，不要提交到版本库
- 如果 Telegram 收到的内容格式异常，通常是上游标题或摘要包含特殊字符，当前脚本已做基础 HTML 转义
- NewsAPI 免费额度有限，轮询频率不要设置过低

## 后续可扩展

- 增加更多筛选关键词
- 增加地区/来源过滤
- 增加异常重试与日志落盘
- 改为 systemd、pm2 或 Docker 常驻运行
