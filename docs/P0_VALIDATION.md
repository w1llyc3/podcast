# Windows P0 实测记录 · 2026-10-20

## 修改前只读审计

- 仓库 main：`d3ad68899841f45ff5fe0c1a86d0a9707d467e4b`。
- RSS Watch 运行 `39393760359`：success，2026-10-20 16:29 北京时间。
- `feigongshi20` 历史 GUID 90，pending 0。本次单集测试未修改生产基线。
- 旧云端 workflow 为手动空提示；本次继续保持禁用，旧 pipeline 直接运行也会拒绝。
- Windows Python 3.12 已安装；系统环境仅 pip，无项目依赖和虚拟环境。
- 原代码存在：最终音频文件可能是下载残片；无检查点、失败状态和并发锁；完成状态非原子写；无原始分段稿；中文字体未嵌入；RSS 响应内重复 GUID 可重复排队；500 条队列截断可丢任务；默认输出与启动器不一致；无隐私 `.gitignore`。

## 实际环境与依赖修复

- 使用独立 `.venv`，免费本地 faster-whisper 1.2.1 / CTranslate2 4.8.3，CPU int8。
- 真机首次运行失败：PyAV 19 移除 `metadata_errors` 参数，与 faster-whisper 不兼容。安装 PyAV 16.1.0，并加入 `av>=14,<17` 约束后通过。
- reportlab 4.5.1，嵌入 Windows SimHei TrueType 字体；字体不进入仓库。
- pypdf 6.21.1 做文字提取，PyMuPDF 1.26.7 与 Poppler 渲染每页；fonttools 校验已用字形。
- `pip check` 实际输出：No broken requirements found。

## 真实单集 E2E

- 显式选择公开 RSS GUID `6988cde266e2c303777f8add`，Ep 6《家族办公室：不是投资机构，是创始人意志的对外表达》。没有批量处理历史节目。
- 源文件为真实 M4A 容器，8,692,269 字节；SHA256 `5dfa4d54e90c73f47db6e8f6beb35ea80b94188ed2953d284d5d50145960e4f8`。
- RSS 标注 8:57；容器 537.4 秒；完整解码 537.3794375 秒，一致。未裁剪音频。
- small 和 medium 两轮成功后均保留备份，最终 large-v3-turbo（使用 RSS 标题主题提示）覆盖完整 6 个连续检查点，最后终点 537.3794375 秒；172 个非空原始分段。
- 已生成完整原音频、`transcript.raw.json`、`transcript.txt`、`transcript.pdf`、`metadata.json`，随后生成本地摘录式 `summary.md`。
- 最终 TXT 2,465 字符（含空白），13 个阅读段落；PDF A4 共 2 页，有原始标题、来源链接和页码，无时间戳。
- 172 个原始分段均可从 PDF 提取；去空白后 TXT 与原始分段完全一致。所有使用的中文字形在嵌入字体中存在。
- 全部页面渲染并视觉检查：未见黑块、缺字、裁切、覆盖、空白末页或仅链接孤页。两页提取字符数分别为 1,405 / 1,238（含标题链接页脚）。
- 本地完整报告和哈希保存在 `D:\podcast\evidence\pdf-check.json`，逐页 PNG 和总览图同目录；不提交到 GitHub。

## 去重、失败与恢复

- 对同一真实单集重复运行：日志 `Already completed; skipped`；六个产物 SHA256 均未改变，无二次转录。
- 真实 medium 及最终 large-v3-turbo 恢复实验：另存隔离检查点，保留前 5 个 chunk，去掉最后一个 chunk；模型只调用 1 次，补全最后 87.379 秒，已提交前文逐项完全一致。实验不改最终原始稿。
- 故障注入测试：本地 HTTP 服务在发送 700,000 字节后主动断开连接；worker 实际遇到 IncompleteRead，再以 Range 恢复，最终 2 MiB 数据逐字节一致。
- 失败状态→再次运行成功→重复任务跳过的消费测试通过。
- 转录第二块注入异常→从第一块后继续、不重复第一块的恢复测试通过。
- 同一输出根目录的独占锁验证通过。
- RSS 隔离夹具：首次仅建基线；重复 GUID 仅一次入队；再次轮询不重复。夹具不连接生产 RSS、不写生产 queue。
- `python -m unittest discover -s tests -v`：5 tests，OK。日志中的 ERROR 来自主动注入故障，不是未通过的测试。
- 生产 `queue/state.json` 无 diff，仍为 90 / 0。

## P1/P2 实际状态

- 本地学习笔记：已生成、引用 TXT 段落，使用原文摘录与核验问题，不调用收费 API；不是生成式高质量总结。
- 当前用户任务 `PodcastLocalWorker`：已安装，登录后 + 每小时、隐藏窗口、单实例、失败后重试。2026-10-20 16:57:14 实际触发，LastTaskResult 0；日志 selected=0, failures=0。登录前不运行；真实重启登录尚未验收。
- 私有本地索引 JSON/CSV 与通知 outbox 已生成。outbox 明确标注 `local_only_no_chatgpt_bridge`，没有声称投递到 ChatGPT。
- Drive：仅实现显式选择的 rclone copy，默认 dry-run；当前无 rclone 和授权 remote，未上传、未验收。
- 用户选择当前 Codex 聊天通知、本次不启用 Drive。已创建 ACTIVE 每小时本地检查（自动化 ID `podcast`），仅在真正完成、失败变化或需要处理时提醒；现有测试集已建立通知游标。首次定时投递尚待实际触发，不声称已完成端到端投递。电脑与 Codex 应用需保持运行。ChatGPT 网页独立桥接仍未实现。

## 准确性边界与剩余验收

本次通过的是完整下载、完整时长处理、文件一致性、PDF 显示和可复制性、容错与去重。**未逐句听校音频，不能将机器稿称为精校稿，不能宣称逐字语义完整性已获人工验收。** 仍有“家办”等术语、专名、标点及简繁混用问题；90 秒切片边界也需核查。数字和人名没有通过规则自动改写。元数据 `human_reviewed=false`。

未经用户授权不启用收费服务；不创建 Google Cloud 项目、服务账号或实例；不上传音频、全文、笔记、密钥或个人资料到公开 GitHub。
