# mat-agent

![mat-agent crystal unit cell](integrations/deepseek-harness/foundation/material-mark.svg)

English · [简体中文](README.zh-CN.md)

mat-agent is a local materials research agent for desktop browsers, built on DeepSeek Harness. It brings literature, experimental data, structures, code and computational results together in local research projects.

## Install and run

On Windows, install Python 3.12, Node.js 24, Git and uv. Open PowerShell in the repository root and run:

```powershell
uv sync --locked
npm --prefix integrations/deepseek-harness/web-runtime ci
./scripts/start_workbench.ps1 -OpenBrowser
```

The workbench opens in Chrome or Edge. It listens locally on port 8790 by default. To select another port, add `-Port 8791` to the launcher. Stop it with Ctrl+C in the launch terminal.

1. Under **Settings → Models**, configure a model provider and select a default model.
2. Add a local research directory from the sidebar. Create a conversation or a research case.
3. Use project permissions to choose which files the agent may read or modify.
4. Describe the task or select a built-in skill with `/`. Open the results in project artifacts.

## Research workflows

| Area | What you can do |
| --- | --- |
| Literature and evidence | Retrieve accessible publications, read documents and save observations with source locations. |
| Materials and structures | Check chemical identities and preview molecular and crystal structures. |
| Experimental analysis | Fit initial-rate kinetics, analyse calibration and colorimetry, simulate reactions and export plots. |
| Research cases | Track hypotheses, evidence, candidate designs, controls and validation results. |
| Computation | Connect user-operated SSH/Slurm or compatible HTTP resources for Quantum ESPRESSO workflows. |
| Project records | Group artifacts, reference saved versions, and review or restore changes through Git. |

Model and compute connections are configured by the user. Research files stay in the selected project directories. Application state is created under `runtime/` at launch. An optional compatible nanozyme dataset and material-space registry can be connected in **Settings → Tools & compute → Nanozyme data**.

See the [usage guide](docs/usage-guide.md), [synthetic research examples](examples/general-research/README.md) and [Harness integration](integrations/deepseek-harness/README.md).

## Offline checks

```powershell
.venv/Scripts/python.exe -X utf8 -B scripts/check_foundation.py
```

## License

mat-agent is released under the [MIT License](LICENSE). The pinned [DeepSeek Harness runtime](integrations/deepseek-harness/upstream.lock.json) retains its [upstream copyright and MIT license](integrations/deepseek-harness/LICENSE.upstream).
