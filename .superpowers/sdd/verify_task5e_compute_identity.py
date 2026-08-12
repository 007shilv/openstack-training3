#!/usr/bin/env python3
"""Read-only, non-disclosing cross-node verification of Nova compute identity."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import uuid

import paramiko


ROOT = Path(__file__).resolve().parents[2]
HOSTS = {
    "controller": ("192.168.234.151", ROOT / ".superpowers" / "sdd" / "known_hosts.controller"),
    "compute": ("192.168.234.150", ROOT / ".superpowers" / "sdd" / "known_hosts.compute"),
}

REMOTE = {
    "compute": r'''
import json,os,stat,uuid
path='/etc/nova/compute_id'
fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
try:
 before=os.fstat(fd);data=b''
 while True:
  chunk=os.read(fd,128)
  if not chunk:break
  data+=chunk
  if len(data)>128:raise SystemExit('compute_id too long')
 after=os.fstat(fd)
finally:os.close(fd)
identity=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink)
if identity(before)!=identity(after) or not stat.S_ISREG(before.st_mode) or before.st_nlink!=1:raise SystemExit('unsafe compute_id')
value=data.decode('ascii').rstrip('\n');parsed=uuid.UUID(value)
if data!=f'{parsed}\n'.encode() or parsed.int==0:raise SystemExit('invalid compute_id')
import pwd
nova=pwd.getpwnam('nova')
if (before.st_uid,before.st_gid,stat.S_IMODE(before.st_mode))!=(nova.pw_uid,nova.pw_gid,0o644):raise SystemExit('metadata mismatch')
print(json.dumps({'uuid':value,'owner':'nova:nova','mode':'0644','nlink':before.st_nlink}))
''',
    "controller": r'''
import json,subprocess
def mysql(query):
 p=subprocess.run(['mysql','-uroot','-NBe',query],text=True,capture_output=True,check=True)
 return [line.split('\t') for line in p.stdout.splitlines() if line]
compute=mysql("SELECT uuid,hypervisor_hostname,hypervisor_type FROM nova.compute_nodes WHERE hypervisor_hostname='compute'")
provider=mysql("SELECT uuid,name FROM placement.resource_providers WHERE name='compute'")
if len(compute)!=1 or len(provider)!=1:raise SystemExit('internal UUID query cardinality mismatch')
print(json.dumps({'database_uuid':compute[0][0],'host':compute[0][1],'type':compute[0][2],
                  'provider_uuid':provider[0][0],'provider_name':provider[0][1]}))
''',
}


def run(node: str, password: str) -> dict[str, object]:
    host, known_hosts = HOSTS[node]
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
        channel.exec_command("python3 -")
        channel.sendall(REMOTE[node].encode("utf-8")); channel.shutdown_write()
        stdout = channel.makefile("rb", -1).read()
        stderr = channel.makefile_stderr("rb", -1).read()
        rc = channel.recv_exit_status()
    finally:
        password = ""
        client.close()
    if rc:
        raise RuntimeError(f"{node} read-only identity probe failed rc={rc}: {stderr.decode('utf-8', 'replace').strip()}")
    return json.loads(stdout.decode("utf-8"))


def main() -> int:
    password = os.environ.pop("LAB_SSH_PASSWORD", "")
    if not password:
        raise SystemExit("LAB_SSH_PASSWORD is required")
    try:
        compute = run("compute", password)
        controller = run("controller", password)
    finally:
        password = ""
    identifiers = (compute["uuid"], controller["database_uuid"], controller["provider_uuid"])
    parsed = [uuid.UUID(str(value)) for value in identifiers]
    if len(set(identifiers)) != 1 or any(value.int == 0 or str(value) != raw for value, raw in zip(parsed, identifiers)):
        raise SystemExit("compute identity cross-node UUID mismatch")
    if compute != {"uuid": identifiers[0], "owner": "nova:nova", "mode": "0644", "nlink": 1}:
        raise SystemExit("compute identity metadata mismatch")
    if controller["host"] != "compute" or controller["type"] != "QEMU" or controller["provider_name"] != "compute":
        raise SystemExit("compute internal identity binding mismatch")
    print("COMPUTE_ID_REMOTE_READONLY=PASS owner=nova:nova mode=0644 nlink=1 internal_uuid_consistency=3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
