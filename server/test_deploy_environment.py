"""Hợp đồng deploy: form Environment chỉ hiện biến người cài cần dùng.

Chạy: python server/test_deploy_environment.py
"""
from pathlib import Path
import re
import sys

import yaml


ROOT = Path(__file__).resolve().parent.parent
FAIL = []


def check(label, ok):
    print(("PASS" if ok else "FAIL") + ": " + label)
    if not ok:
        FAIL.append(label)


def compose(name):
    return yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))


hostinger = compose("docker-compose.hostinger.yml")["services"]["javis"]
hostinger_env = set((hostinger.get("environment") or {}).keys())
check(
    "Hostinger chỉ hiện ba trường có ý nghĩa",
    hostinger_env
    == {"DOMAIN_NAME", "JAVIS_ADMIN_USER", "JAVIS_ADMIN_PASSWORD"},
)
check(
    "biến target Hostinger được giấu khỏi form Environment",
    "JAVIS_DEPLOY_TARGET=hostinger" in " ".join(hostinger.get("command") or []),
)

internal = {
    "JAVIS_HOST",
    "JAVIS_PORT",
    "JAVIS_REQUIRE_LOGIN",
    "JAVIS_STATE_DIR",
    "BRAIN_PATH",
    "BRAINS_DIR",
    "OBSIDIAN_VAULT_PATH",
    "CLAUDE_CWD",
    "JAVIS_DEPLOY_TARGET",
}
check("Hostinger không lộ biến kỹ thuật", not (hostinger_env & internal))
check(
    "Hostinger không tạo thêm trường COMPOSE_PROJECT_NAME",
    "${COMPOSE_PROJECT_NAME" not in (ROOT / "docker-compose.hostinger.yml").read_text(encoding="utf-8"),
)
hostinger_vars = set(
    re.findall(
        r"\$\{([A-Z0-9_]+)",
        (ROOT / "docker-compose.hostinger.yml").read_text(encoding="utf-8"),
    )
)
check("Hostinger chỉ tham chiếu đúng ba biến nhập liệu", hostinger_vars == hostinger_env)

vps = compose("docker-compose.yml")["services"]["javis"]
check(
    "VPS production chỉ giữ token Watchtower cần chia sẻ",
    set((vps.get("environment") or {}).keys()) == {"WATCHTOWER_TOKEN"},
)

build = compose("docker-compose.build.yml")["services"]["javis"]
check("compose build không lặp mặc định Docker image", not build.get("environment"))

dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
for key in (
    "JAVIS_HOST=0.0.0.0",
    "JAVIS_PORT=7777",
    "JAVIS_STATE_DIR=/data/state",
    "BRAINS_DIR=/brains",
    "OBSIDIAN_VAULT_PATH=/data/vault",
    "CLAUDE_CWD=/app",
):
    check("Docker image vẫn có mặc định " + key, key in dockerfile)

docs = "\n".join(
    (ROOT / name).read_text(encoding="utf-8")
    for name in ("README.md", "DEPLOY.md", "docs/16-cau-hinh-env.md")
)
check(
    "tài liệu nói rõ ba trường Hostinger",
    all(k in docs for k in ("DOMAIN_NAME", "JAVIS_ADMIN_USER", "JAVIS_ADMIN_PASSWORD"))
    and "chỉ còn 3 trường" in docs,
)

if FAIL:
    print("\nFAILED:", ", ".join(FAIL))
    sys.exit(1)
print("\nOK - test_deploy_environment: tất cả pass")
