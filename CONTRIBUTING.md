# Contributing

使用 Windows x64 和 Python 3.11+。开发环境只需安装 `requirements.txt` 中的依赖；测试无需真实中转站或账户。

提交更改前运行 README 中的测试和发布内容检查。对协议或 SDK 兼容行为的更改应增加对应的本地模拟测试。

示例地址使用 `https://relay.example.com`，测试密钥使用明显的虚构值。问题报告、日志和截图中应移除真实 Key、中转地址、项目内容及个人目录。

真实配置保存在仓库外。不要将 `.state`、`.env`、`runtime.json`、会话数据或本地虚拟环境纳入提交。
