---
name: lab-meeting-summary
description: 在 Windows 和 Conda 中按步骤检查并按需准备工具及 ASR 模型，内存转写科研组会视频，由具备本地工具与图像能力的当前 AI 生成逐人详细 Markdown 纪要；仅保存最终 MD。适用于 Codex、DeepSeek Harness 等本地 AI 软件，不用于视频剪辑或实时参会。
---

# LabMeeting-AI：给调用软件的执行步骤

当前 AI 使用本机工具完成解码、转写和定点取帧，再自行写纪要。脚本不提供总结 API，也不自动写 MD；无需另装本地总结 LLM 或启动第二个 AI CLI。以下步骤不依赖某个软件的专用工具名称，具体进程、stdout和图像接口按宿主适配。

## 如何让不同软件调用

1. 让调用软件能够访问完整项目，而非只上传本文件。Skill可位于项目内，也可经用户授权安装到宿主skills目录；本机全局位置为 `J:\codex\.codex-data\home\skills\lab-meeting-summary`，安装状态须实际核实。若软件已发现并注册此Skill，可使用 `$lab-meeting-summary` 加视频与输出完整路径。
2. 未注册时，直接向具备本地工具能力的AI发送下面的请求；换机先替换Skill路径和输入输出占位符：

```text
请完整阅读 E:\BRC\Meet\LabMeeting-AI\.agents\skills\lab-meeting-summary\SKILL.md，并按其中步骤及引用文件执行。
视频：<视频的完整路径>
输出：<最终纪要.md的完整路径>
先核对已有环境和模型，缺失时按当前授权规则准备；会议处理只保存最终MD。
```

3. 收到调用后，从第0步开始；环境齐全则走复用分支。普通聊天窗口、仅支持上传文档或无法运行本机工具的软件不能据此自动处理本地视频。

## 始终保留的约束

- 会议处理只写用户指定的最终 MD。音频、转写、截图、提纲、日志、性能记录均不落盘，不用重定向或Tee，不先生成再删除；原视频只读。工具代码、Conda环境与可复用模型是持久资产，首次安装缓存须与会议处理区分。
- 日常通过Skill自带的固定 `scripts/run.cmd`启动已核实的Conda环境绝对解释器，或等价地直接调用该解释器；不用会先写临时批处理再删除的 `conda run`。固定入口是持久工具文件，运行时不生成临时启动脚本。主脚本尽早禁用Python字节码及CUDA缓存、启用HF离线模式，并以Python audit hook拦截文件写入尝试。该约束覆盖本工具的Python层，不代表能控制AI应用自身会话数据库、系统分页或未暴露audit事件的原生DLL写入；宿主不得另存转写、截图或磁盘spool，适配边界见[协议](references/工具调用协议.md)。
- 优先复用已验证资产；缺失项才进入安装分支。安装、修改环境、下载、覆盖与清理按当前用户规则及有效授权执行；已有覆盖本步的授权不重复询问。不要擅自改base、驱动、系统PATH、安装WSL或其他总结后端。
- 本流程在Windows x64 + Conda + NVIDIA CUDA上验证。支持不同本地AI软件调用，不表示已经跨操作系统验证；全局安装及宿主发现状态另行核实。

## 第0步：确定输入、输出和项目位置

1. 从用户请求取得视频的完整路径和最终MD完整路径；仅缺必需信息时询问。目标已存在时核对覆盖授权，不自动生成第二份“临时稿”。
2. 优先使用用户明确提供的完整项目路径，或本次进程的 `LABMEETING_AI_PROJECT`。项目内Skill可从 `SKILL.md`所在目录向上三级寻找项目；全局副本不能这样认定仓库位置，可使用已核实的本机项目 `E:\BRC\Meet\LabMeeting-AI`。核实根目录的 `labmeeting.py`、`download_model.py`、`environment.yml`可读。Skill中的固定入口与参考文件不包含完整工具代码或模型；项目缺失时进入[首次配置第0–1步](references/首次配置.md)。
3. 核实宿主能访问上述路径、直接运行已核实Conda环境解释器的独立子进程、持续完整接收stdout、保持跨调用内存状态，并查看内存JPEG；这些步骤不得另行生成会议中间文件。首次适配一个软件时，先读[工具调用协议](references/工具调用协议.md)。
4. 每次命令调用都指定工作目录或使用绝对路径；不要假设两次终端共享变量、当前目录或 `conda activate` 状态。不要将脚本导入宿主自己的Python进程。

本机路径实例：Conda为 `D:\software\Anaconda\Scripts\conda.exe`，环境解释器为 `D:\software\Anaconda\envs\labmeeting-ai\python.exe`，项目为 `E:\BRC\Meet\LabMeeting-AI`，环境名 `labmeeting-ai`，模型在 `models/large-v3-turbo`。环境仍由Conda管理；其他机器先核实再替换，不把实例路径当作已存在证据。

## 第1步：选择复用或首次配置分支

| 已确认状态 | 下一步 |
|---|---|
| 环境、GPU DLL和模型均已验证，且未变化 | 直接第2步，不每次重复安装、下载、help、check或短测 |
| 首次使用、换机或缺组件 | **先完整阅读并逐步执行[首次配置](references/首次配置.md)**：源码→Conda/依赖→GPU库→模型→短测 |
| 已有环境但出现导入、DLL、模型或推理错误 | 只进入首次配置中对应的排错步骤，列清差异，不盲目重装 |
| 宿主不能执行本地命令、完整接收输出或查看图片 | 报告具体能力缺口；不能用普通文字聊天冒充执行或视觉核验 |

首次配置文档包含完整命令、来源、固定模型revision/SHA256、安装授权节点、成功条件与失败分支；不要从其他示例自行拼一套未核实安装流程。Python依赖由项目 `environment.yml` 定义；CUDA12/cuBLAS/cuDNN9不由该文件保证齐全。本机只是复用已有 `DL/torch/lib` DLL，并不要求其他电脑安装PyTorch或创建同名环境。

## 第2步：启动完整内存转写

将下面路径替换为第0–1步确认的实际值；视频占位文字不能直接执行。模型必须是本地CTranslate2目录，不能只传 `turbo` 名称。推荐使用Skill自带的固定入口：

```powershell
& 'C:\Windows\System32\cmd.exe' /d /c '"E:\BRC\Meet\LabMeeting-AI\.agents\skills\lab-meeting-summary\scripts\run.cmd" stream --video "会议视频的实际完整路径.mp4" --model "E:\BRC\Meet\LabMeeting-AI\models\large-v3-turbo" --dll-dir "D:\software\Anaconda\envs\DL\Lib\site-packages\torch\lib" --compute-type int8_float16 --batch-size 2 --beam-size 1 --language auto'
```

全局安装后，可将入口路径换为 `J:\codex\.codex-data\home\skills\lab-meeting-summary\scripts\run.cmd`。固定入口接收完整的 `labmeeting.py` CLI参数并原样透传；项目优先取进程变量 `LABMEETING_AI_PROJECT`，否则从入口所在目录向上四级查找，未找到再回退本机项目路径。用户明确指定项目时，将该路径传入本次子进程的 `LABMEETING_AI_PROJECT`。解释器默认使用本机已核实路径，可用进程变量 `LABMEETING_AI_PYTHON`覆盖；换机先核实并在每次子进程调用中传入实际值，不修改系统环境。

直接解释器是等价备用，两种入口二选一，不重复转写：

```powershell
& 'D:\software\Anaconda\envs\labmeeting-ai\python.exe' -I -B -u -X utf8 'E:\BRC\Meet\LabMeeting-AI\labmeeting.py' stream --video '会议视频的实际完整路径.mp4' --model 'E:\BRC\Meet\LabMeeting-AI\models\large-v3-turbo' --dll-dir 'D:\software\Anaconda\envs\DL\Lib\site-packages\torch\lib' --compute-type int8_float16 --batch-size 2 --beam-size 1 --language auto
```

正式运行不带 `--limit-seconds`。默认配置适用于本机已验证路线；显存不足时明确报告并评估batch1，不自动转CPU、关其他程序或换模型。正常转写不联网下载权重。

默认 `--language auto`以原语言转写（`task=transcribe`），启用多语种模式；每个VAD音频块（约30秒）选择主语言提示，支持中英文交替。不等于逐词或每条最终字幕段的语言检测，同一块内的混合术语仍需复核。`--language zh`或 `en`固定语言提示并关闭分块切换，也不做翻译。

`-I`隔离用户site和 `PYTHONPATH`，`-B`禁止字节码写盘，`-u`实时输出，`-X utf8`固定UTF-8；不依赖 `activate` 或上次shell状态。入口在当前进程加载本环境 `sys.prefix\Library\bin`，并按 `--dll-dir`加入已核实的GPU DLL目录。Python写盘尝试被拦截时直接报错，不通过先写再删补救；本机原生库的本轮验证结果单独报告。

## 第3步：持续接收并核对全部转写

1. 在工具截断前持续消费子进程输出；不要等整场结束后让一个低额度工具调用一次性返回全文。逐行JSON及宿主伪代码见[协议](references/工具调用协议.md)。
2. 按顺序接收 `audio_ready`、全部 `segments` 批次、最终 `complete`；保存到宿主内存，分批向当前AI返回可读文字，不能把base64或大量原始JSON元数据当正文。
3. 可以边转写边整理内存提纲，但必须读完最后一批和问答尾声。按宿主cursor避免重复消费同一输出，不能按文本去重删掉真实重复发言。
4. 成功条件同时满足：进程exit0；收到 `complete`；实际收到的段数等于 `complete.count`；`scope="full"` 且 `limit_seconds=null`；音频处理时长与原视频时长无未解释的明显缺口。原视频时长未知时明示，不编造覆盖范围。
5. 非零退出、无完成事件、计数不一致或底层已丢失输出时，说明处理缺口并修正调用方式。没有宿主原始内存缓冲就不能假设可恢复，不用落盘转写或盲目重跑整场掩盖失败，不将未读全的结果称为完整纪要。

## 第4步：按转写定位少量视频画面

先从转写确定需要核实的姓名、课题切换、图表、专业术语及数字，再定点取帧。优先合并少量相关时间，避免全视频抽帧。

```powershell
& 'D:\software\Anaconda\envs\labmeeting-ai\python.exe' -I -B -u -X utf8 'E:\BRC\Meet\LabMeeting-AI\labmeeting.py' frame-inline --video '会议视频的实际完整路径.mp4' --times 00:05:00 00:32:10 4200 --width 1920
```

`--times`是原视频秒数或时分秒；4200即70分钟。解析每个 `frame` 事件，核对请求与实际时间，把 `data_url` 转成宿主真正的图像内容交给当前模型。**不打印base64正文，不保存截图，不把“拿到图片字符串”等同于“看过画面”。** 内存渲染和限额处理见[协议](references/工具调用协议.md)。

画面不清时，仅查看必要的相邻时刻或调整宽度；不可辨认或宿主没有图像能力时保留待核，不编造确认结果。录屏同时含个人聊天或浏览器时，只采用实际会议区域；会后无关录屏不写入会议内容。

## 第5步：当前AI撰写唯一最终MD

按实际内容组织：会议整体要点、汇报时间索引、每位汇报者详细内容、讨论与导师意见、待办和待核事项。每人说明研究问题、方法、已报告结果、局限与下一步；事务汇报不补写不存在的科研课题。

- 只标原视频时间，例如 `[00:32:10]` 或时间范围，不嵌图、不附转写全文。
- 姓名依据口头介绍或画面；不凭声线认定导师/学生。不能确认时明确“姓名待核”。
- 区分实测结果、机制假设、个人意见、建议和明确决定；相关性不写成因果，投稿目标不写成录用。
- 基因、蛋白、药物、细胞类型、样本量、效应方向和统计量需有转写或画面证据；听不清或冲突时待核，不靠背景知识补齐。
- 纪要用中文撰写，保留有依据的英文专业术语、缩写和名称原文；不因自动语言检测而翻译或补写未确认的术语。
- 不引入会议未提到的外部研究充当会议内容。确有未处理范围时简要说明。

## 第6步：核验与交付

1. 在写出前确认最终路径、目标存在状态与授权；完整正文在内存准备好后直接写该MD，不先保存草稿、图像清单、校对表或性能JSON，不用原子写入的临时副本。目标不存在时使用独占创建，文件工具不得暗自生成备份或自动保存副本。
2. 回读最终MD，检查覆盖全部汇报及会议尾声、名字与重要时间/数字准确、假设与结果区分、无图片语法与无关会后内容。
3. 运行前确认启动与宿主调用不生成会议中间文件，运行后检查本工具是否留下其他文件；末尾无残留不能证明从未写入。不为检查创建测试产物，不以删除中间文件作为合规补救，不删除来源不明的既有数据。
4. 在回复中给最终MD路径、覆盖范围、关键待核项和实测耗时。完整耗时包括本地处理、当前AI阅读、画面复核及MD核验；安装下载另报，不能拿短测或ASR阶段替代端到端达标证明。

目标为每小时视频最多五分钟，不能保证所有材料及宿主软件都达标。技术依据和已实现边界见[方案依据](references/方案依据.md)；当前无词级对齐或自动说话人身份识别，不把段落归人冒充diarization。

Skill可留在项目内，也可经用户授权安装到宿主skills目录；安装、更新和发现状态以实际核验为准，不能把克隆仓库当作已注册。未来发布代码须有对应授权；会议视频、纪要、真实转写、截图、模型、密钥或私人对话不得随工具代码发布。
