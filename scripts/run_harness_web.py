"""Launch mat-agent directly on the pinned, complete Harness Web distribution."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def prepare(home: Path):
    if __package__:
        from .prepare_harness_web import prepare_product_copy
    else:
        from prepare_harness_web import prepare_product_copy
    prepare_product_copy()
    profile = home / 'profiles/web'
    profile.mkdir(parents=True, exist_ok=True)
    manifest = profile / 'package.json'
    if not manifest.exists():
        manifest.write_text(json.dumps({'name': 'mat-agent-web', 'private': True, 'type': 'module', 'dsh': {'profile': {'bundles': ['@deepseek-ai/dsh-base', '@deepseek-ai/dsh-web-app']}}}, indent=2), encoding='utf-8')
    settings = profile / 'cordis.patch.yml'
    saved = settings.read_text(encoding='utf-8') if settings.exists() else ''
    if not re.search(r'^\s*-\s+id:\s*[\'\"]?agent-default-model[\'\"]?\s*$', saved, re.M):
        saved = re.sub(r'^\[\]\s*$', '', saved, flags=re.M)
        settings.write_text(saved + "\n- id: agent-default-model\n  config:\n    provider: ''\n    model: ''\n", encoding='utf-8')
    plugin = (ROOT / 'integrations/deepseek-harness/foundation').as_posix()
    patch = ROOT / 'integrations/deepseek-harness/foundation/cordis.patch.yml'
    overlay = home / 'foundation.patch.yml'
    # Reuse the pinned preset's native tools and platform-specific Shell selection.
    standard = ROOT / 'integrations/deepseek-harness/web-runtime/node_modules/@deepseek-ai/dsh-web-app/presets/standard.patch.yml'
    research = standard.read_text(encoding='utf-8')
    research = research.replace('id: preset-standard', 'id: preset-research').replace('id: standard', 'id: research')
    research = research.replace('        id: research\n', '        id: research\n        name: General research\n        description: Literature, data, structures, code, and research documents.\n')
    research = research.replace("            name: '@deepseek-ai/dsh-skill-filesystem'\n", "            name: '@deepseek-ai/dsh-skill-filesystem'\n            config:\n              includeDefaultRoots: false\n              bundledSkillDir: " + json.dumps(plugin + '/skills') + '\n')
    persona = (ROOT / 'integrations/deepseek-harness/foundation/research-persona.txt').read_text(encoding='utf-8').strip()
    research = research.replace('prefix: You are a coding agent powered by the {{model}} model.', 'prefix: ' + json.dumps(persona, ensure_ascii=False))
    plan = (ROOT / 'integrations/deepseek-harness/foundation/research-plan.txt').read_text(encoding='utf-8').strip()
    research, plan_sections = re.subn(
        r"(name: '@deepseek-ai/dsh-plan-mode'\n\s+config:\n)                  section: \|\n.*?(?=          - id: compaction\n)",
        lambda match: match.group(1) + '                  section: ' + json.dumps(plan) + '\n',
        research, flags=re.S,
    )
    if plan_sections != 1:
        raise RuntimeError('The pinned Harness plan-mode configuration changed; review the research preset adapter.')
    research = research.replace('- id: tool-schedule\n', '- id: tool-schedule\n            disabled: true\n')
    terminal_bundle = ROOT / 'integrations/deepseek-harness/web-runtime/node_modules/@deepseek-ai/dsh-experimental-terminal-bundle/cordis.patch.yml'
    terminal_group = '\n'.join('      ' + line for line in terminal_bundle.read_text(encoding='utf-8').splitlines()[1:]) + '\n'
    research = research.replace('          - id: tool-jobs\n', terminal_group + '          - id: tool-jobs\n')
    research = research.replace('          - id: tool-jobs\n', "          - id: workarea\n            name: cordis:group\n            group: true\n            isolate:\n              worktrees: true\n            config:\n              - id: worktree\n                name: '@deepseek-ai/dsh-experimental-worktree'\n          - id: tool-jobs\n")
    product = patch.read_text(encoding='utf-8').replace('__FOUNDATION_PLUGIN__', plugin)
    overlay.write_text(product + '\n' + research, encoding='utf-8')
    return overlay


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8790)
    parser.add_argument('--home', type=Path, default=ROOT / 'runtime/foundation/home')
    parser.add_argument('--open-browser', action='store_true')
    args = parser.parse_args()
    entry = ROOT / 'integrations/deepseek-harness/web-runtime/node_modules/@deepseek-ai/dsh/lib/bin.js'
    if not entry.exists():
        raise SystemExit('Install the locked Web runtime: npm ci in integrations/deepseek-harness/web-runtime')
    home = args.home.resolve()
    overlay = prepare(home)
    environment = {k: v for k, v in os.environ.items() if not re.search(r'API_KEY|DEEPSEEK|OPENAI|ANTHROPIC|GEMINI|DSH_', k, re.I)}
    environment.update(DSH_HOME=str(home), DSH_TELEMETRY='0')
    # A clean launch cwd prevents the upstream credential fallback from reading the research repo's .env.
    cwd = home / 'launch'
    cwd.mkdir(exist_ok=True)
    command = [shutil.which('node') or 'node', str(entry), 'web', '--patch', str(overlay), '--no-open', '--port', str(args.port)]
    process = subprocess.Popen(command, cwd=cwd, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
    print(f'mat-agent: http://127.0.0.1:{args.port}', flush=True)
    try:
        for line in process.stdout:
            # Harness startup access URLs are credentials. Keep the private receipt out of console logs.
            if 'token=' in line:
                url = re.search(r'https?://\S+', line)
                if url:
                    (home / 'access-url.txt').write_text(url.group(0).strip(), encoding='utf-8')
                    print('Browser access link saved privately in the runtime home.', flush=True)
                    if args.open_browser:
                        webbrowser.open(url.group(0).strip())
            else:
                print(line, end='', flush=True)
        return process.wait()
    except KeyboardInterrupt:
        process.terminate()
        try: process.wait(timeout=15)
        except subprocess.TimeoutExpired: process.kill()
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
