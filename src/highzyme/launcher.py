"""Launch the local Web application from this source distribution."""
from pathlib import Path
import runpy
import sys


def main():
    scripts = Path(__file__).resolve().parents[2] / 'scripts'
    sys.path.insert(0, str(scripts))
    runpy.run_path(str(scripts / 'run_harness_web.py'), run_name='__main__')
