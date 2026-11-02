# Security and local data

- API Key 通过 Windows DPAPI 按当前 Windows 用户加密保存；这不替代设备和账户本身的访问控制。
- Key 不写入 MCP 启动参数或 Codex 配置，常规错误消息会隐藏已知 Key。
- 状态目录默认在仓库外；SDK 会话可能包含任务和文件内容。
- 端点必须使用 HTTPS。模型发现和基础连接测试会阻止向其他来源重定向凭据。
- `review` 仅启用读取工具；`edit` 可以执行命令，并非系统沙箱。

报告问题时请使用虚构凭据和最小复现，移除日志、截图及路径中的个人信息。发布前可运行 `python -B scripts/audit_release.py` 检查常见凭据和本机路径；此检查是辅助工具，不能识别所有形式的敏感信息。
