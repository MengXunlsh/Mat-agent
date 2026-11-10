# DeepSeek Harness 接入

[English](README.md) · 简体中文

[程序首页](../../README.zh-CN.md) · [功能与使用说明](../../docs/usage-guide.zh-CN.md)

## 版本与职责

运行依赖由 [web-runtime/package-lock.json](web-runtime/package-lock.json) 锁定为 `@deepseek-ai/dsh@0.2.1-rc.2`。上游仓库、标签、源码提交和适配入口见 [upstream.lock.json](upstream.lock.json)。当前程序不需要完整上游源码副本。

`foundation/` 保存 mat-agent 插件、界面、科研身份、内部角色和 16 项内置技能。Harness 提供对话、计划、工具调用、压缩、子 Agent、项目文件、Shell、持久终端、后台任务及原生界面组件。

## 安装与启动

从程序根安装 Node 依赖：

```powershell
npm --prefix integrations/deepseek-harness/web-runtime ci
./scripts/start_workbench.ps1 -OpenBrowser
```

启动时，`scripts/prepare_harness_web.py`、`scripts/harness_ui_extensions.py` 和 `scripts/harness_lifecycle_extensions.py` 从受控源码生成适配。修改功能应修改这些源码及 `foundation/`，再重新生成，不手改已安装的 Node 包。

## 科研扩展

- 主 Agent 使用通用研究身份；文献、分析、核查与成果整理按需使用原生子 Agent。
- 内置技能由本目录的 `skills/` 加载；用户全局和用户项目技能目录不自动扫描。
- 项目与案例共用文件、成果、权限、版本与任务机制。数据库和科学计算通过内部工具接入。
- 模型和检索连接由用户分别配置，当前会话可单独选择模型，子 Agent 默认继承。
- 项目记忆通过 Harness MCP 客户端连接本地记忆服务，按项目启用与保存。
- 文件、文献、代码及整组成果引用读取相应保存版本，预览不重新执行科学计算。

曲线预览使用锁定的 Apache ECharts，结构预览使用 3Dmol.js；本机 RDKit、Gemmi、ASE 提供结构解析。前端组件从本机运行包加载。

## 运行配置和许可

运行配置、模型凭据及会话位于程序 `runtime/foundation/home/`，用户科研文件位于各自项目目录。启动器使用本机访问授权；接收方新安装后自行配置接口。

上游许可保留在 [LICENSE.upstream](LICENSE.upstream)。mat-agent 自有代码采用 [MIT 许可证](../../LICENSE)。Python 依赖由程序根的 `pyproject.toml` 和 `uv.lock` 管理。
