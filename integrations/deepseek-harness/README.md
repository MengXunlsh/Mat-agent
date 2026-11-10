# DeepSeek Harness integration

English · [简体中文](README.zh-CN.md)

[Application](../../README.md) · [Usage guide](../../docs/usage-guide.md)

## Version and responsibilities

[web-runtime/package-lock.json](web-runtime/package-lock.json) pins `@deepseek-ai/dsh@0.2.1-rc.2`. [upstream.lock.json](upstream.lock.json) records its repository, tag, source commit and adapter entry. A complete upstream source checkout is not needed to run this application.

`foundation/` contains the mat-agent plugin, interface, research identity, internal roles and 15 built-in skills. Harness supplies conversation, planning, tool calls, compression, subagents, project files, Shell, persistent terminals, background tasks and native interface components.

## Install and launch

From the application root:

```powershell
npm --prefix integrations/deepseek-harness/web-runtime ci
./scripts/start_workbench.ps1 -OpenBrowser
```

At launch, `scripts/prepare_harness_web.py`, `scripts/harness_ui_extensions.py` and `scripts/harness_lifecycle_extensions.py` generate the adaptations from controlled sources. Change these files and `foundation/`, then regenerate; do not hand-edit installed Node packages.

## Research extensions

- General research is the main identity. Literature, analysis, verification and artifact synthesis use native subagents as needed.
- Skills load from `foundation/skills/`. User-global and project skill folders are not scanned automatically.
- Projects and cases share files, artifacts, permissions, versions and tasks. Built-in tools process project files and prepare scientific computations.
- Users configure models and search separately. Conversations select their own models; subagents inherit by default.
- Project memory connects a local memory service through Harness's MCP client and is enabled per project.
- Files, literature, code and artifact groups are read at their saved reference version. Previews do not rerun computations.

Curve previews use pinned Apache ECharts; structure previews use 3Dmol.js. Local RDKit, Gemmi and ASE parse structures. Frontend components load from the local runtime package.

## Runtime and licences

Local settings, credentials and conversations are created under `runtime/foundation/home/`; scientific files remain in user-selected projects. Personal runtime state is excluded from the handover. The launcher uses local access authorisation; recipients configure their own connections.

[LICENSE.upstream](LICENSE.upstream) preserves the upstream licence. The application code is distributed under the [MIT License](../../LICENSE). Python dependencies are managed by the root `pyproject.toml` and `uv.lock`.
