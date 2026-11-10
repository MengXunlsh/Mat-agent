import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('../../../', import.meta.url));
const python = path.join(root, process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python');
export const scientificRuntime = { python, figureStyleModule: 'highzyme.tools.figure_style', figureProfile: 'highzyme-cns' };

export function science(request, signal) {
  return runPython('highzyme.foundation_science', request, signal, 90000);
}

export function runPython(module, request, signal, timeout = 350000) {
  return new Promise((resolve, reject) => {
    const child = spawn(python, ['-m', module], {
      cwd: root, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'], signal,
      env: { ...process.env, PYTHONPATH: path.join(root, 'src'), PYTHONIOENCODING: 'utf-8' },
    });
    let output = '', error = '';
    const timer = setTimeout(() => child.kill(), timeout);
    child.stdout.on('data', chunk => { output += chunk; if (output.length > 4 * 1024 ** 2) child.kill(); });
    child.stderr.on('data', chunk => { error = (error + chunk).slice(-2000); });
    child.on('error', reject);
    child.on('close', () => {
      clearTimeout(timer);
      let value;
      try { value = JSON.parse(output); }
      catch { reject(new Error(error || 'Scientific reader did not return a result')); return; }
      if (value.error) reject(new Error(value.error)); else resolve(value.result);
    });
    child.stdin.end(JSON.stringify(request));
  });
}
