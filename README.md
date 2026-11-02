# Codex Gemini Antigravity

让 Codex 通过 MCP 将任务交给 Gemini，并使用 Antigravity SDK 执行文件读取、代码修改和命令调用。中转地址与模型由使用者自行配置。

**Windows x64 · Python 3.11+ · MCP stdio · 自选 Gemini 兼容端点**

```text
Codex → MCP Bridge → Antigravity SDK → Gemini 兼容服务
```

这是一个独立的外部代理工具，通过 MCP 返回任务结果。它使用 Antigravity 的代理运行框架；具体能力由本项目启用的工具决定。Windows SDK 安装包自带运行组件，无需额外安装 `agy` 或 Gemini CLI。

## 功能

- 本地配置窗口：填写中转地址和 Key，实时拉取、搜索并选择模型。
- Key 由 Windows DPAPI 加密，默认存储在仓库外。
- `review` 模式只读，适合代码审查、定位问题和理解项目。
- `edit` 模式支持修改文件和执行命令。
- 后台任务支持结果查询、分页、取消和超时控制。
- 默认最多两个并发任务，每个任务最多 40 次模型调用和 100 次工具调用。

## 安装

准备 Windows x64、带 Tkinter 的 Python 3.11+，以及可在终端运行的 Codex CLI。

在项目目录打开 PowerShell：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

安装脚本在项目内创建 `.venv`，安装固定版本依赖，并注册名为 `gemini-antigravity` 的 MCP 服务。Python 路径按安装位置自动生成，仓库中不保存本机路径。

只准备运行环境、不注册 MCP：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -SkipMcpRegistration
```

## 配置与使用

1. 双击 `configure.cmd`，填写自己的 **Base URL** 和 **API Key**。
2. 点击“拉取模型”。默认搜索 `gemini`，清空搜索可查看所有可用模型。
3. 选择模型并保存。可点击“测试所选模型”发送一条简短请求，验证原生接口并消耗少量服务额度。
4. 重启 Codex，加载新注册的 MCP。

在 Codex 中下达任务：

> 用 gemini-antigravity 审查这个项目的登录模块。先读取配置，再以 review 模式提交任务，最后核实返回的问题。

> 把这个重构任务交给 gemini-antigravity，允许它修改本项目代码并执行测试。完成后检查差异和测试结果。

每个任务都读取最新保存的配置，切换模型后不必重启 MCP。

## MCP 工具

| 工具 | 用途 |
| --- | --- |
| `get_configuration` | 查看所选模型、凭据是否已配置及准备状态 |
| `list_models` | 拉取模型列表，`query=""` 返回全部模型 |
| `select_model` | 按用户要求保存新的默认模型 |
| `test_connection` | 测试所选模型的原生 Gemini 文本生成 |
| `submit_task` | 提交后台任务，立即返回任务 ID |
| `get_job` | 查询状态及结果，可等待最多 20 秒并分页读取 |
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

可用 `GEMINI_RELAY_STATE_DIR` 指定其他状态目录，也可用 `GEMINI_RELAY_API_KEY` 提供 Key；该环境变量优先于本地保存的 Key。环境变量设置由使用者自行管理，本项目不会读取 `.env` 文件。

仓库不预置中转地址、账户、Key、个人模型选择或会话记录。`.gitignore` 排除了常见本地配置、凭据和缓存文件。模型请求会将任务及代理读取的相关内容发送到使用者配置的服务。SDK 会话可能包含任务文本和文件内容，因此默认放在仓库外。

## 开发与验证

在已准备依赖的环境中执行：

```powershell
python -B -m unittest discover -s tests -p "test_*.py" -v
python -B tests/runtime_smoke.py
python -B scripts/audit_release.py
```

测试使用本地模拟接口，不需要真实 Key，也不会调用付费模型。覆盖凭据存储、模型列表回退、任务生命周期、MCP stdio 握手和实际 Windows SDK 运行组件。GitHub Actions 在 Windows 上运行同样的检查。

## 维护

移动项目目录后重新运行 `install.ps1`，更新 MCP 的启动位置。

移除 MCP 注册：

```powershell
codex mcp remove gemini-antigravity
```

该命令不删除本地状态目录。项目未附加开源许可证；许可证选择由发布者确定。
