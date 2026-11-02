# Codex Gemini Antigravity

让 Codex 通过 MCP 将任务交给 Gemini，使用 Antigravity SDK 执行文件读取、代码修改和命令调用。在 Codex 右侧统一完成连接配置、模型选择、任务提交和进度查看。

**Windows x64 · Python 3.11+ · MCP stdio · 自选 Gemini 兼容端点**

```text
Codex → MCP Bridge → Antigravity SDK → Gemini 兼容服务
```

这是一个独立的外部代理工具，通过 MCP 返回任务结果。右侧界面是本项目的本地网页面板；具体代理能力由本项目启用的工具决定。Windows SDK 安装包自带运行组件，无需额外安装 `agy` 或 Gemini CLI。

## 功能

- 统一网页面板：填写中转地址和 Key，拉取、搜索并选择模型，测试连接。
- 在面板中指定项目目录、选择只读或编辑模式，提交和取消任务。
- 自动刷新当前阶段、真实工具活动、模型与工具调用次数、耗时和最终结果。
- 任务摘要保存在本机，刷新页面或重新打开面板后仍可查看最近记录。
- Key 由 Windows DPAPI 加密，默认存储在仓库外。
- `review` 模式只读，适合代码审查、定位问题和理解项目。
- `edit` 模式支持修改文件和执行命令。
- 后台任务支持结果查询、分页、取消和超时控制。
- 默认最多两个并发任务，每个任务最多 40 次模型调用和 100 次工具调用。

## 安装

准备 Windows x64、Python 3.11+，以及可在终端运行的 Codex CLI。无需 Tkinter。

在项目目录打开 PowerShell：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

安装脚本在项目内创建 `.venv`，安装固定版本依赖，并注册名为 `gemini-antigravity` 的 MCP 服务。Python 路径按安装位置自动生成，仓库中不保存本机路径。

只准备运行环境、不注册 MCP：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -SkipMcpRegistration
```

## 在 Codex 右侧使用

安装后重新加载 Codex 的 MCP 服务，然后对 Codex 说：

> 打开 Gemini 的统一面板，放到右侧，默认项目目录使用当前项目。

Codex 调用 `get_panel(project_dir=项目绝对路径)` 后，用应用的 `open_in_codex` 打开返回的 `url`：`target.type="browser"`、`placement="right"`。需要 Codex 桌面应用提供浏览器面板工具；其他 MCP 客户端可在普通浏览器中打开同一地址。

1. 在“连接设置”填写自己的 **Base URL** 和 **API Key**。
2. 点击“拉取可用模型”，搜索并选择准确的模型 ID，然后保存。
3. 可点击“测试连接”发送一条简短请求，验证原生文本接口并消耗少量服务额度。
4. 在“新建任务”指定现有项目的绝对路径，填写任务，选择模式后提交。
5. 在“任务”中查看活动时间线、调用次数、耗时、结果，或终止运行中的任务。

默认使用只读 `review`；选择 `edit` 会允许代理修改文件并执行命令。面板显示已发生的活动，不推测完成百分比或预计剩余时间。单条文本测试通过后，仍应通过小型只读任务验证代理工具调用能力。

双击 `configure.cmd` 也会打开同一网页界面；已有面板运行时复用，否则启动本机服务并在默认浏览器中打开。原 `setup_gui.py` 保留为兼容启动入口。后台界面进程关闭后，面板地址失效，重新获取即可。

开发环境可直接启动：

```powershell
python -B server.py --panel --project-dir C:\Projects\my-app
```

加 `--no-browser` 只输出面板地址，便于由桌面应用打开。

## 通过对话委派

在 Codex 中下达任务：

> 用 gemini-antigravity 审查这个项目的登录模块。先读取配置，再以 review 模式提交任务，最后核实返回的问题。

> 把这个重构任务交给 gemini-antigravity，允许它修改本项目代码并执行测试。完成后检查差异和测试结果。

每个任务都读取最新保存的配置，切换模型后不必重启 MCP。

## MCP 工具

| 工具 | 用途 |
| --- | --- |
| `get_configuration` | 查看所选模型、凭据是否已配置及准备状态 |
| `get_panel` | 获取统一面板地址，可传 `project_dir` 预填任务目录 |
| `list_models` | 拉取模型列表，`query=""` 返回全部模型 |
| `select_model` | 按用户要求保存新的默认模型 |
| `test_connection` | 测试所选模型的原生 Gemini 文本生成 |
| `submit_task` | 提交后台任务，立即返回任务 ID 和 `dashboard_url` |
| `get_job` | 查询状态、活动摘要及结果，可等待最多 20 秒并分页读取 |
| `cancel_job` | 结束任务及本机运行进程树 |

`submit_task` 接收 `task`、项目绝对路径 `project_dir`、`mode`、可选 `model` 和 `timeout_seconds`。模式默认为 `review`；超时默认为 600 秒，可设为 10–1800 秒。

`edit` 启用文件修改和命令执行。项目目录和系统指令用于约束任务范围，不构成操作系统级沙箱。请根据已授权的任务选择模式。

## 协议要求

模型列表优先使用 `/v1/models`，必要时回退到 `/v1beta/models`。代理调用需要 Gemini 原生兼容的 `generateContent`、`streamGenerateContent` 及函数调用能力。

出现在模型列表中不代表一定支持完整代理流程。单条文本测试通过后，可先委派一个小型只读任务验证工具调用。如果服务仅支持 OpenAI Chat Completions，需要另外适配协议。

## 本地数据与隐私

默认状态目录为 `%LOCALAPPDATA%\CodexGeminiAntigravity`：

| 内容 | 文件或目录 |
| --- | --- |
| Windows 用户加密的 Key | `key.dpapi` |
| Base URL 与所选模型 | `settings.json` |
| SDK 会话和运行数据 | `jobs/` |
| 任务摘要与最终结果 | `jobs/<任务 ID>/job.json` |
| 本机面板地址 | `panel.json` |

可用 `GEMINI_RELAY_STATE_DIR` 指定其他状态目录，也可用 `GEMINI_RELAY_API_KEY` 提供 Key；该环境变量优先于本地保存的 Key。环境变量设置由使用者自行管理，本项目不会读取 `.env` 文件。

仓库不预置中转地址、账户、Key、个人模型选择或会话记录。`.gitignore` 排除了常见本地配置、凭据和缓存文件。模型请求会将任务及代理读取的相关内容发送到使用者配置的服务。SDK 会话与任务结果可能包含任务文本和文件内容，因此默认放在仓库外。

面板仅监听 `127.0.0.1`，每次服务启动生成随机访问令牌，接口检查 Host、请求来源和自定义请求头。不要分享面板地址或将本机服务转发到公网。页面不使用浏览器存储保存 Key；保存后清空输入框，读取配置只返回是否已配置。进度摘要只读取工具类型、状态、时间和计数，不展示模型思考或原始命令输出。

面板任务可以直接运行，无需 Codex 持续轮询；Codex 委派的任务也会显示在同一状态目录的面板中。MCP 服务退出时会取消其拥有的活动任务，历史状态不会被当作可恢复的运行会话。

## 开发与验证

在已准备依赖的环境中执行：

```powershell
python -B -m unittest discover -s tests -p "test_*.py" -v
python -B tests/runtime_smoke.py
python -B scripts/audit_release.py
```

测试使用本地模拟接口，不需要真实 Key，也不会调用付费模型。覆盖凭据存储、模型列表回退、面板配置与请求来源校验、进度摘要、任务生命周期与历史、MCP stdio 握手和实际 Windows SDK 运行组件。GitHub Actions 在 Windows 上运行同样的检查。

欢迎通过 Issue 或 Pull Request 贡献。提交前运行以上检查；修改协议或 SDK 兼容行为时，请补充相应的本地模拟测试。示例使用 `https://relay.example.com` 和明显虚构的 Key；日志、截图与提交中请移除真实凭据、个人目录和会话内容。

## 维护

移动项目目录后重新运行 `install.ps1`，更新 MCP 的启动位置。

移除 MCP 注册：

```powershell
codex mcp remove gemini-antigravity
```

该命令不删除本地状态目录。

## 许可证

本项目采用 [MIT License](LICENSE)，Copyright (c) 2026 sdpd2333。第三方依赖遵循各自的许可证。
