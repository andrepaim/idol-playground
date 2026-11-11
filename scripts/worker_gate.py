"""Linux bootstrap: no target code executes before its durable lease is granted."""
import argparse
import ctypes
import os
import signal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gate', type=int, required=True)
    parser.add_argument('--resource', type=int, required=True)
    parser.add_argument('--parent', type=int, required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    library = ctypes.CDLL(None, use_errno=True)
    if library.prctl(1, signal.SIGTERM, 0, 0, 0) != 0:  # PR_SET_PDEATHSIG
        raise OSError(ctypes.get_errno(), 'Parent-death signaling unavailable')
    if os.getppid() != args.parent or os.read(args.gate, 1) != b'G':
        raise SystemExit(125)
    os.close(args.gate)
    os.set_inheritable(args.resource, True)
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        raise SystemExit('Missing registered worker command')
    os.execvpe(command[0], command, os.environ)


if __name__ == '__main__':
    main()
