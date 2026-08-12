"""Static safety and supply-chain contracts for the controlled deployment copy."""

from __future__ import annotations

import ast
import copy
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import tempfile
import textwrap
import types
import uuid
import zipfile
from pathlib import Path

import pytest


WORK_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = WORK_ROOT / "deployment" / "openstack-ts" / "final-scripts"
MATRIX_PATH = WORK_ROOT / "config" / "version-matrix.json"
DEFAULT_REPOSITORY_ZIP = WORK_ROOT.parent.parent.parent / "openstack_repo.zip"

EXPECTED_SCRIPTS = {
    f"{number:02d}-{role}-{component}.sh"
    for number, role, component in (
        (1, "controller", "network"),
        (2, "compute", "network"),
        (3, "controller", "base"),
        (4, "compute", "base"),
        (5, "controller", "services"),
        (6, "controller", "keystone"),
        (7, "controller", "glance"),
        (8, "controller", "placement"),
        (9, "controller", "nova"),
        (10, "compute", "nova"),
        (11, "controller", "neutron"),
        (12, "compute", "neutron"),
        (13, "controller", "cinder"),
        (14, "compute", "cinder"),
        (15, "controller", "swift"),
        (16, "compute", "swift"),
        (17, "controller", "horizon"),
    )
}

# These package names are the core service RPMs present in the supplied archive.
CORE_RPM_PATTERNS = {
    "keystone": re.compile(r"(?:^|/)openstack-keystone-(?P<version>\d+(?:\.\d+)+)-[^/]+\.rpm$"),
    "glance": re.compile(r"(?:^|/)openstack-glance-(?P<version>\d+(?:\.\d+)+)-[^/]+\.rpm$"),
    "placement": re.compile(r"(?:^|/)openstack-placement-api-(?P<version>\d+(?:\.\d+)+)-[^/]+\.rpm$"),
    "nova": re.compile(r"(?:^|/)openstack-nova-common-(?P<version>\d+(?:\.\d+)+)-[^/]+\.rpm$"),
    "neutron": re.compile(r"(?:^|/)openstack-neutron-common-(?P<version>\d+(?:\.\d+)+)-[^/]+\.rpm$"),
    "cinder": re.compile(r"(?:^|/)openstack-cinder-common-(?P<version>\d+(?:\.\d+)+)-[^/]+\.rpm$"),
    "swift": re.compile(r"(?:^|/)openstack-swift-common-(?P<version>\d+(?:\.\d+)+)-[^/]+\.rpm$"),
    "horizon": re.compile(r"(?:^|/)python3-horizon-(?P<version>\d+(?:\.\d+)+)-[^/]+\.rpm$"),
}

DESTRUCTIVE_COMMANDS = {
    "pvcreate", "pvremove", "vgcreate", "vgremove", "lvcreate", "lvremove",
    "mkfs", "wipefs", "dd", "parted", "fdisk", "sgdisk", "mkswap",
}
DEVICE_LITERAL = re.compile(r"/dev/sd[a-z](?:\d+)?\b")
VARIABLE_REFERENCE = re.compile(r"^\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?$")
ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*?)\s*$")
HEREDOC_OPEN = re.compile(r"<<-?\s*(?:(['\"])([A-Za-z_][A-Za-z0-9_]*)\1|([A-Za-z_][A-Za-z0-9_]*))")


def strip_shell_comment(line: str) -> str:
    """Remove shell comments while preserving hashes inside simple quoted values."""
    quote: str | None = None
    escaped = False
    result: list[str] = []
    for character in line:
        if escaped:
            result.append(character)
            escaped = False
            continue
        if character == "\\" and quote != "'":
            result.append(character)
            escaped = True
            continue
        if character in "'\"":
            if quote == character:
                quote = None
            elif quote is None:
                quote = character
            result.append(character)
            continue
        if character == "#" and quote is None:
            break
        result.append(character)
    return "".join(result).rstrip()


def shell_sections(text: str) -> tuple[list[str], list[tuple[str, str, str]]]:
    """Separate executable shell lines from heredoc bodies without executing either."""
    executable: list[str] = []
    heredocs: list[tuple[str, str, str]] = []
    raw_lines = text.splitlines()
    index = 0
    while index < len(raw_lines):
        raw_line = raw_lines[index]
        line = strip_shell_comment(raw_line)
        if line.strip():
            executable.append(line)
        opener = HEREDOC_OPEN.search(line)
        if opener is None:
            index += 1
            continue
        delimiter = opener.group(2) or opener.group(3)
        body: list[str] = []
        index += 1
        while index < len(raw_lines) and raw_lines[index].strip() != delimiter:
            body.append(raw_lines[index])
            index += 1
        heredocs.append((line, delimiter, "\n".join(body)))
        index += 1  # Skip the terminator when present.
    return executable, heredocs


def active_lines(text: str) -> list[str]:
    return shell_sections(text)[0]


def unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def shell_constants(text: str) -> dict[str, str]:
    constants: dict[str, str] = {}
    for line in active_lines(text):
        if match := ASSIGNMENT.match(line):
            constants[match.group(1)] = unquote(match.group(2))
    return constants


def resolve_value(value: str, constants: dict[str, str], seen: set[str] | None = None) -> str | None:
    value = unquote(value)
    if not (match := VARIABLE_REFERENCE.match(value)):
        return value
    variable = match.group(1)
    seen = set() if seen is None else seen
    if variable in seen or variable not in constants:
        return None
    seen.add(variable)
    return resolve_value(constants[variable], constants, seen)


def legacy_address_violations(text: str) -> list[str]:
    return [line for line in active_lines(text) if "192.168.234.152" in line]


def expected_role_ip(script_name: str) -> str:
    return "192.168.234.151" if "controller" in script_name else "192.168.234.150"


def role_identity_violations(script_name: str, text: str) -> list[str]:
    expected = expected_role_ip(script_name)
    constants = shell_constants(text)
    violations: list[str] = []
    for name in ("CONTROLLER_IP", "COMPUTE_IP", "EXPECTED_HOST_IP"):
        if name in constants:
            value = resolve_value(constants[name], constants)
            required = "192.168.234.151" if name == "CONTROLLER_IP" else "192.168.234.150"
            if value is None or not value.startswith(required):
                violations.append(f"{name} is {value!r}, expected {required}")
    if "SWIFT_STORAGE_IP" in constants:
        value = resolve_value(constants["SWIFT_STORAGE_IP"], constants)
        if value is None or not value.startswith("192.168.234.150"):
            violations.append(f"SWIFT_STORAGE_IP is {value!r}, expected compute .150")

    active = "\n".join(active_lines(text))
    config_identity = re.compile(
        r"cfg\.set\(\s*['\"][^'\"]+['\"]\s*,\s*['\"](?:my_ip|local_ip|target_ip_address)['\"]\s*,\s*['\"](192\.168\.234\.\d+)['\"]"
    )
    for match in config_identity.finditer(active):
        if match.group(1) != expected:
            violations.append(f"configuration identity is {match.group(1)}, expected {expected}")
    for line in active_lines(text):
        if "ens33" in line and (match := re.search(r"192\.168\.234\.\d+/24", line)):
            if match.group(0).removesuffix("/24") != expected:
                violations.append(f"ens33 identity is {match.group(0)}, expected {expected}/24")
    identity_keys = {"my_ip", "local_ip", "target_ip_address", "bind_ip", "address"}

    def check_identity(key: str, value: str | None) -> None:
        if value is None:
            violations.append(f"{key} identity value is not a parseable literal")
        elif key == "bind_ip" and value == "0.0.0.0":
            return
        elif value != expected:
            violations.append(f"{key} identity is {value!r}, expected {expected}")

    for opener, _delimiter, body in shell_sections(text)[1]:
        parsed = first_shell_command(opener)
        if parsed is None:
            continue
        command, _arguments = parsed
        if command == "python3":
            try:
                tree = ast.parse(body)
            except SyntaxError:
                continue
            python_constants: dict[str, str] = {}
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    python_constants[node.targets[0].id] = node.value.value
            def python_string(node: ast.expr) -> str | None:
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    return node.value
                if isinstance(node, ast.Name):
                    return python_constants.get(node.id)
                return None
            safe_dynamic_keys: set[str] = set()
            dictionary_keys = {
                key.value
                for item in ast.walk(tree)
                if isinstance(item, ast.Dict)
                for key in item.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
            for item in ast.walk(tree):
                if not isinstance(item, ast.For) or not isinstance(item.target, ast.Tuple) or not item.target.elts:
                    continue
                if not isinstance(item.iter, ast.Call) or not isinstance(item.iter.func, ast.Attribute) or item.iter.func.attr != "items":
                    continue
                first_target = item.target.elts[0]
                if isinstance(first_target, ast.Name) and not (dictionary_keys & identity_keys):
                    safe_dynamic_keys.add(first_target.id)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or node.func.attr != "set":
                    continue
                if len(node.args) < 3:
                    continue
                key = python_string(node.args[1])
                if key is None:
                    if not (isinstance(node.args[1], ast.Name) and node.args[1].id in safe_dynamic_keys):
                        violations.append("cfg.set identity key is not a parseable literal")
                elif key in identity_keys:
                    check_identity(key, python_string(node.args[2]))
        elif command == "cat":
            for raw in body.splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = (part.strip() for part in line.split("=", maxsplit=1))
                if key in identity_keys:
                    check_identity(key, value if "$" not in value else None)
    return violations


def command_tokens(line: str) -> tuple[str, list[str]] | None:
    try:
        tokens = shlex.split(line, posix=True)
    except ValueError:
        return None
    for index, token in enumerate(tokens):
        command = token.rsplit("/", maxsplit=1)[-1]
        if command in DESTRUCTIVE_COMMANDS or command.startswith("mkfs."):
            return command, tokens[index + 1 :]
    return None


def first_shell_command(line: str) -> tuple[str, list[str]] | None:
    try:
        tokens = shlex.split(line, posix=True)
    except ValueError:
        return None
    ignored = {"if", "then", "else", "fi", "do", "done", "!", "{"}
    for index, token in enumerate(tokens):
        if token in ignored or ASSIGNMENT.match(token):
            continue
        return token.rsplit("/", maxsplit=1)[-1], tokens[index + 1 :]
    return None


def disk_command_targets(text: str) -> tuple[list[str], list[str]]:
    """Return resolved disk targets and fail-closed errors for unsafe unknown targets."""
    constants = shell_constants(text)
    targets: list[str] = []
    errors: list[str] = []
    for line in active_lines(text):
        parsed = first_shell_command(line)
        if parsed is None:
            continue
        command, arguments = parsed
        if command not in DESTRUCTIVE_COMMANDS and not command.startswith("mkfs."):
            continue
        positional: list[str] = []
        skip_next = False
        for argument in arguments:
            if skip_next:
                skip_next = False
            elif argument in {"-L", "-t", "-T", "-n", "--physicalextentsize", "--align"}:
                skip_next = True
            elif argument.startswith("-"):
                continue
            else:
                positional.append(argument)
        if command == "dd":
            target_values = [argument.split("=", maxsplit=1)[1] for argument in arguments if argument.startswith("of=")]
        elif command == "vgcreate":
            target_values = positional[1:]
        elif command.startswith("mkfs.") or command == "mkfs":
            target_values = positional[-1:]
        elif command in {"parted", "fdisk", "sgdisk"}:
            target_values = positional[:1]
        else:
            target_values = positional
        for value in target_values:
            resolved = resolve_value(value, constants)
            if resolved is None:
                errors.append(f"{command} has unresolved disk variable {value!r}: {line.strip()}")
            elif not DEVICE_LITERAL.fullmatch(resolved):
                errors.append(f"{command} has non-device target {value!r}: {line.strip()}")
            else:
                targets.append(resolved)
    return targets, errors


def destructive_disk_violations(text: str) -> list[str]:
    targets, errors = disk_command_targets(text)
    return errors + [f"destructive command targets system disk {target}" for target in targets if target.startswith("/dev/sda")]


def antelope_contract_violations(text: str) -> list[str]:
    lines = active_lines(text)
    constants = shell_constants(text)
    violations: list[str] = []
    if resolve_value(constants.get("ANTELOPE_REPO_FILE", ""), constants) != "/etc/yum.repos.d/openstack-antelope.repo":
        violations.append("ANTELOPE_REPO_FILE is not the active openstack-antelope.repo path")
    installs_release = False
    for line in lines:
        parsed = first_shell_command(line)
        if parsed is None:
            continue
        command, arguments = parsed
        if command == "dnf" and "install" in arguments and "openstack-release-antelope" in arguments and arguments.index("install") < arguments.index("openstack-release-antelope"):
            installs_release = True
    if not installs_release:
        violations.append("no active dnf install command for openstack-release-antelope")
    def sed_is_required_rewrite(arguments: list[str]) -> bool:
        positional = [argument for argument in arguments if not argument.startswith("-")]
        if len(positional) < 2:
            return False
        expression, target = positional[0], positional[-1]
        if len(expression) < 4 or expression[0] != "s":
            return False
        delimiter = expression[1]
        fields = expression[2:].split(delimiter)
        return (
            len(fields) >= 3
            and fields[0] == "openEuler-24.03-LTS-SP3"
            and fields[1] == "openEuler-24.03-LTS-SP2"
            and resolve_value(target, constants) == "/etc/yum.repos.d/openstack-antelope.repo"
        )

    shell_rewrite = any(
        (parsed := first_shell_command(line)) is not None and parsed[0] == "sed" and sed_is_required_rewrite(parsed[1])
        for line in lines
    )
    if not shell_rewrite:
        violations.append("no active SP3-to-SP2 correction for ANTELOPE_REPO_FILE")
    return violations


def script_text(script_name: str) -> str:
    return (SCRIPTS_DIR / script_name).read_text(encoding="utf-8")


def all_script_paths() -> list[Path]:
    return sorted(SCRIPTS_DIR.glob("*.sh"))


def load_version_matrix() -> dict[str, object]:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def shell_function_body(text: str, name: str) -> str | None:
    """Return executable lines in a simple Bash function, excluding comments/heredocs."""
    active = "\n".join(active_lines(text))
    match = re.search(
        rf"(?m)^{re.escape(name)}\(\)\s*\{{\n(?P<body>.*?)(?=^\}}\s*$)",
        active,
        flags=re.DOTALL,
    )
    return None if match is None else match.group("body")


def blank_disk_guard_violations(text: str) -> list[str]:
    """Check executable blank-disk guard paths, including the orphan-PV case."""
    root_guard = shell_function_body(text, "assert_not_root_ancestor")
    blank_guard = shell_function_body(text, "assert_blank_data_disk")
    if root_guard is None or blank_guard is None:
        return ["required disk guard function is missing"]
    violations: list[str] = []
    root_lines = "\n".join(active_lines(root_guard))
    blank_lines = "\n".join(active_lines(blank_guard))
    if "findmnt -nro SOURCE /" not in root_lines or "lsblk -s -nrpo NAME" not in root_lines:
        violations.append("root-ancestor guard does not resolve the full root ancestry")
    if not re.search(r"readlink\s+-f\s+.*root_source", root_lines) or not re.search(r"readlink\s+-f\s+.*device", root_lines):
        violations.append("root-ancestor guard does not canonicalize source and target")
    if not re.search(r"^\s*assert_not_root_ancestor\s+['\"]?\$\{device\}['\"]?", blank_lines, flags=re.MULTILINE):
        violations.append("blank-disk guard does not invoke the root-ancestor guard")
    classifier_names = ("require_safe_cinder_disk", "require_safe_swift_disk")
    classifier = next((shell_function_body(text, name) for name in classifier_names if shell_function_body(text, name) is not None), None)
    if classifier is None or "assert_not_root_ancestor" not in "\n".join(active_lines(classifier)):
        violations.append("state classifier does not invoke the root-ancestor guard")
    if not re.search(r"^\s*command\s+-v\s+pvs\s+>/dev/null\s+2>&1\s+\|\|\s+die", blank_lines, flags=re.MULTILINE):
        violations.append("blank-disk guard does not fail closed when pvs is unavailable")
    if not re.search(r"pvs\s+--noheadings\s+--readonly\s+-o\s+pv_uuid,pv_name", blank_lines):
        violations.append("blank-disk guard does not inspect pv_uuid and pv_name")
    if "vg_name" in blank_lines:
        violations.append("blank-disk guard relies on vg_name and misses orphan PVs")
    if re.search(r"pvs[^\n]*\|\|\s*true", blank_lines):
        violations.append("blank-disk guard masks pvs errors")
    return violations


def replace_blank_guard_line(text: str, old: str, new: str) -> str:
    body = shell_function_body(text, "assert_blank_data_disk")
    assert body is not None
    return text.replace(body, body.replace(old, new, 1), 1)


GIT_BASH = Path(r"C:\Program Files\Git\bin\bash.exe")


def shell_function_definition(text: str, name: str) -> str:
    body = shell_function_body(text, name)
    assert body is not None, f"missing {name}"
    return f"{name}() {{\n{body}\n}}"


def run_blank_guard_harness(text: str, device: str, scenario: str) -> int:
    """Execute extracted guard functions with command mocks and no block-device access."""
    assert GIT_BASH.is_file(), "Git Bash is required for isolated Bash guard tests"
    functions = "\n\n".join(
        shell_function_definition(text, name)
        for name in ("die", "is_block_device", "assert_not_root_ancestor", "assert_blank_data_disk")
    )
    root_chain = "/dev/mapper/vg-root\n" + (f"{device}\n" if scenario == "root_ancestor" else "")
    pvs_mock = ""
    if scenario != "pvs_missing":
        pvs_status = "2" if scenario == "pvs_error" else "0"
        pvs_output = f"pv-uuid {device}" if scenario == "orphan_pv" else ""
        pvs_mock = f"""
        pvs() {{
          [[ {pvs_status} -eq 0 ]] || return {pvs_status}
          printf '%s\\n' '{pvs_output}'
        }}
        """
    harness = f"""
    set -euo pipefail
    {functions}
    is_block_device() {{ return 0; }}
    findmnt() {{ printf '%s\\n' /dev/mapper/vg-root; }}
    readlink() {{
      [[ "$1" == '-f' ]] || return 2
      printf '%s\\n' "$2"
    }}
    lsblk() {{
      case " $* " in
        *" -dn -o TYPE "*) printf '%s\\n' disk ;;
        *" -bdn -o SIZE "*) printf '%s\\n' 53687091200 ;;
        *" -s -nrpo NAME "*) printf '%s' '{root_chain}' ;;
        *) return 0 ;;
      esac
    }}
    awk() {{ return 0; }}
    blkid() {{ return 0; }}
    {pvs_mock}
    PATH=/nonexistent
    assert_blank_data_disk '{device}' 50
    """
    with tempfile.TemporaryDirectory() as directory:
        harness_path = Path(directory) / "blank-disk-harness.sh"
        harness_path.write_text(textwrap.dedent(harness), encoding="utf-8", newline="\n")
        completed = subprocess.run(
            [str(GIT_BASH), str(harness_path)],
            text=True,
            capture_output=True,
            check=False,
        )
    return completed.returncode


def blank_guard_behavior_violations(text: str, device: str) -> list[str]:
    expected = {
        "blank": 0,
        "root_ancestor": 1,
        "pvs_missing": 1,
        "pvs_error": 1,
        "orphan_pv": 1,
    }
    violations: list[str] = []
    for scenario, expected_exit in expected.items():
        actual_exit = run_blank_guard_harness(text, device, scenario)
        if (actual_exit == 0) != (expected_exit == 0):
            violations.append(f"{scenario}: expected exit class {expected_exit}, got {actual_exit}")
    return violations


def test_blank_disk_guards_execute_fail_closed_behavior() -> None:
    for script_name, device in (("14-compute-cinder.sh", "/dev/sdb"), ("16-compute-swift.sh", "/dev/sdc")):
        text = script_text(script_name)
        assert blank_guard_behavior_violations(text, device) == [], script_name
        blank_body = shell_function_body(text, "assert_blank_data_disk")
        assert blank_body is not None
        bypassed = text.replace(blank_body, "  return 0\n" + blank_body, 1)
        assert blank_guard_behavior_violations(bypassed, device), "return-0 mutation must be detected"


def test_blank_disk_guards_fail_closed_for_root_and_orphan_pv_states() -> None:
    for script_name in ("14-compute-cinder.sh", "16-compute-swift.sh"):
        text = script_text(script_name)
        assert blank_disk_guard_violations(text) == [], script_name
        assert "root-ancestor" in blank_disk_guard_violations(
            replace_blank_guard_line(text, 'assert_not_root_ancestor "${device}"\n', "")
        )[0]
        classifier_name = "require_safe_cinder_disk" if "cinder" in script_name else "require_safe_swift_disk"
        device_name = "CINDER_DEVICE" if "cinder" in script_name else "SWIFT_DEVICE"
        classifier = shell_function_body(text, classifier_name)
        assert classifier is not None
        assert "state classifier" in blank_disk_guard_violations(
            text.replace(classifier, classifier.replace(f'assert_not_root_ancestor "${{{device_name}}}"\n', "", 1), 1)
        )[-1]
        assert "pvs is unavailable" in blank_disk_guard_violations(
            replace_blank_guard_line(text, "command -v pvs >/dev/null 2>&1 || die", "command -v true >/dev/null 2>&1 || die")
        )[0]
        assert "pv_uuid and pv_name" in blank_disk_guard_violations(
            replace_blank_guard_line(text, "pv_uuid,pv_name", "vg_name")
        )[0]


def test_final_script_inventory_is_complete() -> None:
    actual = {path.name for path in all_script_paths()}
    assert actual == EXPECTED_SCRIPTS, (
        "final-scripts must contain exactly the 17 approved scripts; "
        f"missing={sorted(EXPECTED_SCRIPTS - actual)}, unexpected={sorted(actual - EXPECTED_SCRIPTS)}"
    )


def test_scripts_are_utf8_without_bom() -> None:
    bom_files = [path.name for path in all_script_paths() if path.read_bytes().startswith(b"\xef\xbb\xbf")]
    assert not bom_files, f"shell scripts must not have a UTF-8 BOM: {bom_files}"


def test_legacy_compute_address_is_absent() -> None:
    offenders = [path.name for path in all_script_paths() if legacy_address_violations(script_text(path.name))]
    assert not offenders, f"legacy .152 address remains in: {offenders}"


def test_management_addresses_are_bound_to_their_network_role_scripts() -> None:
    violations = {
        path.name: role_identity_violations(path.name, script_text(path.name))
        for path in all_script_paths()
    }
    assert not {name: errors for name, errors in violations.items() if errors}, (
        f"role-local IP identity mismatch: {violations}"
    )


def test_cinder_is_limited_to_sdb() -> None:
    text = script_text("14-compute-cinder.sh")
    constants = shell_constants(text)
    assert resolve_value(constants.get("CINDER_DEVICE", ""), constants) == "/dev/sdb"
    targets, errors = disk_command_targets(text)
    assert not errors, f"Cinder has an unresolvable destructive disk target: {errors}"
    assert targets and set(targets) == {"/dev/sdb"}, f"Cinder disk commands resolve to {targets}, not only /dev/sdb"


def test_swift_is_limited_to_sdc() -> None:
    text = script_text("16-compute-swift.sh")
    constants = shell_constants(text)
    assert resolve_value(constants.get("SWIFT_DEVICE", ""), constants) == "/dev/sdc"
    targets, errors = disk_command_targets(text)
    assert not errors, f"Swift has an unresolvable destructive disk target: {errors}"
    assert targets and set(targets) == {"/dev/sdc"}, f"Swift disk commands resolve to {targets}, not only /dev/sdc"


def test_destructive_commands_never_target_sda() -> None:
    violations = {
        path.name: destructive_disk_violations(script_text(path.name)) for path in all_script_paths()
    }
    assert not {name: errors for name, errors in violations.items() if errors}, (
        f"destructive system-disk target or unresolvable disk variable: {violations}"
    )


def test_antelope_release_configuration_remains_present() -> None:
    for script_name in ("03-controller-base.sh", "04-compute-base.sh"):
        violations = antelope_contract_violations(script_text(script_name))
        assert not violations, f"{script_name} Antelope contract failed: {violations}"


def test_repository_core_rpms_match_the_version_matrix() -> None:
    matrix = load_version_matrix()
    assert matrix.get("openstack_release") == "2023.1 Antelope", "matrix must identify the lab release as 2023.1 Antelope"
    components = matrix.get("components")
    assert isinstance(components, dict), "version matrix must contain a components object"

    repository_zip = Path(os.environ.get("OPENSTACK_REPO_ZIP", DEFAULT_REPOSITORY_ZIP))
    assert repository_zip.is_file(), f"repository ZIP not found: {repository_zip}"

    with zipfile.ZipFile(repository_zip) as archive:
        rpm_names = [name for name in archive.namelist() if name.endswith(".rpm")]

    for component, pattern in CORE_RPM_PATTERNS.items():
        matches = [(name, match.group("version")) for name in rpm_names if (match := pattern.search(name))]
        assert matches, f"missing core {component} RPM matching {pattern.pattern} in {repository_zip}"
        versions = {version for _, version in matches}
        assert len(versions) == 1, f"ambiguous {component} core RPM versions in {repository_zip}: {matches}"
        expected = components.get(component)
        assert expected is not None, f"version matrix is missing component: {component}"
        assert versions.pop() == expected, (
            f"{component} version mismatch: ZIP has {matches}; matrix specifies {expected}"
        )


def test_comment_only_ip_and_antelope_text_do_not_satisfy_contracts() -> None:
    comment_only = """
    # 192.168.234.152 is retired.
    # dnf install openstack-release-antelope
    # ANTELOPE_REPO_FILE=/etc/yum.repos.d/openstack-antelope.repo
    # s#openEuler-24.03-LTS-SP3#openEuler-24.03-LTS-SP2#g
    """
    assert legacy_address_violations(comment_only) == []
    assert antelope_contract_violations(comment_only), "comments must not satisfy the Antelope contract"


def test_reversed_role_identity_is_rejected() -> None:
    reversed_compute = 'COMPUTE_IP="192.168.234.151/24"\ncfg.set("DEFAULT", "my_ip", "192.168.234.151")\n'
    assert role_identity_violations("02-compute-network.sh", reversed_compute)


def test_active_legacy_address_is_rejected() -> None:
    assert legacy_address_violations('COMPUTE_IP="192.168.234.152/24"\n')


def test_indirect_system_disk_target_is_rejected() -> None:
    indirect_target = 'TARGET="/dev/sda"\npvcreate "${TARGET}"\n'
    violations = destructive_disk_violations(indirect_target)
    assert any("/dev/sda" in violation for violation in violations)


def test_unresolved_destructive_disk_variable_is_rejected() -> None:
    violations = destructive_disk_violations('pvcreate "${UNVERIFIED_TARGET}"\n')
    assert any("unresolved disk variable" in violation for violation in violations)


def test_system_disk_warning_comment_is_not_a_destructive_violation() -> None:
    assert destructive_disk_violations("# Never run pvcreate /dev/sda on the system disk.\n") == []


def test_cat_and_echo_heredoc_antelope_forgeries_are_rejected() -> None:
    cat_forgery = """\
ANTELOPE_REPO_FILE="/etc/yum.repos.d/openstack-antelope.repo"
cat <<'PY'
dnf install openstack-release-antelope
sed -ri 's#openEuler-24.03-LTS-SP3#openEuler-24.03-LTS-SP2#g' "${ANTELOPE_REPO_FILE}"
PY
"""
    echo_forgery = """\
ANTELOPE_REPO_FILE="/etc/yum.repos.d/openstack-antelope.repo"
echo 'dnf install openstack-release-antelope'
echo 'openEuler-24.03-LTS-SP3 openEuler-24.03-LTS-SP2 ANTELOPE_REPO_FILE'
"""
    assert antelope_contract_violations(cat_forgery)
    assert antelope_contract_violations(echo_forgery)


def test_python_heredoc_replace_without_a_write_is_rejected() -> None:
    python_fix = """\
ANTELOPE_REPO_FILE="/etc/yum.repos.d/openstack-antelope.repo"
dnf install openstack-release-antelope
python3 - <<'PY'
url = "openEuler-24.03-LTS-SP3".replace("openEuler-24.03-LTS-SP3", "openEuler-24.03-LTS-SP2")
PY
"""
    assert antelope_contract_violations(python_fix)


def test_dd_and_mkfs_unknown_targets_fail_closed() -> None:
    assert destructive_disk_violations('dd if=/dev/zero of="${FOO}"\n')
    assert destructive_disk_violations('mkfs.xfs "${FOO}"\n')


def test_semantic_disk_targets_accept_safe_variable_and_reject_system_partitions() -> None:
    assert destructive_disk_violations('SAFE="/dev/sdb"\nmkfs.xfs -L data "${SAFE}"\n') == []
    assert destructive_disk_violations('TARGET="/dev/sda2"\nparted "${TARGET}" print\n')


def test_python_cfg_heredoc_role_identity_is_checked() -> None:
    bad = """\
python3 - <<'PY'
cfg.set('DEFAULT', 'my_ip', '192.168.234.151')
PY
"""
    good = bad.replace(".151", ".150")
    assert role_identity_violations("10-compute-nova.sh", bad)
    assert role_identity_violations("10-compute-nova.sh", good) == []


def test_antelope_requires_real_sed_targeting_the_antelope_repo() -> None:
    base = 'ANTELOPE_REPO_FILE="/etc/yum.repos.d/openstack-antelope.repo"\ndnf install openstack-release-antelope\n'
    valid = base + "sed -ri 's#openEuler-24.03-LTS-SP3#openEuler-24.03-LTS-SP2#g' \"${ANTELOPE_REPO_FILE}\"\n"
    assert antelope_contract_violations(valid) == []
    assert antelope_contract_violations(base + 'python3 -c "x.replace(\'openEuler-24.03-LTS-SP3\', \'openEuler-24.03-LTS-SP2\')"\n')
    assert antelope_contract_violations(base + "sed -ri 's#openEuler-24.03-LTS-SP3#openEuler-24.03-LTS-SP2#g' /tmp/other.repo\n")


def test_nonexecuting_disk_text_and_option_positions_are_handled() -> None:
    assert destructive_disk_violations("echo pvcreate /dev/sda\nprintf 'mkfs.xfs /dev/sda'\n") == []
    assert destructive_disk_violations("vgcreate --physicalextentsize 4M cinder-volumes /dev/sdb\n") == []
    assert destructive_disk_violations("parted --align optimal /dev/sdb print\n") == []


def test_antelope_rejects_non_install_dnf_actions_and_invalid_sed_expressions() -> None:
    base = 'ANTELOPE_REPO_FILE="/etc/yum.repos.d/openstack-antelope.repo"\n'
    rewrite = "sed -ri 's#openEuler-24.03-LTS-SP3#openEuler-24.03-LTS-SP2#g' \"${ANTELOPE_REPO_FILE}\"\n"
    assert antelope_contract_violations(base + "dnf remove openstack-release-antelope\n" + rewrite)
    install = base + "dnf install openstack-release-antelope\n"
    assert antelope_contract_violations(install + "sed -ri 's#openEuler-24.03-LTS-SP2#openEuler-24.03-LTS-SP3#g' \"${ANTELOPE_REPO_FILE}\"\n")
    assert antelope_contract_violations(install + "sed -n 'openEuler-24.03-LTS-SP3 openEuler-24.03-LTS-SP2' \"${ANTELOPE_REPO_FILE}\"\n")


def test_python_cfg_set_resolves_constant_key_and_value_variables() -> None:
    template = """\
python3 - <<'PY'
key = 'my_ip'
value = '192.168.234.{}'
cfg.set('DEFAULT', key, value)
PY
"""
    assert role_identity_violations("10-compute-nova.sh", template.format("151"))
    assert role_identity_violations("10-compute-nova.sh", template.format("150")) == []
    unknown_key = "python3 - <<'PY'\ncfg.set('DEFAULT', key, '192.168.234.150')\nPY\n"
    assert role_identity_violations("10-compute-nova.sh", unknown_key)


MANUAL_INSTALL_DIR = WORK_ROOT / "validation" / "manual-install"


def manual_markdown(name: str) -> str:
    return (MANUAL_INSTALL_DIR / name).read_text(encoding="utf-8")


def markdown_fenced_blocks(name: str, language: str) -> list[str]:
    pattern = re.compile(
        rf"(?ms)^```{re.escape(language)}[ \t]*\n(?P<body>.*?)^```[ \t]*$"
    )
    return [match.group("body") for match in pattern.finditer(manual_markdown(name))]


def manual_shell_text(name: str) -> str:
    return "\n\n".join(markdown_fenced_blocks(name, "bash"))


def manual_function_definitions(text: str, names: tuple[str, ...]) -> str:
    return "\n\n".join(shell_function_definition(text, name) for name in names)


def run_git_bash(text: str) -> subprocess.CompletedProcess[str]:
    assert GIT_BASH.is_file(), "Git Bash is required for manual-install behavior tests"
    with tempfile.TemporaryDirectory() as temp_dir:
        harness_path = Path(temp_dir) / "harness.sh"
        harness_path.write_text(textwrap.dedent(text), encoding="utf-8", newline="\n")
        return subprocess.run(
            [str(GIT_BASH), str(harness_path)],
            text=True,
            capture_output=True,
            check=False,
        )


@pytest.mark.parametrize(
    ("document", "runner", "stages", "failing_stage"),
    (
        (
            "01-base.md",
            "run_base_sequence",
            (
                "stage_starting_state",
                "stage_identity_hosts",
                "stage_repository_security",
                "stage_chrony",
                "stage_secret_metadata",
            ),
            "stage_chrony",
        ),
        (
            "02-infrastructure.md",
            "run_infrastructure_sequence",
            (
                "stage_package_install",
                "stage_mariadb",
                "stage_rabbitmq",
                "stage_memcached",
                "stage_openstack_cli",
            ),
            "stage_rabbitmq",
        ),
    ),
)
def test_manual_install_sessions_stop_at_the_first_failed_gate(
    document: str,
    runner: str,
    stages: tuple[str, ...],
    failing_stage: str,
) -> None:
    text = manual_shell_text(document)
    active = active_lines(text)
    assert "set -Eeuo pipefail" in active, f"{document} must start a strict reusable shell session"
    assert any(first_shell_command(line) == ("trap", ["on_error \"$LINENO\" \"$BASH_COMMAND\"", "ERR"]) for line in active), (
        f"{document} must install an executable ERR trap"
    )
    runner_body = shell_function_body(text, runner)
    assert runner_body is not None, f"{document} is missing {runner}"
    calls = [line.strip() for line in active_lines(runner_body) if line.strip() in stages]
    assert calls == list(stages), f"{runner} does not preserve the required gate order: {calls}"

    mocks = "\n".join(
        f"{stage}() {{ printf '%s\\n' {stage}; {'return 23' if stage == failing_stage else 'return 0'}; }}"
        for stage in stages
    )
    completed = run_git_bash(
        f"""
        set -Eeuo pipefail
        {shell_function_definition(text, runner)}
        {mocks}
        {runner}
        """
    )
    assert completed.returncode != 0
    observed = completed.stdout.splitlines()
    assert observed == list(stages[: stages.index(failing_stage) + 1]), (
        f"{runner} continued after {failing_stage}: {observed}"
    )


def run_manual_blank_disk_guard(scenario: str) -> int:
    text = manual_shell_text("01-base.md")
    definitions = manual_function_definitions(
        text,
        ("die", "is_block_device", "assert_not_root_ancestor", "assert_blank_data_disk"),
    )
    pvs_definition = "" if scenario == "pvs_missing" else f"""
    pvs() {{
      [[ {scenario!r} == pvs_error ]] && return 4
      [[ {scenario!r} == pv ]] && printf '%s\\n' 'pv-uuid /dev/sdb'
      return 0
    }}
    """
    harness = f"""
    set -Eeuo pipefail
    {definitions}
    is_block_device() {{ [[ {scenario!r} != not_block ]]; }}
    readlink() {{ [[ "$1" == -f ]] || return 9; printf '%s\\n' "$2"; }}
    findmnt() {{ printf '%s\\n' /dev/mapper/system-root; }}
    blockdev() {{ [[ "$1" == --getsize64 ]] || return 9; [[ {scenario!r} == wrong_size ]] && printf '%s\\n' 1 || printf '%s\\n' 53687091200; }}
    lsblk() {{
      if [[ "$1" == -s && "$2" == -nrpo && "$3" == NAME ]]; then
        printf '%s\\n' /dev/mapper/system-root
        [[ {scenario!r} == root ]] && printf '%s\\n' /dev/sdb || printf '%s\\n' /dev/sda
      elif [[ "$1" == -nrpo && "$2" == NAME ]]; then
        printf '%s\\n' /dev/sdb
        [[ {scenario!r} == child ]] && printf '%s\\n' /dev/sdb1
        return 0
      elif [[ "$1" == -dnro && "$2" == FSTYPE,MOUNTPOINT ]]; then
        [[ {scenario!r} == filesystem ]] && printf '%s\\n' 'xfs '
        [[ {scenario!r} == mount ]] && printf '%s\\n' ' /srv/data'
        return 0
      else
        return 9
      fi
    }}
    {pvs_definition}
    blkid() {{
      [[ {scenario!r} == signature ]] && return 0
      [[ {scenario!r} == blkid_error ]] && return 4
      return 2
    }}
    assert_blank_data_disk /dev/sdb 53687091200
    """
    return run_git_bash(harness).returncode


def test_manual_base_blank_disk_guard_is_behaviorally_fail_closed() -> None:
    expected_success = {"blank"}
    scenarios = {
        "blank", "not_block", "wrong_size", "root", "child", "filesystem",
        "mount", "pvs_missing", "pvs_error", "pv", "signature", "blkid_error",
    }
    actual_success = {scenario for scenario in scenarios if run_manual_blank_disk_guard(scenario) == 0}
    assert actual_success == expected_success


def test_manual_hosts_rewrite_preserves_unrelated_aliases_and_comments() -> None:
    shell = manual_shell_text("01-base.md")
    bodies = [body for _opener, _delimiter, body in shell_sections(shell)[1] if "TARGET_ALIASES" in body]
    assert len(bodies) == 1, "01-base must contain one executable hosts-rewrite heredoc"
    source = """\
127.0.0.1 localhost
192.168.234.151 controller repo mirror # preserve-controller-line
10.0.0.8 compute legacy # preserve-other-ip
# controller and compute in this comment must survive
192.168.234.150 compute # preserve-comment-only
"""
    expected = """\
127.0.0.1 localhost
192.168.234.151 repo mirror  # preserve-controller-line
10.0.0.8 legacy  # preserve-other-ip
# controller and compute in this comment must survive
# preserve-comment-only
192.168.234.151 controller
192.168.234.150 compute
"""
    with tempfile.TemporaryDirectory() as temp_dir:
        source_path = Path(temp_dir) / "hosts.in"
        output_path = Path(temp_dir) / "hosts.out"
        source_path.write_text(source, encoding="utf-8", newline="\n")
        completed = subprocess.run(
            ["python", "-c", bodies[0], str(source_path), str(output_path)],
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        assert output_path.read_text(encoding="utf-8") == expected


@pytest.mark.parametrize(
    ("scenario", "expected_success"),
    (("absent", True), ("installed", False), ("query_error", False), ("misleading_rc1", False)),
)
def test_manual_later_package_absence_probe_distinguishes_all_exit_classes(
    scenario: str, expected_success: bool
) -> None:
    text = manual_shell_text("02-infrastructure.md")
    definitions = manual_function_definitions(text, ("die", "assert_packages_absent"))
    completed = run_git_bash(
        f"""
        set -Eeuo pipefail
        {definitions}
        rpm() {{
          if [[ "$2" == rpm ]]; then return 0; fi
          case {scenario!r} in
            absent) printf '%s\\n' 'package openstack-keystone is not installed'; return 1 ;;
            installed) printf '%s\\n' 'openstack-keystone-1.0-1.noarch'; return 0 ;;
            query_error) printf '%s\\n' 'rpmdb unavailable' >&2; return 2 ;;
            misleading_rc1) printf '%s\\n' 'rpmdb unavailable' >&2; return 1 ;;
          esac
        }}
        assert_packages_absent openstack-keystone
        """
    )
    assert (completed.returncode == 0) is expected_success


def test_manual_secret_transfer_is_strict_exclusive_atomic_and_cleanup_safe() -> None:
    blocks = [block for block in markdown_fenced_blocks("01-base.md", "python") if "def connect_pinned" in block]
    assert len(blocks) == 1, "01-base must contain one full workstation Paramiko transfer program"
    source = blocks[0]
    tree = ast.parse(source)
    compile(tree, "01-base-secret-transfer", "exec")

    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    constants = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)}
    assert {"load_host_keys", "RejectPolicy", "getpass"} <= (attributes | names)
    assert "AutoAddPolicy" not in attributes
    assert "hashlib" not in names and "hexdigest" not in attributes
    assert ".superpowers/sdd/known_hosts.controller" in constants
    assert ".superpowers/sdd/known_hosts.compute" in constants
    assert 65536 in constants

    exclusive_assignment = next(
        node for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "CREATE_EXCLUSIVE_PROGRAM" for target in node.targets)
    )
    assert isinstance(exclusive_assignment.value, ast.Constant) and isinstance(exclusive_assignment.value.value, str)
    exclusive_tree = ast.parse(exclusive_assignment.value.value)
    exclusive_attributes = {
        node.attr for node in ast.walk(exclusive_tree) if isinstance(node, ast.Attribute)
    }
    exclusive_constants = {
        node.value for node in ast.walk(exclusive_tree) if isinstance(node, ast.Constant)
    }
    assert {"O_EXCL", "O_NOFOLLOW", "fchmod", "fchown", "fstat", "lstat", "fsync"} <= exclusive_attributes
    assert 0o600 in exclusive_constants

    stream_assignment = next(
        node for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "STREAM_OWNED_PROGRAM" for target in node.targets)
    )
    assert isinstance(stream_assignment.value, ast.Constant) and isinstance(stream_assignment.value.value, str)
    stream_tree = ast.parse(stream_assignment.value.value)
    stream_attributes = {
        node.attr for node in ast.walk(stream_tree) if isinstance(node, ast.Attribute)
    }
    stream_constants = {
        node.value for node in ast.walk(stream_tree) if isinstance(node, ast.Constant)
    }
    assert {"O_NOFOLLOW", "fstat", "lstat", "ftruncate", "fsync"} <= stream_attributes
    assert 65536 in stream_constants

    connect_calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "connect"
    ]
    assert len(connect_calls) == 1
    for call in connect_calls:
        password_keywords = [kw.value for kw in call.keywords if kw.arg == "password"]
        assert len(password_keywords) == 1 and isinstance(password_keywords[0], ast.Name), (
            "SSH password must be supplied from an in-memory variable, never a literal"
        )
    pinned_calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "connect_pinned"
    ]
    assert len(pinned_calls) == 2, "controller and compute must each use the pinned connector"

    transfer = next(
        node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "transfer_secret"
    )
    calls = [
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(transfer)
        if isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute))
    ]
    assert "create_exclusive_temp" in calls
    assert "promote_atomic" in calls
    assert "verify_metadata_equal" in calls
    assert any(isinstance(node, ast.Try) and node.finalbody for node in ast.walk(transfer)), (
        "partial-transfer cleanup must be protected by finally"
    )
    assert "cleanup_exact_temp" in calls


def test_manual_secret_transfer_does_not_cleanup_a_preexisting_unowned_temp() -> None:
    source = next(
        block for block in markdown_fenced_blocks("01-base.md", "python")
        if "def connect_pinned" in block
    )
    tree = ast.parse(source)
    transfer = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "transfer_secret"
    )
    module = ast.Module(body=[transfer], type_ignores=[])
    namespace: dict[str, object] = {}
    cleanup_calls: list[str] = []

    class DummySource:
        def read(self, _size: int) -> bytes:
            return b""

        def close(self) -> None:
            return None

    class DummySftp:
        def open(self, _path: str, _mode: str) -> DummySource:
            return DummySource()

        def close(self) -> None:
            return None

    class DummyClient:
        def open_sftp(self) -> DummySftp:
            return DummySftp()

    class DummyUuid:
        hex = "review-temp"

    class DummyUuidModule:
        @staticmethod
        def uuid4() -> DummyUuid:
            return DummyUuid()

    namespace.update(
        SECRET_PATH="/root/.openstack-lab-secrets",
        CHUNK_SIZE=65536,
        uuid=DummyUuidModule,
        create_exclusive_temp=lambda _client, _path: (_ for _ in ()).throw(FileExistsError("preexisting")),
        promote_atomic=lambda *_args: None,
        verify_metadata_equal=lambda *_args: None,
        cleanup_exact_temp=lambda _client, path: cleanup_calls.append(path),
    )
    exec(compile(module, "01-base-transfer-owned-cleanup", "exec"), namespace)

    with pytest.raises(FileExistsError, match="preexisting"):
        namespace["transfer_secret"](DummyClient(), DummyClient())  # type: ignore[operator]
    assert cleanup_calls == [], "O_EXCL failure must not remove a preexisting unowned path"


def run_rabbit_configuration_harness(
    existing: bool,
    auth_ok: bool,
    list_users_rc: int = 0,
) -> subprocess.CompletedProcess[str]:
    text = manual_shell_text("02-infrastructure.md")
    definitions = manual_function_definitions(text, ("die", "configure_rabbitmq"))
    user_row = "openstack\t[]" if existing else "guest\t[administrator]"
    return run_git_bash(
        f"""
        set -Eeuo pipefail
        TRACE=$(mktemp)
        {definitions}
        systemctl() {{ return 0; }}
        rabbitmqctl() {{
          case "$1" in
            list_users) printf 'user\\ttags\\n%b\\n' {user_row!r}; return {list_users_rc} ;;
            add_user) printf '%s\\n' add >> "$TRACE" ;;
            change_password) printf '%s\\n' change >> "$TRACE" ;;
            set_permissions) printf '%s\\n' permissions >> "$TRACE" ;;
            authenticate_user) printf '%s\\n' auth >> "$TRACE"; [[ {str(auth_ok).lower()} == true ]] ;;
            *) return 9 ;;
          esac
        }}
        configure_rabbitmq '<RABBIT_PASS>'
        cat "$TRACE"
        rm -f "$TRACE"
        """
    )


def test_manual_rabbitmq_configuration_is_idempotent_and_auth_failure_is_fatal() -> None:
    missing = run_rabbit_configuration_harness(existing=False, auth_ok=True)
    existing = run_rabbit_configuration_harness(existing=True, auth_ok=True)
    auth_failure = run_rabbit_configuration_harness(existing=True, auth_ok=False)
    assert missing.returncode == 0, missing.stderr
    assert missing.stdout.splitlines() == ["add", "change", "permissions", "auth"]
    assert existing.returncode == 0, existing.stderr
    assert existing.stdout.splitlines() == ["change", "permissions", "auth"]
    assert auth_failure.returncode != 0, "failed RabbitMQ authentication must stop the session"


def test_manual_rabbitmq_list_users_probe_failure_is_fatal_before_mutation() -> None:
    probe_failure = run_rabbit_configuration_harness(
        existing=False,
        auth_ok=True,
        list_users_rc=7,
    )
    assert probe_failure.returncode != 0
    assert probe_failure.stdout.splitlines() == [], (
        "list_users failure must stop before add/change/set_permissions/authenticate"
    )


def test_manual_service_gates_assert_live_state_not_just_display_it() -> None:
    base = manual_shell_text("01-base.md")
    infrastructure = manual_shell_text("02-infrastructure.md")
    chrony = shell_function_body(base, "assert_chrony")
    mariadb = shell_function_body(infrastructure, "assert_mariadb")
    rabbit = shell_function_body(infrastructure, "assert_rabbitmq")
    memcached = shell_function_body(infrastructure, "assert_memcached")
    assert all(body is not None for body in (chrony, mariadb, rabbit, memcached))
    assert "Leap status" in chrony and "Normal" in chrony and "chronyc sources" in chrony
    assert "@@bind_address" in mariadb and "0.0.0.0" in mariadb and "grep -qx" in mariadb
    assert "list_user_permissions" in rabbit and "authenticate_user" in rabbit
    assert "expected_listeners" in memcached and "actual_listeners" in memcached
    memcache_bodies = [
        body for _opener, _delimiter, body in shell_sections(infrastructure)[1]
        if "task5a_listener_check" in body
    ]
    assert len(memcache_bodies) == 1
    tree = ast.parse(memcache_bodies[0])
    assert any(isinstance(node, ast.Raise) for node in ast.walk(tree)), (
        "Memcached client verification must raise on set/get/delete failure"
    )


def test_manual_protected_checks_do_not_mask_failures_with_or_true() -> None:
    violations: dict[str, list[str]] = {}
    for document in ("01-base.md", "02-infrastructure.md"):
        offenders = [line for line in active_lines(manual_shell_text(document)) if "|| true" in line]
        if offenders:
            violations[document] = offenders
    assert not violations, f"protected manual-install checks mask failures: {violations}"


def test_manual_keystone_session_preserves_dependency_order_and_stops_on_failure() -> None:
    text = manual_shell_text("03-keystone.md")
    stages = (
        "stage_starting_state",
        "stage_package_transaction",
        "stage_database",
        "stage_configuration",
        "stage_schema",
        "stage_keys",
        "stage_bootstrap",
        "stage_apache",
        "stage_identity_validation",
        "stage_cross_slice_audit",
    )
    active = active_lines(text)
    assert "set -Eeuo pipefail" in active
    assert any(first_shell_command(line) == ("trap", ['on_error "$LINENO" "$BASH_COMMAND"', "ERR"]) for line in active)
    runner = shell_function_body(text, "run_keystone_sequence")
    assert runner is not None
    calls = [line.strip() for line in active_lines(runner) if line.strip() in stages]
    assert calls == list(stages)

    mocks = "\n".join(
        f"{stage}() {{ printf '%s\\n' {stage}; {'return 31' if stage == 'stage_schema' else 'return 0'}; }}"
        for stage in stages
    )
    completed = run_git_bash(
        f"""
        set -Eeuo pipefail
        {shell_function_definition(text, "run_keystone_sequence")}
        {mocks}
        run_keystone_sequence
        """
    )
    assert completed.returncode != 0
    assert completed.stdout.splitlines() == list(stages[:5])


def test_manual_keystone_preflight_is_repo_only_and_rejects_unsafe_transactions() -> None:
    text = manual_shell_text("03-keystone.md")
    active = "\n".join(active_lines(text))
    assert "--assumeno" in active
    assert "--setopt=install_weak_deps=False" in active
    assert "--disablerepo='*'" in active
    assert "--enablerepo='openstack-local'" in active
    assert re.search(r"install\s+openstack-keystone\s+httpd\s+mod_wsgi", active)
    for forbidden in ("--allowerasing", "--nodeps", "--skip-broken"):
        assert forbidden not in active_lines(text)

    definitions = manual_function_definitions(text, ("die", "validate_keystone_preflight"))
    candidates = "openstack-keystone|openstack-local\nhttpd|openstack-local\npython3-mod_wsgi|openstack-local\npython3-keystone|openstack-local"
    transaction = "Install 4 Packages\nOperation aborted."

    def validate(candidate_text: str, transaction_text: str) -> subprocess.CompletedProcess[str]:
        return run_git_bash(
                f"""
                set -Eeuo pipefail
                {definitions}
                validate_keystone_preflight {shlex.quote(candidate_text)} {shlex.quote(transaction_text)}
                """
            )

    assert validate(candidates, transaction).returncode == 0
    assert validate(candidates.replace("python3-keystone|openstack-local", "python3-keystone|external"), transaction).returncode != 0
    assert validate(candidates, transaction + "\nRemoving: old-package").returncode != 0
    assert validate(candidates.replace("python3-mod_wsgi|openstack-local\n", ""), transaction).returncode != 0


def test_manual_keystone_database_and_configuration_are_secret_safe() -> None:
    text = manual_shell_text("03-keystone.md")
    schema_body = shell_function_body(text, "stage_schema")
    assert schema_body is not None
    assert "alembic_version" in schema_body
    assert "migrate_version" not in schema_body
    python_bodies = [body for _opener, _delimiter, body in shell_sections(text)[1] if "CREATE DATABASE IF NOT EXISTS keystone" in body]
    assert len(python_bodies) == 1
    database_source = python_bodies[0]
    database_tree = ast.parse(database_source)
    constants = {node.value for node in ast.walk(database_tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert {"localhost", "127.0.0.1", "%"} <= constants
    assert any("GRANT ALL PRIVILEGES ON keystone.* TO %s@%s" in value for value in constants)
    assert any("CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s" in value for value in constants)
    assert not any("@'%'" in value or "@'%%'" in value for value in constants)
    assert not any(isinstance(node, (ast.JoinedStr, ast.BinOp)) for node in ast.walk(database_tree) if isinstance(node, ast.JoinedStr) or (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod)))

    config_bodies = [body for _opener, _delimiter, body in shell_sections(text)[1] if "RawConfigParser" in body]
    assert len(config_bodies) == 1
    config_tree = ast.parse(config_bodies[0])
    attributes = {node.attr for node in ast.walk(config_tree) if isinstance(node, ast.Attribute)}
    names = {node.id for node in ast.walk(config_tree) if isinstance(node, ast.Name)}
    assert "quote" in names and "replace" in attributes
    assert "OPENSTACK_DEPLOY_PASSWORD" in config_bodies[0]
    assert "provider" in config_bodies[0] and "fernet" in config_bodies[0]

    snapshot = (MANUAL_INSTALL_DIR / "config-snapshots" / "controller-keystone.conf.sanitized").read_text(encoding="utf-8")
    assert "mysql+pymysql://keystone:<DB_PASSWORD>@127.0.0.1/keystone" in snapshot
    assert "provider = fernet" in snapshot


def test_manual_keystone_percent_grant_host_is_passed_as_a_database_parameter(monkeypatch: pytest.MonkeyPatch) -> None:
    text = manual_shell_text("03-keystone.md")
    database_source = next(
        body for _opener, _delimiter, body in shell_sections(text)[1]
        if "CREATE DATABASE IF NOT EXISTS keystone" in body
    )
    calls: list[tuple[str, tuple[str, ...] | None]] = []

    class FakeCursor:
        def __enter__(self) -> "FakeCursor":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, sql: str, args: tuple[str, ...] | None = None) -> None:
            calls.append((sql, args))

        def fetchone(self) -> tuple[int]:
            return (1,)

    class FakeConnection:
        def cursor(self) -> FakeCursor:
            return FakeCursor()

        def close(self) -> None:
            return None

    fake_pymysql = types.SimpleNamespace(connect=lambda **_kwargs: FakeConnection())
    monkeypatch.setitem(sys.modules, "pymysql", fake_pymysql)
    monkeypatch.setenv("OPENSTACK_DEPLOY_PASSWORD", "memory-only-test-value")
    monkeypatch.setenv("MYSQL_SOCKET", "/memory-only/mysql.sock")
    exec(compile(database_source, "keystone-parameterized-grants", "exec"), {})

    percent_calls = [args for sql, args in calls if "%s@%s" in sql and args is not None and "%" in args]
    assert percent_calls
    assert all("memory-only-test-value" not in sql for sql, _args in calls)


def test_manual_keystone_key_classifier_rejects_partial_or_unsafe_repositories() -> None:
    text = manual_shell_text("03-keystone.md")
    definitions = manual_function_definitions(text, ("die", "classify_key_repository"))

    def classify(scenario: str) -> subprocess.CompletedProcess[str]:
        return run_git_bash(
            f"""
            set -Eeuo pipefail
            {definitions}
            root=$(mktemp -d)
            trap 'chmod -R u+rwX "$root"; rm -rf "$root"' EXIT
            KEYSTONE_KEY_OWNER=$(/usr/bin/stat -c '%U:%G' "$root")
            stat() {{
              local path="${{@: -1}}" mode
              if [[ -d $path ]]; then mode=700
              elif [[ {scenario!r} == badmode && $path == */0 ]]; then mode=644
              else mode=600
              fi
              printf '%s %s\n' "$KEYSTONE_KEY_OWNER" "$mode"
            }}
            case {scenario!r} in
              absent) rmdir "$root" ;;
              valid) chmod 700 "$root"; printf x >"$root/0"; printf y >"$root/1"; chmod 600 "$root/0" "$root/1" ;;
              partial) chmod 700 "$root"; printf x >"$root/0"; chmod 600 "$root/0" ;;
              extra) chmod 700 "$root"; printf x >"$root/0"; printf y >"$root/1"; printf z >"$root/2"; chmod 600 "$root/"* ;;
              badmode) chmod 700 "$root"; printf x >"$root/0"; printf y >"$root/1"; chmod 644 "$root/0"; chmod 600 "$root/1" ;;
              zerobyte) chmod 700 "$root"; : >"$root/0"; printf y >"$root/1"; chmod 600 "$root/0" "$root/1" ;;
            esac
            classify_key_repository "$root"
            """
        )

    assert classify("absent").stdout.strip() == "ABSENT"
    assert classify("valid").stdout.strip() == "VALID"
    for scenario in ("partial", "extra", "badmode", "zerobyte"):
        assert classify(scenario).returncode != 0


@pytest.mark.parametrize(
    ("state", "marker", "expected", "success"),
    (
        ("ABSENT", "absent", "BOOTSTRAP", True),
        ("FULL", "present", "SKIP", True),
        ("FULL", "absent", "RECOVER_MARKER", True),
        ("ABSENT", "present", "", False),
        ("PARTIAL", "absent", "", False),
        ("PARTIAL", "present", "", False),
    ),
)
def test_manual_keystone_bootstrap_decision_requires_database_evidence(
    state: str, marker: str, expected: str, success: bool
) -> None:
    text = manual_shell_text("03-keystone.md")
    definitions = manual_function_definitions(text, ("die", "bootstrap_action"))
    completed = run_git_bash(
        f"""
        set -Eeuo pipefail
        {definitions}
        bootstrap_action {state!r} {marker!r}
        """
    )
    assert (completed.returncode == 0) is success
    if success:
        assert completed.stdout.strip() == expected

    bootstrap_probe = next(body for _opener, _delimiter, body in shell_sections(text)[1] if "BOOTSTRAP_STATE" in body)
    assert "assignment" in bootstrap_probe
    assert "identity" in bootstrap_probe
    assert "RegionOne" in bootstrap_probe
    assert "<<null>>" in bootstrap_probe, "Antelope's null-domain role sentinel must be recognized"
    assert {"admin", "internal", "public"} <= set(re.findall(r"['\"](admin|internal|public)['\"]", bootstrap_probe))


def test_manual_keystone_endpoint_validator_and_service_project_are_exact() -> None:
    text = manual_shell_text("03-keystone.md")
    assert 'endpoint list --service "$identity_service_id" -f json' in text
    service_validator = next(body for _opener, _delimiter, body in shell_sections(text)[1] if "IDENTITY_SERVICE_ROWS" in body)
    good_service = [{"ID": "service-id", "Name": "keystone", "Type": "identity"}]
    service_ok = subprocess.run(
        ["python", "-c", service_validator], input=json.dumps(good_service), text=True,
        capture_output=True, check=False,
    )
    service_duplicate = subprocess.run(
        ["python", "-c", service_validator], input=json.dumps(good_service * 2), text=True,
        capture_output=True, check=False,
    )
    assert service_ok.returncode == 0 and service_ok.stdout.strip() == "service-id"
    assert service_duplicate.returncode != 0
    validator = next(body for _opener, _delimiter, body in shell_sections(text)[1] if "EXPECTED_INTERFACES" in body)
    tree = ast.parse(validator)
    compile(tree, "keystone-endpoint-validator", "exec")
    good = [
        {"Region": "RegionOne", "Service Type": "identity", "Interface": interface, "URL": "http://controller:5000/v3/"}
        for interface in ("admin", "internal", "public")
    ]

    def run(rows: list[dict[str, str]]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python", "-c", validator],
            input=json.dumps(rows),
            text=True,
            capture_output=True,
            check=False,
        )

    assert run(good).returncode == 0
    assert run(good[:2]).returncode != 0
    wrong_region = [dict(row, Region="RegionTwo") for row in good]
    assert run(wrong_region).returncode != 0
    duplicate = good[:2] + [dict(good[1])]
    assert run(duplicate).returncode != 0

    ensure_project = shell_function_body(text, "ensure_service_project")
    assert ensure_project is not None
    assert "project list" in ensure_project and "project create" in ensure_project and "project show" in ensure_project
    assert "--name" not in ensure_project, "this OpenStack CLI does not support project list --name"


def test_manual_keystone_final_audit_keeps_later_packages_and_compute_disks_fail_closed() -> None:
    text = manual_shell_text("03-keystone.md")
    package_body = shell_function_body(text, "assert_packages_absent")
    disk_body = shell_function_body(text, "assert_compute_data_disk")
    assert package_body is not None and disk_body is not None
    assert "openstack-glance" in text and "python3-horizon" in text
    assert "findmnt -nro SOURCE /" in disk_body
    assert "lsblk -s -nrpo NAME" in disk_body
    assert "wipefs --no-act" in disk_body and "--noheadings" in disk_body
    assert "blkid -p" in disk_body
    assert "|| true" not in disk_body
    assert "/dev/sdb" in text and "/dev/sdc" in text and "53687091200" in text


def test_manual_keystone_snapshots_and_openrc_contain_no_embedded_credentials() -> None:
    snapshots = {
        "controller-keystone.conf.sanitized",
        "controller-apache-keystone.conf",
        "controller-admin-openrc.sanitized",
    }
    snapshot_dir = MANUAL_INSTALL_DIR / "config-snapshots"
    assert snapshots <= {path.name for path in snapshot_dir.iterdir()}
    combined = "\n".join((snapshot_dir / name).read_text(encoding="utf-8") for name in snapshots)
    assert "<DB_PASSWORD>" in combined
    assert "OPENSTACK_DEPLOY_PASSWORD" in combined
    assert not re.search(
        r"(?im)^\s*(?:export\s+)?(?:OS_)?(?:TOKEN|PASSWORD)\s*=\s*(?!<|\$|\{|$)[^\s#]+",
        combined,
    )


def extract_python_definitions(source: str, names: set[str]) -> dict[str, object]:
    tree = ast.parse(source)
    selected = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
    ]
    assert {node.name for node in selected} == names
    namespace: dict[str, object] = {"json": json}
    exec(compile(ast.Module(body=selected, type_ignores=[]), "extracted-task5b-python", "exec"), namespace)
    return namespace


def test_manual_keystone_bootstrap_full_classifier_binds_exact_relations() -> None:
    text = manual_shell_text("03-keystone.md")
    source = next(
        body for _opener, _delimiter, body in shell_sections(text)[1]
        if "def classify_bootstrap_evidence" in body
    )
    classifier = extract_python_definitions(source, {"classify_bootstrap_evidence"})[
        "classify_bootstrap_evidence"
    ]
    evidence = {
        "projects": [{"id": "project-id", "name": "admin", "domain_id": "default", "enabled": 1, "is_domain": 0}],
        "users": [{"id": "user-id", "name": "admin", "domain_id": "default", "enabled": 1}],
        "roles": [{"id": "role-id", "name": "admin", "domain_id": "<<null>>"}],
        "assignments": [{"type": "UserProject", "actor_id": "user-id", "target_id": "project-id", "role_id": "role-id", "inherited": 0}],
        "services": [{"id": "service-id", "type": "identity", "enabled": 1, "extra": '{"name": "keystone"}'}],
        "regions": [{"id": "RegionOne"}],
        "endpoints": [
            {"service_id": "service-id", "interface": interface, "region_id": "RegionOne", "url": "http://controller:5000/v3/", "enabled": 1}
            for interface in ("admin", "internal", "public")
        ],
    }
    assert classifier(evidence) == "FULL"  # type: ignore[operator]
    assert classifier({key: [] for key in evidence}) == "ABSENT"  # type: ignore[operator]

    mutations: list[dict[str, list[dict[str, object]]]] = []
    extra_identity = {key: [dict(row) for row in rows] for key, rows in evidence.items()}
    extra_identity["services"].append(
        {"id": "disabled-service", "type": "identity", "enabled": 0, "extra": '{"name": "keystone"}'}
    )
    mutations.append(extra_identity)
    wrong_name = {key: [dict(row) for row in rows] for key, rows in evidence.items()}
    wrong_name["services"][0]["extra"] = '{"name": "not-keystone"}'
    mutations.append(wrong_name)
    wrong_domain = {key: [dict(row) for row in rows] for key, rows in evidence.items()}
    wrong_domain["roles"][0]["domain_id"] = "default"
    mutations.append(wrong_domain)
    duplicate_endpoint = {key: [dict(row) for row in rows] for key, rows in evidence.items()}
    duplicate_endpoint["endpoints"].append(dict(duplicate_endpoint["endpoints"][0]))
    mutations.append(duplicate_endpoint)
    wrong_service_binding = {key: [dict(row) for row in rows] for key, rows in evidence.items()}
    wrong_service_binding["endpoints"][0]["service_id"] = "other-service"
    mutations.append(wrong_service_binding)
    wrong_assignment = {key: [dict(row) for row in rows] for key, rows in evidence.items()}
    wrong_assignment["assignments"][0]["role_id"] = "domain-role-id"
    mutations.append(wrong_assignment)
    for mutated in mutations:
        assert classifier(mutated) == "PARTIAL"  # type: ignore[operator]


def test_manual_keystone_cli_validates_admin_objects_and_exact_assignment() -> None:
    text = manual_shell_text("03-keystone.md")
    active = "\n".join(active_lines(text))
    for command in (
        "openstack project show admin -f json",
        "openstack user show admin -f json",
        "openstack role show admin -f json",
        "openstack role assignment list",
    ):
        assert command in active
    source = next(
        body for _opener, _delimiter, body in shell_sections(text)[1]
        if "def validate_admin_cli_evidence" in body
    )
    validator = extract_python_definitions(source, {"validate_admin_cli_evidence"})[
        "validate_admin_cli_evidence"
    ]
    evidence = {
        "project": {"id": "project-id", "name": "admin", "domain_id": "default", "enabled": True, "is_domain": False},
        "user": {"id": "user-id", "name": "admin", "domain_id": "default", "enabled": True},
        "role": {"id": "role-id", "name": "admin", "domain_id": None},
        "assignments": [{"Role": "role-id", "User": "user-id", "Project": "project-id", "Group": "", "Domain": "", "System": "", "Inherited": False}],
    }
    assert validator(evidence) == ("project-id", "user-id", "role-id")  # type: ignore[operator]
    wrong_role = {key: (dict(value) if isinstance(value, dict) else [dict(row) for row in value]) for key, value in evidence.items()}
    wrong_role["role"]["domain_id"] = "default"  # type: ignore[index]
    with pytest.raises(ValueError):
        validator(wrong_role)  # type: ignore[operator]
    wrong_assignment = {key: (dict(value) if isinstance(value, dict) else [dict(row) for row in value]) for key, value in evidence.items()}
    wrong_assignment["assignments"][0]["Role"] = "other-role"  # type: ignore[index]
    with pytest.raises(ValueError):
        validator(wrong_assignment)  # type: ignore[operator]


@pytest.mark.parametrize(
    ("scenario", "expected_success"),
    (
        ("missing", False),
        ("symlink", False),
        ("wrong_owner", False),
        ("wrong_mode", False),
        ("wrong_nlink", False),
        ("multiline", False),
        ("malformed", False),
        ("empty", False),
        ("success", True),
    ),
)
def test_manual_keystone_runtime_secret_loader_is_uniform_and_fail_closed(
    scenario: str, expected_success: bool
) -> None:
    text = manual_shell_text("03-keystone.md")
    definitions = manual_function_definitions(text, ("die", "load_runtime_secret"))
    loader_body = shell_function_body(text, "load_runtime_secret")
    assert loader_body is not None
    assert loader_body.index("stat -c") < loader_body.index("mapfile")
    assert "^OPENSTACK_DEPLOY_PASSWORD=(.+)$" in loader_body
    assert manual_markdown("03-keystone.md").count("load_runtime_secret ") >= 4
    snapshot_text = (
        MANUAL_INSTALL_DIR / "config-snapshots" / "controller-admin-openrc.sanitized"
    ).read_text(encoding="utf-8")
    assert shell_function_body(snapshot_text, "_openstack_load_runtime_secret") == loader_body
    markdown = manual_markdown("03-keystone.md")
    assert markdown.index("load_runtime_secret DB_PASS") < markdown.index(
        "CREATE DATABASE IF NOT EXISTS keystone"
    )
    assert markdown.index("load_runtime_secret CONFIG_PASS") < markdown.index(
        'parser = configparser.RawConfigParser'
    )
    assert markdown.index("load_runtime_secret ADMIN_PASS") < markdown.index(
        "keystone-manage bootstrap"
    )
    completed = run_git_bash(
        f"""
        set -Eeuo pipefail
        {definitions}
        root=$(mktemp -d)
        trap 'chmod -R u+rwX "$root"; rm -rf "$root"' EXIT
        path="$root/secret"
        case {scenario!r} in
          missing) : ;;
          symlink) printf '%s\n' 'OPENSTACK_DEPLOY_PASSWORD=memory-only' >"$root/target"; ln -s "$root/target" "$path" ;;
          multiline) printf '%s\n%s\n' 'OPENSTACK_DEPLOY_PASSWORD=memory-only' extra >"$path" ;;
          malformed) printf '%s\n' 'WRONG_KEY=memory-only' >"$path" ;;
          empty) printf '%s\n' 'OPENSTACK_DEPLOY_PASSWORD=' >"$path" ;;
          *) printf '%s\n' 'OPENSTACK_DEPLOY_PASSWORD=memory-only' >"$path" ;;
        esac
        stat() {{
          case {scenario!r} in
            wrong_owner) printf '%s\n' 'nobody:nobody 600 1' ;;
            wrong_mode) printf '%s\n' 'root:root 644 1' ;;
            wrong_nlink) printf '%s\n' 'root:root 600 2' ;;
            *) printf '%s\n' 'root:root 600 1' ;;
          esac
        }}
        readlink() {{
          [[ {scenario!r} == symlink ]] && return 0
          command readlink "$@"
        }}
        value=UNCHANGED
        set +e
        load_runtime_secret value "$path"
        rc=$?
        set -e
        if [[ $rc -eq 0 ]]; then
          [[ "$value" == memory-only ]] || exit 91
          printf '%s\n' SUCCESS
        else
          [[ "$value" == UNCHANGED ]] || exit 92
          printf '%s\n' FAILURE
        fi
        """
    )
    assert (completed.returncode == 0) is True, completed.stderr
    assert (completed.stdout.strip() == "SUCCESS") is expected_success


def test_manual_keystone_dual_node_starting_gate_precedes_mutation_and_short_circuits() -> None:
    markdown = manual_markdown("03-keystone.md")
    gate_call = markdown.index("def run_dual_node_starting_gate(")
    assert gate_call < markdown.index("dnf -y --setopt=install_weak_deps=False")
    assert gate_call < markdown.index("CREATE DATABASE IF NOT EXISTS keystone")
    source = next(
        block for block in markdown_fenced_blocks("03-keystone.md", "python")
        if "CONTROLLER_GATE" in block and "COMPUTE_GATE" in block
    )
    assert all(token in source for token in (
        "192.168.234.151/24", "192.168.234.150/24", "ens34", "chronyd",
        "openstack-local", "information_schema.SCHEMATA", "/etc/keystone/keystone.conf",
        "/root/.keystone-bootstrap-complete", "sport = :5000", "/dev/sdb", "/dev/sdc",
        "lsblk -s -nrpo NAME", "blkid -p", "wipefs --no-act",
    ))
    tree = ast.parse(source)
    selected = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "run_dual_node_starting_gate"
    ]
    namespace: dict[str, object] = {
        "os": os,
        "Path": Path,
        "stat": __import__("stat"),
        "uuid": __import__("uuid"),
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), "dual-node-gate", "exec"), namespace)
    calls: list[str] = []

    class FakeClient:
        def __init__(self, name: str) -> None:
            self.name = name

        def close(self) -> None:
            calls.append(f"close:{self.name}")

    def connector(name: str, _password: str) -> FakeClient:
        calls.append(f"connect:{name}")
        return FakeClient(name)

    def failing_runner(client: FakeClient, _script: str) -> None:
        calls.append(f"run:{client.name}")
        if client.name == "controller":
            raise RuntimeError("controller gate failed")

    with pytest.raises(RuntimeError, match="controller gate failed"):
        namespace["run_dual_node_starting_gate"](
            "memory-only", connector=connector, runner=failing_runner,
            controller_gate="controller-script", compute_gate="compute-script",
        )
    assert calls == ["connect:controller", "run:controller", "close:controller"]

    calls.clear()

    def successful_runner(client: FakeClient, _script: str) -> None:
        calls.append(f"run:{client.name}")

    namespace["run_dual_node_starting_gate"](
        "memory-only", connector=connector, runner=successful_runner,
        controller_gate="controller-script", compute_gate="compute-script",
    )
    assert calls == [
        "connect:controller", "run:controller", "close:controller",
        "connect:compute", "run:compute", "close:compute",
    ]

    calls.clear()

    def compute_failing_runner(client: FakeClient, _script: str) -> None:
        calls.append(f"run:{client.name}")
        if client.name == "compute":
            raise RuntimeError("compute gate failed")

    with pytest.raises(RuntimeError, match="compute gate failed"):
        namespace["run_dual_node_starting_gate"](
            "memory-only", connector=connector, runner=compute_failing_runner,
            controller_gate="controller-script", compute_gate="compute-script",
        )
    assert calls == [
        "connect:controller", "run:controller", "close:controller",
        "connect:compute", "run:compute", "close:compute",
    ]


@pytest.mark.parametrize(
    ("scenario", "expected_success", "expected_creates"),
    (("zero", True, 1), ("one", True, 0), ("duplicate", False, 0), ("query_failure", False, 0)),
)
def test_manual_keystone_service_project_executes_production_branches(
    scenario: str, expected_success: bool, expected_creates: int
) -> None:
    text = manual_shell_text("03-keystone.md")
    definitions = manual_function_definitions(text, ("die", "service_project_ids", "ensure_service_project"))
    completed = run_git_bash(
        f"""
        set -Eeuo pipefail
        {definitions}
        state=$(mktemp)
        trace=$(mktemp)
        trap 'rm -f "$state" "$trace"' EXIT
        printf '%s\n' {scenario!r} >"$state"
        python3() {{ command python "$@"; }}
        openstack() {{
          if [[ "$1 $2" == 'project list' ]]; then
            [[ $(<"$state") != query_failure ]] || return 7
            case $(<"$state") in
              zero) printf '%s\n' '[]' ;;
              one) printf '%s\n' '[{{"ID":"service-id","Name":"service"}}]' ;;
              duplicate) printf '%s\n' '[{{"ID":"one","Name":"service"}},{{"ID":"two","Name":"service"}}]' ;;
            esac
          elif [[ "$1 $2" == 'project create' ]]; then
            printf '%s\n' create >>"$trace"
            printf '%s\n' one >"$state"
          elif [[ "$1 $2" == 'project show' ]]; then
            local index column=''
            for ((index=1; index<=$#; index++)); do
              if [[ "${{!index}}" == -c ]]; then index=$((index+1)); column=${{!index}}; fi
            done
            case "$column" in
              id) printf '%s\n' service-id ;;
              name) printf '%s\n' service ;;
              domain_id) printf '%s\n' default ;;
              enabled) printf '%s\n' True ;;
              *) return 9 ;;
            esac
          else
            return 10
          fi
        }}
        set +e
        ensure_service_project
        rc=$?
        set -e
        printf 'RC=%s CREATES=%s\n' "$rc" "$(wc -l <"$trace")"
        """
    )
    assert completed.returncode == 0, completed.stderr
    assert ("RC=0" in completed.stdout) is expected_success
    assert f"CREATES={expected_creates}" in completed.stdout


def test_manual_keystone_admin_openrc_installer_is_exclusive_atomic_and_cleanup_exact(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    text = manual_shell_text("03-keystone.md")
    source = next(
        body for _opener, _delimiter, body in shell_sections(text)[1]
        if "ADMIN_OPENRC_CONTENT" in body and "def install_admin_openrc" in body
    )
    tree = ast.parse(source)
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert {"O_EXCL", "O_NOFOLLOW", "fchmod", "fchown", "fsync", "replace", "lstat"} <= attributes
    selected = [
        node for node in tree.body
        if (isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "ADMIN_OPENRC_CONTENT" for target in node.targets))
        or (isinstance(node, ast.FunctionDef) and node.name == "install_admin_openrc")
    ]
    namespace: dict[str, object] = {
        "os": os,
        "Path": Path,
        "stat": __import__("stat"),
        "uuid": __import__("uuid"),
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), "admin-openrc-installer", "exec"), namespace)

    class OpsProxy:
        def __init__(self, fail_replace: bool) -> None:
            self.fail_replace = fail_replace

        def __getattr__(self, name: str) -> object:
            if name in {"fchown", "fchmod", "chown"}:
                return lambda *_args: None
            if name == "replace" and self.fail_replace:
                return lambda *_args: (_ for _ in ()).throw(OSError("replace failure"))
            return getattr(os, name)

    target = tmp_path / "admin-openrc"
    target.write_text("preexisting\n", encoding="utf-8")
    with pytest.raises(OSError, match="replace failure"):
        namespace["install_admin_openrc"](
            target=target, owner_uid=0, owner_gid=0, ops=OpsProxy(True), nonce="review-failure"
        )
    assert target.read_text(encoding="utf-8") == "preexisting\n"
    assert list(tmp_path.glob(".admin-openrc.task5b.*")) == []


def test_manual_glance_session_preserves_required_order_and_stops_on_failure() -> None:
    markdown = manual_markdown("04-glance.md")
    markers = (
        "def run_after_both_gates",
        "validate_glance_preflight",
        "CREATE DATABASE IF NOT EXISTS glance",
        "def ensure_glance_identity_objects",
        "rpm -V openstack-glance openstack-glance-api",
        "glance-manage db_sync",
        "systemctl enable --now openstack-glance-api",
        "def run_image_lifecycle",
        "## 依赖顺序驱动器与跨切片收口",
    )
    positions = [markdown.index(marker) for marker in markers]
    assert positions == sorted(positions)
    assert "stage_starting_state()" not in markdown
    assert "run_glance_sequence" not in markdown


def test_manual_glance_dual_node_gate_is_strict_and_short_circuits() -> None:
    markdown = manual_markdown("04-glance.md")
    assert all(token in markdown for token in (
        "192.168.234.151", "192.168.234.150", "known_hosts.controller",
        "known_hosts.compute", "paramiko.RejectPolicy()", "ens34", "openstack-local",
        "/dev/sdb", "/dev/sdc", "lsblk -s -nrpo NAME", "wipefs --no-act", "blkid -p",
    ))
    namespace = _glance_python_function_namespace("run_dual_node_starting_gate")
    calls: list[str] = []

    class FakeClient:
        def __init__(self, name: str) -> None:
            self.name = name

        def close(self) -> None:
            calls.append(f"close:{self.name}")

    def connector(name: str, _password: str) -> FakeClient:
        calls.append(f"connect:{name}")
        return FakeClient(name)

    def fail_controller(client: FakeClient, _script: str) -> None:
        calls.append(f"run:{client.name}")
        raise RuntimeError("controller gate failed")

    with pytest.raises(RuntimeError, match="controller gate failed"):
        namespace["run_dual_node_starting_gate"](
            "memory-only", connector=connector, runner=fail_controller,
            controller_gate="controller", compute_gate="compute",
        )
    assert calls == ["connect:controller", "run:controller", "close:controller"]


def test_manual_glance_package_preflight_executes_repo_only_failure_branches(tmp_path: Path) -> None:
    text = manual_shell_text("04-glance.md")
    active = "\n".join(active_lines(text))
    assert "--disablerepo='*'" in active and "--enablerepo='openstack-local'" in active
    assert "--setopt=install_weak_deps=False" in active
    assert not any(flag in active for flag in ("--allowerasing", "--nodeps", "--skip-broken"))
    definitions = manual_function_definitions(text, ("validate_glance_preflight",))

    def validate(candidates: str, transaction: str) -> int:
        candidate_file = tmp_path / "candidates.txt"
        transaction_file = tmp_path / "transaction.txt"
        candidate_file.write_text(candidates, encoding="utf-8")
        transaction_file.write_text(transaction, encoding="utf-8")
        completed = run_git_bash(
            f"""
            set -Eeuo pipefail
            {definitions}
            validate_glance_preflight {shlex.quote(str(candidate_file))} {shlex.quote(str(transaction_file))}
            """
        )
        return completed.returncode

    good_candidates = "openstack-glance|openstack-local\npython3-glance|openstack-local\n"
    good_transaction = "openstack-glance noarch 26 local openstack-local 1 M\nInstall 1 Package\nOperation aborted.\n"
    assert validate(good_candidates, good_transaction) == 0
    assert validate(good_candidates.replace("python3-glance|openstack-local", "python3-glance|external"), good_transaction) != 0
    assert validate(good_candidates, good_transaction.replace("Install 1 Package", "Install 2 Packages")) != 0
    assert validate(good_candidates, good_transaction + "Removing: unsafe\n") != 0


def test_manual_glance_database_grants_are_parameterized_and_secret_safe() -> None:
    text = manual_shell_text("04-glance.md")
    python_bodies = [
        body for _opener, _delimiter, body in shell_sections(text)[1]
        if "CREATE DATABASE IF NOT EXISTS glance" in body
    ]
    assert len(python_bodies) == 1
    tree = ast.parse(python_bodies[0])
    constants = {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert "CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s" in constants
    assert "ALTER USER %s@%s IDENTIFIED BY %s" in constants
    assert "GRANT ALL PRIVILEGES ON glance.* TO %s@%s" in constants
    assert '("glance", host, password)' in python_bodies[0]
    assert '("glance", host)' in python_bodies[0]
    assert "authentication_string" not in text


@pytest.mark.parametrize(
    ("record", "metadata", "expected"),
    (
        ("OPENSTACK_DEPLOY_PASSWORD=memory-only\n", "root:root 600 1", True),
        ("OPENSTACK_DEPLOY_PASSWORD=\n", "root:root 600 1", False),
        ("MALFORMED=memory-only\n", "root:root 600 1", False),
        ("OPENSTACK_DEPLOY_PASSWORD=one\nEXTRA=two\n", "root:root 600 1", False),
        ("OPENSTACK_DEPLOY_PASSWORD=memory-only\n", "root:root 644 1", False),
        ("OPENSTACK_DEPLOY_PASSWORD=memory-only\n", "root:root 600 2", False),
    ),
)
def test_manual_glance_runtime_secret_loader_executes_fail_closed_branches(
    tmp_path: Path, record: str, metadata: str, expected: bool
) -> None:
    text = manual_shell_text("04-glance.md")
    definition = shell_function_definition(text, "load_runtime_secret")
    secret = tmp_path / "runtime-secret"
    secret.write_text(record, encoding="utf-8", newline="\n")
    completed = run_git_bash(
        f"""
        set -Eeuo pipefail
        {definition}
        stat() {{ printf '%s\n' {shlex.quote(metadata)}; }}
        set +e
        load_runtime_secret loaded {shlex.quote(str(secret))}
        rc=$?
        set -e
        [[ $rc -eq 0 ]] && [[ $loaded == memory-only ]]
        """
    )
    assert (completed.returncode == 0) is expected


def test_manual_glance_identity_classifier_handles_zero_one_duplicate_error_and_mutations() -> None:
    namespace = _glance_python_function_namespace("validate_glance_identity_evidence")
    evidence = {
        "user": {"id": "user", "name": "glance", "domain_id": "default", "enabled": True},
        "service": {"id": "service", "name": "glance", "type": "image", "enabled": True},
        "admin_role_id": "admin-role",
        "service_project_id": "service-project",
        "assignments": [{
            "role": "admin-role", "user": "user", "project": "service-project",
            "group": "", "domain": "", "system": "", "inherited": False,
        }],
        "endpoints": [
            {
                "interface": interface, "region": "RegionOne", "service_id": "service",
                "url": "http://controller:9292", "enabled": True,
            }
            for interface in ("public", "internal", "admin")
        ],
    }
    namespace["validate_glance_identity_evidence"](evidence)
    for mutation in ("disabled-user", "wrong-role", "duplicate-endpoint", "wrong-url"):
        broken = json.loads(json.dumps(evidence))
        if mutation == "disabled-user":
            broken["user"]["enabled"] = False
        elif mutation == "wrong-role":
            broken["assignments"][0]["role"] = "member"
        elif mutation == "duplicate-endpoint":
            broken["endpoints"].append(dict(broken["endpoints"][0]))
        else:
            broken["endpoints"][0]["url"] = "http://wrong:9292"
        with pytest.raises(ValueError):
            namespace["validate_glance_identity_evidence"](broken)


def test_manual_glance_atomic_config_and_sanitized_snapshot_are_exact(tmp_path: Path) -> None:
    source = next(
        block for block in markdown_fenced_blocks("04-glance.md", "python")
        if "def write_glance_config" in block
    )
    tree = ast.parse(source)
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert {"O_EXCL", "fchmod", "fchown", "fsync", "replace", "lstat"} <= attributes
    assert 'getattr(ops, "O_NOFOLLOW", 0)' in source
    namespace: dict[str, object] = {}
    exec(compile(source, "glance-config-writer", "exec"), namespace)

    class OpsProxy:
        def __getattr__(self, name: str) -> object:
            if name in {"fchown", "fchmod"}:
                return lambda *_args: None
            if name == "replace":
                return lambda *_args: (_ for _ in ()).throw(OSError("replace failure"))
            return getattr(os, name)

    target = tmp_path / "glance-api.conf"
    target.write_text("[DEFAULT]\n", encoding="utf-8")
    with pytest.raises(OSError, match="replace failure"):
        namespace["write_glance_config"](target, "memory-only", 0, ops=OpsProxy())
    assert target.read_text(encoding="utf-8") == "[DEFAULT]\n"
    assert list(tmp_path.glob(".glance-api.conf.task5c.*")) == []

    markdown = manual_markdown("04-glance.md")
    second_load = markdown.index('load_runtime_secret OPENSTACK_DEPLOY_PASSWORD || die "secret load before validation failed"')
    unset_function = markdown.index("unset -f load_runtime_secret", second_load)
    assert second_load < unset_function
    snapshot = (MANUAL_INSTALL_DIR / "config-snapshots" / "controller-glance-api.conf").read_text(encoding="utf-8")
    assert "<DB_PASSWORD>" in snapshot and "<SERVICE_PASSWORD>" in snapshot
    assert 'quote(runtime_password, safe="")' in snapshot
    assert "enabled_backends = file:file" in snapshot
    assert "filesystem_store_datadir = /var/lib/glance/images/" in snapshot


def test_manual_glance_schema_api_and_later_boundaries_are_fail_closed() -> None:
    text = manual_shell_text("04-glance.md")
    active = "\n".join(active_lines(text))
    assert "su -s /bin/sh -c 'glance-manage db_sync' glance" in active
    assert "COUNT(DISTINCT TABLE_NAME)" in active
    assert "alembic_version" in active and "image_locations" in active and "task_info" in active
    assert "systemctl enable --now openstack-glance-api" in active
    assert "sport = :9292" in active and "wc -l" in active
    assert "openstack token issue -f value -c expires >/dev/null" in active
    assert "openstack image list -f json" in active
    markdown = manual_markdown("04-glance.md")
    assert all(package in markdown for package in (
        "openstack-placement-api", "openstack-nova-common", "openstack-neutron-common",
        "openstack-cinder-common", "openstack-swift-common", "python3-horizon",
    ))
    assert markdown.index("glance-manage db_sync") < markdown.index("systemctl enable --now openstack-glance-api")


def test_manual_glance_image_lifecycle_exact_ownership_and_cleanup() -> None:
    namespace = _glance_python_function_namespace("classify_task_image")
    classify = namespace["classify_task_image"]
    assert classify([], "task", "owner", "artifact") == "ABSENT"
    good = {"id": "image-id", "name": "task", "properties": {"task_owner": "owner", "task_artifact": "artifact"}}
    assert classify([good], "task", "owner", "artifact") == "image-id"
    with pytest.raises(RuntimeError, match="ambiguous"):
        classify([good, dict(good, id="other")], "task", "owner", "artifact")
    wrong = json.loads(json.dumps(good))
    wrong["properties"]["task_owner"] = "someone-else"
    with pytest.raises(RuntimeError, match="not exactly task-owned"):
        classify([wrong], "task", "owner", "artifact")

    markdown = manual_markdown("04-glance.md")
    assert "task5c-synthetic-validation-v1" in markdown
    assert 'f"task_owner={TASK_OWNER}"' in markdown and 'f"task_artifact={TASK_ARTIFACT}"' in markdown
    assert '"--disk-format", "raw"' in markdown and '"--container-format", "bare"' in markdown
    assert "hashlib.sha256" in markdown and "downloaded task image digest/size mismatch" in markdown
    assert "_delete_verified_candidate(executor, candidate_id" in markdown
    assert "_cleanup_owned_workdir(workdir, identity, (payload, download))" in markdown


def _glance_python_function_namespace(required_name: str) -> dict[str, object]:
    candidates = markdown_fenced_blocks("04-glance.md", "python")
    candidates.extend(body for _opener, _delimiter, body in shell_sections(manual_shell_text("04-glance.md"))[1])
    source = next(block for block in candidates if f"def {required_name}" in block)
    tree = ast.parse(source)
    selected = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            aliases = [alias for alias in node.names if alias.name != "pymysql"]
            if aliases:
                selected.append(ast.copy_location(ast.Import(names=aliases), node))
        elif isinstance(node, (ast.ImportFrom, ast.Assign, ast.FunctionDef, ast.ClassDef)):
            selected.append(node)
    namespace: dict[str, object] = {}
    module = ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[]))
    exec(compile(module, f"glance-{required_name}", "exec"), namespace)
    return namespace


def test_manual_glance_production_dual_gate_blocks_all_mutation_on_either_node_failure() -> None:
    namespace = _glance_python_function_namespace("run_after_both_gates")
    run_guarded = namespace["run_after_both_gates"]
    for name in ("CONTROLLER_GATE", "COMPUTE_GATE"):
        with tempfile.NamedTemporaryFile("w", suffix=".sh", encoding="utf-8", newline="\n", delete=False) as stream:
            stream.write(namespace[name])
            gate_path = Path(stream.name)
        try:
            syntax = subprocess.run([str(GIT_BASH), "-n", str(gate_path)], text=True, capture_output=True, check=False)
            assert syntax.returncode == 0, syntax.stderr
        finally:
            gate_path.unlink(missing_ok=True)
    calls: list[str] = []

    class FakeClient:
        def __init__(self, name: str) -> None:
            self.name = name

        def close(self) -> None:
            calls.append(f"close:{self.name}")

    def connector(name: str, _password: str) -> FakeClient:
        calls.append(f"connect:{name}")
        return FakeClient(name)

    def mutation() -> None:
        calls.append("MUTATION")

    for failing in ("controller", "compute"):
        calls.clear()

        def runner(client: FakeClient, _script: str, failing: str = failing) -> None:
            assert _script == namespace[f"{client.name.upper()}_GATE"]
            calls.append(f"run:{client.name}")
            if client.name == failing:
                raise RuntimeError(f"{failing} failed")

        with pytest.raises(RuntimeError, match=f"{failing} failed"):
            run_guarded(
                "memory-only", mutation, connector=connector, runner=runner,
            )
        assert "MUTATION" not in calls
        if failing == "controller":
            assert calls == ["connect:controller", "run:controller", "close:controller"]
        else:
            assert calls == [
                "connect:controller", "run:controller", "close:controller",
                "connect:compute", "run:compute", "close:compute",
            ]

    calls.clear()
    run_guarded(
        "memory-only", mutation, connector=connector,
        runner=lambda client, script: (
            script == namespace[f"{client.name.upper()}_GATE"]
            and calls.append(f"run:{client.name}")
        ),
    )
    assert calls == [
        "connect:controller", "run:controller", "close:controller",
        "connect:compute", "run:compute", "close:compute", "MUTATION",
    ]


class _FakeGlanceIdentity:
    def __init__(self, scenario: str) -> None:
        self.scenario = scenario
        self.user = scenario in {
            "correct", "duplicate", "disabled_user", "wrong_id_user", "wrong_assignment",
            "disabled_service", "wrong_id_service", "partial_endpoint", "wrong_endpoint",
            "created_wrong_endpoint",
        }
        self.assignment = scenario in {
            "correct", "duplicate", "wrong_assignment", "disabled_service", "wrong_id_service",
            "partial_endpoint", "wrong_endpoint", "created_wrong_endpoint",
        }
        self.service = scenario in {
            "correct", "duplicate", "disabled_service", "wrong_id_service",
            "partial_endpoint", "wrong_endpoint", "created_wrong_endpoint",
        }
        self.endpoints = scenario in {"correct", "duplicate", "partial_endpoint", "wrong_endpoint"}
        if scenario == "partial_endpoint":
            self.endpoint_interfaces = ["public"]
        elif self.endpoints:
            self.endpoint_interfaces = ["public", "internal", "admin"]
        else:
            self.endpoint_interfaces = []
        self.mutations: list[tuple[str, ...]] = []

    @staticmethod
    def _endpoint(interface: str, suffix: str = "") -> dict[str, object]:
        return {
            "ID": f"endpoint-{interface}{suffix}", "Interface": interface,
            "Region": "RegionOne", "Service ID": "image-service",
            "Service Type": "image", "URL": "http://controller:9292",
        }

    def query(self, args: list[str]) -> object:
        key = tuple(args[:2])
        if self.scenario == "query_error" and key == ("user", "list"):
            raise RuntimeError("query failed")
        if key == ("project", "list"):
            return [{"ID": "service-project", "Name": "service"}]
        if key == ("project", "show"):
            return {
                "id": "service-project", "name": "service", "domain_id": "default",
                "enabled": True, "is_domain": False,
            }
        if key == ("role", "list"):
            return [{"ID": "admin-role", "Name": "admin", "Domain": ""}]
        if key == ("role", "show"):
            return {"id": "admin-role", "name": "admin", "domain_id": None}
        if key == ("user", "list"):
            rows = ([{"ID": "glance-user", "Name": "glance"}] if self.user else [])
            return rows + ([{"ID": "duplicate-user", "Name": "glance"}] if self.scenario == "duplicate" else [])
        if key == ("user", "show"):
            return {
                "id": "wrong-user-id" if self.scenario == "wrong_id_user" else "glance-user",
                "name": "glance", "domain_id": "default",
                "enabled": self.scenario != "disabled_user",
            }
        if key == ("role", "assignment"):
            rows = ([{
                "Role": "member-role" if self.scenario == "wrong_assignment" else "admin-role",
                "User": "glance-user", "Project": "service-project",
                "Group": "", "Domain": "", "System": "", "Inherited": False,
            }] if self.assignment else [])
            return rows + ([dict(rows[0])] if self.scenario == "duplicate" and rows else [])
        if key == ("service", "list"):
            rows = ([{"ID": "image-service", "Name": "glance", "Type": "image"}] if self.service else [])
            return rows + ([{"ID": "duplicate-service", "Name": "glance", "Type": "image"}] if self.scenario == "duplicate" else [])
        if key == ("service", "show"):
            return {
                "id": "wrong-service-id" if self.scenario == "wrong_id_service" else "image-service",
                "name": "glance", "type": "image",
                "enabled": self.scenario != "disabled_service",
            }
        if key == ("endpoint", "list"):
            rows = [self._endpoint(interface) for interface in self.endpoint_interfaces]
            return rows + ([self._endpoint("public", "-duplicate")] if self.scenario == "duplicate" else [])
        if key == ("endpoint", "show"):
            endpoint_id = args[2]
            interface = endpoint_id.removeprefix("endpoint-").split("-duplicate", 1)[0]
            return {
                "id": endpoint_id, "interface": interface, "region": "RegionOne",
                "service_id": "image-service",
                "url": "http://wrong:9292"
                if (
                    self.scenario == "wrong_endpoint" and interface == "public"
                    or self.scenario == "created_wrong_endpoint" and interface == "internal"
                )
                else "http://controller:9292",
                "enabled": True,
            }
        raise AssertionError(f"unexpected identity query: {args}")

    def mutate(self, args: list[str]) -> object:
        self.mutations.append(tuple(args))
        key = tuple(args[:2])
        if key == ("user", "create"):
            self.user = True
            return {"id": "glance-user"}
        if key == ("role", "add"):
            self.assignment = True
            return None
        if key == ("service", "create"):
            self.service = True
            return {"id": "image-service"}
        if key == ("endpoint", "create"):
            self.endpoint_interfaces.append(args[-2])
            return {"id": f"endpoint-{args[-2]}"}
        raise AssertionError(f"unexpected identity mutation: {args}")


@pytest.mark.parametrize(
    ("scenario", "success", "minimum_mutations"),
    (("zero", True, 6), ("correct", True, 0), ("duplicate", False, 0), ("query_error", False, 0)),
)
def test_manual_glance_production_identity_ensure_executes_all_state_branches(
    scenario: str, success: bool, minimum_mutations: int
) -> None:
    namespace = _glance_python_function_namespace("ensure_glance_identity_objects")
    fake = _FakeGlanceIdentity(scenario)
    if success:
        evidence = namespace["ensure_glance_identity_objects"](
            "memory-only", query=fake.query, mutate=fake.mutate
        )
        namespace["validate_glance_identity_evidence"](evidence)
        assert len(fake.mutations) >= minimum_mutations
        if scenario == "correct":
            assert fake.mutations == []
    else:
        with pytest.raises((RuntimeError, ValueError)):
            namespace["ensure_glance_identity_objects"](
                "memory-only", query=fake.query, mutate=fake.mutate
            )
        assert fake.mutations == []


@pytest.mark.parametrize(
    "scenario",
    (
        "disabled_user", "wrong_id_user", "wrong_assignment", "disabled_service",
        "wrong_id_service", "partial_endpoint", "wrong_endpoint",
    ),
)
def test_manual_glance_identity_stage_failure_blocks_all_downstream_mutations(scenario: str) -> None:
    namespace = _glance_python_function_namespace("ensure_glance_identity_objects")
    fake = _FakeGlanceIdentity(scenario)
    with pytest.raises((RuntimeError, ValueError)):
        namespace["ensure_glance_identity_objects"](
            "memory-only", query=fake.query, mutate=fake.mutate
        )
    assert fake.mutations == [], f"{scenario} reached a downstream mutation: {fake.mutations}"


def test_manual_glance_endpoint_create_requery_stops_before_later_interfaces() -> None:
    namespace = _glance_python_function_namespace("ensure_glance_identity_objects")
    fake = _FakeGlanceIdentity("created_wrong_endpoint")
    with pytest.raises(ValueError, match="endpoint stage exact-state mismatch"):
        namespace["ensure_glance_identity_objects"](
            "memory-only", query=fake.query, mutate=fake.mutate
        )
    endpoint_creates = [args for args in fake.mutations if args[:2] == ("endpoint", "create")]
    assert [args[-2] for args in endpoint_creates] == ["public", "internal"]
    assert all(args[-2] != "admin" for args in endpoint_creates)


def test_manual_placement_session_preserves_required_order() -> None:
    markdown = manual_markdown("05-placement.md")
    markers = (
        "def run_after_both_placement_gates",
        "validate_placement_preflight",
        "CREATE DATABASE IF NOT EXISTS placement",
        "def ensure_placement_identity_objects",
        "rpm -V openstack-placement-api",
        "placement-manage db sync",
        "upgrade=$(placement-status upgrade check)",
        "systemctl restart httpd",
        "openstack resource provider list",
        "## 跨切片收口审计",
    )
    positions = [markdown.index(marker) for marker in markers]
    assert positions == sorted(positions)


def test_manual_glance_production_version_validator_rejects_status_and_body_failures() -> None:
    namespace = _glance_python_function_namespace("validate_glance_version_response")
    validate = namespace["validate_glance_version_response"]
    good = {"versions": [{"id": "v2.16", "status": "CURRENT"}]}
    validate(200, good)
    validate(300, good)
    for status, payload in ((404, good), (500, good), (300, {"versions": []}), (200, {"versions": [{"id": "v1", "status": "SUPPORTED"}]})):
        with pytest.raises((RuntimeError, ValueError)):
            validate(status, payload)


def test_manual_glance_production_grant_validator_rejects_probe_host_and_scope_mutations() -> None:
    namespace = _glance_python_function_namespace("validate_glance_grant_evidence")
    validate = namespace["validate_glance_grant_evidence"]
    account = {
        "global": [{"privilege": "USAGE", "grantable": "NO"}],
        "schema": [
            {"schema": "glance", "privilege": privilege, "grantable": "NO"}
            for privilege in sorted(namespace["EXPECTED_SCHEMA_PRIVILEGES"])
        ],
        "table": [], "column": [], "routine": [],
    }
    good = {
        "probe_ok": True,
        "hosts": ["%", "127.0.0.1", "localhost"],
        "accounts": {host: json.loads(json.dumps(account)) for host in ("%", "127.0.0.1", "localhost")},
        "proxy": [], "roles": [],
    }
    validate(good)
    mutations = []
    extra_host = json.loads(json.dumps(good)); extra_host["hosts"].append("controller"); mutations.append(extra_host)
    extra_global = json.loads(json.dumps(good)); extra_global["accounts"]["%"]["global"].append({"privilege": "SUPER", "grantable": "NO"}); mutations.append(extra_global)
    extra_schema = json.loads(json.dumps(good)); extra_schema["accounts"]["localhost"]["schema"].append({"schema": "nova", "privilege": "SELECT", "grantable": "NO"}); mutations.append(extra_schema)
    extra_table = json.loads(json.dumps(good)); extra_table["accounts"]["127.0.0.1"]["table"].append({"schema": "glance", "table": "images", "privilege": "SELECT"}); mutations.append(extra_table)
    extra_routine = json.loads(json.dumps(good)); extra_routine["accounts"]["%"]["routine"].append({"schema": "nova", "routine": "unsafe", "privilege": "EXECUTE"}); mutations.append(extra_routine)
    extra_proxy = json.loads(json.dumps(good)); extra_proxy["proxy"].append(["%", "glance", "%", "root", "YES"]); mutations.append(extra_proxy)
    failed_probe = json.loads(json.dumps(good)); failed_probe["probe_ok"] = False; mutations.append(failed_probe)
    for mutation in mutations:
        with pytest.raises((RuntimeError, ValueError)):
            validate(mutation)


class _FakeImageLifecycle:
    def __init__(self, scenario: str, backend_root: Path) -> None:
        self.scenario = scenario
        self.backend_root = backend_root
        self.backend_root.mkdir()
        self.deleted_ids: list[str] = []
        self.images: dict[str, dict[str, object]] = {
            "foreign-image": {
                "id": "foreign-image", "name": "user-image", "status": "active",
                "visibility": "private", "disk_format": "raw", "container_format": "bare",
                "size": 4, "properties": {"task_owner": "someone-else"},
            }
        }
        if scenario == "foreign":
            self.images["foreign-image"]["name"] = "task5c-synthetic-validation-v1"
        elif scenario == "preexisting_exact":
            self.images["preexisting-task-image"] = {
                "id": "preexisting-task-image", "name": "task5c-synthetic-validation-v1",
                "status": "active", "visibility": "private", "disk_format": "raw",
                "container_format": "bare", "size": 4,
                "properties": {
                    "task_owner": "lab-task-5c", "task_artifact": "synthetic-validation-v1",
                },
            }
        elif scenario == "duplicate":
            for image_id in ("duplicate-one", "duplicate-two"):
                self.images[image_id] = {
                    "id": image_id, "name": "task5c-synthetic-validation-v1",
                    "properties": {
                        "task_owner": "lab-task-5c", "task_artifact": "synthetic-validation-v1",
                    },
                }

    def __call__(self, args: list[str], expect_json: bool = False) -> object:
        key = tuple(args[:2])
        if key == ("image", "list"):
            return [{"ID": image_id, "Name": row["name"]} for image_id, row in self.images.items()]
        if key == ("image", "show"):
            image_id = args[2]
            if image_id not in self.images:
                raise RuntimeError("show failed")
            return dict(self.images[image_id])
        if key == ("image", "create"):
            payload = Path(args[args.index("--file") + 1])
            data = payload.read_bytes()
            image_id = "created-task-image"
            self.images[image_id] = {
                "id": image_id, "name": "task5c-synthetic-validation-v1", "status": "active",
                "visibility": "private", "disk_format": "raw", "container_format": "bare",
                "size": len(data), "properties": {
                    "task_owner": "lab-task-5c", "task_artifact": "synthetic-validation-v1",
                },
            }
            (self.backend_root / image_id).write_bytes(data)
            return {"id": image_id}
        if key == ("image", "save"):
            if self.scenario == "mid_failure":
                raise RuntimeError("injected download failure")
            destination = Path(args[args.index("--file") + 1])
            image_id = args[-1]
            destination.write_bytes((self.backend_root / image_id).read_bytes())
            return None
        if key == ("image", "delete"):
            image_id = args[2]
            self.deleted_ids.append(image_id)
            self.images.pop(image_id)
            (self.backend_root / image_id).unlink()
            return None
        raise AssertionError(f"unexpected image command: {args}, expect_json={expect_json}")


@pytest.mark.parametrize(
    "scenario", ("foreign", "preexisting_exact", "duplicate", "mid_failure", "success")
)
def test_manual_glance_production_image_lifecycle_cleanup_is_exact(
    scenario: str, tmp_path: Path
) -> None:
    namespace = _glance_python_function_namespace("run_image_lifecycle")
    executor = _FakeImageLifecycle(scenario=scenario, backend_root=tmp_path / "backend")
    if scenario == "success":
        result = namespace["run_image_lifecycle"](
            executor=executor, work_root=tmp_path, backend_root=tmp_path / "backend"
        )
        assert result["status"] == "PASS"
    else:
        with pytest.raises((RuntimeError, ValueError)):
            namespace["run_image_lifecycle"](
                executor=executor, work_root=tmp_path, backend_root=tmp_path / "backend"
            )
    assert not list(tmp_path.glob(".task5c-image.*"))
    if scenario in {"foreign", "preexisting_exact", "duplicate"}:
        assert executor.deleted_ids == []
    elif scenario == "mid_failure":
        assert executor.deleted_ids == ["created-task-image"]
        assert "foreign-image" not in executor.deleted_ids
    else:
        assert executor.deleted_ids == ["created-task-image"]


def _placement_python_function_namespace(required_name: str) -> dict[str, object]:
    candidates = markdown_fenced_blocks("05-placement.md", "python")
    candidates.extend(body for _opener, _delimiter, body in shell_sections(manual_shell_text("05-placement.md"))[1])
    source = next(block for block in candidates if f"def {required_name}" in block)
    tree = ast.parse(source)
    selected = [
        node for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.FunctionDef, ast.ClassDef))
    ]
    namespace: dict[str, object] = {}
    exec(compile(ast.Module(body=selected, type_ignores=[]), f"placement-{required_name}", "exec"), namespace)
    return namespace


def test_manual_placement_dual_gate_blocks_mutation_until_both_nodes_pass() -> None:
    namespace = _placement_python_function_namespace("run_after_both_placement_gates")
    for name in ("CONTROLLER_GATE", "COMPUTE_GATE"):
        script = namespace[name]
        with tempfile.NamedTemporaryFile("w", suffix=".sh", encoding="utf-8", newline="\n", delete=False) as stream:
            stream.write(script); gate_path = Path(stream.name)
        try:
            completed = subprocess.run([str(GIT_BASH), "-n", str(gate_path)], text=True, capture_output=True, check=False)
            assert completed.returncode == 0, completed.stderr
        finally:
            gate_path.unlink(missing_ok=True)
    calls: list[str] = []

    class Client:
        def __init__(self, name: str) -> None: self.name = name
        def close(self) -> None: calls.append(f"close:{self.name}")

    def connector(name: str, _password: str) -> Client:
        calls.append(f"connect:{name}"); return Client(name)

    for failing in ("controller", "compute"):
        calls.clear()
        def runner(client: Client, script: str, failing: str = failing) -> None:
            assert script == namespace[f"{client.name.upper()}_GATE"]
            calls.append(f"run:{client.name}")
            if client.name == failing: raise RuntimeError(f"{failing} failed")
        with pytest.raises(RuntimeError, match=f"{failing} failed"):
            namespace["run_after_both_placement_gates"](
                "memory-only", lambda: calls.append("MUTATION"), connector=connector, runner=runner
            )
        assert "MUTATION" not in calls

    markdown = manual_markdown("05-placement.md")
    assert all(token in markdown for token in (
        "paramiko.RejectPolicy()", "known_hosts.controller", "known_hosts.compute",
        "ens34", "/dev/sdb", "/dev/sdc", "wipefs --no-act", "blkid -p",
    ))


def test_manual_placement_package_preflight_is_local_only_and_fail_closed(tmp_path: Path) -> None:
    text = manual_shell_text("05-placement.md")
    active = "\n".join(active_lines(text))
    assert "--disablerepo='*'" in active and "--enablerepo='openstack-local'" in active
    assert "--setopt=install_weak_deps=False" in active
    assert not any(flag in active for flag in ("--allowerasing", "--nodeps", "--skip-broken"))
    definition = shell_function_definition(text, "validate_placement_preflight")

    def run(candidates: str, transaction: str) -> int:
        candidate_path = tmp_path / "candidates"; transaction_path = tmp_path / "transaction"
        candidate_path.write_text(candidates, encoding="utf-8")
        transaction_path.write_text(transaction, encoding="utf-8")
        result = run_git_bash(
            f"set -Eeuo pipefail\n{definition}\nvalidate_placement_preflight "
            f"{shlex.quote(str(candidate_path))} {shlex.quote(str(transaction_path))}\n"
        )
        return result.returncode

    good_candidates = "openstack-placement-api|openstack-local\npython3-placement|openstack-local\n"
    good_transaction = "openstack-placement-api noarch 9 local openstack-local 1 M\nInstall 1 Package\nOperation aborted.\n"
    assert run(good_candidates, good_transaction) == 0
    assert run(good_candidates.replace("python3-placement|openstack-local", "python3-placement|external"), good_transaction) != 0
    assert run(good_candidates, good_transaction.replace("Install 1 Package", "Install 2 Packages")) != 0
    assert run(good_candidates, good_transaction + "Removing: unsafe\n") != 0


@pytest.mark.parametrize(
    ("record", "metadata", "expected"),
    (
        ("OPENSTACK_DEPLOY_PASSWORD=memory-only\n", "root:root 600 1", True),
        ("OPENSTACK_DEPLOY_PASSWORD=\n", "root:root 600 1", False),
        ("OTHER=memory-only\n", "root:root 600 1", False),
        ("OPENSTACK_DEPLOY_PASSWORD=one\nEXTRA=two\n", "root:root 600 1", False),
        ("OPENSTACK_DEPLOY_PASSWORD=memory-only\n", "root:root 644 1", False),
    ),
)
def test_manual_placement_secret_loader_executes_failure_branches(
    tmp_path: Path, record: str, metadata: str, expected: bool
) -> None:
    definition = shell_function_definition(manual_shell_text("05-placement.md"), "load_runtime_secret")
    secret = tmp_path / "secret"; secret.write_text(record, encoding="utf-8", newline="\n")
    completed = run_git_bash(
        f"set -Eeuo pipefail\n{definition}\nstat(){{ printf '%s\\n' {shlex.quote(metadata)}; }}\n"
        f"set +e; load_runtime_secret loaded {shlex.quote(str(secret))}; rc=$?; set -e\n"
        "[[ $rc -eq 0 && $loaded == memory-only ]]\n"
    )
    assert (completed.returncode == 0) is expected


def test_manual_placement_database_uses_parameters_and_exact_scope_validator() -> None:
    text = manual_shell_text("05-placement.md")
    python_body = next(body for _opener, _delimiter, body in shell_sections(text)[1] if "CREATE DATABASE IF NOT EXISTS placement" in body)
    tree = ast.parse(python_body)
    constants = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert "CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s" in constants
    assert "ALTER USER %s@%s IDENTIFIED BY %s" in constants
    assert "GRANT ALL PRIVILEGES ON placement.* TO %s@%s" in constants
    assert "authentication_string" not in text

    namespace = _placement_python_function_namespace("validate_placement_grant_evidence")
    privileges = namespace["EXPECTED_SCHEMA_PRIVILEGES"]
    account = {
        "global": [["USAGE", "NO"]],
        "schema": [["placement", privilege, "NO"] for privilege in privileges],
        "table": [], "column": [], "routine": [],
    }
    good = {
        "hosts": ["%", "127.0.0.1", "localhost"],
        "accounts": {host: json.loads(json.dumps(account)) for host in ("%", "127.0.0.1", "localhost")},
        "proxy": [], "roles": [],
    }
    namespace["validate_placement_grant_evidence"](good)
    for change in ("extra-host", "global", "schema", "table", "proxy"):
        bad = json.loads(json.dumps(good))
        if change == "extra-host": bad["hosts"].append("controller")
        elif change == "global": bad["accounts"]["%"]["global"].append(["SUPER", "NO"])
        elif change == "schema": bad["accounts"]["localhost"]["schema"].append(["nova", "SELECT", "NO"])
        elif change == "table": bad["accounts"]["127.0.0.1"]["table"].append(["placement", "allocations", "SELECT"])
        else: bad["proxy"].append(["placement", "root"])
        with pytest.raises(ValueError): namespace["validate_placement_grant_evidence"](bad)


class _FakePlacementIdentity:
    def __init__(self, scenario: str) -> None:
        self.scenario = scenario
        create_path = scenario in {"zero", "bad-created-endpoint", "created-wrong-user", "created-wrong-assignment", "created-wrong-service"}
        self.user = not create_path
        self.assignment = not create_path
        self.service = not create_path
        if scenario == "partial-endpoint": self.interfaces = ["public"]
        elif create_path: self.interfaces = []
        else: self.interfaces = ["public", "internal", "admin"]
        self.mutations: list[tuple[str, ...]] = []

    @staticmethod
    def endpoint(interface: str) -> dict[str, object]:
        return {"ID": f"endpoint-{interface}", "Interface": interface}

    def query(self, args: list[str]) -> object:
        key = tuple(args[:2])
        error_stage = {
            "query-user": ("user", "list"), "query-assignment": ("role", "assignment"),
            "query-service": ("service", "list"), "query-endpoint": ("endpoint", "list"),
        }.get(self.scenario)
        if error_stage == key: raise RuntimeError("query failed")
        if key == ("project", "list"): return [{"ID": "project", "Name": "service"}]
        if key == ("project", "show"): return {"id": "project", "name": "service", "domain_id": "default", "enabled": True, "is_domain": False}
        if key == ("role", "list"): return [{"ID": "role", "Name": "admin"}]
        if key == ("role", "show"): return {"id": "role", "name": "admin", "domain_id": None}
        if key == ("user", "list"):
            rows = [{"ID": "user", "Name": "placement"}] if self.user else []
            return rows + ([{"ID": "duplicate", "Name": "placement"}] if self.scenario == "duplicate-user" else [])
        if key == ("user", "show"): return {"id": "wrong" if self.scenario in {"wrong-user", "created-wrong-user"} else "user", "name": "placement", "domain_id": "default", "enabled": self.scenario != "disabled-user"}
        if key == ("role", "assignment"):
            if not self.assignment: return []
            rows = [{"Role": "other" if self.scenario in {"wrong-assignment", "created-wrong-assignment"} else "role", "User": "user", "Project": "project", "Group": "", "Domain": "", "System": "", "Inherited": False}]
            return rows + ([dict(rows[0])] if self.scenario == "duplicate-assignment" else [])
        if key == ("service", "list"):
            rows = [{"ID": "service", "Name": "placement", "Type": "placement"}] if self.service else []
            return rows + ([{"ID": "duplicate-service", "Name": "placement", "Type": "placement"}] if self.scenario == "duplicate-service" else [])
        if key == ("service", "show"): return {"id": "wrong-service" if self.scenario in {"wrong-service", "created-wrong-service"} else "service", "name": "placement", "type": "placement", "enabled": self.scenario != "disabled-service"}
        if key == ("endpoint", "list"):
            rows = [self.endpoint(i) for i in self.interfaces]
            return rows + ([self.endpoint("public") | {"ID": "endpoint-public-duplicate"}] if self.scenario == "duplicate-endpoint" else [])
        if key == ("endpoint", "show"):
            interface = args[2].removeprefix("endpoint-").split("-duplicate", 1)[0]
            url = "http://wrong:8778" if self.scenario in {"bad-created-endpoint", "wrong-endpoint"} and interface == "internal" else "http://controller:8778"
            service_id = "wrong-service" if self.scenario == "wrong-endpoint-service" and interface == "public" else "service"
            return {"id": args[2], "interface": interface, "region": "RegionOne", "service_id": service_id, "url": url, "enabled": True}
        raise AssertionError(args)

    def mutate(self, args: list[str]) -> object:
        self.mutations.append(tuple(args)); key = tuple(args[:2])
        if key == ("user", "create"): self.user = True
        elif key == ("role", "add"): self.assignment = True
        elif key == ("service", "create"): self.service = True
        elif key == ("endpoint", "create"): self.interfaces.append(args[-2])
        else: raise AssertionError(args)
        return None


@pytest.mark.parametrize("scenario", ("zero", "correct"))
def test_manual_placement_identity_zero_and_exact_states_succeed(scenario: str) -> None:
    namespace = _placement_python_function_namespace("ensure_placement_identity_objects")
    fake = _FakePlacementIdentity(scenario)
    evidence = namespace["ensure_placement_identity_objects"]("memory-only", fake.query, fake.mutate)
    namespace["validate_placement_identity_evidence"](evidence)
    if scenario == "correct": assert fake.mutations == []
    else: assert len(fake.mutations) == 6


@pytest.mark.parametrize(
    "scenario",
    (
        "duplicate-user", "query-user", "disabled-user", "wrong-user",
        "duplicate-assignment", "query-assignment", "wrong-assignment",
        "duplicate-service", "query-service", "disabled-service", "wrong-service",
        "partial-endpoint", "duplicate-endpoint", "query-endpoint", "wrong-endpoint", "wrong-endpoint-service",
    ),
)
def test_manual_placement_identity_failure_blocks_downstream_mutations(scenario: str) -> None:
    namespace = _placement_python_function_namespace("ensure_placement_identity_objects")
    fake = _FakePlacementIdentity(scenario)
    with pytest.raises((RuntimeError, ValueError)):
        namespace["ensure_placement_identity_objects"]("memory-only", fake.query, fake.mutate)
    assert fake.mutations == []


@pytest.mark.parametrize(
    ("scenario", "expected_keys"),
    (
        ("created-wrong-user", [("user", "create")]),
        ("created-wrong-assignment", [("user", "create"), ("role", "add")]),
        ("created-wrong-service", [("user", "create"), ("role", "add"), ("service", "create")]),
    ),
)
def test_manual_placement_created_stage_failure_blocks_every_later_stage(
    scenario: str, expected_keys: list[tuple[str, str]]
) -> None:
    namespace = _placement_python_function_namespace("ensure_placement_identity_objects")
    fake = _FakePlacementIdentity(scenario)
    with pytest.raises(ValueError):
        namespace["ensure_placement_identity_objects"]("memory-only", fake.query, fake.mutate)
    assert [args[:2] for args in fake.mutations] == expected_keys


def test_manual_placement_endpoint_create_requery_stops_before_admin() -> None:
    namespace = _placement_python_function_namespace("ensure_placement_identity_objects")
    fake = _FakePlacementIdentity("zero")
    fake.scenario = "bad-created-endpoint"
    with pytest.raises(ValueError, match="endpoint binding mismatch"):
        namespace["ensure_placement_identity_objects"]("memory-only", fake.query, fake.mutate)
    endpoint_mutations = [args for args in fake.mutations if args[:2] == ("endpoint", "create")]
    assert [args[-2] for args in endpoint_mutations] == ["public", "internal"]


def test_manual_placement_atomic_config_failure_preserves_target_and_snapshots(tmp_path: Path) -> None:
    source = next(block for block in markdown_fenced_blocks("05-placement.md", "python") if "def write_placement_config" in block)
    namespace: dict[str, object] = {"__name__": "test"}
    exec(compile(source, "placement-config", "exec"), namespace)

    class Ops:
        def __getattr__(self, name: str) -> object:
            if name in {"fchown", "fchmod"}: return lambda *_args: None
            if name == "replace": return lambda *_args: (_ for _ in ()).throw(OSError("replace failed"))
            return getattr(os, name)

    target = tmp_path / "placement.conf"; target.write_text("package-default\n", encoding="utf-8")
    with pytest.raises(OSError, match="replace failed"):
        namespace["write_placement_config"](target, "p@ss:/word", 0, 0, ops=Ops(), nonce="failure")
    assert target.read_text(encoding="utf-8") == "package-default\n"
    assert not list(tmp_path.glob(".placement.conf.task5d.*"))

    snapshot = (MANUAL_INSTALL_DIR / "config-snapshots" / "controller-placement.conf").read_text(encoding="utf-8")
    assert "<URL_ENCODED_DB_PASSWORD>" in snapshot and "<SERVICE_PASSWORD>" in snapshot
    assert "policy_file = policy.yaml" in snapshot
    wsgi = (MANUAL_INSTALL_DIR / "config-snapshots" / "controller-apache-placement.conf").read_text(encoding="utf-8")
    assert "Listen 8778" in wsgi and "WSGIPassAuthorization On" in wsgi
    policy = (MANUAL_INSTALL_DIR / "config-snapshots" / "controller-placement-policy.yaml").read_text(encoding="utf-8")
    assert "没有自定义策略覆盖" in policy


def test_manual_placement_schema_upgrade_and_api_order_are_fail_closed() -> None:
    markdown = manual_markdown("05-placement.md")
    active = "\n".join(active_lines(manual_shell_text("05-placement.md")))
    assert "su -s /bin/sh -c 'placement-manage db sync' placement" in active
    assert "placement-manage db version" in active and "422ece571366" in markdown
    for table in ("alembic_version", "allocations", "consumer_types", "resource_providers", "users"):
        assert table in markdown
    for check in ("Missing Root Provider IDs", "Incomplete Consumers", "Policy File JSON to YAML Migration"):
        assert check in markdown
    assert "oslopolicy-convert-json-to-yaml --namespace placement" in active
    assert markdown.index("placement-manage db sync") < markdown.index("systemctl restart httpd")
    assert "apachectl configtest" in active and "sport = :8778" in active


def test_manual_placement_version_and_provider_classifiers_distinguish_empty_from_error() -> None:
    version_ns = _placement_python_function_namespace("validate_placement_version_response")
    good_version = {"versions": [{"id": "v1.0", "status": "CURRENT", "max_version": "1.39"}]}
    version_ns["validate_placement_version_response"](200, good_version)
    for status, payload in ((401, good_version), (500, good_version), (200, {"versions": []}), (200, {"versions": [{"id": "v2", "status": "CURRENT", "max_version": "1.39"}]})):
        with pytest.raises((RuntimeError, ValueError)):
            version_ns["validate_placement_version_response"](status, payload)

    provider_ns = _placement_python_function_namespace("classify_resource_provider_response")
    assert provider_ns["classify_resource_provider_response"](200, {"resource_providers": []}) == []
    with pytest.raises(RuntimeError): provider_ns["classify_resource_provider_response"](401, {"resource_providers": []})
    with pytest.raises(ValueError): provider_ns["classify_resource_provider_response"](200, {})
    with pytest.raises(ValueError): provider_ns["classify_resource_provider_response"](200, {"resource_providers": [{}]})
    markdown = manual_markdown("05-placement.md")
    assert "Unknown command ['resource', 'provider', 'list']" in markdown
    assert "OpenStack-API-Version: placement 1.39" in markdown
    assert "不能为了得到非空结果手工创建资源提供者" in markdown


def test_manual_placement_later_package_and_compute_disk_boundaries_are_explicit() -> None:
    markdown = manual_markdown("05-placement.md")
    for package in (
        "openstack-nova-common", "openstack-nova-api", "openstack-nova-compute",
        "openstack-neutron-common", "openstack-cinder-common", "openstack-swift-common", "python3-horizon",
    ):
        assert package in markdown
    for marker in ("53687091200", "lsblk -s -nrpo NAME", "wipefs --no-act", "blkid -p", "resource_providers=[]"):
        assert marker in markdown
    assert "没有创建资源提供者" in markdown


def test_manual_placement_production_orchestrator_wires_every_stage_and_short_circuits() -> None:
    namespace = _placement_python_function_namespace("run_placement_deployment")
    calls: list[str] = []
    failure: str | None = None
    def mark(name: str, result: object = None) -> object:
        calls.append(name)
        if failure == name: raise RuntimeError(f"{name} failed")
        return result
    class Runtime:
        config_path = Path("/memory/placement.conf"); placement_gid = 987
        def package_stage(self): return mark("package", {})
        def validate_package_evidence(self, _e): mark("validate-package")
        def database_and_grant_stage(self): return mark("database", object())
        def load_runtime_secret(self): return mark("load-secret", "memory-only")
        def schema_stage(self): return mark("schema", {})
        def validate_schema_evidence(self, _e): mark("validate-schema")
        def upgrade_stage(self): return mark("upgrade", {})
        def validate_upgrade_evidence(self, _e): mark("validate-upgrade")
        def apache_hardening_stage(self): return mark("apache", {})
        def validate_apache_evidence(self, _e): mark("validate-apache")
        def final_dual_node_audit(self): return mark("final-audit", {"status": "FINAL_AUDIT_PASS"})
    class Executor:
        def __init__(self): mark("executor")
        def query(self, _args): return None
        def mutate(self, _args): return None
    namespace.update({
        "collect_placement_grant_evidence": lambda _cursor: mark("collect-grants", {}),
        "validate_placement_grant_evidence": lambda _e: mark("validate-grants"),
        "OpenStackExecutor": Executor,
        "ensure_placement_identity_objects": lambda *_args: mark("ensure-identity", {}),
        "validate_placement_identity_evidence": lambda _e: mark("validate-identity"),
        "write_placement_config": lambda *_args: mark("write-config"),
        "validate_written_placement_config": lambda *_args: mark("validate-config"),
        "curl_placement_request": object(),
        "run_placement_api_validation": lambda _request: mark("api", {"status": "PASS", "providers": 0}),
    })
    expected = [
        "package", "validate-package", "database", "collect-grants", "validate-grants",
        "load-secret", "executor", "ensure-identity", "validate-identity", "write-config",
        "validate-config", "schema", "validate-schema", "upgrade", "validate-upgrade",
        "apache", "validate-apache", "api", "final-audit",
    ]
    result = namespace["run_placement_deployment"](Runtime())
    assert calls == expected and result == {"status": "PASS", "providers": 0}
    for failing in expected:
        calls.clear(); failure = failing
        with pytest.raises(RuntimeError, match=f"{failing} failed"):
            namespace["run_placement_deployment"](Runtime())
        assert calls == expected[: expected.index(failing) + 1]


def test_manual_placement_starting_gate_has_complete_future_and_partial_state_boundaries() -> None:
    namespace = _placement_python_function_namespace("run_after_both_placement_gates")
    controller = namespace["CONTROLLER_GATE"]
    compute = namespace["COMPUTE_GATE"]
    for token in (
        "service project", "global admin role", "EXPECTED_PLACEMENT_RPMS",
        "partial Placement package state", "nova_api", "nova_cell0", "neutron", "cinder",
        "User IN ('nova','neutron','cinder','swift')", "openstack-placement-api",
        "sport = :$port", "placement-api", "http://controller:8778",
    ):
        assert token in controller
    assert "EXPECTED_PLACEMENT_RPMS" in compute and "partial Placement package state" in compute
    assert all(token in compute for token in ("/dev/sdb", "/dev/sdc", "disk /dev/sdb", "disk /dev/sdc"))


def test_manual_placement_partial_transaction_gate_executes_zero_partial_complete_and_probe_error() -> None:
    namespace = _placement_python_function_namespace("run_after_both_placement_gates")
    controller = namespace["CONTROLLER_GATE"]
    match = re.search(r"assert_placement_transaction_absent\(\)\{\n(.*?)\n\}", controller, re.S)
    assert match
    definitions = "die(){ exit 1; }\nassert_placement_transaction_absent(){\n" + match.group(1) + "\n}"
    array_line = next(line for line in controller.splitlines() if line.startswith("EXPECTED_PLACEMENT_RPMS="))
    packages = [
        "openstack-placement-api", "openstack-placement-common", "python3-microversion-parse",
        "python3-os-resource-classes", "python3-os-traits", "python3-placement",
    ]
    def run(installed: list[str], probe_error: str = "") -> int:
        csv = ",".join(installed)
        script = f"""
        set -Eeuo pipefail
        {array_line}
        {definitions}
        INSTALLED={shlex.quote(csv)}
        PROBE_ERROR={shlex.quote(probe_error)}
        rpm() {{
          [[ $1 == -q ]] || return 99
          local p=$2
          if [[ $p == "$PROBE_ERROR" ]]; then printf 'probe error\n' >&2; return 2; fi
          if [[ ,$INSTALLED, == *,$p,* ]]; then printf '%s-1\n' "$p"; return 0; fi
          printf 'package %s is not installed\n' "$p" >&2; return 1
        }}
        assert_placement_transaction_absent
        """
        return run_git_bash(script).returncode
    assert run([]) == 0
    assert run(packages[:1]) != 0
    assert run(packages[:5]) != 0
    assert run(packages) != 0
    assert run([], probe_error="python3-os-traits") != 0


def test_manual_placement_final_audits_are_executable_and_block_completion() -> None:
    namespace = _placement_python_function_namespace("run_placement_final_audits")
    for name in ("FINAL_CONTROLLER_AUDIT", "FINAL_COMPUTE_AUDIT"):
        with tempfile.NamedTemporaryFile("w", suffix=".sh", encoding="utf-8", newline="\n", delete=False) as stream:
            stream.write(namespace[name]); path = Path(stream.name)
        try:
            completed = subprocess.run([str(GIT_BASH), "-n", str(path)], text=True, capture_output=True, check=False)
            assert completed.returncode == 0, completed.stderr
        finally: path.unlink(missing_ok=True)
    calls: list[str] = []
    class Client:
        def __init__(self, name: str) -> None: self.name = name
        def close(self) -> None: calls.append(f"close:{self.name}")
    def connector(name: str, _password: str) -> Client:
        calls.append(f"connect:{name}"); return Client(name)
    for failing in ("controller", "compute"):
        calls.clear()
        def runner(client: Client, script: str, failing: str = failing) -> None:
            assert script == namespace[f"FINAL_{client.name.upper()}_AUDIT"]
            calls.append(f"run:{client.name}")
            if client.name == failing: raise RuntimeError(f"{failing} failed")
        with pytest.raises(RuntimeError, match=f"{failing} failed"):
            namespace["run_placement_final_audits"]("memory-only", connector=connector, runner=runner)
        assert "FINAL_AUDIT_PASS" not in calls


def test_manual_placement_api_production_path_wires_strict_validators() -> None:
    namespace = _placement_python_function_namespace("run_placement_api_validation")
    calls: list[tuple[str, bool]] = []
    version = {"versions": [{"id": "v1.0", "status": "CURRENT", "max_version": "1.39"}]}
    providers = {"resource_providers": []}
    def request(path: str, authenticated: bool) -> tuple[int, dict]:
        calls.append((path, authenticated))
        if path == "/": return 200, version
        if not authenticated: return 401, {}
        return 200, providers
    result = namespace["run_placement_api_validation"](request)
    assert result == {"status": "PASS", "providers": 0}
    assert calls == [("/", False), ("/resource_providers", False), ("/resource_providers", True)]
    valid_provider = {"uuid": "provider-uuid", "name": "compute", "generation": 0}
    nonempty = namespace["run_placement_api_validation"](
        lambda path, auth: (200, version) if path == "/" else ((200, {"resource_providers": [valid_provider]}) if auth else (401, {}))
    )
    assert nonempty == {"status": "PASS", "providers": 1}
    for broken in (
        lambda path, auth: (500, {}) if path == "/" else (401, {}),
        lambda path, auth: (200, version) if path == "/" else ((403, {}) if auth else (401, {})),
        lambda path, auth: (200, version) if path == "/" else ((200, {"resource_providers": [{}]}) if auth else (401, {})),
    ):
        with pytest.raises((RuntimeError, ValueError)):
            namespace["run_placement_api_validation"](broken)


def test_manual_placement_hardened_wsgi_is_atomic_and_has_no_global_alias(tmp_path: Path) -> None:
    source = next(block for block in markdown_fenced_blocks("05-placement.md", "python") if "def write_hardened_placement_wsgi" in block)
    namespace: dict[str, object] = {"__name__": "test"}; exec(compile(source, "placement-wsgi", "exec"), namespace)
    payload = namespace["HARDENED_PLACEMENT_WSGI"]
    assert "Listen 8778" in payload and "<VirtualHost *:8778>" in payload
    assert "Alias /placement-api" not in payload and "<Location /placement-api>" not in payload
    target = tmp_path / "00-placement-api.conf"; target.write_text("package-default\n", encoding="utf-8")
    class Ops:
        def __getattr__(self, name: str) -> object:
            if name in {"fchown", "fchmod"}: return lambda *_args: None
            if name == "replace": return lambda *_args: (_ for _ in ()).throw(OSError("replace failed"))
            return getattr(os, name)
    with pytest.raises(OSError, match="replace failed"):
        namespace["write_hardened_placement_wsgi"](target, 0, 0, ops=Ops(), nonce="failure")
    assert target.read_text(encoding="utf-8") == "package-default\n"
    assert not list(tmp_path.glob(".00-placement-api.conf.task5d.*"))
    snapshot = (MANUAL_INSTALL_DIR / "config-snapshots" / "controller-apache-placement.conf").read_text(encoding="utf-8")
    assert snapshot == payload


def test_manual_placement_records_exact_six_nevras_and_history_evidence() -> None:
    markdown = manual_markdown("05-placement.md")
    assert "EXACT_PLACEMENT_TRANSACTION_NEVRAS" in markdown
    assert markdown.count(".oe2403sp2") >= 6
    for marker in ("dnf history info", "RPM_DELTA=6", "REPO_ROWS=6", "zero remove/replace"):
        assert marker in markdown


def test_manual_placement_controller_gate_fails_closed_for_every_future_api_listener() -> None:
    namespace = _placement_python_function_namespace("run_after_both_placement_gates")
    controller = namespace["CONTROLLER_GATE"]
    ports = (8778, 8774, 9696, 8776, 8080)
    assert 'for port in 8778 8774 9696 8776 8080; do assert_listener_absent "$port"; done' in controller
    definition = shell_function_definition(controller, "assert_listener_absent")

    for port in ports:
        for mode in ("present", "probe-error"):
            completed = run_git_bash(
                f"""
                set -Eeuo pipefail
                die(){{ exit 1; }}
                {definition}
                MODE={shlex.quote(mode)}
                ss() {{
                  if [[ $MODE == probe-error ]]; then return 2; fi
                  printf '%s\n' 'LISTEN injected'
                }}
                assert_listener_absent {port}
                """
            )
            assert completed.returncode != 0, f"port {port} {mode} must fail closed"

    completed = run_git_bash(
        f"""
        set -Eeuo pipefail
        die(){{ exit 1; }}
        {definition}
        ss() {{ return 0; }}
        assert_listener_absent 8778
        """
    )
    assert completed.returncode == 0


def test_manual_placement_unique_entry_runs_full_deployment_only_after_both_gates() -> None:
    entry_namespace = _placement_python_function_namespace("run_guarded_placement_deployment")
    gate_namespace = _placement_python_function_namespace("run_after_both_placement_gates")
    entry_namespace["run_after_both_placement_gates"] = gate_namespace["run_after_both_placement_gates"]
    listener_definition = shell_function_definition(
        gate_namespace["CONTROLLER_GATE"], "assert_listener_absent"
    )
    entry_source = next(
        block for block in markdown_fenced_blocks("05-placement.md", "python")
        if "def run_guarded_placement_deployment" in block
    )
    assert "run_placement_deployment(runtime)" in entry_source
    assert "lambda: print(" not in manual_markdown("05-placement.md")

    gate_calls: list[str] = []
    stage_calls: list[str] = []

    class Client:
        def __init__(self, name: str) -> None:
            self.name = name

        def close(self) -> None:
            gate_calls.append(f"close:{self.name}")

    def connector(name: str, _password: str) -> Client:
        gate_calls.append(f"connect:{name}")
        return Client(name)

    def deployment(_runtime: object) -> dict:
        stage_calls.append("run-placement-deployment")
        return {"status": "PASS", "providers": 0}

    entry_namespace["run_placement_deployment"] = deployment
    failures: list[tuple[str, str]] = [
        (str(port), mode)
        for port in (8778, 8774, 9696, 8776, 8080)
        for mode in ("present", "probe-error")
    ] + [("compute", "runner-error")]
    for failure, mode in failures:
        gate_calls.clear()
        stage_calls.clear()

        def runner(
            client: Client, _script: str, failure: str = failure, mode: str = mode
        ) -> None:
            gate_calls.append(f"run:{client.name}")
            if client.name == "controller" and failure != "compute":
                completed = run_git_bash(
                    f"""
                    set -Eeuo pipefail
                    die(){{ exit 1; }}
                    {listener_definition}
                    MODE={shlex.quote(mode)}
                    ss() {{
                      if [[ $MODE == probe-error ]]; then return 2; fi
                      printf '%s\n' 'LISTEN injected'
                    }}
                    assert_listener_absent {failure}
                    """
                )
                assert completed.returncode != 0
                raise RuntimeError(f"gate failed: controller:{failure}:{mode}")
            if client.name == "compute" and failure == "compute":
                raise RuntimeError("gate failed: compute")

        with pytest.raises(RuntimeError, match="gate failed"):
            entry_namespace["run_guarded_placement_deployment"](
                "memory-only", object(), connector=connector, runner=runner
            )
        assert stage_calls == []

    gate_calls.clear()
    stage_calls.clear()

    def passing_runner(client: Client, _script: str) -> None:
        gate_calls.append(f"run:{client.name}")

    result = entry_namespace["run_guarded_placement_deployment"](
        "memory-only", object(), connector=connector, runner=passing_runner
    )
    assert result == {"status": "PASS", "providers": 0}
    assert gate_calls == [
        "connect:controller", "run:controller", "close:controller",
        "connect:compute", "run:compute", "close:compute",
    ]
    assert stage_calls == ["run-placement-deployment"]


def test_manual_placement_keeps_one_authoritative_api_validator() -> None:
    markdown = manual_markdown("05-placement.md")
    bash = manual_shell_text("05-placement.md")
    assert markdown.count("def run_placement_api_validation") == 1
    assert "payload['versions'][0]['id']" not in bash
    assert "provider_status=$(curl" not in bash
    assert "run_placement_api_validation(curl_placement_request)" in markdown


def _nova_python_function_namespace(document: str, required_name: str) -> dict[str, object]:
    candidates = markdown_fenced_blocks(document, "python")
    candidates.extend(
        body for _opener, _delimiter, body in shell_sections(manual_shell_text(document))[1]
    )
    source = next(block for block in candidates if f"def {required_name}" in block)
    tree = ast.parse(source)
    selected = [
        node for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.FunctionDef, ast.ClassDef))
    ]
    namespace: dict[str, object] = {"__name__": "test"}
    exec(compile(ast.Module(body=selected, type_ignores=[]), f"nova-{required_name}", "exec"), namespace)
    return namespace


def test_manual_nova_documents_preserve_the_mandatory_cross_node_order() -> None:
    controller = manual_markdown("06-nova-controller.md")
    compute = manual_markdown("07-nova-compute.md")
    controller_markers = (
        "双节点单一起始门", "Nova 控制节点软件包", "三个数据库与最小授权",
        "Nova 身份对象", "控制节点原子配置", "API 数据库、cell0 与 cell1",
        "控制平面服务与 API", "重新执行计算节点写前门",
    )
    compute_markers = (
        "计算节点本地源软件包", "计算节点原子配置", "稳定 compute_id",
        "libvirt 先于 nova-compute", "主机发现", "最终双节点审计",
    )
    assert [controller.index(x) for x in controller_markers] == sorted(controller.index(x) for x in controller_markers)
    assert [compute.index(x) for x in compute_markers] == sorted(compute.index(x) for x in compute_markers)


def test_manual_nova_guard_uses_strict_host_trust_and_blocks_partial_state() -> None:
    namespace = _nova_python_function_namespace("06-nova-controller.md", "run_after_both_nova_gates")
    assert all(token in manual_markdown("06-nova-controller.md") for token in (
        "paramiko.RejectPolicy()", "known_hosts.controller", "known_hosts.compute",
        "partial Nova package state", "nova_api", "nova_cell0", "resource_providers",
        "ens34", "/dev/sdb", "/dev/sdc", "wipefs --no-act", "blkid -p",
    ))
    calls: list[str] = []
    class Client:
        def __init__(self, name: str) -> None: self.name = name
        def close(self) -> None: calls.append(f"close:{self.name}")
    def connector(name: str, _password: str) -> Client:
        calls.append(f"connect:{name}"); return Client(name)
    for failing in ("controller", "compute"):
        calls.clear()
        def runner(client: Client, _script: str, failing: str = failing) -> None:
            calls.append(f"run:{client.name}")
            if client.name == failing: raise RuntimeError(f"{failing} failed")
        with pytest.raises(RuntimeError, match=f"{failing} failed"):
            namespace["run_after_both_nova_gates"](
                "memory-only", lambda: calls.append("MUTATION"), connector=connector, runner=runner
            )
        assert "MUTATION" not in calls


@pytest.mark.parametrize("document", ("06-nova-controller.md", "07-nova-compute.md"))
def test_manual_nova_transactions_are_local_only_and_reject_unsafe_actions(document: str) -> None:
    text = manual_shell_text(document)
    active = "\n".join(active_lines(text))
    assert "--disablerepo='*'" in active and "--enablerepo='openstack-local'" in active
    assert "--setopt=install_weak_deps=False" in active
    assert not any(flag in active for flag in ("--allowerasing", "--nodeps", "--skip-broken"))
    assert all(action in text for action in ("Removing", "Erasing", "Obsoleting", "Replacing", "Downgrading"))
    assert "dnf history info" in text and "EXACT_" in text and "NEVRAS" in text


@pytest.mark.parametrize(
    ("record", "metadata", "expected"),
    (
        ("OPENSTACK_DEPLOY_PASSWORD=memory-only\n", "root:root 600 1", True),
        ("OPENSTACK_DEPLOY_PASSWORD=\n", "root:root 600 1", False),
        ("OTHER=memory-only\n", "root:root 600 1", False),
        ("OPENSTACK_DEPLOY_PASSWORD=one\nEXTRA=two\n", "root:root 600 1", False),
        ("OPENSTACK_DEPLOY_PASSWORD=memory-only\n", "root:root 644 1", False),
    ),
)
def test_manual_nova_secret_loader_fails_closed(
    tmp_path: Path, record: str, metadata: str, expected: bool
) -> None:
    definition = shell_function_definition(manual_shell_text("06-nova-controller.md"), "load_runtime_secret")
    secret = tmp_path / "secret"; secret.write_text(record, encoding="utf-8", newline="\n")
    completed = run_git_bash(
        f"set -Eeuo pipefail\n{definition}\nstat(){{ printf '%s\\n' {shlex.quote(metadata)}; }}\n"
        f"set +e; load_runtime_secret loaded {shlex.quote(str(secret))}; rc=$?; set -e\n"
        "[[ $rc -eq 0 && $loaded == memory-only ]]\n"
    )
    assert (completed.returncode == 0) is expected


def test_manual_nova_database_code_is_parameterized_and_exactly_three_scopes() -> None:
    text = manual_shell_text("06-nova-controller.md")
    body = next(body for _opener, _delimiter, body in shell_sections(text)[1] if "CREATE DATABASE IF NOT EXISTS" in body and "nova_cell0" in body)
    constants = {
        node.value for node in ast.walk(ast.parse(body))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert "CREATE DATABASE IF NOT EXISTS `{}`" in constants
    assert "CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s" in constants
    assert "GRANT ALL PRIVILEGES ON `{}`.* TO %s@%s" in constants
    assert all(name in body for name in ("nova_api", "nova", "nova_cell0"))
    assert "authentication_string" not in text


def test_manual_nova_identity_and_endpoint_stages_are_explicit_and_exact() -> None:
    text = manual_markdown("06-nova-controller.md")
    assert all(token in text for token in (
        "def ensure_nova_identity_objects", "enabled Default-domain `nova`", "global-admin",
        "name=`nova`、type=`compute`", "http://controller:8774/v2.1",
        "public", "internal", "admin", "create/requery/immediate validation",
    ))
    assert "|| true" not in manual_shell_text("06-nova-controller.md")


def test_manual_nova_atomic_configs_and_snapshots_are_sanitized() -> None:
    controller = _nova_python_function_namespace("06-nova-controller.md", "write_nova_config")
    compute = _nova_python_function_namespace("07-nova-compute.md", "write_compute_nova_config")
    assert callable(controller["write_nova_config"])
    assert callable(compute["write_compute_nova_config"])
    snapshots = MANUAL_INSTALL_DIR / "config-snapshots"
    for name in ("controller-nova.conf", "compute-nova.conf"):
        payload = (snapshots / name).read_text(encoding="utf-8")
        assert "<SERVICE_PASSWORD>" in payload and "<URL_ENCODED_DB_PASSWORD>" in payload
        assert "guosai" not in payload and "rabbit://openstack:@" not in payload
    identity = (snapshots / "compute-identity.metadata").read_text(encoding="utf-8")
    assert "<COMPUTE_ID>" in identity
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", identity, re.I)


def test_manual_nova_cell_state_machine_and_upgrade_gate_precede_services() -> None:
    markdown = manual_markdown("06-nova-controller.md")
    active = "\n".join(active_lines(manual_shell_text("06-nova-controller.md")))
    for token in (
        "nova-manage api_db sync", "nova-manage cell_v2 map_cell0",
        "nova-manage cell_v2 create_cell --name=cell1", "nova-manage db sync",
        "nova-status upgrade check",
    ):
        assert token in markdown
    assert markdown.index("nova-manage api_db sync") < markdown.index("systemctl enable --now openstack-nova-api")
    assert "--verbose" not in active


def test_manual_nova_compute_identity_is_exclusive_stable_and_no_follow() -> None:
    namespace = _nova_python_function_namespace("07-nova-compute.md", "ensure_compute_id")
    source = next(block for block in markdown_fenced_blocks("07-nova-compute.md", "python") if "def ensure_compute_id" in block)
    assert all(token in source for token in ("O_CREAT", "O_EXCL", "O_NOFOLLOW", "lstat", "S_ISREG", "uuid.UUID"))
    assert "never rotate" in manual_markdown("07-nova-compute.md")
    assert callable(namespace["ensure_compute_id"])


def test_manual_nova_service_host_discovery_and_inventory_order() -> None:
    controller = manual_markdown("06-nova-controller.md")
    compute = manual_markdown("07-nova-compute.md")
    assert controller.index("openstack-nova-api") < controller.index("openstack-nova-scheduler")
    assert compute.index("systemctl enable --now libvirtd") < compute.index("systemctl enable --now openstack-nova-compute")
    assert compute.index("openstack-nova-compute") < compute.index("nova-manage cell_v2 discover_hosts")
    for token in ("--by-service", "scheduler", "conductor", "compute", "hypervisor", "resource_providers", "VCPU", "MEMORY_MB", "DISK_GB"):
        assert token in compute


def test_manual_nova_future_boundaries_and_disk_guards_are_explicit() -> None:
    combined = manual_markdown("06-nova-controller.md") + manual_markdown("07-nova-compute.md")
    for token in (
        "openstack-neutron-common", "openstack-cinder-common", "openstack-swift-common",
        "python3-horizon", "/dev/sdb", "/dev/sdc", "53687091200",
        "lsblk -s -nrpo NAME", "wipefs --no-act", "blkid -p",
        "不创建实例", "不创建网络", "不创建规格", "不上传镜像",
    ):
        assert token in combined


def test_manual_nova_has_one_guarded_entry_and_final_two_node_audit() -> None:
    namespace = _nova_python_function_namespace("07-nova-compute.md", "run_nova_final_audits")
    assert all(name in namespace for name in ("FINAL_CONTROLLER_AUDIT", "FINAL_COMPUTE_AUDIT", "run_nova_final_audits"))
    markdown = manual_markdown("07-nova-compute.md")
    assert all(token in markdown for token in (
        "exactly one `compute` host mapping", "FINAL_NOVA_AUDIT=PASS",
        "Neutron and later", "no task temporary files",
    ))


def test_manual_nova_exact_grant_validator_rejects_host_scope_and_extra_privileges() -> None:
    namespace = _nova_python_function_namespace("06-nova-controller.md", "validate_nova_grant_evidence")
    account = {
        "global": [["USAGE", "NO"]],
        "schema": [
            [database, privilege, "NO"]
            for database in sorted(namespace["EXPECTED_NOVA_DATABASES"])
            for privilege in sorted(namespace["EXPECTED_SCHEMA_PRIVILEGES"])
        ],
        "table": [], "column": [], "routine": [],
    }
    good = {
        "hosts": ["%", "127.0.0.1", "localhost"],
        "accounts": {
            host: json.loads(json.dumps(account))
            for host in ("%", "127.0.0.1", "localhost")
        },
        "proxy": [], "roles": [],
    }
    namespace["validate_nova_grant_evidence"](good)
    mutations: list[dict] = []
    extra_host = json.loads(json.dumps(good)); extra_host["hosts"].append("controller"); mutations.append(extra_host)
    wrong_scope = json.loads(json.dumps(good)); wrong_scope["accounts"]["localhost"]["schema"].append(["neutron", "SELECT", "NO"]); mutations.append(wrong_scope)
    extra_global = json.loads(json.dumps(good)); extra_global["accounts"]["%"]["global"].append(["SUPER", "NO"]); mutations.append(extra_global)
    extra_table = json.loads(json.dumps(good)); extra_table["accounts"]["127.0.0.1"]["table"].append(["nova", "instances", "SELECT"]); mutations.append(extra_table)
    extra_proxy = json.loads(json.dumps(good)); extra_proxy["proxy"].append(["nova", "root"]); mutations.append(extra_proxy)
    for mutation in mutations:
        with pytest.raises(ValueError):
            namespace["validate_nova_grant_evidence"](mutation)


class _FakeNovaIdentity:
    def __init__(self, scenario: str) -> None:
        self.scenario = scenario
        self.user = scenario == "exact"
        self.assignment = scenario == "exact"
        self.service = scenario == "exact"
        self.interfaces = ["public", "internal", "admin"] if scenario == "exact" else []
        if scenario == "partial-endpoints":
            self.user = self.assignment = self.service = True
            self.interfaces = ["public"]
        self.mutations: list[list[str]] = []

    def query(self, args: list[str]) -> object:
        key = tuple(args[:2])
        if key == ("project", "list"): return [{"ID": "project-id", "Name": "service"}]
        if key == ("role", "list"): return [{"ID": "role-id", "Name": "admin"}]
        if key == ("user", "list"):
            if self.scenario == "duplicate-user": return [{"ID": "u1", "Name": "nova"}, {"ID": "u2", "Name": "nova"}]
            return [{"ID": "user-id", "Name": "nova"}] if self.user else []
        if key == ("user", "show"):
            return {"id": "user-id", "name": "nova", "domain_id": "default", "enabled": True}
        if key == ("role", "assignment"):
            return [{"Role": "role-id", "User": "user-id", "Project": "project-id", "Group": "", "Domain": "", "System": "", "Inherited": False}] if self.assignment else []
        if key == ("service", "list"):
            return [{"ID": "service-id", "Name": "nova", "Type": "compute"}] if self.service else []
        if key == ("service", "show"):
            return {"id": "service-id", "name": "nova", "type": "compute", "enabled": True}
        if key == ("endpoint", "list"):
            return [{"ID": f"endpoint-{name}", "Interface": name} for name in self.interfaces]
        if key == ("endpoint", "show"):
            interface = args[2].removeprefix("endpoint-")
            return {"id": args[2], "interface": interface, "region": "RegionOne", "service_id": "service-id", "url": "http://controller:8774/v2.1", "enabled": True}
        raise AssertionError(f"unexpected Nova identity query: {args}")

    def mutate(self, args: list[str]) -> None:
        self.mutations.append(args)
        key = tuple(args[:2])
        if key == ("user", "create"): self.user = True
        elif key == ("role", "add"): self.assignment = True
        elif key == ("service", "create"): self.service = True
        elif key == ("endpoint", "create"): self.interfaces.append(args[-2])
        else: raise AssertionError(f"unexpected Nova identity mutation: {args}")


def test_manual_nova_identity_stages_create_requery_and_fail_closed() -> None:
    namespace = _nova_python_function_namespace("06-nova-controller.md", "ensure_nova_identity_objects")
    exact = _FakeNovaIdentity("exact")
    result = namespace["ensure_nova_identity_objects"]("memory-only", exact.query, exact.mutate)
    assert result["user"]["name"] == "nova" and len(result["endpoints"]) == 3
    assert exact.mutations == []

    zero = _FakeNovaIdentity("zero")
    result = namespace["ensure_nova_identity_objects"]("memory-only", zero.query, zero.mutate)
    assert len(result["endpoints"]) == 3
    assert [args[:2] for args in zero.mutations] == [
        ["user", "create"], ["role", "add"], ["service", "create"],
        ["endpoint", "create"], ["endpoint", "create"], ["endpoint", "create"],
    ]

    for scenario in ("duplicate-user", "partial-endpoints"):
        fake = _FakeNovaIdentity(scenario)
        with pytest.raises(ValueError):
            namespace["ensure_nova_identity_objects"]("memory-only", fake.query, fake.mutate)
        assert fake.mutations == []


@pytest.mark.parametrize(
    ("document", "function_name"),
    (("06-nova-controller.md", "write_nova_config"), ("07-nova-compute.md", "write_compute_nova_config")),
)
def test_manual_nova_atomic_config_failure_preserves_package_default(
    document: str, function_name: str, tmp_path: Path
) -> None:
    namespace = _nova_python_function_namespace(document, function_name)
    class Ops:
        def __getattr__(self, name: str) -> object:
            if name in {"fchown", "fchmod"}: return lambda *_args: None
            if name == "replace": return lambda *_args: (_ for _ in ()).throw(OSError("replace failed"))
            return getattr(os, name)
    target = tmp_path / "nova.conf"; target.write_text("package-default\n", encoding="utf-8")
    with pytest.raises(OSError, match="replace failed"):
        namespace[function_name](target, "p@ss:/word", 0, 0, ops=Ops(), nonce="failure")
    assert target.read_text(encoding="utf-8") == "package-default\n"
    assert not list(tmp_path.glob(".nova.conf.task5e.*"))


def test_manual_nova_compute_id_creation_rerun_and_failure_cleanup(tmp_path: Path) -> None:
    namespace = _nova_python_function_namespace("07-nova-compute.md", "ensure_compute_id")
    account = types.SimpleNamespace(pw_uid=0, pw_gid=0)
    fixed = uuid.UUID("11111111-1111-4111-8111-111111111111")

    class Ops:
        O_WRONLY = os.O_WRONLY; O_CREAT = os.O_CREAT; O_EXCL = os.O_EXCL
        O_RDONLY = os.O_RDONLY; O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
        O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
        def __init__(self, fail_write: bool = False) -> None: self.fail_write = fail_write
        def __getattr__(self, name: str) -> object: return getattr(os, name)
        def fchown(self, *_args: object) -> None: return None
        def fchmod(self, *_args: object) -> None: return None
        def _meta(self, value: os.stat_result) -> object:
            return types.SimpleNamespace(st_mode=stat.S_IFREG | 0o644, st_uid=0, st_gid=0, st_nlink=1, st_dev=value.st_dev, st_ino=value.st_ino)
        def fstat(self, fd: int) -> object: return self._meta(os.fstat(fd))
        def lstat(self, path: Path) -> object: return self._meta(os.lstat(path))
        def open(self, path: str, flags: int, mode: int = 0o777) -> int:
            if Path(path).is_dir(): return -999
            return os.open(path, flags, mode)
        def fsync(self, fd: int) -> None:
            if fd != -999: os.fsync(fd)
        def close(self, fd: int) -> None:
            if fd != -999: os.close(fd)
        def write(self, fd: int, payload: bytes) -> int:
            if self.fail_write: raise OSError("injected write failure")
            return os.write(fd, payload)

    target = tmp_path / "compute_id"; ops = Ops()
    state, value = namespace["ensure_compute_id"](target, account=account, ops=ops, value_factory=lambda: fixed)
    assert state == "created" and value == fixed
    state, repeated = namespace["ensure_compute_id"](target, account=account, ops=ops, value_factory=lambda: uuid.uuid4())
    assert state == "existing-stable" and repeated == fixed

    failed = tmp_path / "failed_compute_id"
    with pytest.raises(OSError, match="injected write failure"):
        namespace["ensure_compute_id"](failed, account=account, ops=Ops(fail_write=True), value_factory=lambda: fixed)
    assert not failed.exists()


def test_manual_nova_cell_mapping_commands_are_idempotent_and_url_safe() -> None:
    bash = manual_shell_text("06-nova-controller.md")
    assert "cell0_count" in bash and "cell1_count" in bash
    assert "[[ $cell0_count == 0 || $cell0_count == 1 ]]" in bash
    assert "[[ $cell1_count == 0 || $cell1_count == 1 ]]" in bash
    assert "if [[ $cell0_count == 0 ]]; then nova-manage cell_v2 map_cell0; fi" in bash
    assert "if [[ $cell1_count == 0 ]]; then nova-manage cell_v2 create_cell --name=cell1; fi" in bash
    assert "list_cells --verbose" not in bash and "create_cell --name=cell1 --verbose" not in bash


def _exact_nova_start_evidence() -> dict[str, object]:
    interfaces = ("admin", "internal", "public")
    endpoints = [
        {"service": service, "interface": interface, "region": "RegionOne", "url": url,
         "enabled": True, "service_id": f"{service}-id"}
        for service, url in (
            ("identity", "http://controller:5000/v3/"),
            ("image", "http://controller:9292"),
            ("placement", "http://controller:8778"),
        )
        for interface in interfaces
    ]
    return {
        "controller": {
            "probe_errors": [], "hostname": "controller", "ens33": "192.168.234.151/24",
            "ens34_ipv4": [], "ntp": True, "enabled_repositories": ["openstack-local"],
            "prerequisite_packages": {"openstack-keystone", "openstack-glance-api", "openstack-placement-api"},
            "prerequisite_services": {
                "chronyd", "mariadb", "rabbitmq-server", "memcached", "httpd", "openstack-glance-api"
            },
            "service_project": {"id": "project-id", "name": "service", "domain_id": "default", "enabled": True, "is_domain": False},
            "global_admin_role": {"id": "role-id", "name": "admin", "domain_id": None},
            "users": [
                {"id": "glance-user", "name": "glance", "domain_id": "default", "enabled": True, "project_id": "project-id", "role_id": "role-id"},
                {"id": "placement-user", "name": "placement", "domain_id": "default", "enabled": True, "project_id": "project-id", "role_id": "role-id"},
            ],
            "services": [
                {"id": "identity-id", "name": "keystone", "type": "identity", "enabled": True},
                {"id": "image-id", "name": "glance", "type": "image", "enabled": True},
                {"id": "placement-id", "name": "placement", "type": "placement", "enabled": True},
            ],
            "endpoints": endpoints,
            "apis": {
                "keystone": {"http": 200, "id": "v3.14", "status": "stable"},
                "glance": {"http": 300, "id": "v2.15", "status": "CURRENT"},
                "placement": {"http": 200, "id": "v1.0", "status": "CURRENT", "max_version": "1.39"},
            },
            "schemas": {
                "keystone": {"tables": 49, "heads": ["29e87d24a316", "e25ffa003242"]},
                "glance": {"tables": 14, "heads": ["2023_1_contract01"]},
                "placement": {"tables": 13, "heads": ["422ece571366"]},
            },
            "placement_upgrade": {"rc": 0, "successes": 3, "failures": 0, "warnings": 0},
            "placement_providers": [],
            "nova_and_later": {"packages": [], "databases": [], "db_users": [], "users": [], "services": [], "endpoints": [], "listeners": [], "temporary": []},
        },
        "compute": {
            "probe_errors": [], "hostname": "compute", "ens33": "192.168.234.150/24",
            "ens34_ipv4": [], "ntp": True, "enabled_repositories": ["openstack-local"],
            "nova_and_later": {"packages": [], "compute_id": "absent", "temporary": []},
            "disks": {
                "/dev/sdb": {"bytes": 53687091200, "type": "disk", "root_ancestor": False, "children": 0, "filesystem": "", "mountpoint": "", "wipefs": [], "blkid_rc": 2},
                "/dev/sdc": {"bytes": 53687091200, "type": "disk", "root_ancestor": False, "children": 0, "filesystem": "", "mountpoint": "", "wipefs": [], "blkid_rc": 2},
            },
        },
    }


def test_review_nova_start_classifier_fails_closed_before_any_stage() -> None:
    namespace = _nova_python_function_namespace("06-nova-controller.md", "validate_nova_start_evidence")
    validate = namespace["validate_nova_start_evidence"]
    good = _exact_nova_start_evidence()
    validate("controller", good["controller"])
    validate("compute", good["compute"])

    mutations: list[tuple[str, dict[str, object]]] = []
    for role, mutate in (
        ("controller", lambda e: e["probe_errors"].append("query failed")),
        ("controller", lambda e: e["users"].append(dict(e["users"][0]))),
        ("controller", lambda e: e["endpoints"].pop()),
        ("controller", lambda e: e["apis"]["placement"].update(max_version="1.38")),
        ("controller", lambda e: e["schemas"]["placement"].update(heads=["wrong"])),
        ("controller", lambda e: e["placement_upgrade"].update(successes=2)),
        ("controller", lambda e: e["placement_providers"].append({"name": "early"})),
        ("controller", lambda e: e["nova_and_later"]["listeners"].append(8774)),
        ("compute", lambda e: e["probe_errors"].append("blkid failed")),
        ("compute", lambda e: e["nova_and_later"].update(compute_id="present")),
        ("compute", lambda e: e["disks"]["/dev/sdb"].update(blkid_rc=4)),
        ("compute", lambda e: e["disks"]["/dev/sdc"].update(children=1)),
    ):
        evidence = copy.deepcopy(good[role])
        mutate(evidence)
        mutations.append((role, evidence))
    for role, evidence in mutations:
        with pytest.raises((RuntimeError, ValueError)):
            validate(role, evidence)


def test_review_nova_unique_orchestrator_calls_every_production_stage_and_short_circuits_gates() -> None:
    namespace = _nova_python_function_namespace("07-nova-compute.md", "run_guarded_nova_deployment")
    events: list[str] = []

    def record(name: str, result: object = None):
        def call(*_args: object, **_kwargs: object) -> object:
            events.append(name)
            return result
        return call

    for name, result in (
        ("validate_controller_transaction", None), ("collect_grants", {"grants": "exact"}),
        ("validate_grants", None), ("ensure_identity", {"identity": "exact"}),
        ("validate_identity", None), ("write_controller_config", None),
        ("validate_controller_config", None), ("classify_cells", {"cells": "exact"}),
        ("validate_controller_schema", None), ("validate_compute_transaction", None),
        ("write_compute_config", None), ("validate_compute_config", None),
        ("ensure_compute_id", ("existing-stable", uuid.UUID("11111111-1111-4111-8111-111111111111"))),
        ("validate_compute_id_fd", uuid.UUID("11111111-1111-4111-8111-111111111111")),
        ("validate_integration", None), ("validate_final", None),
    ):
        namespace[name] = record(name, result)

    namespace["validate_nova_transaction_evidence"] = lambda node, evidence: (
        namespace[f"validate_{node}_transaction"](evidence)
    )
    namespace["collect_nova_grant_evidence"] = namespace["collect_grants"]
    namespace["validate_nova_grant_evidence"] = namespace["validate_grants"]
    namespace["ensure_nova_identity_objects"] = namespace["ensure_identity"]
    namespace["validate_nova_identity_evidence"] = namespace["validate_identity"]
    namespace["write_nova_config"] = namespace["write_controller_config"]
    namespace["validate_written_nova_config"] = namespace["validate_controller_config"]
    namespace["classify_cell_state"] = namespace["classify_cells"]
    namespace["validate_nova_controller_schema"] = namespace["validate_controller_schema"]
    namespace["write_compute_nova_config"] = namespace["write_compute_config"]
    namespace["validate_written_compute_nova_config"] = namespace["validate_compute_config"]
    namespace["ensure_compute_id"] = namespace["ensure_compute_id"]
    namespace["validate_compute_id_fd"] = namespace["validate_compute_id_fd"]
    namespace["validate_nova_integration_evidence"] = namespace["validate_integration"]
    namespace["validate_nova_final_evidence"] = namespace["validate_final"]

    class Runtime:
        controller_config_args = (Path("/etc/nova/nova.conf"), "secret", 0, 0)
        compute_config_args = (Path("/etc/nova/nova.conf"), "secret", 0, 0)
        compute_id_args = (Path("/etc/nova/compute_id"),)
        def __init__(self, failing_gate: str | None = None) -> None:
            self.failing_gate = failing_gate
            self.stage_calls: list[str] = []
        def run_strict_gate(self, role: str, _password: str) -> None:
            events.append(f"gate:{role}")
            if role == self.failing_gate: raise RuntimeError(f"{role} gate failed")
        def _stage(self, name: str, result: object = None) -> object:
            self.stage_calls.append(name); events.append(name); return result
        def install_controller_packages(self) -> object: return self._stage("controller_package", {"tx": 8})
        def load_secret(self) -> str: return self._stage("secret_loader", "memory-only")
        def create_controller_databases_and_grants(self, _secret: str) -> None: self._stage("database_create")
        def grant_cursor(self) -> object: return self._stage("grant_cursor", object())
        def identity_adapter(self, _secret: str) -> object:
            return self._stage("identity_adapter", types.SimpleNamespace(query=record("identity_query"), mutate=record("identity_mutate")))
        def sync_api_database(self) -> None: self._stage("api_db_sync")
        def collect_and_ensure_cells(self) -> object: return self._stage("cells", {"query_ok": True, "rows": []})
        def sync_main_database(self) -> None: self._stage("main_db_sync")
        def collect_controller_schema(self) -> object: return self._stage("controller_schema", {"schema": "exact"})
        def start_controller_services(self) -> None: self._stage("controller_services")
        def install_compute_packages(self) -> object: return self._stage("compute_package", {"tx": 3})
        def start_libvirt(self) -> None: self._stage("libvirt")
        def start_nova_compute(self) -> None: self._stage("nova_compute")
        def discover_hosts(self) -> None: self._stage("host_discovery")
        def collect_integration_evidence(self) -> object: return self._stage("integration_collect", {"state": "exact"})
        def collect_final_evidence(self) -> object: return self._stage("final_collect", {"state": "exact"})
        def run_final_node_audits(self, _password: str) -> None: self._stage("final_node_audits")

    for failing_gate, expected_gates in (("controller", ["gate:controller"]),
                                          ("compute", ["gate:controller", "gate:compute"])):
        events.clear(); runtime = Runtime(failing_gate)
        with pytest.raises(RuntimeError, match=f"{failing_gate} gate failed"):
            namespace["run_guarded_nova_deployment"]("memory-only", runtime)
        assert events == expected_gates
        assert runtime.stage_calls == []

    events.clear(); runtime = Runtime()
    namespace["run_guarded_nova_deployment"]("memory-only", runtime)
    assert events == [
        "gate:controller", "gate:compute", "controller_package", "validate_controller_transaction",
        "secret_loader", "database_create", "grant_cursor", "collect_grants", "validate_grants",
        "identity_adapter", "ensure_identity", "validate_identity", "write_controller_config",
        "validate_controller_config", "api_db_sync", "cells", "classify_cells", "main_db_sync",
        "controller_schema", "validate_controller_schema", "controller_services", "gate:compute",
        "compute_package", "validate_compute_transaction", "write_compute_config",
        "validate_compute_config", "ensure_compute_id", "validate_compute_id_fd", "libvirt",
        "nova_compute", "host_discovery", "integration_collect", "validate_integration",
        "final_collect", "validate_final", "final_node_audits",
    ]


def test_review_nova_cell_classifier_handles_zero_one_exact_and_all_ambiguous_states_without_urls() -> None:
    namespace = _nova_python_function_namespace("06-nova-controller.md", "classify_cell_state")
    classify = namespace["classify_cell_state"]
    cell0 = {"name": "cell0", "uuid": "00000000-0000-0000-0000-000000000000", "disabled": False}
    cell1 = {"name": "cell1", "uuid": "22222222-2222-4222-8222-222222222222", "disabled": False}
    assert classify({"query_ok": True, "rows": []}) == "create-cell0-then-cell1"
    assert classify({"query_ok": True, "rows": [cell0]}) == "create-cell1"
    assert classify({"query_ok": True, "rows": [cell0, cell1]}) == "exact"

    bad_evidence = (
        {"query_ok": False, "rows": []},
        {"query_ok": True, "rows": [cell1]},
        {"query_ok": True, "rows": [cell0, dict(cell0)]},
        {"query_ok": True, "rows": [cell0, cell1, dict(cell1)]},
        {"query_ok": True, "rows": [{"name": "cell0", "uuid": "wrong", "disabled": False}]},
        {"query_ok": True, "rows": [cell0, {"name": "other", "uuid": cell1["uuid"], "disabled": False}]},
        {"query_ok": True, "rows": [cell0, cell1], "transport_url": "rabbit://user:secret@controller"},
        {"query_ok": True, "rows": [cell0, cell1], "database_connection": "mysql://user:secret@controller/nova"},
    )
    for evidence in bad_evidence:
        with pytest.raises((RuntimeError, ValueError)) as caught:
            classify(evidence)
        message = str(caught.value)
        assert "secret" not in message and "rabbit://" not in message and "mysql://" not in message


def _exact_nova_integration_evidence() -> dict[str, object]:
    cell1_uuid = "22222222-2222-4222-8222-222222222222"
    compute_uuid = "11111111-1111-4111-8111-111111111111"
    service_id = "nova-service-id"
    return {
        "query_ok": True,
        "compute_services": [
            {"binary": "nova-scheduler", "host": "controller", "state": "up", "status": "enabled"},
            {"binary": "nova-conductor", "host": "controller", "state": "up", "status": "enabled"},
            {"binary": "nova-compute", "host": "compute", "state": "up", "status": "enabled"},
        ],
        "cells": [
            {"name": "cell0", "uuid": "00000000-0000-0000-0000-000000000000", "disabled": False},
            {"name": "cell1", "uuid": cell1_uuid, "disabled": False},
        ],
        "host_mappings": [{"host": "compute", "cell_uuid": cell1_uuid}],
        "hypervisors": [{"name": "compute", "type": "QEMU", "state": "up", "status": "enabled", "uuid": compute_uuid}],
        "providers": [{"name": "compute", "uuid": compute_uuid}],
        "inventories": {
            "VCPU": {"total": 4, "reserved": 0, "min_unit": 1, "max_unit": 4, "step_size": 1, "allocation_ratio": 16.0},
            "MEMORY_MB": {"total": 7800, "reserved": 512, "min_unit": 1, "max_unit": 7800, "step_size": 1, "allocation_ratio": 1.5},
            "DISK_GB": {"total": 92, "reserved": 0, "min_unit": 1, "max_unit": 92, "step_size": 1, "allocation_ratio": 1.0},
        },
        "nova_identity": {
            "service": {"id": service_id, "name": "nova", "type": "compute", "enabled": True},
            "endpoints": [
                {"service_id": service_id, "interface": interface, "region": "RegionOne", "url": "http://controller:8774/v2.1", "enabled": True}
                for interface in ("admin", "internal", "public")
            ],
        },
        "nova_api": {"http": 200, "id": "v2.1", "status": "CURRENT", "authenticated": True},
        "resources": {"images": [], "servers": [], "flavors": []},
        "database_grants": {
            "hosts": ["%", "127.0.0.1", "localhost"],
            "schemas": ["nova", "nova_api", "nova_cell0"],
            "global_only_usage": True, "object_privileges": 0, "proxy": 0, "roles": 0,
        },
        "compute_identity": {"file_uuid": compute_uuid, "database_uuid": compute_uuid, "hypervisor_uuid": compute_uuid,
                             "owner": "nova:nova", "mode": "0644", "nlink": 1},
        "upgrade": {"rc": 0, "successes": 7, "failures": 0, "warnings": 0},
        "later": {"packages": [], "databases": [], "db_users": [], "users": [], "services": [], "endpoints": [], "listeners": []},
        "disks": _exact_nova_start_evidence()["compute"]["disks"],
        "temporary": [],
    }


def test_review_nova_integration_and_final_classifiers_reject_duplicates_wrong_bindings_and_invalid_inventory() -> None:
    namespace = _nova_python_function_namespace("07-nova-compute.md", "validate_nova_integration_evidence")
    validate_integration = namespace["validate_nova_integration_evidence"]
    validate_final = namespace["validate_nova_final_evidence"]
    good = _exact_nova_integration_evidence()
    validate_integration(good)

    mutators = (
        lambda e: e.update(query_ok=False),
        lambda e: e["compute_services"].append(dict(e["compute_services"][0])),
        lambda e: e["compute_services"][2].update(state="down"),
        lambda e: e["host_mappings"][0].update(cell_uuid="wrong"),
        lambda e: e["hypervisors"].append(dict(e["hypervisors"][0])),
        lambda e: e["hypervisors"][0].update(type="KVM"),
        lambda e: e["providers"].append(dict(e["providers"][0])),
        lambda e: e["providers"][0].update(uuid="33333333-3333-4333-8333-333333333333"),
        lambda e: e["inventories"].pop("VCPU"),
        lambda e: e["inventories"]["MEMORY_MB"].update(reserved=7800),
        lambda e: e["inventories"]["DISK_GB"].update(total=0),
        lambda e: e["nova_identity"]["endpoints"].pop(),
        lambda e: e["nova_api"].update(status="SUPPORTED"),
        lambda e: e["resources"]["flavors"].append({"name": "unexpected"}),
        lambda e: e["database_grants"]["hosts"].append("controller"),
        lambda e: e["compute_identity"].update(database_uuid="33333333-3333-4333-8333-333333333333"),
        lambda e: e["upgrade"].update(successes=6),
        lambda e: e["later"]["packages"].append("openstack-neutron-common"),
        lambda e: e["disks"]["/dev/sdb"].update(wipefs=["LVM2_member"]),
        lambda e: e["temporary"].append("/root/.task5e-leftover"),
    )
    for mutate in mutators:
        evidence = copy.deepcopy(good); mutate(evidence)
        with pytest.raises((RuntimeError, ValueError)):
            validate_integration(evidence)

    final = {
        "query_ok": True,
        "integration": good,
        "controller": {
            "active_enabled": ["chronyd", "mariadb", "rabbitmq-server", "memcached", "httpd", "openstack-glance-api",
                               "openstack-nova-api", "openstack-nova-scheduler", "openstack-nova-conductor", "openstack-nova-novncproxy"],
            "listeners": [5000, 6080, 8774, 8778, 9292], "databases": ["glance", "keystone", "nova", "nova_api", "nova_cell0", "placement"],
        },
        "compute": {"active_enabled": ["chronyd", "sshd", "libvirtd", "openstack-nova-compute"],
                    "virt_type": "qemu", "domains": [], "boot_changed": False},
    }
    validate_final(final)
    for mutate in (
        lambda e: e.update(query_ok=False),
        lambda e: e["controller"]["active_enabled"].pop(),
        lambda e: e["controller"]["listeners"].append(9696),
        lambda e: e["compute"]["active_enabled"].remove("sshd"),
        lambda e: e["compute"]["domains"].append("unexpected-domain"),
        lambda e: e["compute"].update(boot_changed=True),
    ):
        evidence = copy.deepcopy(final); mutate(evidence)
        with pytest.raises((RuntimeError, ValueError)):
            validate_final(evidence)


def test_review_nova_transaction_artifacts_preserve_every_history_row_and_three_way_match() -> None:
    namespace = _nova_python_function_namespace("06-nova-controller.md", "load_nova_transaction_evidence")
    load = namespace["load_nova_transaction_evidence"]
    validate = namespace["validate_nova_transaction_evidence"]
    root = MANUAL_INSTALL_DIR / "transaction-evidence"
    controller = load(root / "nova-controller-transaction.txt")
    compute = load(root / "nova-compute-transaction.txt")
    validate("controller", controller)
    validate("compute", compute)
    assert len(controller["history_new"]) == 40 and controller["history_old"] == []
    assert sum(row["action"] == "Install" for row in compute["history_new"]) == 398
    assert sum(row["action"] == "Upgrade" for row in compute["history_new"]) == 5
    assert len(compute["history_old"]) == 5

    mutators = (
        lambda e: e["history_new"].pop(),
        lambda e: e["history_new"].append(dict(e["history_new"][0])),
        lambda e: e["history_new"][0].update(repo="external"),
        lambda e: e["history_new"][0].update(action="Downgrade"),
        lambda e: e["current_rpm"].pop(),
        lambda e: e["repository_metadata"].pop(),
        lambda e: e["unsafe_actions"].append("Removing"),
    )
    for baseline in (controller, compute):
        for mutate in mutators:
            evidence = copy.deepcopy(baseline); mutate(evidence)
            with pytest.raises((RuntimeError, ValueError)):
                validate(evidence["node"], evidence)


def test_review_nova_compute_id_uses_one_fd_and_rejects_symlink_metadata_content_and_descriptor_swap(tmp_path: Path) -> None:
    namespace = _nova_python_function_namespace("07-nova-compute.md", "validate_compute_id_fd")
    validate = namespace["validate_compute_id_fd"]
    ensure = namespace["ensure_compute_id"]
    source = next(block for block in markdown_fenced_blocks("07-nova-compute.md", "python") if "def validate_compute_id_fd" in block)
    assert "path.read_text" not in source
    assert "ops.read(" in source and source.count("ops.fstat(descriptor)") >= 2
    assert "ops.O_RDONLY | getattr(ops, \"O_NOFOLLOW\"" in source

    fixed = uuid.UUID("11111111-1111-4111-8111-111111111111")
    account = types.SimpleNamespace(pw_uid=101, pw_gid=102)

    class StrictOps:
        O_RDONLY = os.O_RDONLY; O_WRONLY = os.O_WRONLY; O_RDWR = os.O_RDWR; O_CREAT = os.O_CREAT; O_EXCL = os.O_EXCL
        O_DIRECTORY = getattr(os, "O_DIRECTORY", 0); O_NOFOLLOW = 0x20000000
        def __init__(self, *, uid: int = 101, gid: int = 102, mode: int = 0o644, nlink: int = 1,
                     swap_fstat: bool = False, fail_write: bool = False, swap_cleanup: bool = False,
                     reject_as_symlink: bool = False) -> None:
            self.uid, self.gid, self.mode, self.nlink = uid, gid, mode, nlink
            self.swap_fstat, self.fail_write, self.swap_cleanup = swap_fstat, fail_write, swap_cleanup
            self.reject_as_symlink = reject_as_symlink
            self.fstat_calls = 0; self.opened_path: Path | None = None
        def _meta(self, value: os.stat_result, *, swapped: bool = False) -> object:
            return types.SimpleNamespace(st_mode=stat.S_IFREG | self.mode, st_uid=self.uid, st_gid=self.gid,
                                         st_nlink=self.nlink, st_dev=value.st_dev,
                                         st_ino=value.st_ino + (1 if swapped else 0))
        def open(self, path: str, flags: int, mode: int = 0o777) -> int:
            target = Path(path); self.opened_path = target
            if (target.is_symlink() or self.reject_as_symlink) and flags & self.O_NOFOLLOW: raise OSError("symlink rejected")
            if target.is_dir(): return -999
            return os.open(path, flags & ~self.O_NOFOLLOW, mode)
        def fstat(self, fd: int) -> object:
            self.fstat_calls += 1
            return self._meta(os.fstat(fd), swapped=self.swap_fstat and self.fstat_calls == 2)
        def lstat(self, path: Path) -> object: return self._meta(os.lstat(path), swapped=self.swap_cleanup)
        def read(self, fd: int, size: int) -> bytes: return os.read(fd, size)
        def lseek(self, fd: int, offset: int, whence: int) -> int: return os.lseek(fd, offset, whence)
        def write(self, fd: int, payload: bytes) -> int:
            if self.fail_write:
                raise OSError("injected write failure")
            return os.write(fd, payload)
        def fchown(self, *_args: object) -> None: return None
        def fchmod(self, *_args: object) -> None: return None
        def fsync(self, fd: int) -> None:
            if fd != -999: os.fsync(fd)
        def close(self, fd: int) -> None:
            if fd != -999: os.close(fd)
        def unlink(self, path: Path) -> None: os.unlink(path)

    def write_target(name: str, payload: str) -> Path:
        target = tmp_path / name; target.write_text(payload, encoding="ascii", newline="\n"); return target

    exact = write_target("exact", f"{fixed}\n")
    assert validate(exact, account.pw_uid, account.pw_gid, ops=StrictOps()) == fixed
    for target, ops in (
        (write_target("wrong-owner", f"{fixed}\n"), StrictOps(uid=999)),
        (write_target("wrong-mode", f"{fixed}\n"), StrictOps(mode=0o600)),
        (write_target("wrong-link", f"{fixed}\n"), StrictOps(nlink=2)),
        (write_target("malformed", "not-a-uuid\n"), StrictOps()),
        (write_target("empty", ""), StrictOps()),
        (write_target("descriptor-swap", f"{fixed}\n"), StrictOps(swap_fstat=True)),
    ):
        with pytest.raises((OSError, RuntimeError, ValueError)):
            validate(target, account.pw_uid, account.pw_gid, ops=ops)

    symlink = write_target("symlink-probe", f"{fixed}\n")
    with pytest.raises((OSError, RuntimeError, ValueError)):
        validate(symlink, account.pw_uid, account.pw_gid, ops=StrictOps(reject_as_symlink=True))

    created = tmp_path / "created"
    state, value = ensure(created, account=account, ops=StrictOps(), value_factory=lambda: fixed)
    assert state == "created" and value == fixed
    state, repeated = ensure(created, account=account, ops=StrictOps(), value_factory=uuid.uuid4)
    assert state == "existing-stable" and repeated == fixed

    failed = tmp_path / "failed"
    with pytest.raises(OSError, match="injected write failure"):
        ensure(failed, account=account, ops=StrictOps(fail_write=True), value_factory=lambda: fixed)
    assert not failed.exists()
    swapped = tmp_path / "swapped"
    with pytest.raises(OSError, match="injected write failure"):
        ensure(swapped, account=account, ops=StrictOps(fail_write=True, swap_cleanup=True), value_factory=lambda: fixed)
    assert swapped.exists(), "cleanup must not unlink a path whose lstat inode differs from the created inode"


def _neutron_python_function_namespace(required_name: str) -> dict[str, object]:
    candidates = markdown_fenced_blocks("09-neutron-compute.md", "python")
    source = next(block for block in candidates if f"def {required_name}" in block)
    tree = ast.parse(source)
    selected = [
        node for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.FunctionDef, ast.ClassDef))
    ]
    namespace: dict[str, object] = {"__name__": "test"}
    exec(compile(ast.Module(body=selected, type_ignores=[]), f"neutron-{required_name}", "exec"), namespace)
    return namespace


def test_manual_neutron_documents_keep_the_required_manual_order_and_boundaries() -> None:
    controller = manual_markdown("08-neutron-controller.md")
    compute = manual_markdown("09-neutron-compute.md")
    markers = (
        "只读双节点门禁", "控制节点本地源软件包", "neutron 数据库与三条主机授权",
        "身份、服务和端点", "手工编辑控制节点配置", "数据库同步与启用控制节点服务",
    )
    assert [controller.index(marker) for marker in markers] == sorted(controller.index(marker) for marker in markers)
    assert "再次只读门禁" in compute and "计算节点本地源软件包" in compute
    combined = controller + compute
    for command in (
        "openstack user create --domain Default --password", "openstack role add --project service --user neutron admin",
        "openstack service create --name neutron --description", "openstack endpoint create --region RegionOne network",
        "neutron-db-manage --config-file /etc/neutron/neutron.conf --config-file /etc/neutron/plugins/ml2/ml2_conf.ini upgrade head",
        "systemctl enable --now neutron-server neutron-linuxbridge-agent neutron-dhcp-agent neutron-metadata-agent neutron-l3-agent",
        "systemctl enable --now neutron-linuxbridge-agent", "systemctl restart openstack-nova-compute",
    ):
        assert command in combined
    for forbidden in ("openstack router", "openstack subnet", "server create", "snapshot"):
        assert forbidden not in manual_shell_text("08-neutron-controller.md") + manual_shell_text("09-neutron-compute.md")


def test_manual_neutron_snapshots_are_sanitized_and_match_the_two_node_mapping() -> None:
    snapshots = MANUAL_INSTALL_DIR / "config-snapshots"
    required = {
        "controller-neutron.conf", "controller-ml2_conf.ini", "controller-linuxbridge_agent.ini",
        "controller-l3_agent.ini", "controller-dhcp_agent.ini", "controller-metadata_agent.ini",
        "controller-99-openstack-neutron.conf", "compute-neutron.conf", "compute-linuxbridge_agent.ini",
        "compute-99-openstack-neutron.conf",
    }
    assert required <= {path.name for path in snapshots.iterdir()}
    payloads = {name: (snapshots / name).read_text(encoding="utf-8") for name in required}
    combined = "\n".join(payloads.values())
    assert "<SERVICE_PASSWORD>" in combined and "<URL_ENCODED_PASSWORD>" in combined
    assert "guosai" not in combined and "rabbit://openstack:@" not in combined
    assert "provider:ens34" in payloads["controller-linuxbridge_agent.ini"]
    assert "local_ip = 192.168.234.151" in payloads["controller-linuxbridge_agent.ini"]
    assert "local_ip = 192.168.234.150" in payloads["compute-linuxbridge_agent.ini"]
    assert "vni_ranges = 1:1000" in payloads["controller-ml2_conf.ini"]


def test_focused_neutron_contract_accepts_only_a_clean_lightweight_result() -> None:
    validate = _neutron_python_function_namespace("validate_neutron_lightweight_evidence")["validate_neutron_lightweight_evidence"]
    good = {
        "services": {
            "controller": ["neutron-server", "neutron-linuxbridge-agent", "neutron-dhcp-agent", "neutron-metadata-agent", "neutron-l3-agent"],
            "compute": ["neutron-linuxbridge-agent", "openstack-nova-compute"],
        },
        "api": {"http": 200, "authenticated": True},
        "agents": {"alive": True, "hosts": ["controller", "compute"], "types": ["DHCP agent", "L3 agent", "Linux bridge agent", "Metadata agent"]},
        "network_lifecycle": {"name_prefix": "task5f-private-", "created": True, "listed": True, "deleted_exact_id": True, "absent_after_delete": True},
        "boundaries": {"ens34_address_free": True, "compute_disks_unchanged": True, "routers": [], "subnets": [], "instances": [], "provider_networks": []},
    }
    validate(good)
    for mutate in (
        lambda item: item["api"].update(authenticated=False),
        lambda item: item["agents"].update(hosts=["controller"]),
        lambda item: item["network_lifecycle"].update(absent_after_delete=False),
        lambda item: item["boundaries"]["subnets"].append("unexpected"),
    ):
        evidence = copy.deepcopy(good); mutate(evidence)
        with pytest.raises((RuntimeError, ValueError)):
            validate(evidence)


def test_focused_cinder_contract_accepts_only_the_small_authorized_lifecycle() -> None:
    candidates = markdown_fenced_blocks("11-cinder-compute.md", "python")
    source = next(block for block in candidates if "def validate_cinder_lightweight_evidence" in block)
    namespace: dict[str, object] = {"__name__": "test"}
    exec(compile(ast.parse(source), "cinder-contract", "exec"), namespace)
    validate = namespace["validate_cinder_lightweight_evidence"]
    good = {
        "services": {
            "controller": ["openstack-cinder-api", "openstack-cinder-scheduler"],
            "compute": ["targetclid", "openstack-cinder-volume"],
        },
        "api_cli": {"api_reachable": True, "authenticated_cli": True},
        "backend": {"name": "compute@lvm#LVM-ISCSI", "up": True, "volume_type": "lvm"},
        "volume_lifecycle": {"size_gib": 1, "created": True, "available": True, "deleted_exact_id": True, "absent_after_delete": True},
        "disk": {"device": "/dev/sdb", "vg": "cinder-volumes", "initialized": True, "sda_touched": False, "sdc_touched": False},
        "boundaries": {"attachments": [], "snapshots": [], "swift": False, "horizon": False},
    }
    validate(good)
    for mutate in (
        lambda item: item["backend"].update(up=False),
        lambda item: item["volume_lifecycle"].update(size_gib=2),
        lambda item: item["disk"].update(device="/dev/sdc"),
        lambda item: item["boundaries"]["attachments"].append("forbidden"),
    ):
        evidence = copy.deepcopy(good); mutate(evidence)
        with pytest.raises(ValueError):
            validate(evidence)


def test_cinder_disk_classifier_rejects_root_ancestor() -> None:
    candidates = markdown_fenced_blocks("11-cinder-compute.md", "python")
    source = next(block for block in candidates if "def validate_cinder_lightweight_evidence" in block)
    namespace: dict[str, object] = {"__name__": "test"}
    exec(compile(ast.parse(source), "cinder-disk-contract", "exec"), namespace)
    classify = namespace["classify_cinder_disk_state"]
    with pytest.raises(ValueError, match="root ancestor"):
        classify(
            target="/dev/sdb", root_chain=["/dev/sda2", "/dev/sdb"], pvs_ok=True,
            pvs=[], wipefs_empty=True, blkid_rc=2, signatures=[],
        )


def test_cinder_disk_classifier_accepts_only_blank_or_exact_initialized_state() -> None:
    candidates = markdown_fenced_blocks("11-cinder-compute.md", "python")
    source = next(block for block in candidates if "def validate_cinder_lightweight_evidence" in block)
    namespace: dict[str, object] = {"__name__": "test"}
    exec(compile(ast.parse(source), "cinder-disk-contract", "exec"), namespace)
    classify = namespace["classify_cinder_disk_state"]
    assert classify(target="/dev/sdb", root_chain=["/dev/sda2", "/dev/sda"], pvs_ok=True,
                    pvs=[], wipefs_empty=True, blkid_rc=2, signatures=[]) == "blank"
    assert classify(target="/dev/sdb", root_chain=["/dev/sda2", "/dev/sda"], pvs_ok=True,
                    pvs=[("/dev/sdb", "cinder-volumes")], wipefs_empty=False, blkid_rc=0,
                    signatures=["LVM2_member"]) == "initialized"
    with pytest.raises(ValueError, match="signature"):
        classify(target="/dev/sdb", root_chain=["/dev/sda2", "/dev/sda"], pvs_ok=True,
                 pvs=[("/dev/sdb", "cinder-volumes")], wipefs_empty=False, blkid_rc=0,
                 signatures=["LVM2_member", "ext4"])
    for rows in ([('/dev/sdb', '')], [('/dev/sdb', 'foreign-vg')],
                 [('/dev/sdb', 'cinder-volumes'), ('/dev/sdb', 'cinder-volumes')]):
        with pytest.raises(ValueError, match="PV"):
            classify(target="/dev/sdb", root_chain=["/dev/sda2", "/dev/sda"], pvs_ok=True,
                     pvs=rows, wipefs_empty=True, blkid_rc=2, signatures=[])
    with pytest.raises(ValueError, match="probe"):
        classify(target="/dev/sdb", root_chain=["/dev/sda2", "/dev/sda"], pvs_ok=False,
                 pvs=[], wipefs_empty=True, blkid_rc=2, signatures=[])


def test_manual_cinder_records_are_manual_sanitized_and_disk_guarded() -> None:
    controller = manual_markdown("10-cinder-controller.md")
    compute = manual_markdown("11-cinder-compute.md")
    combined = controller + compute
    controller_steps = (
        "CREATE DATABASE cinder", "CREATE USER 'cinder'@'localhost'",
        "CREATE USER 'cinder'@'127.0.0.1'", "CREATE USER 'cinder'@'%'",
        "openstack user create --domain Default --password", "openstack role add --project service --user cinder admin",
        "openstack service create --name cinderv3", "openstack endpoint create --region RegionOne volumev3 public",
        "vi /etc/cinder/cinder.conf", "cinder-manage db sync",
        "systemctl enable --now openstack-cinder-api openstack-cinder-scheduler",
        "os_region_name = RegionOne", "openstack volume type set --property volume_backend_name=LVM-ISCSI lvm",
    )
    assert [controller.index(step) for step in controller_steps] == sorted(controller.index(step) for step in controller_steps)
    for token in (
        "openstack-local", "vi /etc/cinder/cinder.conf", "pvcreate /dev/sdb", "vgcreate cinder-volumes /dev/sdb",
        "target_helper = lioadm", "target_ip_address = 192.168.234.150",
        "systemctl enable --now targetclid", "systemctl enable --now openstack-cinder-volume",
        "openstack volume create --size 1 --type lvm", "openstack volume delete \"$volume_id\"",
        "paramiko.RejectPolicy()", "known_hosts", "53687091200", "root_chain=$(lsblk -s -nrpo NAME \"$root\")",
        "pv_rows=$(pvs --noheadings --readonly", "if [[ ${#target_vgs[@]} -eq 0 ]]; then",
        "elif [[ ${#target_vgs[@]} -eq 1 && ${target_vgs[0]} == cinder-volumes ]]; then",
    ):
        assert token in combined
    assert "! lsblk -s -nrpo NAME \"$root\" | while" not in compute
    assert "pvcreate /dev/sda" not in manual_shell_text("11-cinder-compute.md")
    assert "pvcreate /dev/sdc" not in manual_shell_text("11-cinder-compute.md")
    assert "openstack server add volume" not in manual_shell_text("11-cinder-compute.md")
    snapshots = MANUAL_INSTALL_DIR / "config-snapshots"
    required = {"controller-cinder.conf", "compute-cinder.conf", "controller-nova-cinder.conf", "compute-cinder-storage-state.txt"}
    assert required <= {path.name for path in snapshots.iterdir()}
    payloads = {name: (snapshots / name).read_text(encoding="utf-8") for name in required}
    combined_snapshots = "\n".join(payloads.values())
    assert "<SERVICE_PASSWORD>" in combined_snapshots and "<URL_ENCODED_PASSWORD>" in combined_snapshots
    assert "rabbit://openstack:@" not in combined_snapshots
    assert "my_ip = 192.168.234.151" in payloads["controller-cinder.conf"]
    assert "my_ip = 192.168.234.150" in payloads["compute-cinder.conf"]
    assert "volume_group = cinder-volumes" in payloads["compute-cinder.conf"]
    assert "protected_device=/dev/sda" in payloads["compute-cinder-storage-state.txt"]
    assert "untouched_swift_device=/dev/sdc" in payloads["compute-cinder-storage-state.txt"]


def test_focused_swift_contract_accepts_only_the_clean_lightweight_result() -> None:
    candidates = markdown_fenced_blocks("13-swift-compute.md", "python")
    source = next(block for block in candidates if "validate_swift_lightweight_evidence" in block)
    namespace: dict[str, object] = {"__name__": "test"}
    exec(compile(ast.parse(source), "swift-contract", "exec"), namespace)
    good = {
        "services": {"controller": {"openstack-swift-proxy"}, "compute": {"rsyncd", "openstack-swift-account", "openstack-swift-container", "openstack-swift-object"}},
        "rings": {"replicas": 1, "ip": "192.168.234.150", "device": "sdc"},
        "disk": {"device": "/dev/sdc", "filesystem": "xfs", "label": "swift-data", "mounted": True, "cinder_untouched": True},
        "lifecycle": {"api": True, "authenticated_cli": True, "one_object": True, "digest_matches": True, "deleted_exactly": True, "no_residue": True},
    }
    namespace["validate_swift_lightweight_evidence"](good)
    for key, value in (("rings", {"replicas": 2}), ("disk", {"device": "/dev/sdb"}), ("lifecycle", {"api": False})):
        bad = copy.deepcopy(good); bad[key] = value
        with pytest.raises(ValueError):
            namespace["validate_swift_lightweight_evidence"](bad)


def test_review_nova_student_path_is_explicit_manual_commands_in_fixed_order_not_the_validation_model() -> None:
    controller = manual_markdown("06-nova-controller.md")
    compute = manual_markdown("07-nova-compute.md")
    controller_steps = (
        "mysql -uroot", "CREATE DATABASE nova_api", "CREATE DATABASE nova_cell0",
        "CREATE USER 'nova'@'localhost'", "GRANT ALL PRIVILEGES ON nova_api.*",
        "openstack user create --domain default --password-prompt nova",
        "openstack role add --project service --user nova admin",
        "openstack service create --name nova --description \"OpenStack Compute\" compute",
        "openstack endpoint create --region RegionOne compute public http://controller:8774/v2.1",
        "openstack endpoint create --region RegionOne compute internal http://controller:8774/v2.1",
        "openstack endpoint create --region RegionOne compute admin http://controller:8774/v2.1",
        "vi /etc/nova/nova.conf", "[api_database]", "[keystone_authtoken]", "[placement]",
        "nova-manage api_db sync", "nova-manage cell_v2 map_cell0",
        "nova-manage cell_v2 create_cell --name=cell1", "nova-manage db sync",
        "systemctl enable --now openstack-nova-api", "systemctl enable --now openstack-nova-scheduler",
        "systemctl enable --now openstack-nova-conductor", "systemctl enable --now openstack-nova-novncproxy",
    )
    positions = [controller.index(step) for step in controller_steps]
    assert positions == sorted(positions), "controller manual command block was deleted or reordered"

    compute_steps = (
        "vi /etc/nova/nova.conf", "[keystone_authtoken]", "[vnc]", "[glance]", "[placement]", "virt_type = qemu",
        "systemctl enable --now libvirtd", "systemctl enable --now openstack-nova-compute",
        "nova-manage cell_v2 discover_hosts --by-service",
    )
    positions = [compute.index(step) for step in compute_steps]
    assert positions == sorted(positions), "compute manual command block was deleted or reordered"
    appendix = compute.index("附录：验证用顺序模型")
    assert appendix > positions[-1]
    assert "学生不得运行它来安装 OpenStack" in compute


def test_review_nova_collectors_and_post_write_validators_are_real_and_fail_closed(tmp_path: Path) -> None:
    grant_ns = _nova_python_function_namespace("06-nova-controller.md", "collect_nova_grant_evidence")
    identity_ns = _nova_python_function_namespace("06-nova-controller.md", "validate_nova_identity_evidence")
    controller_config_ns = _nova_python_function_namespace("06-nova-controller.md", "validate_written_nova_config")
    compute_config_ns = _nova_python_function_namespace("07-nova-compute.md", "validate_written_compute_nova_config")
    schema_ns = _nova_python_function_namespace("06-nova-controller.md", "validate_nova_controller_schema")

    account = {
        "global": [["USAGE", "NO"]],
        "schema": [[database, privilege, "NO"] for database in sorted(grant_ns["EXPECTED_NOVA_DATABASES"])
                   for privilege in sorted(grant_ns["EXPECTED_SCHEMA_PRIVILEGES"])],
        "table": [], "column": [], "routine": [],
    }
    class Cursor:
        def __init__(self) -> None:
            self.results = [[("nova", host) for host in ("%", "127.0.0.1", "localhost")]]
            for _host in ("%", "127.0.0.1", "localhost"):
                self.results.extend([account["global"], account["schema"], account["table"], account["column"], account["routine"]])
            self.results.extend([[], []]); self.index = -1; self.calls: list[tuple[str, object]] = []
        def execute(self, sql: str, parameters: object = None) -> None:
            self.calls.append((sql, parameters)); self.index += 1
        def fetchall(self) -> object: return self.results[self.index]
    cursor = Cursor()
    grant_evidence = grant_ns["collect_nova_grant_evidence"](cursor)
    grant_ns["validate_nova_grant_evidence"](grant_evidence)
    assert len(cursor.calls) == 18 and all("authentication_string" not in sql for sql, _ in cursor.calls)

    identity = {
        "user": {"id": "user-id", "name": "nova", "domain_id": "default", "enabled": True},
        "assignment": {"Role": "role-id", "User": "user-id", "Project": "project-id", "Group": "", "Domain": "", "System": "", "Inherited": False},
        "service": {"id": "service-id", "name": "nova", "type": "compute", "enabled": True},
        "endpoints": [{"id": f"endpoint-{interface}", "interface": interface, "region": "RegionOne",
                       "service_id": "service-id", "url": "http://controller:8774/v2.1", "enabled": True}
                      for interface in ("admin", "internal", "public")],
        "service_project_id": "project-id", "admin_role_id": "role-id",
    }
    identity_ns["validate_nova_identity_evidence"](identity)
    for mutate in (
        lambda e: e["endpoints"].pop(), lambda e: e["assignment"].update(Project="wrong"),
        lambda e: e["service"].update(type="network"),
    ):
        evidence = copy.deepcopy(identity); mutate(evidence)
        with pytest.raises(ValueError): identity_ns["validate_nova_identity_evidence"](evidence)

    password = "p@ss:/word"
    for namespace, builder, validator, name in (
        (controller_config_ns, "build_nova_config", "validate_written_nova_config", "controller.conf"),
        (compute_config_ns, "build_compute_nova_config", "validate_written_compute_nova_config", "compute.conf"),
    ):
        target = tmp_path / name; target.write_text(namespace[builder](password), encoding="utf-8", newline="\n")
        metadata = os.lstat(target)
        class MetadataOps:
            @staticmethod
            def lstat(_path: Path) -> object:
                return types.SimpleNamespace(st_mode=stat.S_IFREG | 0o640, st_uid=101, st_gid=102,
                                             st_nlink=1, st_dev=metadata.st_dev, st_ino=metadata.st_ino)
        namespace[validator](target, password, 101, 102, ops=MetadataOps())
        target.write_text("[DEFAULT]\nwrong = true\n", encoding="utf-8")
        with pytest.raises(ValueError): namespace[validator](target, password, 101, 102, ops=MetadataOps())

    good_schema = {
        "query_ok": True,
        "api": {"tables": 32, "head": "b30f573d3377"},
        "main": {"tables": 110, "head": "960aac0e09ea"},
        "cell0": {"tables": 110, "head": "960aac0e09ea"},
        "cells": {"query_ok": True, "rows": [
            {"name": "cell0", "uuid": "00000000-0000-0000-0000-000000000000", "disabled": False},
            {"name": "cell1", "uuid": "22222222-2222-4222-8222-222222222222", "disabled": False},
        ]},
        "upgrade": {"rc": 0, "successes": 7, "failures": 0, "warnings": 0},
    }
    schema_ns["validate_nova_controller_schema"](good_schema)
    for mutate in (lambda e: e["api"].update(tables=31), lambda e: e["main"].update(head="wrong"),
                   lambda e: e["cells"]["rows"].pop(), lambda e: e["upgrade"].update(successes=6)):
        evidence = copy.deepcopy(good_schema); mutate(evidence)
        with pytest.raises((RuntimeError, ValueError)): schema_ns["validate_nova_controller_schema"](evidence)
