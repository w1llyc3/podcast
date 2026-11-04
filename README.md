# Podcast → PDF · 混合模式 C

当前架构：**GitHub 每小时检查小宇宙 RSS；Windows 电脑启动本地 worker 后才会下载音频、转录全文并生成无时间戳 PDF。无 Google Cloud。**

## 现状与限制

- RSS 监控配置：`config/feeds.json`，首个节目《非共识20分钟》。
- GitHub 工作流：`.github/workflows/rss-watch.yml`；首次运行仅登记历史节目基线，之后只追加新节目。
- 新节目信息公开保存在 `queue/state.json`（标题、公开地址，不含转录全文）。
- Windows 转写：`scripts/local_worker.py`；运行 `run-local.ps1`。
- 固定归档根目录 `D:\podcast`，每期包含压缩音频、带时间分段 JSON、无时间戳 TXT/PDF、元数据和本地摘录式学习笔记。
- 学习笔记为免费本地原文摘录，带段落来源与核验清单；不是高质量生成式总结。人物分离尚未实现。当前 Codex 聊天可配置本地完成通知，ChatGPT 网页独立投递桥接尚未实现。Drive 提供显式选择的 rclone 复制工具，默认 dry-run，尚未真实上传验收。
- 公开仓库请勿提交完整音频、转写全文、秘钥或个人批注。
- 首次运行不会把已有历史节目加入待处理队列。
- 未经端到端运行验证，不能视为生产级上线。

## Windows 首次运行

1. 安装 Python 3.12（含 `py` 启动器）。PyAV 自带解码组件；imageio-ffmpeg 依赖提供压缩用 FFmpeg，也可通过 PODCAST_FFMPEG 指定本机程序。
2. 下载或 clone 仓库：`git clone https://github.com/w1llyc3/podcast.git`
3. GitHub → Actions → **RSS Watch** → Run workflow，运行初始基线；检查 `queue/state.json`。
4. 未来发现新节目后，在 PowerShell 中进入仓库并运行 `.\\run-local.ps1`。首次会安装依赖及下载免费本地 Whisper 模型；已有环境需要更新依赖时加 `-InstallDependencies`。
5. 检查产物后运行 `./install-task.ps1`，安装当前用户登录后 + 每小时任务（隐藏窗口、单实例、断网重试）。`./status.ps1` 查看结果；`./uninstall-task.ps1` 卸载。登录前、电脑关机时不会转录。
6. 通过编辑 `config/feeds.json` 添加更多小宇宙 RSS；首次出现的 RSS 会建立基线。

## 文件

- `scripts/rss_watch.py`：监控公开 RSS、去重并更新队列
- `queue/state.json`：持久化监听状态与待处理元数据
- `scripts/local_worker.py`：本地转写与 PDF 排版
- `run-local.ps1`：Windows 启动器
- `.github/workflows/podcast.yml`：旧云端转录流程已禁用，仅手动提示

## 设计约束

不自动下载付费内容、不推断未经确认的说话人姓名。自动转录中的专名和金融数字仍需校对。GitHub Actions 定时触发可能延迟。

## 已执行的 Windows P0 验证（2026-10-20）

审计与证据摘要见 [docs/P0_VALIDATION.md](docs/P0_VALIDATION.md)。真实测试选用公开 Ep 6，未修改 90 个历史 GUID 或生产待处理队列。完整音频 8,692,269 字节，解码 537.379 秒；large-v3-turbo/int8 全段处理，最终 2 页 PDF。172 个分段均可从 PDF 提取，TXT 与原始识别内容一致。逐页视觉检查通过，但术语、专名和部分断句有 ASR 错误，未经逐句听校，不能称为精校稿。

```powershell
# 显式试跑历史公开单集，不更改云端历史基线
.\run-local.ps1 -EpisodeId 6988cde266e2c303777f8add -Model large-v3-turbo
# 默认为 D:\podcast，small/medium 可选；默认 large-v3-turbo
.\run-local.ps1 -Model large-v3-turbo
# 安装测试依赖后核验本地产物（不上传）
.\.venv\Scripts\python.exe -m pip install -r requirements-test.txt
.\.venv\Scripts\python.exe scripts/verify_local.py --resume-test
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

下载使用 `.part`、ETag/Last-Modified + Range，验证长度后重命名；服务器不支持续传时重新下载。转录每 90 秒保存原子检查点，失败最多重试 3 次；再次运行从已提交检查点继续。独立切片的边界文字仍需校对。完成清单校验产物哈希，重复运行跳过已完成集；显式 `--reprocess` 才重做并备份旧分段稿。

`D:\podcast\logs`、`completed.json`、`worker-state.json`、`index.json` / `index.csv`、`notification-outbox.json` 均只存本地。通知 outbox 只是数据文件，不能当作已通知。此次已按用户选择配置当前 Codex 聊天每小时本地检查，变化时才提醒；首次定时投递尚待实际触发，需电脑与 Codex 桌面应用运行。没有启用 ChatGPT 网页独立桥接。无收费 API 配置。

## 可选私有 Drive 归档

需先在本机安装 rclone，并自行完成个人 Drive 的 OAuth 授权，配置一个私有 remote；本项目不会创建 Google Cloud 项目或服务账号。

```powershell
# 默认仅演练；remote 必须由用户明确指定
.\.venv\Scripts\python.exe scripts/archive_drive.py --remote 'my-private-drive:Podcast Library'
# 确认目标后显式加 --upload 才复制；不会删除本地或远端文件
```

当前环境未配置 rclone/remote，因此上传未启用、未实测；不把代码存在视作归档成功。公开仓库仅存代码、公开 RSS 元数据和脱敏验收结果。完整音频/转录/笔记/日志/模型禁止提交。

## 自动音频压缩

以后每集必须完成压缩与验收才标记 completed，交付音频固定为 `audio.mp3`：MP3 / 48 kbps / 24 kHz。单声道或高度相似的双声道合并为单声道；疑似独立声道保留立体声并在元数据记录，避免丢失单侧内容。声道判断是相似度规则，不是人物识别。

转录先使用下载原文件，压缩不降低本次识别输入质量。原文件先复制到输出根目录的 `.audio-backups/automatic` 并校验 SHA256；压缩文件通过完整解码、编码参数与时长检查（差值不超过 0.25 秒），所有产物和完成索引写入后才移除节目目录内的原文件。备份仅本地保留，可供人工恢复。

压缩失败会重试并复用已完成的转录检查点；压缩收据支持中断后恢复，已验证的 MP3 不重复有损编码。队列遇到旧版已完成归档时，仅迁移音频，不重写 TXT/PDF/学习笔记。重新部署或更新既有环境时运行 `./run-local.ps1 -InstallDependencies` 安装新增依赖。本次机器已安装。

测试范围和实际结果见 [docs/AUDIO_COMPRESSION_VALIDATION.md](docs/AUDIO_COMPRESSION_VALIDATION.md)。音频、全文、备份和本地运行证据均不提交 GitHub。
