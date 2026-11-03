# LabMeeting-AI

## 1. 主要功能

在 Windows + Conda 中，将本地科研组会视频整理为一份中文 Markdown 纪要。音频解码和 GPU 语音识别在本地完成；正在运行的 Codex 或 DeepSeek Harness 完整阅读转写，按需查看关键画面，再写出纪要。

日常流程只有四步：

**视频 → 内存转写 → AI 阅读并按需回看视频 → 最终 MD**

只保存最终会议 MD，图表用原视频时间定位。音频、转写、图片和计时信息不写成中间文件。环境、模型和代码是复用的工具资产。

## 2. 文件树与说明

```text
LabMeeting-AI/
├── README.md                         使用入口、文件索引和运行顺序
├── labmeeting.py                     内存转写、定点取帧及只读诊断 CLI
├── download_model.py                 首次准备本地模型，校验固定版本与 SHA256
├── environment.yml                   已验证的 Conda/Python 依赖版本
├── .gitignore                        排除模型、临时资料及会议数据
├── .agents/
│   └── skills/
│       └── lab-meeting-summary/
│           ├── SKILL.md              Codex/DeepSeek Harness 的会议总结指令
│           ├── agents/
│           │   └── openai.yaml       Skill 名称、描述和调用提示
│           └── references/
│               └── 方案依据.md       选型、GPU 依赖、模型来源和性能边界
├── tests/
│   └── test_pipeline.py              不创建文件的内存/只读测试
├── models/                           本地 ASR 模型及来源信息，不进入 Git
│   └── large-v3-turbo/
└── tmp/                              用户预建的安装临时区，日常会议处理不用
```

`models/` 和 `tmp/` 不随仓库发布。不要自动创建缺失的 `tmp`；需要首次下载时，先确认适用的临时区和用户授权。

## 3. 使用与阅读顺序

### 直接让 AI 总结

在 Codex 或 DeepSeek Harness 中给出视频路径和最终 MD 路径，并指定本项目的 Skill，例如：

```text
请读取 E:\BRC\Meet\LabMeeting-AI\.agents\skills\lab-meeting-summary\SKILL.md，
总结“视频完整路径.mp4”，只生成“最终纪要完整路径.md”。
包括会议主要内容、每位汇报者的详细课题、导师意见、待办与视频时间索引。
```

在已发现该项目 Skill 的会话中，也可使用 `$lab-meeting-summary`。Skill 保存在项目内，不自动安装到全局目录。

阅读路径：本 README → `SKILL.md`。仅首次安装、换机、依赖变化或排错时，再读 `references/方案依据.md`。

### 前置条件

- Conda 环境 `labmeeting-ai` 及本地 `models/large-v3-turbo` 已准备好。
- GPU 推理需要 CUDA 12 的 cuBLAS 和 cuDNN 9。当前机器复用 `D:\software\Anaconda\envs\DL\Lib\site-packages\torch\lib`；其他电脑必须核实自己的兼容 DLL 路径。`environment.yml` 不包含这些 GPU DLL。
- 安装环境、依赖或下载模型前遵守用户授权；复用既有环境时不重复安装。首次环境创建命令为：

```powershell
& 'D:\software\Anaconda\Scripts\conda.exe' env create -f .\environment.yml
```

首次模型下载命令、固定 revision 和官方 SHA256 见[方案依据](.agents/skills/lab-meeting-summary/references/方案依据.md#首次模型下载与完整性)。正常处理会议不会联网下载模型。

## 4. 代码运行顺序

以下在仓库根目录执行。路径含空格时保留引号；示例中的视频路径需替换为真实文件。

### 日常处理

**第一步：本地内存转写。** 入口为 `stream`，默认采用 `int8_float16`、batch 2、beam 1、中文转写。

```powershell
& 'D:\software\Anaconda\Scripts\conda.exe' run --no-capture-output -n labmeeting-ai python -B .\labmeeting.py stream --video '视频完整路径.mp4' --model '.\models\large-v3-turbo' --dll-dir 'D:\software\Anaconda\envs\DL\Lib\site-packages\torch\lib'
```

输入为原视频和已有模型；输出为 stdout 中分批的 `segments` 事件，以及末尾带段数、音频时长、原视频时长、片段限制、参数和阶段耗时的 `complete` 事件。编排层须在工具截断之前完整接收各批次，在内存分批返回文字，并确认进程成功退出；已经丢失的输出不能视作已读。不要将 stdout 重定向或保存为文件。此命令只产生转写，最终纪要由当前 AI 完成。

**第二步：AI 阅读并按需核对画面。** 从转写中选择课题切换、名字、关键数字或专业术语等时间点，一次可查看多帧：

```powershell
& 'D:\software\Anaconda\Scripts\conda.exe' run --no-capture-output -n labmeeting-ai python -B .\labmeeting.py frame-inline --video '视频完整路径.mp4' --times 00:05:00 00:32:10 --width 1920
```

输出为内存 JPEG 的 data URL。AI 工具编排层解析 JSON 后直接显示图片，不打印 base64 正文、不保存截图。画面只能补充核验，不能替代完整转写阅读。

**第三步：当前 AI 写最终 MD。** 包含整体要点、逐人详细内容、导师意见、待办及原视频时间，未能确认的术语和数字保留待核。会议结束后的无关录屏不混入纪要，MD 不嵌图。

### 首次或故障诊断

`check` 检查包和 CUDA 可见性，`metadata` 查看媒体轨道；环境、模型和输入正常时，无需每次单独运行。

```powershell
& 'D:\software\Anaconda\Scripts\conda.exe' env list
& 'D:\software\Anaconda\Scripts\conda.exe' run -n labmeeting-ai python -B -c "import sys; print(sys.executable); print(sys.version)"
& 'D:\software\Anaconda\Scripts\conda.exe' run -n labmeeting-ai python -B .\labmeeting.py check --dll-dir 'D:\software\Anaconda\envs\DL\Lib\site-packages\torch\lib'
& 'D:\software\Anaconda\Scripts\conda.exe' run -n labmeeting-ai python -B .\labmeeting.py metadata --video '视频完整路径.mp4'
```

检测到 CUDA 不等于 GPU 实际推理成功；`--limit-seconds 120` 可用于明确标注的短测，不能据此生成整场纪要。

需要验证代码时：

```powershell
& 'D:\software\Anaconda\Scripts\conda.exe' run -n labmeeting-ai python -B -m unittest discover -s tests -v
```

性能目标为每小时视频最多五分钟，计算范围包括 AI 阅读、画面核对和最终 MD 写出；首次安装、下载单独计算。具体实测及适用边界见方案依据，不作所有材料均可达标的保证。
