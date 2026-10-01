"""Watchtower đi kèm phải là bản nói chuyện được với Docker Engine mới.

Chạy: python tests/run.py watchtower_image

Bối cảnh (2026-10-01): máy cài mới không bấm "Cập nhật ngay" được. Log container
`javis-watchtower` trên VPS Hostinger:
    client version 1.25 is too old. Minimum supported API version is 1.40
Image `containrrr/watchtower` mặc định nói Docker API 1.25 và repo đó đã archive, nên nó
Restarting mãi, app không nối được `watchtower:8080` và nút cập nhật chết trên MỌI máy mới.
Bản fork `nicholas-fedor/watchtower` tự thương lượng phiên bản API.
"""
from _paths import ROOT  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import sys

import yaml


FAIL = []


def check(label, ok):
    print(("PASS" if ok else "FAIL") + ": " + label)
    if not ok:
        FAIL.append(label)


for name in ("docker-compose.yml", "docker-compose.hostinger.yml"):
    svc = yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))["services"]["watchtower"]
    image = str(svc["image"])
    env = svc.get("environment") or {}

    check(f"CANARY {name}: KHÔNG dùng containrrr/watchtower (archive, kẹt Docker API 1.25)",
          "containrrr" not in image)
    check(f"{name}: dùng bản fork còn bảo trì", image.startswith("ghcr.io/nicholas-fedor/watchtower"))
    # `:latest` sẽ kéo v2 về, mà v2 bỏ các biến HTTP API kiểu cũ: nút chết lần nữa không ai hay.
    check(f"{name}: ghim major 1, không trôi theo latest", image.endswith(":1"))
    # App gọi POST http://watchtower:8080/v1/update kèm Bearer token (server/main.py, /update).
    check(f"{name}: bật endpoint update của HTTP API",
          "update" in str(env.get("WATCHTOWER_HTTP_API_ENDPOINTS", "")).replace(",", " ").split())
    check(f"{name}: có token cho HTTP API", bool(env.get("WATCHTOWER_HTTP_API_TOKEN")))
    # Ghim DOCKER_API_VERSION là vá tạm: Docker còn nâng mức tối thiểu, ghim là chết lại.
    check(f"{name}: không ghim cứng DOCKER_API_VERSION", "DOCKER_API_VERSION" not in env)

if FAIL:
    print("\nFAILED:", ", ".join(FAIL))
    sys.exit(1)
print("\nOK - test_watchtower_image: tất cả pass")
