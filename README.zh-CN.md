# mat-agent

![mat-agent 晶体晶胞](integrations/deepseek-harness/foundation/material-mark.svg)

[English](README.md) · 简体中文

mat-agent 是基于 DeepSeek Harness 的本地材料科研 Agent，面向电脑端浏览器。可以在同一个项目内管理文献、实验数据、材料结构、代码和计算成果。

## 安装与启动

在 Windows 上安装 Python 3.12、Node.js 24、Git 和 uv，在程序根目录打开 PowerShell 并运行：

```powershell
uv sync --locked
npm --prefix integrations/deepseek-harness/web-runtime ci
./scripts/start_workbench.ps1 -OpenBrowser
```

使用 Chrome 或 Edge 打开工作台，默认本地端口为 8790。启动时加 `-Port 8791` 可以换端口。在启动终端按 Ctrl+C 停止服务。

1. 在 **设置 → 模型** 中添加自己的模型连接，并选择默认模型。
2. 从侧栏添加本地科研项目目录，然后新建会话或案例。
3. 在项目权限中选择 Agent 可以读取和修改的文件。
4. 描述研究任务，或输入 `/` 选择内置技能。完成后在项目成果中查看结果。

## 科研功能

| 功能 | 可以做什么 |
| --- | --- |
| 文献与证据 | 查找可访问论文、读取文档、保存带来源位置的观测数据。 |
| 材料与结构 | 核对化学身份，预览分子和晶体结构。 |
| 实验数据分析 | 拟合初始速率动力学，分析校准和图像比色，模拟反应并导出图表。 |
| 案例研究 | 管理假设、证据、候选设计、对照和验证结果。 |
| 外接计算 | 使用用户自己的 SSH、Slurm 或兼容 HTTP 资源运行 Quantum ESPRESSO 工作流。 |
| 项目记录 | 整理成组成果，引用已保存的版本，通过 Git 查看和恢复修改。 |

模型和计算连接由用户配置。研究文件保存在用户选择的项目目录，应用状态在首次启动时写入 `runtime/`。需要检索纳米酶数据时，可在 **设置 → 工具与计算资源 → 纳米酶数据** 连接兼容的数据注册表和材料空间注册表。

更多内容见[使用指南](docs/usage-guide.zh-CN.md)、[合成数据示例](examples/general-research/README.zh-CN.md)和 [Harness 集成](integrations/deepseek-harness/README.zh-CN.md)。

## 离线检查

```powershell
.venv/Scripts/python.exe -X utf8 -B scripts/check_foundation.py
```

## 许可证

mat-agent 采用 [MIT 许可证](LICENSE)。固定版本的 [DeepSeek Harness](integrations/deepseek-harness/upstream.lock.json) 保留[原版权声明和 MIT 许可证](integrations/deepseek-harness/LICENSE.upstream)。
