"""Static safety and supply-chain contracts for the controlled deployment copy."""

from __future__ import annotations

import json
import os
import re
import shlex
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


def active_lines(text: str) -> list[str]:
    return [line for line in (strip_shell_comment(raw) for raw in text.splitlines()) if line.strip()]


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


def disk_command_targets(text: str) -> tuple[list[str], list[str]]:
    """Return resolved disk targets and fail-closed errors for unsafe unknown targets."""
    constants = shell_constants(text)
    targets: list[str] = []
    errors: list[str] = []
    for line in active_lines(text):
        parsed = command_tokens(line)
        if parsed is None:
            continue
        command, arguments = parsed
        skip_next = False
        for argument in arguments:
            if skip_next:
                skip_next = False
                continue
            if argument in {"-L", "-t", "-T", "-n", "-y", "-f"}:
                skip_next = argument in {"-L", "-t", "-T", "-n"}
                continue
            value = argument.split("=", maxsplit=1)[-1] if command == "dd" and "=" in argument else argument
            resolved = resolve_value(value, constants)
            literal = DEVICE_LITERAL.search(resolved or "")
            if literal:
                targets.append(literal.group(0))
                continue
            variable = VARIABLE_REFERENCE.match(value)
            if variable and (command in {"pvcreate", "pvremove", "wipefs", "parted", "fdisk", "sgdisk", "mkswap"} or re.search(r"(?:DEVICE|DISK|TARGET)", variable.group(1))):
                errors.append(f"{command} has unresolved disk variable {value!r}: {line.strip()}")
    return targets, errors


def destructive_disk_violations(text: str) -> list[str]:
    targets, errors = disk_command_targets(text)
    return errors + [f"destructive command targets system disk {target}" for target in targets if target.startswith("/dev/sda")]


def antelope_contract_violations(text: str) -> list[str]:
    lines = active_lines(text)
    active = "\n".join(lines)
    constants = shell_constants(text)
    violations: list[str] = []
    if resolve_value(constants.get("ANTELOPE_REPO_FILE", ""), constants) != "/etc/yum.repos.d/openstack-antelope.repo":
        violations.append("ANTELOPE_REPO_FILE is not the active openstack-antelope.repo path")
    if not any(re.search(r"\bdnf\b.*\binstall\s+openstack-release-antelope\b", line) for line in lines):
        violations.append("no active dnf install command for openstack-release-antelope")
    if not any(
        "openEuler-24.03-LTS-SP3" in line
        and "openEuler-24.03-LTS-SP2" in line
        and "ANTELOPE_REPO_FILE" in line
        for line in lines
    ):
        violations.append("no active SP3-to-SP2 correction for ANTELOPE_REPO_FILE")
    return violations


def script_text(script_name: str) -> str:
    return (SCRIPTS_DIR / script_name).read_text(encoding="utf-8")


def all_script_paths() -> list[Path]:
    return sorted(SCRIPTS_DIR.glob("*.sh"))


def load_version_matrix() -> dict[str, object]:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


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
