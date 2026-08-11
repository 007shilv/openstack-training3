"""Static safety and supply-chain contracts for the controlled deployment copy."""

from __future__ import annotations

import ast
import json
import os
import re
import shlex
import subprocess
import tempfile
import textwrap
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
