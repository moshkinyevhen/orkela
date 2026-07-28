#!/usr/bin/env python3

"""Reduce the exact Android 17 Emulator matrix into a fail-closed verdict."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


GUEST_HASH_SET = "android17-r06-google-apis-x86_64-4k-v1"
GUEST_FINGERPRINT = (
    "google/sdk_gphone64_x86_64/emu64xa:17/"
    "CE2A.260420.019/15611780:userdebug/dev-keys"
)

EXPECTED: dict[str, dict[str, Any]] = {
    "control-36_6_11-swiftshader": {
        "renderer": "swiftshader",
        "revision": "36.6.11",
        "build_id": 15507667,
        "binary_version": "36.6.11.0",
        "archive_sha1": "f8d8b83cf21a04966326eb1378bacda255f63b93",
        "archive_sha256": (
            "1eade4cf2df6ea8eeead4902c635897ba"
            "12aaa32aac4389eaae0fdb498a5b830"
        ),
        "archive_size": 331232577,
    },
    "candidate-37_1_10-swiftshader": {
        "renderer": "swiftshader",
        "revision": "37.1.10",
        "build_id": 15888535,
        "binary_version": "37.1.10.0",
        "archive_sha1": "489e57e560e310f9dfadf098951a713bf5651cd2",
        "archive_sha256": (
            "5ca4e61b25e4fe94224ef7af745e1c5d"
            "6901c2e957ccfb30b5f7fed3fad0e317"
        ),
        "archive_size": 334377561,
    },
    "candidate-37_1_10-swangle": {
        "renderer": "swangle",
        "revision": "37.1.10",
        "build_id": 15888535,
        "binary_version": "37.1.10.0",
        "archive_sha1": "489e57e560e310f9dfadf098951a713bf5651cd2",
        "archive_sha256": (
            "5ca4e61b25e4fe94224ef7af745e1c5d"
            "6901c2e957ccfb30b5f7fed3fad0e317"
        ),
        "archive_size": 334377561,
    },
    "candidate-37_1_10-lavapipe": {
        "renderer": "lavapipe",
        "revision": "37.1.10",
        "build_id": 15888535,
        "binary_version": "37.1.10.0",
        "archive_sha1": "489e57e560e310f9dfadf098951a713bf5651cd2",
        "archive_sha256": (
            "5ca4e61b25e4fe94224ef7af745e1c5d"
            "6901c2e957ccfb30b5f7fed3fad0e317"
        ),
        "archive_size": 334377561,
    },
    "candidate-37_2_1-swiftshader": {
        "renderer": "swiftshader",
        "revision": "37.2.1",
        "build_id": 15875889,
        "binary_version": "37.2.1.0",
        "archive_sha1": "1c39ceb4bca042b973344d252a051189d367ab83",
        "archive_sha256": (
            "3fb1f765795b284f864b9b3403d1c5e1"
            "ad0f317eb6522441460001ff660d3d7d"
        ),
        "archive_size": 346539649,
    },
    "candidate-37_2_1-swangle": {
        "renderer": "swangle",
        "revision": "37.2.1",
        "build_id": 15875889,
        "binary_version": "37.2.1.0",
        "archive_sha1": "1c39ceb4bca042b973344d252a051189d367ab83",
        "archive_sha256": (
            "3fb1f765795b284f864b9b3403d1c5e1"
            "ad0f317eb6522441460001ff660d3d7d"
        ),
        "archive_size": 346539649,
    },
    "candidate-37_2_1-lavapipe": {
        "renderer": "lavapipe",
        "revision": "37.2.1",
        "build_id": 15875889,
        "binary_version": "37.2.1.0",
        "archive_sha1": "1c39ceb4bca042b973344d252a051189d367ab83",
        "archive_sha256": (
            "3fb1f765795b284f864b9b3403d1c5e1"
            "ad0f317eb6522441460001ff660d3d7d"
        ),
        "archive_size": 346539649,
    },
}

PROMOTION_ORDER = (
    "candidate-37_2_1-swiftshader",
    "candidate-37_2_1-swangle",
    "candidate-37_2_1-lavapipe",
    "candidate-37_1_10-swiftshader",
    "candidate-37_1_10-swangle",
    "candidate-37_1_10-lavapipe",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def archive_url(build_id: int) -> str:
    return (
        "https://dl.google.com/android/repository/"
        f"emulator-linux_x64-{build_id}.zip"
    )


def validate_result(result: dict[str, Any]) -> None:
    cell_id = result.get("cell_id")
    require(cell_id in EXPECTED, f"unexpected cell ID: {cell_id!r}")
    expected = EXPECTED[cell_id]
    emulator = result["emulator"]
    guest = result["guest"]

    require(result["schema"] == 1, f"{cell_id}: schema mismatch")
    require(
        result["renderer"] == expected["renderer"],
        f"{cell_id}: requested renderer mismatch",
    )
    require(
        result["expected_control_failure"]
        == cell_id.startswith("control-"),
        f"{cell_id}: control role mismatch",
    )
    require(
        emulator["revision"] == expected["revision"],
        f"{cell_id}: archive revision mismatch",
    )
    require(
        emulator["build_id"] == expected["build_id"],
        f"{cell_id}: archive build mismatch",
    )
    require(
        emulator["archive_url"] == archive_url(expected["build_id"]),
        f"{cell_id}: archive URL mismatch",
    )
    require(
        emulator["archive_sha1"] == expected["archive_sha1"],
        f"{cell_id}: archive SHA-1 mismatch",
    )
    require(
        emulator["archive_sha256"] == expected["archive_sha256"],
        f"{cell_id}: archive SHA-256 mismatch",
    )
    require(
        emulator["archive_size"] == expected["archive_size"],
        f"{cell_id}: archive size mismatch",
    )
    require(
        emulator["expected"] == expected["binary_version"],
        f"{cell_id}: expected binary version mismatch",
    )
    require(
        emulator["observed"] == expected["binary_version"],
        f"{cell_id}: observed binary version mismatch",
    )
    require(emulator["archive_verified"], f"{cell_id}: archive unverified")
    require(
        guest["expected_hash_set"] == GUEST_HASH_SET,
        f"{cell_id}: expected guest hash-set mismatch",
    )
    require(
        guest["hash_set"] == GUEST_HASH_SET,
        f"{cell_id}: observed guest hash-set mismatch",
    )
    require(
        guest["expected_fingerprint"] == GUEST_FINGERPRINT,
        f"{cell_id}: expected fingerprint mismatch",
    )
    require(
        guest["observed_fingerprint"] == GUEST_FINGERPRINT,
        f"{cell_id}: observed fingerprint mismatch",
    )
    require(
        result["effective_renderer_count"] == 1,
        f"{cell_id}: effective renderer tuple is not singular",
    )
    require(
        bool(result["effective_renderer_line"]),
        f"{cell_id}: effective renderer tuple is missing",
    )
    require(
        result["crash_evidence_complete"],
        f"{cell_id}: crash evidence is incomplete",
    )
    require(result["boot_completed"], f"{cell_id}: boot did not complete")
    require(
        result["environment_exact"],
        f"{cell_id}: environment is not exact",
    )
    require(
        guest["selinux"] == "Enforcing",
        f"{cell_id}: SELinux mismatch",
    )
    require(
        str(guest["luma_sampling"]) in {"default", "1"},
        f"{cell_id}: luma-sampling mismatch",
    )
    require(guest["page_size"] == 4096, f"{cell_id}: page-size mismatch")
    require(
        guest["display_width"] > 0 and guest["display_height"] > 0,
        f"{cell_id}: invalid display dimensions",
    )
    require(
        result["soak"]["requested_seconds"] == 120,
        f"{cell_id}: soak duration mismatch",
    )


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit(
            "usage: reduce_emulator_probe.py "
            "<artifact-root> <assessment-json> <promotion-json>"
        )
    artifact_root = Path(sys.argv[1])
    assessment_path = Path(sys.argv[2])
    promotion_path = Path(sys.argv[3])
    paths = sorted(artifact_root.glob("**/PROBE-RESULT.json"))
    require(
        len(paths) == len(EXPECTED),
        f"expected {len(EXPECTED)} results, found {len(paths)}",
    )

    results: dict[str, dict[str, Any]] = {}
    for path in paths:
        result = json.loads(path.read_text(encoding="utf-8"))
        validate_result(result)
        cell_id = result["cell_id"]
        require(cell_id not in results, f"duplicate cell ID: {cell_id}")
        results[cell_id] = result
    require(set(results) == set(EXPECTED), "exact cell set mismatch")

    control = results["control-36_6_11-swiftshader"]
    control_reproduced = (
        control["environment_exact"]
        and control["crash_evidence_complete"]
        and control["known_control_crash_reproduced"]
        and control["known_failing_tuple"]
        and "setCurrentRenderer: swiftshader swiftshader"
        in control["effective_renderer_line"]
        and not control["stable"]
    )
    candidates = [
        cell_id
        for cell_id in PROMOTION_ORDER
        if (
            results[cell_id]["environment_exact"]
            and results[cell_id]["stable"]
            and results[cell_id]["stage1_candidate"]
            and not results[cell_id]["known_failing_tuple"]
            and results[cell_id]["soak"]["observations"] == 24
            and results[cell_id]["soak"]["healthy_observations"] == 24
            and bool(
                results[cell_id]["soak"]["initial_surfaceflinger_pid"]
            )
            and (
                results[cell_id]["soak"]["final_surfaceflinger_pid"]
                == results[cell_id]["soak"]["initial_surfaceflinger_pid"]
            )
            and results[cell_id]["soak"]["pid_changes"] == 0
            and results[cell_id]["soak"]["crash_signatures"] == 0
            and results[cell_id]["soak"]["valid_screenshots"] == 4
            and not results[cell_id]["failures"]
        )
    ]
    assessment = {
        "schema": 1,
        "scope": (
            "This exact GitHub runner, Android 17 guest hash set, "
            "Emulator archive matrix, and requested renderer set"
        ),
        "control_reproduced": control_reproduced,
        "stage1_candidates": candidates,
        "results": results,
    }
    assessment_path.write_text(
        json.dumps(assessment, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if not control_reproduced:
        raise SystemExit("exact 36.6.11 control crash was not reproduced")
    if not candidates:
        raise SystemExit(
            "no Stage-1 candidate in this exact run/runner/guest matrix"
        )

    selected = results[candidates[0]]
    promotion = {
        "schema": 1,
        "cell_id": selected["cell_id"],
        "emulator": selected["emulator"],
        "guest": {
            "hash_set": selected["guest"]["hash_set"],
            "fingerprint": selected["guest"]["observed_fingerprint"],
        },
        "requested_renderer": selected["renderer"],
        "effective_renderer": selected["effective_renderer_line"],
        "required_next_gate": {
            "cold_4k_boots": 3,
            "cold_16k_boots": 3,
            "exact_orkela_apk_pair": True,
            "sdkmanager_latest_emulator_forbidden": True,
        },
    }
    promotion_path.write_text(
        json.dumps(promotion, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, TypeError, ValueError) as error:
        raise SystemExit(f"invalid Emulator probe evidence: {error}") from error
