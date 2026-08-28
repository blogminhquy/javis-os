# syntax=docker/dockerfile:1
# ============================================================================
# Javis OS - container image
# "Brain" = Claude Code CLI (npm global). FastAPI app served by uvicorn.
# Code tree is immutable; ALL mutable state lives on the /data volume and the
# Claude auth volume (~/.claude). Node comes from the official image (Debian's
# nodejs lags LTS), and tini runs as PID 1 so signals reach uvicorn cleanly.
# ============================================================================

# ---------- Stage 1: Node 22 LTS source ----------
# Copy node/npm/npx from the official image instead of apt (Debian's nodejs lags LTS).
FROM node:22-bookworm-slim AS node_source

# ---------- Stage 2: runtime ----------
FROM python:3.12-slim

# OCI image labels: Docker Manager (Hostinger) + registry đọc để hiện cột "Guide"
# (Documentation / Quick start / Source). Trỏ về docs trên GitHub.
LABEL org.opencontainers.image.title="Javis OS" \
      org.opencontainers.image.description="AI operating layer: chat + voice + second brain + tự động hoá, xây trên CLI của nhà cung cấp AI (Claude Code, ChatGPT/Codex)." \
      org.opencontainers.image.url="https://github.com/blogminhquy/javis-os" \
      org.opencontainers.image.source="https://github.com/blogminhquy/javis-os" \
      org.opencontainers.image.documentation="https://github.com/blogminhquy/javis-os/blob/main/docs/README.md" \
      org.opencontainers.image.licenses="MIT" \
      com.hostinger.documentation="https://github.com/blogminhquy/javis-os/blob/main/docs/README.md" \
      com.hostinger.quickstart="https://github.com/blogminhquy/javis-os/blob/main/QUICKSTART.md"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps: ca-certs (TLS), git (Claude tools), ripgrep (fast search used by
# Claude's Grep), ffmpeg (edge-tts mp3), curl, tini (PID-1 reaper for the node
# subprocesses Claude spawns).
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl git ripgrep ffmpeg tini \
    && rm -rf /var/lib/apt/lists/*

# Node 22 LTS from stage 1 (npm/npx are symlinks → recreate on PATH).
COPY --from=node_source /usr/local/bin/node /usr/local/bin/node
COPY --from=node_source /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
RUN ln -sf /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -sf /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

# The brain: Claude Code CLI, installed globally. Overridable build-arg.
ARG CLAUDE_CLI_VERSION=latest
RUN npm install -g "@anthropic-ai/claude-code@${CLAUDE_CLI_VERSION}" \
    && npm cache clean --force \
    && claude --version

# Codex CLI - cho provider ChatGPT subscription (OpenAI OAuth). Đăng nhập 1 lần trên trang Models
# (token lưu ở volume .codex).
#
# HẾT best-effort từ 0.35.7: lối `|| echo` cũ nuốt lỗi cài, và nó đã xảy ra thật - có image phát
# hành ra ngoài KHÔNG có codex, người mới cài đăng nhập ChatGPT xanh (OAuth do Javis tự lo, không
# cần binary) rồi vào chat mới vỡ, không có lấy một dòng lỗi chỉ đường (báo cáo 16/08). Thiếu
# codex thì build phải ĐỎ để CI chặn lại, không được ship image què.
RUN npm install -g @openai/codex && npm cache clean --force && codex --version

# Gemini CLI KHÔNG còn được cài sẵn (bỏ ở 0.29.1).
#
# 0.28.8 có cài, nhưng lúc đó chưa ai biết Google đã ngừng phục vụ Gemini CLI cho MỌI tài khoản
# cá nhân từ 18/06/2026 (miễn phí, AI Pro, Ultra - mã UNSUPPORTED_CLIENT). Với gần như mọi
# người cài Javis, gói đó nay tải về một CLI không dùng được: phình image, chậm build, và tệ
# hơn là làm thẻ đã chết trông như đã sẵn sàng.
#
# Engine đó đã GỠ HẲN khỏi repo ở 0.50.0. Đường Google cho tài khoản cá nhân hiện nay là
# Antigravity CLI (`agy`); đường xAI dùng gói SuperGrok / X Premium+ là Grok Build (`grok`).
# Cả hai đều là script tải về chạy thẳng, không cài qua npm nên không nằm trong image.

WORKDIR /app

# Layer-cached Python deps (copy requirements first so app changes don't re-pip).
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# App source.
COPY . .

# Non-root runtime user. Code stays root-owned + read-only; state on volumes.
RUN useradd -u 10001 -m -d /home/javis javis \
    && mkdir -p /data/state /data/vault /brains /home/javis/.claude /home/javis/.codex \
    && chown -R javis:javis /data /brains /home/javis

# Writable state under /data; ALL second brains under /brains (mount riêng → git-backup được).
ENV JAVIS_HOST=0.0.0.0 \
    JAVIS_PORT=7777 \
    JAVIS_STATE_DIR=/data/state \
    BRAIN_PATH=/data/brain \
    BRAINS_DIR=/brains \
    OBSIDIAN_VAULT_PATH=/data/vault \
    CLAUDE_CWD=/app \
    HOME=/home/javis \
    PATH=/usr/local/bin:$PATH

# Codex (ChatGPT) bọc mọi lệnh đọc/ghi file của nó bằng bubblewrap. Bubblewrap cần tạo được user
# namespace + đổi propagation của `/`, mà container này chạy user thường, không có CAP_SYS_ADMIN,
# và Ubuntu 24.04 còn chặn user namespace không đặc quyền bằng AppArmor. Nên Ở ĐÂY rào đó không
# phải "chặt hơn" mà là "chết hẳn": mọi việc nền chạy bằng ChatGPT đều trả
# `bwrap: Failed to make / slave: Permission denied` cho TỪNG lệnh một, và loop không đọc nổi
# một file nào (chủ repo báo 2026-08-07 kèm ảnh). Tắt rào riêng của Codex, để CHÍNH CONTAINER
# làm rào.
#
# Đánh đổi phải nói rõ: Codex không có allowlist per-call như Claude, nên với cờ này thì loop
# mức `suggest` chạy bằng Codex không còn thứ gì chặn nó ghi file trong container. Các rào về
# tiền/đơn/đăng bài/gửi tin KHÔNG bị ảnh hưởng - chúng nằm ở MCP Hub chứ không ở sandbox.
# Muốn bật lại rào: đặt JAVIS_CODEX_SANDBOX=auto và cấp quyền cho container (vd
# `security_opt: [apparmor:unconfined]`) để bubblewrap khởi động được.
ENV JAVIS_CODEX_SANDBOX=off

USER javis

# Persist state (/data) + brains (/brains) + Claude auth + Codex auth (login ChatGPT).
VOLUME ["/data", "/brains", "/home/javis/.claude", "/home/javis/.codex"]

EXPOSE 7777

# Healthcheck hits the public /health endpoint with stdlib only (no curl).
HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD python -c "import urllib.request,os,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+os.getenv('JAVIS_PORT','7777')+'/health',timeout=4).status==200 else 1)" || exit 1

# tini reaps node subprocesses; entrypoint.sh links ~/.local, ~/.antigravity, ~/.config
# into /data/home first so CLI người dùng tự cài (agy) + đăng nhập của nó SỐNG QUA UPDATE
# (trước đây HOME không nằm trên volume nào → mỗi lần đổi image là cài + đăng nhập lại).
# uvicorn launched with --app-dir server because main.py uses the "main:app" import
# string and `from claude_cli import ...`.
ENTRYPOINT ["/usr/bin/tini", "--", "/app/docker/entrypoint.sh"]
CMD ["sh", "-c", "python -m uvicorn main:app --app-dir server --host ${JAVIS_HOST} --port ${JAVIS_PORT}"]
