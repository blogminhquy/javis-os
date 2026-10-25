"""Exact sources of unreleased intermediate improvement schemas, vendored for migration tests.

Schema 7 to 10 were built on the M2D1 engineering branch and never shipped on their own; the
branch was squash-merged into 0.314.0, so those commits are not reachable from main and CI's
shallow checkout cannot `git show` them. The bytes below were copied verbatim with `git show`
from the named commits; the hashes pin them so a changed fixture fails loudly instead of
silently testing something else. Stored as .py.txt so nothing imports or lints them as live code.
Released readers (0.292.0, 0.293.0, 0.296.0) are still fetched from their release commits by CI.
"""
from __future__ import annotations

import hashlib
import sys
import types
from pathlib import Path

ROOT = Path(__file__).with_name("fixtures") / "improvement_history"
COMMITS = {
    "79e5985c": "79e5985c",
    "3fad8de8": "3fad8de8",
    "c93cb71825accbb7f07cb5633902d706ce0f51c9": "c93cb718",
    "c93cb718": "c93cb718",
    "dbdec4eb622bc46a0b025753a079b5f8821ef4a6": "dbdec4eb",
    "dbdec4eb": "dbdec4eb",
}
HASHES = {
    ("3fad8de8", "improvement_store"): "6951a65738070fd3a344141b66071f615e97e590a51dcbccfe46f0a5fb9a2255",
    ("79e5985c", "improvement_candidate_schema"): "6d29c83299ecc9e081912f4b3cf6f549890f71abeeb3af9684e9d3f0e66ee5da",
    ("79e5985c", "improvement_case_schema"): "54554b40dc20e58d37cdcb3964fc8384ff11ae95683277352a949ad37dad6865",
    ("79e5985c", "improvement_experiment_schema"): "ac545c99df80d3bdcfef74951bd1b7342827de62820cbedd0c832b3f19abe61d",
    ("79e5985c", "improvement_operation_schema"): "53bcada765678337712051b950b26cbb285b548c66c30e07526471f808530512",
    ("79e5985c", "improvement_store"): "20b4c26c59b265ded362a0f2ead2688e6018552623cc0dd7ac08cd0e6b0dcaf3",
    ("79e5985c", "improvement_trial_schema"): "ac7066cdac48cf35213ed2591ed462d53d4f22955ea127904f568c69643dcae1",
    ("79e5985c", "improvement_view_schema"): "50b6f5c5e7a210adb76df3271d593ea5b7f53a403078145906d7f30dc3f7d172",
    ("c93cb718", "improvement_recipe_schema"): "d3ebd255ea94e9074149d691c37451e57c61851e2108ce684784ac897f561b21",
    ("c93cb718", "improvement_store"): "2cb145a20e271352e9c06a3313caa69844cfa8dae55ef15401c3d53ced7d1a06",
    ("dbdec4eb", "improvement_improver_inputs"): "cb1f6798af6e44f8801334231eb7113383ebbb6faff6a6586e9ab1e7ec1fb458",
}


def source(commit: str, name: str) -> bytes:
    short = COMMITS[commit]
    raw = (ROOT / short / (name + ".py.txt")).read_bytes()
    if hashlib.sha256(raw).hexdigest() != HASHES[(short, name)]:
        raise AssertionError(f"historical fixture {short}/{name} changed")
    return raw


def load(commit: str, name: str, module_name: str):
    module = types.ModuleType(module_name)
    sys.modules[module_name] = module
    short = COMMITS[commit]
    exec(compile(source(commit, name), f"{short}/server/{name}.py", "exec"), module.__dict__)
    return module
