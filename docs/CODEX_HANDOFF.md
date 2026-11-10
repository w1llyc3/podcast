# Codex 开发交接｜Podcast → PDF（C 混合方案）
> 2026-10-20 接手实测更新见 [P0_VALIDATION.md](P0_VALIDATION.md)。以下为原始交接背景；当前本地代码目录为 `D:\podcast\automation`，技术闭环和自动任务已实跑，逐句听校、Drive 实传及 ChatGPT 通知仍未完成。
**仓库**：https://github.com/w1llyc3/podcast  
**本地 Windows 程序目录建议**：D:\podcast-tool  
**最终归档根目录**：D:\podcast  
**禁止恢复 Google Cloud 方案**：GitHub 仅监控 RSS；Windows 开机后本地下载音频、转录、生成 PDF、学习笔记。

## 目标
指定小宇宙节目 RSS 更新后，GitHub Actions 只负责发现新集和入队，不负责音频下载/语音识别；本地 Windows worker 自动消费队列，保存每集 `audio.m4a`（保持真实格式）、`transcript.raw.json`、`transcript.txt`、`transcript.pdf`、`summary.md`、`metadata.json`。最终希望 ChatGPT 可以发送新增节目的学习总结与音频/PDF 链接，但必须验证可访问的通知桥接后才宣称完成。

## 接手时的实际已知状态（请先只读复核）
- 仓库已有 `config/feeds.json`，首条为《非共识20分钟》，RSS `https://feed.xyzfm.space/lmbwg36kuy3x`。
- `.github/workflows/rss-watch.yml` 每小时运行；首次 **RSS Watch #1 成功**，`queue/state.json` 已保存 **90 个历史节目 GUID** 的基线，`pending=0`。
- `scripts/rss_watch.py` 负责基线和新集排队。
- `scripts/local_worker.py`、`requirements-local.txt`、`run-local.ps1` 已提交，但**尚未 Windows 真机 E2E 验证**。
- `run-local.ps1` 已更新输出 `D:\podcast`。
- 旧 `.github/workflows/podcast.yml` 已改为手动空提示，禁止重新启用云端转录。
- `README.md` 有 C 模式说明。仓库目前是 **public**，不得提交音频、全文、私人笔记、token。

## P0：先跑通真实闭环（最优先）
1. **只读审计**：核验 main 分支、代码、工作流状态、队列基线、Windows 依赖；输出缺陷清单。避免推倒重写。
2. **修复依赖与运行器**：Python 3.11/3.12、FFmpeg、faster-whisper、可靠中文字体/PDF 引擎；首次安装模型可复用缓存；Windows 中文路径、非法字符和长路径安全。
3. **增加显式指定单集试跑模式**：例如 `--episode-url` 或 `--episode-id`，允许选择一条《非共识20分钟》的公开短集作为 E2E 测试，**不污染现有 90 集历史基线**。默认不重新转录历史节目。
4. **完整获取音频**：依据 RSS enclosure 下载公开音频，验证 HTTP、文件大小、时长、音频格式。只有试听的付费节目不得宣称完整。
5. **完整转录**：中文为主，保留全部对话与段落顺序。原始带时间的分段存 `transcript.raw.json`；阅读版 TXT/PDF **删除时间戳**。不能可靠识别人物时用 Speaker 1/2 或未标注，不杜撰姓名。
6. **PDF 排版**：参照之前《非共识20分钟_Ep01_完整文字稿》：A4、原节目标题、原节目链接、正文自然段、页码、中文可搜索复制，无时间线，不产生空白末页、黑块/缺字、仅链接孤页。
7. **金融事实风控**：股票代码、数字、百分比、金额、年份和专名不得未经依据改写；疑点留标记，不能宣称人工精校。
8. **增量与容错**：已完成集绝不重复转录；下载中断能恢复；失败记录明确并可重试，日志存 `D:\podcast\logs`。同一个 worker 不能并发抢同一任务。
9. **真实验收**：在用户 Windows 上运行一次指定单集，将实际音频/TXT/PDF 路径、页数、可提取正文检查结果交付；重复运行应跳过已完成集。

## P1：本地自动运行和学习笔记
- Windows 任务计划：登录时启动 + 每小时轮询，独占锁、断网重试、不弹多窗口；提供 `install-task.ps1`、`uninstall-task.ps1`、`status.ps1`。用户同意后再安装自动任务。
- `summary.md` 目前是占位文本，**不是已生成 AI 总结**。实现可配置总结：一句话结论、观点/证据/反方/证伪、资产和股票代码、明确自述交易 vs 建议 vs 假设、跨期观点变化（仅有可靠历史资料时）、待核验事项；引用对应原文，不能杜撰。
- 总结服务如涉及收费 API，先向用户列出费用与授权步骤，经确认才配置；没有 API 时保留转录成功，标记 summary 为 `unavailable`。
- 新增订阅只改 `config/feeds.json`；每个新 RSS 首次建立基线，不回填所有历史。

## P2：长期同步与 ChatGPT 通知
- **本地 D:\podcast 是永久存储的主副本**。Google Drive 作为可选同步，不用 Google Cloud；若采用 rclone，本地用户授权，密钥不进公开仓库。
- 生成可检索的本地 `index.json`/`index.csv`，记录标题、发布时间、原始 URL、处理状态、音频/PDF/总结路径、失败信息；公共 GitHub 不泄漏本地路径或私密信息。
- ChatGPT 主动通知必须依赖 ChatGPT 任务实际可读取的稳定索引或 Drive 链接；**不能假定 GitHub Actions 能直接向 ChatGPT 会话发消息，也不能以 RSS 监控成功代表 PDF 完成**。若桥接不可行，明确限制并提供真实可用的替代通知渠道。
- 每期完成时可交付原音频 + 完整 PDF + 学习笔记 + 可验证链接。

## 约束 / 非目标
- 停止 Google Cloud；不得创建 GCP Bucket、服务账号、云转录实例或启用旧 workflow。
- 无用户明确同意，不开启任何付费服务，不配置额外 API 消费，不公开音频和全文。
- 不能重复处理已有的历史 90 集；试跑仅处理被指定的公开节目。
- 不删改原文立场、不把摘要当逐字稿、不臆测说话人身份。
- 遵守原媒体访问权限，无法取得完整音频应明确报错或标“试听”。

## 实施顺序与汇报格式
A. 只读审核仓库、环境，给出 `已完成｜未完成｜阻塞｜下一步` 表。  
B. P0 单集端到端测试（先提供测试计划，后执行）；对照音频核查 PDF。  
C. 再跑一次同一集验证去重，模拟断点恢复。  
D. 测试 RSS 入队→Windows 消费，但不污染生产基线。  
E. P1 自动运行与总结；F. P2 可选云同步与 ChatGPT 通知。

每阶段产出 GitHub 提交/PR、测试命令、日志摘要、实际文件路径和失败原因。**没有真实执行证据就不得写“已上线”。**

**Codex 现在开始：先对 `w1llyc3/podcast` 做只读审计，然后优先完成 P0，不要等待 P1/P2 全部开发完才向用户反馈。**
