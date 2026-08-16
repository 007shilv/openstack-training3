"""Strict SSH capture helpers for Chapter 14 operations evidence.

This is an authoring utility.  It is not inserted into the textbook.
"""

from __future__ import annotations

from dataclasses import dataclass
from getpass import getpass
from pathlib import Path
import re

import paramiko


SENSITIVE_PATTERNS = (
    re.compile(r"(?i)\bOS_PASSWORD\s*="),
    re.compile(r"(?i)\bX-Auth-Token\s*:"),
    re.compile(r"(?i)\bCookie\s*:"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"[a-z][a-z0-9+.-]*://[^\s/:]+:[^\s/@]+@", re.IGNORECASE),
)


@dataclass(frozen=True)
class CaptureRecord:
    command: str
    stdout: str
    stderr: str
    returncode: int


def sanitize_output(value: str) -> str:
    """Return ordinary output but fail closed when secret-bearing text appears."""

    if not isinstance(value, str):
        raise TypeError("captured output must be text")
    if any(pattern.search(value) for pattern in SENSITIVE_PATTERNS):
        raise ValueError("captured output contains sensitive material")
    return value.replace("\r\n", "\n").replace("\r", "\n").rstrip()


class StrictSSHRunner:
    """Execute commands only after matching a reviewed host-key file."""

    def __init__(
        self,
        host: str,
        known_hosts: Path,
        *,
        username: str = "root",
        password: str,
    ) -> None:
        self.host = host
        self.known_hosts = Path(known_hosts)
        self.username = username
        self.password = password
        if not self.known_hosts.is_file():
            raise FileNotFoundError(f"reviewed known_hosts file is missing: {known_hosts}")

    def connect(self) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        client.load_host_keys(str(self.known_hosts))
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        client.connect(
            self.host,
            username=self.username,
            password=self.password,
            look_for_keys=False,
            allow_agent=False,
            timeout=15,
            auth_timeout=15,
            banner_timeout=15,
        )
        return client

    def run(self, command: str, *, timeout: int = 120) -> CaptureRecord:
        if not isinstance(command, str) or not command.strip():
            raise ValueError("command must be non-empty text")
        client = self.connect()
        try:
            _, stdout, stderr = client.exec_command(command, timeout=timeout)
            out = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")
            returncode = stdout.channel.recv_exit_status()
        finally:
            client.close()
        return CaptureRecord(
            command=command,
            stdout=sanitize_output(out),
            stderr=sanitize_output(err),
            returncode=returncode,
        )


def prompt_runner(host: str, known_hosts: Path) -> StrictSSHRunner:
    """Create a runner while keeping the SSH password only in process memory."""

    password = getpass(f"SSH password for root@{host}: ")
    if not password:
        raise ValueError("SSH password must not be empty")
    return StrictSSHRunner(host, known_hosts, password=password)

