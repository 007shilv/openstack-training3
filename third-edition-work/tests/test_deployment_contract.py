"""Static safety and supply-chain contracts for the controlled deployment copy."""

from __future__ import annotations

import json
import os
import re
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


def script_text(script_name: str) -> str:
    return (SCRIPTS_DIR / script_name).read_text(encoding="utf-8")


def all_script_paths() -> list[Path]:
    return sorted(SCRIPTS_DIR.glob("*.sh"))


def device_references(text: str) -> set[str]:
    return set(re.findall(r"/dev/sd[a-z]\b", text))


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
    offenders = [path.name for path in all_script_paths() if "192.168.234.152" in script_text(path.name)]
    assert not offenders, f"legacy .152 address remains in: {offenders}"


def test_management_addresses_are_bound_to_their_network_role_scripts() -> None:
    assert 'CONTROLLER_IP="192.168.234.151/24"' in script_text("01-controller-network.sh")
    assert 'COMPUTE_IP="192.168.234.150/24"' in script_text("02-compute-network.sh")


def test_cinder_is_limited_to_sdb() -> None:
    text = script_text("14-compute-cinder.sh")
    assert 'CINDER_DEVICE="/dev/sdb"' in text
    assert device_references(text) == {"/dev/sdb"}, "Cinder may reference only /dev/sdb"


def test_swift_is_limited_to_sdc() -> None:
    text = script_text("16-compute-swift.sh")
    assert 'SWIFT_DEVICE="/dev/sdc"' in text
    assert device_references(text) == {"/dev/sdc"}, "Swift may reference only /dev/sdc"


def test_destructive_commands_never_target_sda() -> None:
    command = r"(?:pvcreate|mkfs(?:\.[A-Za-z0-9_-]+)?|wipefs|dd|parted|fdisk)"
    offending_lines: list[str] = []
    for path in all_script_paths():
        for line_number, line in enumerate(script_text(path.name).splitlines(), start=1):
            code = line.split("#", maxsplit=1)[0]
            if re.search(rf"\b{command}\b", code) and "/dev/sda" in code:
                offending_lines.append(f"{path.name}:{line_number}: {line.strip()}")
    assert not offending_lines, "destructive command targets /dev/sda:\n" + "\n".join(offending_lines)


def test_antelope_release_configuration_remains_present() -> None:
    for script_name in ("03-controller-base.sh", "04-compute-base.sh"):
        text = script_text(script_name)
        assert "openstack-release-antelope" in text, f"{script_name} no longer installs the Antelope release package"
        assert "OpenStack_Antelope" in text, f"{script_name} no longer retains Antelope repository handling"


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
