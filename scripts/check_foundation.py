"""Run the current local application's offline checks without model calls."""
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def main():
    suite = unittest.TestSuite()
    for pattern in ('test_foundation_science.py', 'test_candidate_checks.py', 'test_initial_rate.py', 'test_research_evidence.py', 'test_harness_research_preset.py', 'test_project_calculations.py', 'test_compute_connector_foundation.py', 'test_compute_ssh.py', 'test_qe_workflows.py', 'test_result_views.py'):
        suite.addTests(unittest.defaultTestLoader.discover(str(ROOT / 'tests'), pattern=pattern))
    if not unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful():
        return 1
    tests = sorted((ROOT / 'integrations/deepseek-harness/foundation').glob('*.test.mjs'))
    return subprocess.run(['node', '--test', *map(str, tests)], cwd=ROOT).returncode


if __name__ == '__main__':
    raise SystemExit(main())
