#!/usr/bin/env python3
"""Run a command on a fixed lab role over SSH without exposing credentials."""

import argparse
import getpass
import os
import sys
from pathlib import Path

import paramiko


LAB_HOSTS = {
    "controller": "192.168.234.151",
    "compute": "192.168.234.150",
}
SCRIPT_ROOT = Path(__file__).resolve().parent / "final-scripts"


def password_from_runtime(env_name: str) -> str:
    password = os.environ.get(env_name)
    if password:
        return password
    return getpass.getpass(f"SSH password ({env_name} is unset): ")


def approved_stdin_file(value: str | None) -> Path | None:
    if value is None:
        return None
    candidate = Path(value).resolve()
    try:
        candidate.relative_to(SCRIPT_ROOT)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"--stdin-file must be below {SCRIPT_ROOT}"
        ) from error
    if not candidate.is_file():
        raise argparse.ArgumentTypeError("--stdin-file must be an existing file")
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a command on the fixed controller or compute lab role."
    )
    parser.add_argument("--role", required=True, choices=sorted(LAB_HOSTS))
    parser.add_argument("--user", default="root")
    parser.add_argument(
        "--password-env",
        default="OPENSTACK_SSH_PASSWORD",
        help="environment variable containing the SSH password; prompt if unset",
    )
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument(
        "--known-hosts",
        type=Path,
        required=True,
        help="reviewed known_hosts file containing the selected role's SSH host key",
    )
    parser.add_argument("--stdin-file", type=approved_stdin_file)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    command = " ".join(args.command).strip()
    if command.startswith("-- "):
        command = command[3:]
    if not command:
        parser.error("missing remote command")
    if not args.known_hosts.is_file():
        parser.error("--known-hosts must name an existing reviewed file")

    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.load_host_keys(str(args.known_hosts))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        client.connect(
            hostname=LAB_HOSTS[args.role],
            port=args.port,
            username=args.user,
            password=password_from_runtime(args.password_env),
            timeout=args.timeout,
            look_for_keys=False,
            allow_agent=False,
        )
        stdin, stdout, stderr = client.exec_command(command, get_pty=False)
        if args.stdin_file:
            stdin.write(args.stdin_file.read_text(encoding="utf-8"))
            stdin.flush()
            stdin.channel.shutdown_write()
        exit_code = stdout.channel.recv_exit_status()
        sys.stdout.write(stdout.read().decode("utf-8", errors="replace"))
        sys.stderr.write(stderr.read().decode("utf-8", errors="replace"))
        return exit_code
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
