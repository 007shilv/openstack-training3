#!/usr/bin/env python3
"""Collect sanitized Task 5E DNF/RPM/repository evidence through strict SSH."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import paramiko


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "third-edition-work" / "validation" / "manual-install" / "transaction-evidence"
HOSTS = {
    "controller": ("192.168.234.151", ROOT / ".superpowers" / "sdd" / "known_hosts.controller", 8),
    "compute": ("192.168.234.150", ROOT / ".superpowers" / "sdd" / "known_hosts.compute", 3),
}

REMOTE_COLLECTOR = r'''
from __future__ import annotations

import json
import re
import subprocess
import sys


node = sys.argv[1]
transaction_id = int(sys.argv[2])


def run(arguments: list[str], allowed: set[int] = {0}) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(arguments, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if completed.returncode not in allowed:
        raise SystemExit(f"read-only probe failed: {arguments[0]} rc={completed.returncode}")
    return completed


def normalized(fields: list[str]) -> str:
    name, epoch, version, release, architecture = fields[:5]
    prefix = "" if epoch in {"0", "(none)", "None", ""} else f"{epoch}:"
    return f"{name}-{prefix}{version}-{release}.{architecture}"


history = run(["dnf", "history", "info", str(transaction_id)])
rows = []
pattern = re.compile(r"^\s+(Install|Upgrade|Upgraded)\s+(\S+)\s+(@+\S+)\s*$")
for line in history.stdout.splitlines():
    match = pattern.match(line)
    if match:
        action, nevra, repository = match.groups()
        rows.append({"action": action, "nevra": nevra, "repo": repository.lstrip("@")})
if not rows:
    raise SystemExit("DNF history contained no package rows")

history_new = []
current_rpm = []
repository_metadata = []
for row in rows:
    if row["action"] == "Upgraded":
        continue
    rpm = run(["rpm", "-q", row["nevra"], "--qf", "%{NAME}|%{EPOCHNUM}|%{VERSION}|%{RELEASE}|%{ARCH}\\n"])
    rpm_lines = [line for line in rpm.stdout.splitlines() if line]
    if len(rpm_lines) != 1:
        raise SystemExit("installed RPM cardinality mismatch")
    fields = rpm_lines[0].split("|")
    current_nevra = normalized(fields)
    if current_nevra != row["nevra"]:
        raise SystemExit("history/current RPM mismatch")
    package_name = fields[0]
    query = run([
        "dnf", "-q", "repoquery", "--disablerepo=*", "--enablerepo=openstack-local",
        "--qf", "%{name}|%{epoch}|%{version}|%{release}|%{arch}|%{repoid}", package_name,
    ])
    matches = []
    for line in query.stdout.splitlines():
        parts = line.split("|")
        if len(parts) == 6 and normalized(parts[:5]) == row["nevra"] and parts[5] == "openstack-local":
            matches.append({"nevra": row["nevra"], "repo": parts[5]})
    if len(matches) != 1:
        raise SystemExit("openstack-local repository metadata cardinality mismatch")
    history_new.append({"action": row["action"], "nevra": row["nevra"], "repo": row["repo"]})
    current_rpm.append(current_nevra)
    repository_metadata.append(matches[0])

history_old = []
upgrade_names = ("systemd-cryptsetup", "systemd-libs", "systemd-udev", "systemd", "gnutls")


def upgraded_package_name(nevra: str) -> str | None:
    return next((name for name in upgrade_names if nevra.startswith(name + "-")), None)


for row in rows:
    if row["action"] != "Upgraded":
        continue
    old_name = upgraded_package_name(row["nevra"])
    if old_name is None:
        raise SystemExit("unexpected old upgraded package")
    replacements = [item["nevra"] for item in history_new
                    if item["action"] == "Upgrade" and upgraded_package_name(item["nevra"]) == old_name]
    if len(replacements) != 1:
        raise SystemExit("old/new upgraded package pairing mismatch")
    absent = run(["rpm", "-q", row["nevra"]], {1})
    history_old.append({"action": "Upgraded", "nevra": row["nevra"], "repo": "@System",
                        "replaced_by": replacements[0], "current_absent": absent.returncode == 1})

unsafe_words = ("Removing", "Erasing", "Obsoleting", "Replacing", "Downgrading")
evidence = {
    "node": node,
    "transaction_id": transaction_id,
    "history_rc": history.returncode,
    "rpm_rc": 0,
    "repoquery_rc": 0,
    "unsafe_actions": [word for word in unsafe_words if re.search(rf"^\s+{word}\s", history.stdout, re.MULTILINE)],
    "history_new": history_new,
    "history_old": history_old,
    "current_rpm": current_rpm,
    "repository_metadata": repository_metadata,
}
print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
'''


def collect(node: str, password: str) -> dict[str, object]:
    host, known_hosts, transaction_id = HOSTS[node]
    client = paramiko.SSHClient()
    client.load_host_keys(str(known_hosts))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        client.connect(host, username="root", password=password, look_for_keys=False, allow_agent=False,
                       timeout=10, auth_timeout=10, banner_timeout=10)
        transport = client.get_transport()
        if transport is None:
            raise RuntimeError("SSH transport unavailable")
        channel = transport.open_session(timeout=10)
        channel.exec_command(f"python3 - {node} {transaction_id}")
        channel.sendall(REMOTE_COLLECTOR.encode("utf-8"))
        channel.shutdown_write()
        stdout = channel.makefile("rb", -1).read()
        stderr = channel.makefile_stderr("rb", -1).read()
        rc = channel.recv_exit_status()
    finally:
        password = ""
        client.close()
    if rc != 0:
        raise RuntimeError(f"{node} evidence collector failed rc={rc}: {stderr.decode('utf-8', 'replace').strip()}")
    return json.loads(stdout.decode("utf-8"))


def main() -> int:
    password = os.environ.pop("LAB_SSH_PASSWORD", "")
    if not password:
        raise SystemExit("LAB_SSH_PASSWORD is required")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    try:
        for node in ("controller", "compute"):
            evidence = collect(node, password)
            target = OUTPUT / f"nova-{node}-transaction.txt"
            temporary = target.with_suffix(".tmp")
            temporary.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            os.replace(temporary, target)
    finally:
        password = ""
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
