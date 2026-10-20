# Podcast → PDF · 混合模式 C

当前架构：**GitHub 每小时检查小宇宙 RSS；Windows 电脑启动本地 worker 后才会下载音频、转录全文并生成无时间戳 PDF。无 Google Cloud。**

## 现状与限制

- RSS 监控配置：`config/feeds.json`，首个节目《非共识20分钟》。
- GitHub 工作流：`.github/workflows/rss-watch.yml`；首次运行仅登记历史节目基线，之后只追加新节目。
- 新节目信息公开保存在 `queue/state.json`（标题、公开地址，不含转录全文）。
- Windows 转写：`scripts/local_worker.py`；运行 `run-local.ps1`。
- 默认输出到 `%USERPROFILE%\\Podcast Library`，每期包含音频、全文 TXT、PDF、元数据。
- **未完成**：AI 高质量总结、人物可靠分离、自动上传 Drive、ChatGPT 内主动通知、Windows 开机自动启动。本地 `summary.md` 是明确的占位文件。
- 公开仓库请勿提交完整音频、转写全文、秘钥或个人批注。
- 首次运行不会把已有历史节目加入待处理队列。
- 未经端到端运行验证，不能视为生产级上线。

## Windows 首次运行

1. 安装 Python 3.11 或 3.12（含 `py` 启动器）；必要时安装 FFmpeg。
2. 下载或 clone 仓库：`git clone https://github.com/w1llyc3/podcast.git`
3. GitHub → Actions → **RSS Watch** → Run workflow，运行初始基线；检查 `queue/state.json`。
4. 未来发现新节目后，在 PowerShell 中进入仓库并运行 `.\\run-local.ps1`。首次会下载依赖与 Whisper 模型。
5. 检查生成的 PDF、TXT 和音频；待测试通过再通过 Windows 任务计划程序安排开机触发。
6. 通过编辑 `config/feeds.json` 添加更多小宇宙 RSS；首次出现的 RSS 会建立基线。

## 文件

- `scripts/rss_watch.py`：监控公开 RSS、去重并更新队列
- `queue/state.json`：持久化监听状态与待处理元数据
- `scripts/local_worker.py`：本地转写与 PDF 排版
- `run-local.ps1`：Windows 启动器
- `.github/workflows/podcast.yml`：旧云端转录流程已禁用，仅手动提示

## 设计约束

不自动下载付费内容、不推断未经确认的说话人姓名。自动转录中的专名和金融数字仍需校对。GitHub Actions 定时触发可能延迟。
