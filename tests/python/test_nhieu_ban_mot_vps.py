"""Cài được NHIỀU bản Javis trên cùng một VPS, mỗi bản một link riêng.

    python tests/run.py nhieu_ban

Không cần pytest, không cần Docker, không chạm mạng.

Bối cảnh (chủ repo báo, 2026-08-12): "Javis đang không cài được nhiều bản trên cùng 1 VPS".
Bản thân app đã đa-bản-được từ lâu (JAVIS_PORT, JAVIS_STATE_DIR đều đọc từ biến môi trường);
chỗ chặn nằm hết ở FILE CÀI ĐẶT, và đều là cùng một loại lỗi: một cái tên hoặc một con số bị
đóng cứng ở nơi Docker/Traefik/systemd định danh theo phạm vi TOÀN MÁY.

Năm cái tên toàn cục đó:
  1. `container_name: javis`            -> bản hai chết ngay lúc `up` ("name is already in use")
  2. cổng máy chủ `7777:7777`           -> bản hai chết ("port is already allocated")
  3. tên router/service Traefik `javis` -> bản sau đè bản trước, một trong hai tên miền chết
  4. `/etc/systemd/system/javis.service`-> install.sh bản hai ghi đè dịch vụ bản một
  5. `~/.codex/javis.config.toml`       -> hai bản native chung $HOME ghi đè profile của nhau,
     Codex bản A quay sang gọi hub bản B. Lỗi này KHÔNG hiện ra ở đâu cả.

Test khoá cả năm, và khoá luôn điều kiện quan trọng nhất: bỏ trống mọi biến thì mọi thứ phải
render RA Y HỆT TRƯỚC ĐÂY - người đang chạy một bản không được bắt đi sửa gì.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import re
import sys

import yaml

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::([-?])([^}]*))?\}")


def expand(text, env):
    """Bung ${VAR}, ${VAR:-mặc định}, ${VAR:?lỗi} đúng như docker compose làm.

    Tự làm thay vì gọi `docker compose config` để test chạy được ở CI không có Docker.
    """
    def _one(m):
        ten, dau, phu = m.group(1), m.group(2), m.group(3)
        v = env.get(ten, "")
        if v:
            return v
        if dau == "-":
            return phu
        return ""
    return _VAR.sub(_one, text)


def load(name, env=None):
    return yaml.safe_load(expand((ROOT / name).read_text(encoding="utf-8"), env or {}))


def src(name):
    return (ROOT / name).read_text(encoding="utf-8")


BAN2 = {"JAVIS_NAME": "javis-shop", "JAVIS_HOST_PORT": "7778",
        "JAVIS_BIND": "127.0.0.1", "DOMAIN_NAME": "shop.tencuaban.com"}

# ============================================================
# 1. Bỏ trống mọi biến => y hệt hành vi cũ (không ai phải sửa gì)
# ============================================================
for f in ("docker-compose.yml", "docker-compose.build.yml", "docker-compose.hostinger.yml"):
    j = load(f)["services"]["javis"]
    check(f"{f}: mặc định vẫn là container 'javis'", j["container_name"] == "javis")
    check(f"{f}: mặc định vẫn nghe cổng 7777 công khai",
          any(str(p).endswith("7777:7777") and not str(p).startswith("127.")
              for p in j["ports"]))

# ============================================================
# 2. Đặt biến => MỌI tên toàn cục đều tách bạch
# ============================================================
vps = load("docker-compose.yml", BAN2)["services"]
check("compose VPS: container mang tên của bản", vps["javis"]["container_name"] == "javis-shop")
check("compose VPS: cổng máy chủ đổi theo bản",
      any("7778:7777" in str(p) for p in vps["javis"]["ports"]))
check("compose VPS: chỉ MỘT binding cổng (khai thêm ở override là Docker báo cổng đã chiếm)",
      len(vps["javis"]["ports"]) == 1)
check("compose VPS: tunnel mang tên của bản", vps["tunnel"]["container_name"] == "javis-shop-tunnel")
check("compose VPS: watchtower mang tên của bản",
      vps["watchtower"]["container_name"] == "javis-shop-watchtower")
# Watchtower ghi cứng "javis" thì bản này đi cập nhật và restart container của bản KHÁC.
check("compose VPS: watchtower theo dõi ĐÚNG container của bản mình",
      str(vps["watchtower"]["command"]).strip() == "javis-shop")

host = load("docker-compose.hostinger.yml", BAN2)["services"]["javis"]
check("Hostinger: container mang tên của bản", host["container_name"] == "javis-shop")
check("Hostinger: cổng dự phòng đổi theo bản",
      any("7778:7777" in str(p) for p in host["ports"]))
nhan = " ".join(host["labels"])
for phan in ("routers.javis-shop.rule", "routers.javis-shop.service=javis-shop",
             "services.javis-shop.loadbalancer"):
    check(f"Hostinger: nhãn Traefik mang tên của bản ({phan})", phan in nhan)
check("Hostinger: nhãn Traefik lái đúng tên miền của bản",
      "Host(`shop.tencuaban.com`)" in nhan)
check("Hostinger: KHÔNG còn router tên trần 'javis' khi đã đặt JAVIS_NAME",
      "routers.javis." not in nhan)

# ============================================================
# 3. Proxy dùng chung: một cái cho cả máy, đứng NGOÀI mọi bản
# ============================================================
proxy = load("docker-compose.proxy.yml")
psvc = proxy["services"]["proxy"]
check("proxy: giữ cổng 80 và 443", {"80:80", "443:443"} <= {str(p) for p in psvc["ports"]})
check("proxy: chỉ đọc Docker socket (:ro), không cấp quyền ghi",
      any("/var/run/docker.sock" in str(v) and str(v).endswith(":ro") for v in psvc["volumes"]))
check("proxy: chỉ nhìn container trên mạng javis-web",
      psvc["environment"]["CADDY_INGRESS_NETWORKS"] == "javis-web")
check("proxy: mạng javis-web là mạng NGOÀI (dựng một lần cho cả máy)",
      proxy["networks"]["javis-web"].get("external") is True)
check("proxy: giữ chứng chỉ trong volume (restart không xin lại, khỏi cạn rate-limit)",
      any(str(v).startswith("proxy-data:") for v in psvc["volumes"]))

multi = load("docker-compose.multi.yml", BAN2)
msvc = multi["services"]["javis"]
check("multi: giữ CẢ mạng default (khai networks ở service là THAY danh sách, không cộng thêm)",
      set(msvc["networks"]) == {"default", "javis-web"})
check("multi: gắn nhãn tên miền cho proxy tự phát hiện",
      msvc["labels"]["caddy"] == "shop.tencuaban.com")
check("multi: nhãn trỏ đúng cổng trong container",
      "7777" in str(msvc["labels"]["caddy.reverse_proxy"]))
# Cái bẫy đắt nhất của compose nhiều file: `ports` bị NỐI CHỒNG chứ không thay thế.
check("multi: KHÔNG khai lại ports (nối chồng là hai binding cùng một cổng)",
      "ports" not in msvc)
check("multi: thu cổng về loopback bằng biến JAVIS_BIND ở file gốc",
      "JAVIS_BIND" in src("docker-compose.yml") and "JAVIS_BIND" in src("docker-compose.multi.yml"))
check("multi: thiếu DOMAIN_NAME thì báo lỗi rõ chứ không dựng site rỗng",
      "${DOMAIN_NAME:?" in src("docker-compose.multi.yml"))
check("bản Caddy cũ nói rõ nó chỉ dành cho máy chạy MỘT bản",
      "MỘT BẢN JAVIS" in src("docker-compose.https.yml"))

# ============================================================
# 4. Native: tên dịch vụ systemd + cổng đều theo bản
# ============================================================
ins = src("install.sh")
check("install.sh: tên dịch vụ lấy từ JAVIS_NAME", 'SVC="${JAVIS_NAME:-javis}"' in ins)
check("install.sh: cổng lấy từ JAVIS_PORT", 'PORT="${JAVIS_PORT:-7777}"' in ins)
check("install.sh: ghi unit theo tên bản, không đè javis.service",
      '/etc/systemd/system/$SVC.service' in ins)
check("install.sh: không còn --port 7777 đóng cứng", "--port 7777" not in ins)
check("install.sh: chặn tên có ký tự lạ trước khi ghi vào /etc/systemd",
      "JAVIS_NAME chi duoc dung" in ins)

upd = src("update.sh")
check("update.sh: đọc JAVIS_NAME từ .env của thư mục đang đứng", "JAVIS_NAME" in upd)
check("update.sh: restart ĐÚNG dịch vụ của bản mình, không phải 'javis' cứng",
      'systemctl restart "$NAME"' in upd)
check("update.sh: dò container theo tên bản", 'grep -qx "$NAME"' in upd)

# ============================================================
# 5. Profile Codex: hai bản chung $HOME không được ghi đè nhau
# ============================================================
os.environ.pop("JAVIS_PORT", None)
import mcp_hub  # noqa: E402

check("cổng mặc định giữ nguyên tên 'javis' (máy đang chạy không phải sinh file mới)",
      mcp_hub.codex_profile_name() == "javis")
os.environ["JAVIS_PORT"] = "7778"
check("cổng khác => profile khác, không đè nhau", mcp_hub.codex_profile_name() == "javis-7778")
check("đường dẫn file đi theo tên profile",
      mcp_hub.codex_profile_path().name == "javis-7778.config.toml")
os.environ.pop("JAVIS_PORT", None)
check("bỏ biến thì quay lại tên cũ", mcp_hub.codex_profile_name() == "javis")

# Hai nơi ghi profile (hub bật / hub tắt) phải dùng CHUNG một tên, lệch nhau là Codex đọc
# một file mà Javis ghi file kia.
main_src = (SERVER / "main.py").read_text(encoding="utf-8")
check("main.py dùng chung hàm đặt tên của hub, không tự ghi 'javis'",
      "mcp_hub.codex_profile_path()" in main_src
      and "mcp_hub.codex_profile_name()" in main_src)
check("không còn đường dẫn javis.config.toml đóng cứng trong server/",
      'javis.config.toml"' not in main_src
      and 'javis.config.toml"' not in (SERVER / "mcp_hub.py").read_text(encoding="utf-8"))

# ============================================================
# 6. Tài liệu phải có đường đi, không thì tính năng coi như không tồn tại
# ============================================================
docs = src("DEPLOY.md") + src("README.md")
check("DEPLOY/README có mục cài nhiều bản", "nhiều bản" in docs.lower())
for f in ("docker-compose.proxy.yml", "docker-compose.multi.yml"):
    check(f"tài liệu nhắc tới {f}", f in docs)

if _fails:
    print(f"\nFAIL - test_nhieu_ban_mot_vps: {len(_fails)} lỗi: {_fails}")
    sys.exit(1)
print("\nOK - test_nhieu_ban_mot_vps: tất cả pass")
