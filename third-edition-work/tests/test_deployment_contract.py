"""Static safety and supply-chain contracts for the controlled deployment copy."""

from __future__ import annotations

import ast
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
