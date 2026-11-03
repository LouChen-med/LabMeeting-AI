# LabMeeting-AI

## 1. 主要功能

将本地科研组会视频整理为一份中文 Markdown：会议主要内容、每位汇报者的详细课题、导师意见、待办和原视频时间索引。

**Windows 本地内存转写 → 当前 AI 完整阅读 → 按需在内存查看关键帧 → 唯一最终 MD。**

音频解码和语音识别在本机运行，语义总结使用正在工作的 Codex 或 DeepSeek Harness。该 Skill 是调用说明和本地工具的组合；Python CLI 本身不调用总结 API，也不会独立生成会议纪要。

会议处理只写最终 MD，不保存 WAV、转写、截图、日志或计时文件，MD 不嵌图。首次安装的环境、可复用模型和工具代码会保留；模型下载器会使用安装缓存，这与日常会议处理分开。

## 2. 文件树与说明

```text
LabMeeting-AI/
├── README.md                         依赖、环境、下载资料、调用和运行顺序
├── environment.yml                   Conda 环境及主要 Python 依赖版本
├── labmeeting.py                     内存转写、定点取帧、环境和媒体诊断 CLI
├── download_model.py                 首次下载固定版本 ASR 模型并校验 SHA256
├── .gitignore                        排除模型、安装缓存和会议数据
├── .agents/
│   └── skills/
│       └── lab-meeting-summary/
│           ├── SKILL.md              当前 AI 执行会议总结时的指令
│           ├── agents/
│           │   └── openai.yaml       Skill 展示名称和调用提示
│           └── references/
│               ├── 首次配置.md       AI逐步检查、安装依赖、下载模型及短测
│               ├── 工具调用协议.md   不同软件的子进程、stdout及内存图像适配
│               └── 方案依据.md       技术选型、兼容性依据与性能边界
├── tests/
│   └── test_pipeline.py              不产生文件的内存/只读测试
├── models/                           本地模型资产，不随 Git 发布
│   └── large-v3-turbo/               模型文件及 provenance.json 来源记录
└── tmp/                              用户预建的首次安装临时区，日常处理不用
```

Git 仓库不含模型权重、GPU DLL、会议视频或真实会议内容。克隆代码后还需要准备下面列出的运行环境和模型；不能只下载 `SKILL.md` 就开始转写。

## 3. 使用与阅读顺序

### 3.1 环境与工具要求

| 组件 | 要求、用途及准备方式 |
|---|---|
| 操作系统 | Windows x64；本机验证平台为 Windows 11 x64。其他平台未进行本项目端到端验证，不依赖 WSL 或 Docker。 |
| Conda | 管理 Python 和依赖。本机路径为 `D:\software\Anaconda\Scripts\conda.exe`；其他机器替换为自己的 Conda 路径。 |
| Python 环境 | 环境名 `labmeeting-ai`，固定 Python 3.11.18；由 `environment.yml` 创建。 |
| NVIDIA GPU 与驱动 | `stream` 当前固定使用 CUDA，没有 CPU 转写开关。本机为 RTX 4070 Laptop、8 GB 显存、驱动 566.14；这是验证配置，不是所有硬件的最低要求。 |
| GPU 运行库 | CUDA 12 runtime、cuBLAS/cuBLASLt、cuDNN 9 及其组件；**不包含在本项目的 `environment.yml` 中**，需复用已有兼容 DLL 或另行准备。 |
| Windows C++ runtime | CTranslate2 Windows wheel 需要兼容的 Visual C++ runtime；Conda 会带入相关运行库。已有可用运行库时不用再安装；缺失时参考 [Microsoft 官方下载说明](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)。 |
| 当前 AI/Agent | 已配置可用的 Codex 或 DeepSeek Harness，能读写指定本地路径、执行命令、完整消费 stdout、解析并查看内存 JPEG/data URL。只有文本聊天能力时，无法完成全部画面核验。 |
| 网络与认证 | 首次安装包和下载模型需要联网；本地转写与取帧读取已有模型。总结使用宿主 AI 已有的认证和额度，本项目没有额外的 API Key/SDK 配置。 |
| 内存与磁盘 | 内存使用随录像时长增长；仅16 kHz单声道float32音频数组约230 MB/小时，拼接、VAD、模型和特征还会占用内存。本机32 GB内存已验证。权重约1.62 GB；首次分段下载、合并和复制会保留多份安装缓存，建议为模型与缓存预留约6 GB，Conda环境另计。 |

#### Python 主要依赖

这些包由环境文件统一安装，不需要逐个重复执行安装命令。Conda/PyPI还会自动解析它们的传递依赖；该文件固定主要版本，不是完整传递依赖锁文件。

| 依赖 | 固定版本 | 用途/来源 |
|---|---|---|
| Python | 3.11.18 | 解释器，conda-forge |
| setuptools | 81.0.0 | 保留 CTranslate2 4.6.0 使用的 `pkg_resources`，conda-forge |
| NumPy | 2.4.6 | 内存音频数组，conda-forge |
| Pillow | 13.0.0 | 内存 JPEG 编码，conda-forge |
| requests | 2.34.2 | 首次下载，conda-forge |
| PyAV | 18.1.0 | 视频解封装、音频解码和定点取帧，conda-forge |
| faster-whisper | 1.2.1 | Whisper 转写与随包提供的 Silero VAD，PyPI |
| CTranslate2 | 4.6.0 | CUDA/INT8 推理，PyPI |
| huggingface-hub | 0.36.2 | 首次模型下载，PyPI |
| ONNX Runtime | 1.31.1 | 本地 VAD 推理，PyPI |
| tokenizers | 0.23.3 | 模型分词，PyPI |

`pip` 由 Conda 安装，未单独锁定版本。主流程不需要额外安装 PyTorch、WhisperX、pyannote、Ollama、本地总结 LLM、OpenAI/DeepSeek SDK 或独立 FFmpeg 可执行程序。PyAV 提供解码库，见 [faster-whisper 官方依赖说明](https://github.com/SYSTRAN/faster-whisper#requirements)。

#### GPU DLL：本机复用与新电脑准备是两种情况

本机复用以下已有目录，不往该环境安装包，也不修改系统 PATH：

```text
D:\software\Anaconda\envs\DL\Lib\site-packages\torch\lib
```

该目录来自已有 PyTorch 2.5.1+cu124，包含 CUDA 12.4 和 cuDNN 9.1.0.70。**`DL` 环境名及 PyTorch 本身不是本项目依赖**；这里仅借用其 DLL。换机时不能照抄一个不存在的路径。

需要确认的主要文件包括 `cudart64_12.dll`、`cublas64_12.dll`、`cublasLt64_12.dll`、`cudnn64_9.dll`，以及配套的 `cudnn_*64_9.dll` 等依赖。不要只拷贝一个 cuDNN DLL。CTranslate2 4.5 起已切换到 cuDNN 9，见[官方发布说明](https://github.com/OpenNMT/CTranslate2/releases/tag/v4.5.0)。

新电脑优先复用已有兼容运行库。缺失时可经批准在 Conda 环境内安装，或从 [NVIDIA cuBLAS](https://developer.nvidia.com/cublas) 和 [cuDNN Windows 安装说明](https://docs.nvidia.com/deeplearning/cudnn/backend/v9.1.1/installation/windows.html)获取兼容组件；具体顺序和候选命令见第4节。NVIDIA驱动须兼容所选CUDA运行库，`nvidia-smi`显示的CUDA版本不等于已装同版本Toolkit。

### 3.2 额外需要下载哪些模型或数据

**需要单独下载公开 ASR 权重，不需要训练数据集。** 输入资料仅为用户自己的会议视频；无需另找科研数据、语音标注集、说话人声纹、字幕或校准集。

| 项目 | 固定内容 |
|---|---|
| 模型 | multilingual Whisper large-v3-turbo 的 CTranslate2 转换版 |
| 仓库 | [dropbox-dash/faster-whisper-large-v3-turbo](https://huggingface.co/dropbox-dash/faster-whisper-large-v3-turbo) |
| revision | `0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf` |
| 权重文件 | `model.bin`，1,617,884,929字节，约1.62 GB |
| 其他配套文件 | `config.json`、`preprocessor_config.json`、`tokenizer.json`、`vocabulary.json` |
| 本地位置 | `models/large-v3-turbo/`；来源和各文件哈希记录在本地 `provenance.json` |
| Token与许可 | 当前公开模型下载不要求 Hugging Face Token；模型页标注 MIT，分发时仍需遵守许可 |

`model.bin` 的官方 SHA256 为：

```text
e76620f83d5f5b69efd3d87e3dc180c1bd21df9fbebacfd4335e5e1efcc018da
```

可在 [HF 官方固定版本文件页](https://huggingface.co/dropbox-dash/faster-whisper-large-v3-turbo/blob/0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf/model.bin)核对。不要用同名的原始 PyTorch 权重代替 CTranslate2 文件。运行入口会检查核心模型文件是否齐全，并设置 `local_files_only=True`，缺文件会失败，不自动联网补齐。

Silero VAD 的 `silero_vad_v6.onnx` 随 faster-whisper 包安装，不用再手动下载一个 VAD 模型。当前未启用词级对齐或说话人聚类，因此也不用下载对应模型。

### 3.3 三种调用方式

#### A. 推荐：直接给当前 AI 完整路径

在有本地工具权限的 Codex 或 DeepSeek Harness 会话中发送下面内容，把视频和输出路径替换为真实路径：

```text
请读取并按以下 Skill 执行：
E:\BRC\Meet\LabMeeting-AI\.agents\skills\lab-meeting-summary\SKILL.md

视频：E:\BRC\Meet\某次会议\会议.mp4
输出：E:\BRC\Meet\某次会议\会议纪要.md

复用已有 labmeeting-ai 环境和本地模型。
完整阅读转写，按需核对少量视频画面。
纪要包含整体要点、逐人详细课题、导师意见、待办和视频时间索引。
只保存最终 MD，不生成音频、转写、图片或日志中间文件。
```

这条消息可从任意当前目录发起；AI须有目标路径权限，执行相对命令时切换到仓库根目录，或使用完整路径。它没有要求再次安装、下载或额外调用另一个总结 API。已有目标文件时，按用户覆盖授权处理。

#### B. 快捷名：会话已经发现该 Skill 时使用

```text
$lab-meeting-summary
视频：E:\BRC\Meet\某次会议\会议.mp4
输出：E:\BRC\Meet\某次会议\会议纪要.md
只保留最终 MD，并详细总结每位汇报者。
```

Skill 名称是 `lab-meeting-summary`，项目/仓库名是 `LabMeeting-AI`。本仓库没有自动全局安装 Skill；如果当前会话不识别 `$lab-meeting-summary`，使用方式A显式指定文件，不要假设仅克隆仓库就能在所有会话按名称调用。

#### C. 命令行：调试本地步骤

`stream` 输出转写，`frame-inline` 输出内存图像，命令见第4节。命令行没有 `--output-md`，不会自行调用LLM生成纪要；仍需当前AI读取全部输出并完成最后写作。普通终端打印的base64也不等同于AI已经看过图片。

阅读路径：本 README → [SKILL.md](.agents/skills/lab-meeting-summary/SKILL.md)。调用AI可直接从Skill开始，按其步骤在需要时读取技能内部的[首次配置](.agents/skills/lab-meeting-summary/references/首次配置.md)和[工具调用协议](.agents/skills/lab-meeting-summary/references/工具调用协议.md)，不要求先翻README；选型和测试边界见[方案依据](.agents/skills/lab-meeting-summary/references/方案依据.md)。

## 4. 代码运行顺序

### 4.1 首次准备：环境 → GPU运行库 → 模型 → 短测

以下均为 PowerShell 命令，在 `E:\BRC\Meet\LabMeeting-AI` 执行；其他安装位置须替换路径。安装、下载、修改环境和清理安装缓存前遵守用户授权。已有环境与模型时直接跳到4.2，不重新执行首次安装。

**第一步：检查现有环境，缺失时才创建。**

```powershell
Set-Location -LiteralPath 'E:\BRC\Meet\LabMeeting-AI'
& 'D:\software\Anaconda\Scripts\conda.exe' env list
# 仅环境不存在且已获批准时执行下一行。
& 'D:\software\Anaconda\Scripts\conda.exe' env create -f .\environment.yml
& 'D:\software\Anaconda\Scripts\conda.exe' run -n labmeeting-ai python -B -c "import sys; print(sys.executable); print(sys.version)"
& 'D:\software\Anaconda\Scripts\conda.exe' run -n labmeeting-ai python -B -m pip check
```

包来源为 conda-forge，以及环境文件 `pip:` 部分的 PyPI 发行包。创建环境不会下载 ASR 权重，也不会自动准备完整GPU DLL。

**第二步：确认GPU运行库来源。** 本机直接用3.1所列的已有 `DL` DLL目录。新电脑若没有可用运行库，下面是一个经软件包元数据核对的 Conda 候选方案：

```powershell
& 'D:\software\Anaconda\Scripts\conda.exe' install -n labmeeting-ai --override-channels -c conda-forge 'cuda-version=12.4' 'cuda-cudart=12.4.127' 'libcublas=12.4.5.8' 'cudnn=9.3.0.75' --dry-run
```

该方案的 win-64 包和CUDA12依赖可在 [cuda-cudart](https://api.anaconda.org/package/conda-forge/cuda-cudart)、[libcublas](https://api.anaconda.org/package/conda-forge/libcublas)、[cudnn](https://api.anaconda.org/package/conda-forge/cudnn)元数据核对；它**未在本机安装或完成GPU推理验证**。先审阅求解计划，获批准后去掉 `--dry-run` 才会实际安装，不要在已有可用GPU库的机器上重复安装。安装后通常从该环境的 `Library\bin` 提供DLL，仍需核实实际文件并通过短测。

若cuBLAS与cuDNN在不同目录，可重复传入 `--dll-dir`。程序只调整当前进程的DLL查找路径；不需要为了运行本项目改系统PATH，也不要求安装编译器或源码构建工具。

**第三步：首次下载模型。** 下载器要求项目已有用户预建的 `tmp`。没有时先由用户准备，不自动创建；模型目录必须为空或不存在，脚本拒绝覆盖已有非空目录。

官方来源命令：

```powershell
& 'D:\software\Anaconda\Scripts\conda.exe' run --no-capture-output -n labmeeting-ai python -B .\download_model.py --revision '0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf' --expected-model-sha256 'e76620f83d5f5b69efd3d87e3dc180c1bd21df9fbebacfd4335e5e1efcc018da'
```

主站连接受限时，可显式使用本机验证过的传输路径：小配置文件经第三方 `hf-mirror.com`，同一权重经ModelScope下载，再按官方SHA256核验。

```powershell
& 'D:\software\Anaconda\Scripts\conda.exe' run --no-capture-output -n labmeeting-ai python -B .\download_model.py --revision '0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf' --endpoint 'https://hf-mirror.com' --direct --weight-url 'https://modelscope.cn/models/pengzhendong/faster-whisper-large-v3-turbo/resolve/c312f538745ce1237d0b0c8eef0b81d91ea1fce6/model.bin' --expected-model-sha256 'e76620f83d5f5b69efd3d87e3dc180c1bd21df9fbebacfd4335e5e1efcc018da'
```

二选一，不重复下载。`--direct`仅让下载进程忽略环境代理，不关闭TLS验证；镜像不是官方来源的替代证明，完整哈希通过才可使用。缓存位于 `tmp/model-download/`，最终模型位于 `models/large-v3-turbo/`，来源记录为 `provenance.json`。下载及模型核验完成后，可在用户允许范围内清理本次安装缓存，保留模型和 `tmp` 目录本身。

**第四步：检查并短测。** 以下DLL路径适用于本机；若GPU库装在其他目录，替换为已核实的实际路径。

```powershell
nvidia-smi
& 'D:\software\Anaconda\Scripts\conda.exe' run -n labmeeting-ai python -B .\labmeeting.py check --dll-dir 'D:\software\Anaconda\envs\DL\Lib\site-packages\torch\lib'
& 'D:\software\Anaconda\Scripts\conda.exe' run --no-capture-output -n labmeeting-ai python -B .\labmeeting.py stream --video '视频完整路径.mp4' --model '.\models\large-v3-turbo' --dll-dir 'D:\software\Anaconda\envs\DL\Lib\site-packages\torch\lib' --limit-seconds 120
```

包导入、CUDA可见不等于推理成功，需看到短测成功退出和 `complete` 事件。若视频开头没有发言，可增大 `--limit-seconds` 以覆盖实际发言，不另存测试片段；无语音错误不能直接当作GPU故障。短测只验证所覆盖片段，不能生成整场纪要。

### 4.2 日常处理：只转写、按需看帧、写最终MD

**内存转写：**

```powershell
& 'D:\software\Anaconda\Scripts\conda.exe' run --no-capture-output -n labmeeting-ai python -B .\labmeeting.py stream --video '视频完整路径.mp4' --model '.\models\large-v3-turbo' --dll-dir 'D:\software\Anaconda\envs\DL\Lib\site-packages\torch\lib'
```

默认参数为中文 `zh`、`int8_float16`、batch 2、beam 1；需要其他语言可设置 `--language`。输入为原视频和已有模型；stdout依次输出 `audio_ready`、分批 `segments` 和末尾 `complete` 事件。

编排层须在工具截断前完整消费stdout，在内存保存并分批返回可读文字。检查 `complete.count` 与实际收到的段数、`scope=full`、`limit_seconds=null`，以及音频和原视频时长；已丢失内容不能视为已读，明显时长缺口需说明。禁止重定向、Tee或保存中间转写。

**AI完整阅读后，按需回看少量关键帧：**

```powershell
& 'D:\software\Anaconda\Scripts\conda.exe' run --no-capture-output -n labmeeting-ai python -B .\labmeeting.py frame-inline --video '视频完整路径.mp4' --times 00:05:00 00:32:10 4200 --width 1920
```

`--times`接受秒数或 `HH:MM:SS`，以原视频为基准；4200表示70分钟。输出为含 `requested_seconds`、`actual_seconds` 和 `data_url` 的JSON。工具编排层解析后直接渲染图片，不把base64正文交给模型、不保存图片；仅有时间戳而未查看画面时，不能声称已完成画面核验。

**当前AI写最终MD：** 按Skill要求完成逐人纪要，仅标原视频时间，不嵌图；明确区分实测结果、假设和计划，未核清的内容列为待核。确认覆盖会议尾声，并排除会后无关录屏。

### 4.3 排错和验证

| 情况 | 核查方向 |
|---|---|
| 会话不识别 `$lab-meeting-summary` | 用方式A提供完整 `SKILL.md` 路径，确认本地工具权限 |
| 环境或包缺失 | `conda env list`、核对解释器、`python -m pip check`；不盲目重装或升级 |
| 缺 `cublas64_12.dll` / `cudnn*_9.dll` | 核对CUDA12/cuDNN9组件及 `--dll-dir`；仅有驱动不够 |
| OpenMP重复运行库错误 | 主入口已在依赖导入前设置进程内 `MKL_THREADING_LAYER=SEQUENTIAL`；不要用忽略重复错误开关掩盖问题 |
| 显存不足 | 先检查其他GPU占用；可将 `--batch-size`降至1，不保证仍达速度目标；程序不自动转CPU |
| 模型文件缺失/目录非空 | 核对五个模型文件及来源；下载器不会覆盖既有非空模型目录 |
| 媒体轨道或时长异常 | 运行下方 `metadata`；不将其列为每次会议必跑步骤 |
| 图像或转写被工具截断 | 调整工具缓冲与消费方式，不能假定丢失部分可恢复或已核验 |

```powershell
& 'D:\software\Anaconda\Scripts\conda.exe' run -n labmeeting-ai python -B .\labmeeting.py metadata --video '视频完整路径.mp4'
& 'D:\software\Anaconda\Scripts\conda.exe' run -n labmeeting-ai python -B -m unittest discover -s tests -v
```

单位测试不创建测试文件。性能目标为每小时视频最多五分钟，包括AI阅读、关键帧核验和最终MD写出；首次安装和下载另计。不同语速、有效内容比例、噪声、内存/显存占用和宿主AI速度会影响耗时，不能用短测或ASR单步替代端到端测量。
