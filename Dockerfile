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

# Codex CLI - cho provider ChatGPT subscription (OpenAI OAuth). BEST-EFFORT: lỗi cài KHÔNG làm hỏng
# build (Claude vẫn chạy). Đăng nhập 1 lần bằng `codex login` trong terminal (token lưu ở volume .codex).
RUN (npm install -g @openai/codex && npm cache clean --force && codex --version) \
    || echo "[build] codex cài KHÔNG thành công - provider ChatGPT subscription sẽ không dùng được (các provider khác vẫn chạy)."

# Gemini CLI - bộ não thứ 9, chạy bằng ĐĂNG NHẬP GOOGLE (không cần mua API key). BEST-EFFORT
# y như Codex: registry chậm hay npm hỏng thì build vẫn qua, chỉ mất đúng engine đó.
#
# Cài sẵn ở đây vì trong container KHÔNG có đường cài sau: runtime chạy bằng `USER javis`
# (không phải root) nên `npm i -g` lúc đang chạy sẽ bị từ chối ghi vào /usr/local/lib. Trước
# thay đổi này, người dùng Docker muốn có bộ não Gemini CLI phải tự dựng lại image.
#
# KHÔNG cần volume cho ~/.gemini: refresh token nằm trong settings.json của Javis (trên volume
# /data), còn gemini_oauth.ghi_creds_cho_cli() dựng lại file credential của CLI trước mỗi lượt
# chạy. Đăng nhập một lần ở trang Models là sống qua mọi lần cập nhật container.
RUN (npm install -g @google/gemini-cli && npm cache clean --force && gemini --version) \
    || echo "[build] gemini-cli cài KHÔNG thành công - bộ não Gemini CLI sẽ không dùng được (các provider khác vẫn chạy)."

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

# tini reaps node subprocesses. uvicorn launched with --app-dir server because
# main.py uses the "main:app" import string and `from claude_cli import ...`.
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["sh", "-c", "python -m uvicorn main:app --app-dir server --host ${JAVIS_HOST} --port ${JAVIS_PORT}"]
