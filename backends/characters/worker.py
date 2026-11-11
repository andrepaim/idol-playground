"""Registered CPU-only image/manual-review worker. No models or network calls."""
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from character_input import run_input, run_assessment


def main():
    stage,configuration = sys.argv[1:]
    path = Path(configuration)
    config = json.loads(path.read_text())
    functions = {'input':run_input,'assessment':run_assessment}
    if stage not in functions:
        raise ValueError('Unknown registered CPU stage.')
    functions[stage](config,path.parent)


if __name__ == '__main__':
    main()
