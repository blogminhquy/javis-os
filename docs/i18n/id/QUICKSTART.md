<!-- translated-from: QUICKSTART.en.md sha256:f0e9ed53ea49 -->
# Javis OS - Mulai cepat

*[English](../../../QUICKSTART.en.md) · [Tiếng Việt](../../../QUICKSTART.md) · [简体中文](../zh/QUICKSTART.md) · [Español](../es/QUICKSTART.md) · [日本語](../ja/QUICKSTART.md) · [हिन्दी](../hi/QUICKSTART.md) · [Português](../pt-BR/QUICKSTART.md) · [한국어](../ko/QUICKSTART.md) · [Русский](../ru/QUICKSTART.md) · [Deutsch](../de/QUICKSTART.md) · [Français](../fr/QUICKSTART.md) · **Bahasa Indonesia***

> Ini adalah terjemahan otomatis dari panduan mulai cepat berbahasa Inggris.

Jalankan Javis OS dalam beberapa menit. Panduan lengkap: [docs/en/](../../../docs/en/README.md).

## Opsi 1 - VPS Hostinger (Docker Manager, sekali klik)

1. hPanel → VPS → **Docker Manager** → **Compose** → **Compose from URL**.
2. Tempel URL ini:
   ```
   https://raw.githubusercontent.com/blogminhquy/javis-os/main/docker-compose.hostinger.yml
   ```
3. (Opsional, untuk HTTPS + domain) isi ini di kotak **Environment**:
   ```
   DOMAIN_NAME=javis.<vps-hostname>.hstgr.cloud
   ```
   (Hostname ada di hPanel → VPS, contoh `javis.srv1782015.hstgr.cloud`.)
4. **Deploy**. Tunggu 1-3 menit. Buka aplikasi dengan tombol **Open** (atau `https://<DOMAIN_NAME>`).
5. Saat pertama dijalankan, layar akan meminta Anda membuat akun admin. Setelah itu, login ke Claude Code sekali saja dari terminal container: `claude auth login --claudeai`.

Untuk memperbarui: tekan **Redeploy** di Docker Manager (image `:latest`, `pull_policy: always`). Data Brain tetap tersimpan di volume.

## Opsi 2 - Docker di mesin atau VPS apa pun

```
docker compose -f docker-compose.yml up -d
```
Buka http://localhost:7777. Untuk HTTPS lewat Caddy, tambahkan `-f docker-compose.https.yml`.

## Opsi 3 - Jalankan langsung (Windows, tanpa Docker)

1. Instal Python 3.12 + Node 22.
2. Di folder proyek, jalankan `setup.bat` sekali: script ini membuat .venv, menginstal dependency, dan menginstalkan dua engine CLI (Claude Code, Codex) untuk Anda.
3. `start-javis.bat` untuk menjalankan di background (`stop-javis.bat` untuk menghentikan).
4. Buka http://localhost:7777.

## Setelah berjalan

- **Pilih engine/model**: halaman **Models** (Claude Code, ChatGPT/Codex, Antigravity CLI, OpenRouter, OpenAI, Google Gemini, Anthropic API, Groq, Ollama).
- **Pasang koneksi** (POS, iklan, kalender, Zalo...) agar laporan memakai angka nyata: halaman **Connections**, lihat [docs/09](../../../docs/en/09-connections-and-business-data.md).
- **Backup Brain ke GitHub** agar data tidak hilang: halaman **Self-learning**, lihat [docs/18](../../../docs/en/18-github-backup.md).
- **Pantau pemakaian token**: halaman **Usage**, lihat [docs/23](../../../docs/en/23-usage-and-cost.md).

## Dokumentasi lengkap

Lihat [docs/en/README.md](../../../docs/en/README.md): satu panduan per fitur (chat/suara, knowledge graph, skill, agent, workflow, job berulang, Kanban, belajar mandiri, koneksi, Telegram, Zalo, plugin, keamanan, backup...). Panduan yang sama dalam bahasa Vietnam: [docs/README.md](../../../docs/README.md).

## Masalah umum

- **Tombol update di aplikasi tidak berfungsi di Hostinger**: memang dirancang begitu; di Hostinger gunakan **Redeploy** di Docker Manager. Tombol di aplikasi butuh Watchtower, dan Hostinger biasanya memblokir Docker socket.
- **ChatGPT/Codex bilang "model not supported"**: pilih model Codex yang valid di halaman Models (contoh `gpt-5.5`). Jangan pakai `gpt-5-mini` atau `gpt-4o`: itu model API dan akun Codex tidak bisa menjalankannya.
- Selengkapnya: [docs/17 - Pemecahan masalah](../../../docs/en/17-troubleshooting.md).
