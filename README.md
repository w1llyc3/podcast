# Podcast → PDF

多档小宇宙 RSS 自动归档：发现更新 → 下载音频 → 中文转录 → 无时间戳 PDF → 学习笔记 → 云端归档。

> 当前状态：**部署草稿；尚未启用自动生产**。本仓库是公开仓库，不要提交音频、转录全文、个人笔记或任何密钥。

## 预期交付

每期归档 `audio.m4a`、`transcript.txt`、`transcript.pdf`、`summary.md`、`metadata.json`。
PDF 为《非共识20分钟》阅读版：A4、无时间线、完整原文、按段落排版。多人节目暂标记说话人待核对（基础转录不保证准确分离）。

## 部署步骤

1. 审阅 `config/feeds.json`；按需加入其他节目 RSS。
2. 云端持久存储：通过 GitHub Actions Secrets 设置 `RCLONE_CONFIG_B64`（rclone 配置 Base64）；云端目标默认 `podcastdrive:Podcast Library`，也可以使用仓库变量 `ARCHIVE_REMOTE` 指定。
3. 在仓库 Actions 中手动运行 **Podcast pipeline** 做首次测试。首次测试默认仅检测并写入初始基线，不下载历史全部节目；如需转录某一期，设置 `EPISODE_ID` 变量（RSS guid/id）。
4. 检查 PDF、摘要及归档链接。确认后设置仓库 Actions Variable `PODCAST_ENABLED=true`，开启定时执行。
5. 配置额外的 ChatGPT 定时任务读取 `index.json`（需稳定可访问的索引链接），提供新节目通知；**GitHub Actions 本身不能直接向 ChatGPT 对话推送消息**。

### Important limitations

- 定时 GitHub Actions 可能延迟；公共托管 runner 的 CPU 对长篇音频可能较慢，需确认分钟数配额和单次运行限制。
- GPU / 高性能云运行器需另行选型；模型首次下载较耗时。
- 第一次运行只建立基线，防止重转旧节目；之后按 GUID 去重。
- 当前版本生成规则式学习笔记（待校对摘要提取）；未配置可靠的 AI 校对模型，不声称自动完成专业名词和数字人工精校。
- 公开 RSS 仅能获取公开音频；付费试听不会被误称为完整节目。
- 云端 rclone 配置属于密钥，不能提交入库。
