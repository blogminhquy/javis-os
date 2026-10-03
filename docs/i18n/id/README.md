<!-- translated-from: README.md sha256:0928e7bc4ccb -->
<div align="center">

<img src="../../../dashboard/logo.svg" width="88" alt="Logo Javis OS">

# Javis OS

### Agen AI self-hosted Anda dengan otak yang bisa diganti, dan Second Brain yang makin pintar setiap hari.

Jalankan di laptop atau VPS kecil. Ajak bicara dengan suara. Pasang Claude, ChatGPT, Grok, Gemini atau salah satu dari 12 provider, semua tool tetap ada saat Anda berganti, dan biarkan ia bekerja di background selagi Anda tidur.

[![GitHub stars](https://img.shields.io/github/stars/blogminhquy/javis-os?style=flat&logo=github&label=stars)](https://github.com/blogminhquy/javis-os/stargazers)
[![License: MIT](https://img.shields.io/badge/license-MIT-22c55e)](../../../LICENSE)
[![Last commit](https://img.shields.io/github/last-commit/blogminhquy/javis-os?color=f97316)](https://github.com/blogminhquy/javis-os/commits/main)
[![Python 3.12](https://img.shields.io/badge/python-3.12-3776ab?logo=python&logoColor=white)](../../../requirements.txt)
[![Docker](https://img.shields.io/badge/docker-ghcr.io-2496ed?logo=docker&logoColor=white)](https://github.com/blogminhquy/javis-os/pkgs/container/javis-os)
[![MCP](https://img.shields.io/badge/tools-Model%20Context%20Protocol-8b5cf6)](https://modelcontextprotocol.io)

[🇬🇧 English](../../../README.md) · [🇻🇳 Tiếng Việt](../vi/README.md) · [🇨🇳 简体中文](../zh/README.md) · [🇪🇸 Español](../es/README.md) · [🇯🇵 日本語](../ja/README.md) · [🇮🇳 हिन्दी](../hi/README.md) · [🇧🇷 Português](../pt-BR/README.md) · [🇰🇷 한국어](../ko/README.md) · [🇷🇺 Русский](../ru/README.md) · [🇩🇪 Deutsch](../de/README.md) · [🇫🇷 Français](../fr/README.md) · 🇮🇩 **Bahasa Indonesia** · [🌍 Bantu menerjemahkan](../../../CONTRIBUTING.md#translations)

[Mulai cepat](#-mulai-cepat) · [Mengapa Javis](#-mengapa-javis) · [Otak](#-12-otak-satu-toolkit) · [Fitur](#-fitur) · [Instalasi](#-instalasi) · [Dokumentasi](../../../docs/en/README.md) · [Dukungan](#-dukung-javis-os)

<br>

<img src="../../../docs/assets/screenshots/graph.jpg" alt="Dashboard Javis OS pada Brain sungguhan berisi 1.633 catatan dan 2.413 tautan: pohon file di kiri, knowledge graph di tengah dan bar chat di bawah" width="100%">

</div>

> 🌍 Ini adalah terjemahan otomatis dari README berbahasa Inggris. Javis membalas dalam bahasa apa pun yang Anda gunakan saat menulis; antarmukanya untuk saat ini tersedia dalam bahasa Inggris dan Vietnam. Dokumentasi lengkap tersedia dalam bahasa Inggris ([docs/en](../../../docs/en/README.md)). Koreksi sangat kami sambut ([CONTRIBUTING](../../../CONTRIBUTING.md#translations)).

---

## ⚡ Mulai cepat

**Cara mudahnya: biarkan AI Anda sendiri yang menginstalnya.** Berikan link repo ini ke Claude Code atau Codex di mesin Anda lalu katakan *"instalkan Javis OS untuk saya"*. Ia cukup menjalankan satu perintah:

| Mesin | Satu perintah menginstal semuanya |
|---|---|
| **Linux / macOS** | `git clone https://github.com/blogminhquy/javis-os.git javis && cd javis && chmod +x install.sh && ./install.sh` |
| **Windows** | `git clone https://github.com/blogminhquy/javis-os.git javis; cd javis; powershell -ExecutionPolicy Bypass -File install.ps1` |
| **Docker** | `curl -fsSLO https://raw.githubusercontent.com/blogminhquy/javis-os/main/docker-compose.yml && docker compose up -d` |

Lalu buka **http://localhost:7777**. Installer akan menyiapkan Python, empat otak CLI berlangganan (`claude`, `codex`, `agy`, `grok`) dan sebuah `.env`, lalu menjalankan server. Anda login ke setiap otak **di halaman Models pada dashboard**, tanpa perlu mengetik perintah lagi.

> [!NOTE]
> Menginstal CLI tambahan **setelah** Javis sudah berjalan? **Restart Javis.** Proses yang sedang berjalan tetap memakai PATH saat ia pertama dijalankan, sehingga tidak bisa melihat CLI yang diinstal belakangan.

<p align="center">
<img src="../../../docs/assets/diagrams/install-terminal.svg" width="100%" alt="Terminal animasi: installer satu baris menyiapkan Python, empat otak CLI berlangganan dan sebuah .env, lalu melaporkan bahwa Javis berjalan di http://localhost:7777">
</p>

---

## 🤔 Mengapa Javis?

Javis OS **bukan** chatbot. Ini adalah **AI agentik self-hosted** yang berjalan di mesin atau VPS Anda sendiri: ia membaca dan menulis file, memanggil tool lewat MCP, menjalankan skill, mengantrekan pekerjaan background, dan menjadwalkan dirinya sendiri. Semua itu ada di balik **dashboard yang bisa dikendalikan dengan suara** dan sebuah **Second Brain** (memori + wiki) yang mengumpulkan pengetahuan dari waktu ke waktu.

| | Chatbot biasa | **Javis OS** |
|---|---|---|
| **Otak** | Terkunci di satu model, satu panggilan API stateless per pesan | **Bisa diganti**: 12 provider, masing-masing dengan set lengkap tool, MCP, skill dan sesi, termasuk model yang berjalan di mesin Anda sendiri lewat Ollama |
| **Memori** | Lupa setiap kali sesi selesai | **Second Brain yang hidup**, yang mengingat Anda dan makin tebal di setiap percakapan |
| **Data** | Mengarang, atau tidak ada | **Angka nyata** dari koneksi yang Anda pasang (penjualan, iklan, kalender, email, pesan) |
| **Pekerjaan** | Menjawab, lalu menunggu | **Loop background, pengingat, dan antrean tugas yang dijalankan AI** yang melapor kembali ke Anda |
| **Antarmuka** | Kotak chat | Dashboard + knowledge graph + **suara hands-free** + Telegram + CLI |
| **Deployment** | Cloud milik orang lain | **Self-hosted**: Hostinger sekali klik, Docker, atau VPS apa pun |

> 💡 **Filosofinya: kemampuan ada di Javis, bukan di model.** Setiap otak mendapat kotak peralatan yang sama lewat satu hub koneksi bersama (MCP Hub). Beralih dari Claude ke Gemini tidak membuat Anda kehilangan apa pun kecuali akses shell, yang hanya dimiliki engine CLI.

<p align="center">
<img src="../../../docs/assets/diagrams/chat-to-action.svg" width="100%" alt="Diagram animasi: pesan chat masuk ke Javis, yang memilih tool terkecil yang bisa menyelesaikan pekerjaan, mulai dari menjawab langsung, mengantrekan tugas, membuat agent, workflow, pengingat, atau loop">
</p>

---

## 🧠 12 otak, satu toolkit

Pilih otak di halaman **Models** dan ganti kapan pun Anda mau. Saat ini Javis mendukung **12 provider**.

<p align="center">
<img src="../../../docs/assets/diagrams/swappable-brain.svg" width="100%" alt="Diagram animasi: inti Javis di tengah dengan toolkit-nya (MCP Hub, Skills, Second Brain, Tasks, Schedules, Plugins) di sekelilingnya, sementara 12 otak bergantian terpasang dan setiap tool tetap menyala">
</p>

| Otak | Cara bayar | Shell, web, sub-agent |
|---|---|---|
| **Claude Code** | Paket Claude Anda, atau API key Anthropic | ✅ |
| **ChatGPT** (via Codex) | Paket ChatGPT Anda | ✅ |
| **Grok Build** | Paket SuperGrok atau X Premium+ Anda | ✅ |
| **Antigravity CLI** | Paket Google Anda (deretan model yang sama dengan Antigravity IDE, termasuk Claude) | Shell ✅ |
| **OpenRouter** | API key (ratusan model di balik satu key) | via tool Javis |
| **OpenAI API** · **Anthropic API** · **Google Gemini** · **Groq** | API key | via tool Javis |
| **Ollama Cloud** · **Ollama di mesin ini** | API key, atau gratis di hardware Anda sendiri | via tool Javis |
| **Endpoint apa pun yang kompatibel dengan OpenAI** | Apa pun yang dibutuhkan endpoint tersebut | via tool Javis |

Setiap otak bisa memanggil server MCP yang Anda hubungkan, membaca dan menulis Brain, menjalankan skill, mengantrekan pekerjaan Kanban, serta membuat agent, workflow, loop dan pengingat. Engine CLI juga bisa menjalankan **perintah shell**, **mengambil dan mencari di web**, serta **menjalankan sub-agent secara paralel**.

> [!WARNING]
> **Baca ini sebelum membiarkan langganan menjalankan pekerjaan background.** Anthropic membatasi Claude Pro/Max untuk **penggunaan pribadi biasa** Claude Code. Eksekusi background terus-menerus (loop, pengingat, job Kanban, chatbot), menjalankannya di VPS, atau beberapa orang berbagi satu akun, semuanya berada di luar cakupan itu, dan sudah ada akun yang **ditangguhkan** karenanya. Javis tidak pernah membaca token login Anda: ia menjalankan binary `claude` yang asli, tetapi itu tidak membuat penggunaan background nonstop menjadi sah. Agar aman, atur Claude Code agar berjalan dengan **API key** di halaman Models, atau arahkan **model untuk pekerjaan background** ke provider lain. Kehati-hatian yang sama berlaku untuk paket xAI. Lihat `server/claude_auth.py`.

---

## ✨ Fitur

<p align="center">
<img src="../../../docs/assets/diagrams/second-brain-grows.svg" width="100%" alt="Knowledge graph animasi: catatan dan tautan muncul satu per satu saat Second Brain tumbuh dari segelintir catatan menjadi lebih dari seribu">
</p>

<table>
<tr>
<td width="50%" valign="top">

### 🗣️ Ajak bicara
- **Suara hands-free**: Anda bicara, Javis mendengarkan dan menjawab dengan suara (Edge TTS gratis secara default, atau OpenAI dan ElevenLabs).
- **Sesi chat** yang bisa disimpan, dibuka lagi, dan dicari dengan full-text search. Sesi panjang dipadatkan menjadi ringkasan, bukan dipotong.
- **Telegram, CLI, dan dashboard web**, semuanya terhubung ke Javis yang sama.
- **Bahasa apa pun**: Javis membalas dalam bahasa yang Anda gunakan. Antarmukanya tersedia dalam bahasa Inggris dan Vietnam.

### 🧠 Ingat semuanya
- **Second Brain**: vault markdown (kompatibel dengan Obsidian) dengan memori jangka panjang, Wiki, dan Sources mentah.
- **Knowledge graph** dari catatan Anda yang terhubung lewat `[[wikilink]]`, di kanvas terang yang bisa dipakai offline.
- **Belajar mandiri**: setelah setiap percakapan, Javis menyaring memori, pengetahuan wiki, dan skill. Setiap proses belajar adalah satu git commit, jadi **bisa dibatalkan dengan satu ketukan**.
- **Backup ke GitHub**: sinkronisasi dua arah setiap Brain ke repo privat, dipakai bersama antara laptop dan VPS Anda.

</td>
<td width="50%" valign="top">

### ⚙️ Bekerja selagi Anda tidur
- **Tasks (Kanban)**: serahkan sebuah tujuan dengan kata-kata biasa. AI menulis spesifikasinya, memilih worker, menjalankannya di background, dan hanya menghubungi Anda saat ada pengecualian.
- **Loop dan pengingat**: job background berdasarkan interval, jam tertentu, atau ekspresi cron, masing-masing memeriksa hasil kerjanya sendiri.
- **Agent dan workflow**: asisten spesialis dengan memorinya sendiri, dirangkai menjadi workflow multi-langkah dengan verifikasi.
- **Chatbot**: tempatkan agent di depan pelanggan Anda lewat bot Telegram atau Zalo-nya sendiri, dengan inbox bersama yang bisa Anda ambil alih.

### 🔌 Hubungkan apa saja
- **Toko koneksi MCP** dengan beberapa akun per layanan dan tiga level izin yang **ditegakkan secara ketat** oleh Javis.
- **Skill dan plugin**: taruh sebuah folder untuk menambahkan pengetahuan (skill) atau tool Python native (plugin) untuk setiap engine.
- **Pembuatan gambar** memakai paket ChatGPT yang sudah Anda login-kan.
- **Pelacakan penggunaan**: token dan biaya per hari, per provider, dipisahkan antara yang Anda ketik dan yang berjalan sendiri.

</td>
</tr>
</table>

<p align="center">
<img src="../../../docs/assets/diagrams/background-work.svg" width="100%" alt="Papan Kanban animasi di malam hari: tugas berpindah sendiri dari Queued ke Running ke Review ke Done, dan sebuah laporan masuk ke Telegram di pagi hari">
</p>

<div align="center">
<img src="../../../docs/assets/screenshots/tasks.jpg" alt="Halaman Tasks: status dispatcher, jumlah worker, mode dispatcher, dan antrean tugas" width="49%">
<img src="../../../docs/assets/screenshots/skills.jpg" alt="Halaman Skills: skill dikelompokkan per topik, masing-masing dengan toggle, deskripsi, dan foldernya" width="49%">
</div>

---

## 🏗️ Cara kerjanya

```mermaid
flowchart LR
    subgraph You
        W[Web dashboard<br>voice + graph]
        T[Telegram]
        C[Javis CLI]
        Z[Zalo / bot channels]
    end
    subgraph Javis["Javis OS (FastAPI, self-hosted)"]
        R[Engine router]
        H[MCP Hub<br>shared toolbox]
        B[(Second Brain<br>Memory + Wiki + Sources)]
        Q[Background work<br>Tasks, loops, reminders]
    end
    subgraph Brains
        S[Subscription CLIs<br>Claude Code, Codex, Grok, Antigravity]
        A[API engines<br>OpenRouter, OpenAI, Anthropic, Gemini, Groq, Ollama]
    end
    W & T & C & Z --> R
    R --> S & A
    S & A --> H
    H --> B
    H --> M[Your MCP servers<br>sales, ads, calendar, email...]
    Q --> R
```

- **Backend:** Python FastAPI di `server/`: engine (`claude_sdk_engine.py`, `claude_cli.py`, `antigravity_cli.py`, `engine.py`, `aux_engine.py`), tool (`mcp_hub.py`, `mcp_store.py`, `plugins_host.py`), pekerjaan background (`tasks.py`, `self_improve.py`, `reminders.py`, `learn.py`), bahasa dan locale (`lang.py`, `lang_registry.py`, `localefmt.py`).
- **Frontend:** HTML/CSS/JS biasa di `dashboard/`. Tanpa framework dan tanpa build step, sehingga tetap ringan di VPS kecil. String antarmuka ada di `dashboard/i18n/`.
- **Second Brain:** vault markdown di `brains/<brain name>/`.

---

## 🚀 Instalasi

> [!IMPORTANT]
> Javis menjalankan otak AI dengan **hak penuh** di mesin. Saat berjalan secara publik (Docker, VPS, Hostinger), Javis **mewajibkan login dengan sendirinya**: membuka aplikasi akan menampilkan layar buat akun atau login, dan tidak ada yang bisa mengendalikannya tanpa password.

<details open>
<summary><b>Opsi 1: Hostinger Docker Manager (domain + HTTPS, sekali klik)</b></summary>

VPS Hostinger → **Docker Manager → Compose → URL** → tempel file Hostinger lalu tekan **Deploy**:

```
https://raw.githubusercontent.com/blogminhquy/javis-os/main/docker-compose.hostinger.yml
```

Kotak **Environment** hanya butuh tiga field: `DOMAIN_NAME`, `JAVIS_ADMIN_USER`, `JAVIS_ADMIN_PASSWORD`, ditambah `JAVIS_AUTO_UPDATE` yang opsional (isi `true` dan Javis akan memperbarui dirinya setiap hari).

Isi `DOMAIN_NAME` agar Traefik milik Hostinger menerbitkan HTTPS:
- **Link gratis** (tanpa beli domain): `DOMAIN_NAME=javis.<vps-hostname>.hstgr.cloud` (hostname ada di hPanel → VPS, contoh `javis.srv1562015.hstgr.cloud`).
- **Domain Anda sendiri:** `DOMAIN_NAME=example.com` lalu arahkan A record ke IP VPS.

Tunggu 1-3 menit sampai sertifikat terbit, lalu buka `https://<DOMAIN_NAME>`.

**Tiga langkah yang cukup dilakukan sekali:**
1. **Jadikan image GHCR Public:** GitHub → repo → **Packages** → `javis-os` → *Package settings* → Visibility = **Public**.
2. **Buat akun admin:** isi `JAVIS_ADMIN_USER` + `JAVIS_ADMIN_PASSWORD` (disarankan), atau buka aplikasi tepat setelah deploy lalu buat sendiri. Selama belum ada admin, siapa pun yang pertama membuka link bisa membuatnya. Setelah itu **aktifkan 2FA** ([Keamanan dan akun](../../../docs/en/14-security-and-accounts.md)).
3. **Login ke sebuah otak** di halaman **Models**.

Detail dan pemecahan masalah: [DEPLOY.en.md](../../../DEPLOY.en.md).

</details>

<details>
<summary><b>Opsi 2: Docker di VPS apa pun (tanpa clone)</b></summary>

```bash
# Docker required (don't have it?  curl -fsSL https://get.docker.com | sh)
mkdir javis && cd javis
curl -fsSLO https://raw.githubusercontent.com/blogminhquy/javis-os/main/docker-compose.yml

docker compose run --rm javis claude auth login --claudeai   # sign in to Claude once (optional)
docker compose up -d                                          # pull the image and run
```

Buka `http://<vps-ip>:7777` dan segera atur username dan password admin (minimal 8 karakter), atau isi lebih dulu `JAVIS_ADMIN_USER` + `JAVIS_ADMIN_PASSWORD` di environment. Lalu aktifkan 2FA.

Akses jarak jauh tanpa domain: `docker compose --profile tunnel up -d`, lalu `docker compose logs tunnel | grep trycloudflare` akan menampilkan link HTTPS.

</details>

<details>
<summary><b>Opsi 3: Linux atau macOS, tanpa Docker</b></summary>

```bash
git clone https://github.com/blogminhquy/javis-os.git javis && cd javis
chmod +x install.sh && ./install.sh
```

Script ini menginstal Python, Node, dan otak CLI, membuat venv, mendaftarkan service yang berjalan saat boot, lalu menampilkan alamatnya.

🍎 **macOS, buka seperti aplikasi:** klik dua kali `JAVIS OS.app` (atau `Start JAVIS OS.command`). Jalankan saat login: `./bin/javis-autostart.sh install`. Detail: [bin/README.md](../../../bin/README.md).

</details>

<details>
<summary><b>Opsi 4: Windows (komputer pribadi)</b></summary>

```powershell
git clone https://github.com/blogminhquy/javis-os.git javis; cd javis
powershell -ExecutionPolicy Bypass -File install.ps1
```

`install.ps1` mengerjakan semuanya sekaligus: Python, venv dan library, empat otak CLI berlangganan (`claude`, `codex`, `agy`, `grok`), `.env`, mengosongkan port 7777, dan menjalankan server. Di akhir ia menampilkan tabel otak mana saja yang sudah siap. Tanpa `winget`, instal dulu Python 3.12 (centang "Add python.exe to PATH") dan Node.js LTS secara manual, lalu jalankan lagi.

```
Run with a visible window (live log):  setup.bat
Run silently from then on:             start-javis.vbs   (log at server\javis.log)
Stop:                                  stop-javis.bat
Dashboard:                             http://localhost:7777
```

🪟 **Buka seperti aplikasi:** setelah dijalankan pertama kali, klik dua kali **`JAVIS OS.bat`**. Server berjalan di background dan dashboard terbuka di **jendelanya sendiri** dengan entri taskbar sendiri. Jalankan saat login: `javis-autostart.bat install` (hapus: `uninstall`).

</details>

<details>
<summary><b>Beberapa instance Javis di satu VPS</b></summary>

Brain, pengaturan, dan akun tetap terpisah sepenuhnya per instance. Hanya tiga nilai yang berbeda di antara mereka: `JAVIS_NAME`, `JAVIS_HOST_PORT`, `DOMAIN_NAME`.

- **Hostinger:** deploy `docker-compose.hostinger.yml` lagi sebagai stack kedua dan isi ketiga field tersebut.
- **VPS yang Anda kelola sendiri:** jalankan proxy bersama `docker-compose.proxy.yml` sekali untuk seluruh mesin, lalu beri setiap instance foldernya sendiri dengan `docker-compose.multi.yml`. Proxy akan menemukan instance baru dan meminta SSL dengan sendirinya.
- **Native:** `JAVIS_NAME=javis-shop JAVIS_PORT=7778 ./install.sh`.

Langkah demi langkah: [DEPLOY.en.md](../../../DEPLOY.en.md).

</details>

### 🎬 Menjalankan pertama kali

Buka Javis dan setup wizard akan memandu Anda, dalam bahasa browser Anda:

1. **Akun admin**: wajib saat berjalan secara publik, agar orang asing tidak bisa masuk.
2. **Pilih otak**: login sekali dengan langganan, atau tempel API key. Kartu Claude Code punya switch **"Runs on"** untuk memilih antara paket yang Anda login-kan dan API key Anthropic.
3. **Pilih model**: berganti provider nanti tidak menghilangkan fitur apa pun (kecuali perintah shell, yang hanya dimiliki engine CLI).
4. **Pasang koneksi** (opsional): buka **Connections**, pilih layanan, lalu tempel key atau scan kode QR. Setelah itu Javis melapor berdasarkan angka nyata dari sana.

---

## 📖 Menggunakan Javis

Rail kiri mengelompokkan halaman menjadi **6 grup**. Setiap halaman punya panduan di [docs/en/](../../../docs/en/README.md).

| Grup | Halaman | Panduan |
|---|---|---|
| **Brain** | Graph, Chat, Files, Self-learning | [Chat dan suara](../../../docs/en/02-chat-and-voice.md) · [Knowledge graph](../../../docs/en/03-knowledge-graph.md) · [Sesi](../../../docs/en/04-sessions.md) · [Pengelola file](../../../docs/en/05-file-manager.md) · [Belajar mandiri](../../../docs/en/22-self-learning.md) |
| **Code** | Terminal, Coding | [Terminal kode](../../../docs/en/27-code-terminal.md) |
| **Capabilities** | Partners (agent dan workflow), Chatbot, Skills, Plugins | [Agent dan workflow](../../../docs/en/07-agents-and-workflows.md) · [Chatbot](../../../docs/en/25-chatbots.md) · [Percakapan pelanggan](../../../docs/en/28-customer-conversations.md) · [Skill](../../../docs/en/06-skills.md) · [Plugin](../../../docs/en/20-plugins.md) |
| **Work** | Tasks, Scheduled | [Tugas (Kanban)](../../../docs/en/21-kanban-work.md) · [Job berulang dan pengingat](../../../docs/en/08-recurring-jobs.md) |
| **Connections** | Connections, Javis Store, Channels, Models | [Koneksi dan data bisnis](../../../docs/en/09-connections-and-business-data.md) · [Telegram](../../../docs/en/11-telegram.md) · [Zalo](../../../docs/en/12-zalo-agent-mcp.md) · [Model dan engine](../../../docs/en/10-models-and-engines.md) |
| **System** | Settings, Share links, Account | [Memulai](../../../docs/en/01-getting-started.md) · [Keamanan dan akun](../../../docs/en/14-security-and-accounts.md) · [Penggunaan dan biaya](../../../docs/en/23-usage-and-cost.md) · [Javis CLI](../../../docs/en/24-cli.md) |

Selengkapnya: [Second Brain: memori, Wiki, dan INGEST](../../../docs/en/13-second-brain.md) · [Backup GitHub](../../../docs/en/18-github-backup.md) · [Tasks dan Dataview di catatan](../../../docs/en/19-tasks-and-dataview.md) · [Branding dan domain kustom](../../../docs/en/15-branding-and-domains.md) · [Pemecahan masalah](../../../docs/en/17-troubleshooting.md)

### Beberapa hal untuk dicoba

- **Minta angka:** *"Bagaimana omzet hari ini dibandingkan kemarin?"* Javis memanggil koneksi yang tepat dan menjawab dengan angka nyata beserta saran.
- **Cerna pengetahuan:** taruh sebuah file atau catatan. Javis meringkasnya, mengambil insight, menuliskannya ke Wiki, dan mengusulkan tugas.
- **Serahkan pekerjaan background:** **Tasks** → **+ Assign goal** → *"rangkum penjualan minggu ini, cari stok yang lambat laku, buat draf tiga caption untuk mendorongnya"*. AI menyusun spesifikasinya, menjalankannya, dan melapor kembali.
- **Jadwalkan sesuatu:** *"ingatkan saya setiap hari kerja jam 8:30 untuk mengecek budget iklan"*, lewat chat atau di halaman **Scheduled**.
- **Gunakan suara Anda:** tekan mikrofon (atau aktifkan hands-free), bicara, dan Javis menjawab dengan suara.

<div align="center">
<img src="../../../docs/assets/screenshots/mobile.jpg" alt="Javis OS di ponsel: knowledge graph di atas, percakapan di bawahnya, dan bar chat di bagian bawah" width="300">
<br><sub>Bisa juga di ponsel: tambahkan ke layar utama dan ia terbuka seperti aplikasi.</sub>
</div>

---

## ⚙️ Konfigurasi (`.env`)

Setiap baris boleh dibiarkan kosong dan Javis tetap berjalan. Salin `env.example` → `.env` lalu tambahkan yang Anda perlukan. Daftar lengkap beserta penjelasan tiap variabel ada di [docs/en/16-env-configuration.md](../../../docs/en/16-env-configuration.md).

| Variabel | Arti | Default |
|---|---|---|
| `JAVIS_HOST` | Alamat listen. `127.0.0.1` = hanya mesin ini, `0.0.0.0` = publik | `127.0.0.1` |
| `JAVIS_PORT` | Port | `7777` |
| `JAVIS_REQUIRE_LOGIN` | `1`/`0` untuk memaksa login aktif atau nonaktif (default: aktif saat di-bind secara publik) | *(otomatis)* |
| `JAVIS_ADMIN_USER` / `JAVIS_ADMIN_PASSWORD` | Membuat admin saat deploy | - |
| `JAVIS_ALLOWED_HOSTS` | Hostname tambahan di allow-list (perlindungan CSRF dan DNS rebinding) | localhost + domain Anda |
| `JAVIS_STATE_DIR` | Tempat pengaturan, sesi, dan kunci enkripsi disimpan | `server/` (Docker: `/data/state`) |
| `BRAINS_DIR` | Folder induk yang menampung setiap Brain | `brains/` (Docker: `/brains`) |
| `JAVIS_ENABLE_USER_PLUGINS` | `true` mengizinkan plugin buatan Anda sendiri berjalan (Python sungguhan di dalam server) | *(nonaktif)* |
| `TTS_VOICE` / `TTS_RATE` | Suara dan kecepatan untuk Edge TTS | `en-US-EmmaMultilingualNeural` / `+5%` |

---

## 🔐 Keamanan

- **Login wajib** di server publik sebelum fitur apa pun bisa dipakai, karena otak berjalan dengan hak penuh di mesin.
- **2FA (TOTP)**, pembatasan percobaan login, password minimal 8 karakter, cookie `Secure` di bawah HTTPS, sesi yang kedaluwarsa setelah 30 hari.
- **Perlindungan CSRF dan DNS rebinding**: setiap request tulis dari origin yang tidak dikenal akan ditolak.
- **Secret dienkripsi** di `settings.json` (API key, token OAuth, token bot) dengan kunci per mesin.
- **Plugin buatan Anda sendiri diblokir secara default** sampai Anda mengatur `JAVIS_ENABLE_USER_PLUGINS=true`.
- **Izin koneksi ditegakkan** oleh hub, bukan oleh model: akun read-only tidak bisa dipakai untuk mengirim, membayar, atau memublikasikan.

Menemukan celah keamanan? Silakan ikuti [SECURITY.md](../../../SECURITY.md), jangan membuka issue publik.

---

## 🔄 Pembaruan

Di aplikasi: **Settings → Updates → Update now**, dengan progress bar dan tombol rollback jika build baru bermasalah. Di VPS: `cd javis && ./update.sh` (menarik image baru dan restart; data Anda di volume tetap aman).

---

## 🩺 Pemecahan masalah

| Gejala | Yang harus dilakukan |
|---|---|
| Halaman Models bilang sebuah CLI belum terinstal, padahal sudah | **Restart Javis**: proses yang berjalan tetap memakai PATH saat ia dijalankan. |
| Port 7777 terpakai dan build baru tidak mau jalan | Hentikan dulu proses lama (`stop-javis.bat`, atau kill PID-nya), lalu jalankan lagi. |
| Hostinger tidak bisa menarik image | Atur package GHCR menjadi **Public** dan tunggu build GitHub Action selesai. |
| Sebuah otak bilang belum login | **Models** → kartu provider tersebut → login. |

Selengkapnya di [docs/en/17-troubleshooting.md](../../../docs/en/17-troubleshooting.md).

---

## 📂 Struktur repositori

```
javis-os/
├── server/          # FastAPI backend: engines, connections, background work, channels, memory
├── dashboard/       # Frontend (plain JS, no build step)
│   └── i18n/        # Interface strings, one JSON file per language
├── brains/          # Every Second Brain (default: brains/Brain Default)
├── system/          # Ships with the app: bundled plugins, system skills, connection catalogue
├── docs/            # User guides (docs/en/ in English) and translations (docs/i18n/)
├── tests/           # Python + JS test suite (python tests/run.py)
├── install.sh · install.ps1 · update.sh
├── Dockerfile · docker-compose*.yml
└── CLAUDE.md        # The system prompt Javis runs on
```

---

## 🌍 Bahasa

| Apa | Bahasa saat ini |
|---|---|
| **Balasan Javis** | Bahasa apa pun: ia menjawab dalam bahasa yang Anda gunakan, atau bahasa yang Anda kunci di Settings |
| **Dashboard dan pesan server** | 🇬🇧 English · 🇻🇳 Tiếng Việt, per perangkat: setiap browser mendapat bahasanya sendiri sampai Anda memilih |
| **Toko koneksi, plugin, file awal Brain baru** | 🇬🇧 English · 🇻🇳 Tiếng Việt |
| **README dan panduan mulai cepat** | 🇬🇧 English · 🇻🇳 Tiếng Việt · 🇨🇳 简体中文 · 🇪🇸 Español · 🇯🇵 日本語 · 🇮🇳 हिन्दी · 🇧🇷 Português · 🇰🇷 한국어 · 🇷🇺 Русский · 🇩🇪 Deutsch · 🇫🇷 Français · 🇮🇩 Bahasa Indonesia |
| **Dokumentasi lengkap** | 🇬🇧 English · 🇻🇳 Tiếng Việt |

Menambahkan bahasa adalah perubahan data, bukan perubahan kode: satu entri di `server/lang_registry.py` ditambah satu `dashboard/i18n/<code>.json`, dan opsional `system/mcp-catalog.<code>.json`. Apa pun yang belum diterjemahkan akan tampil dalam bahasa Inggris. Lihat [CONTRIBUTING.en.md](../../../CONTRIBUTING.md#translations) jika Anda ingin membantu.

---

## 🤝 Berkontribusi

Laporan bug, ide, terjemahan, dan pull request semuanya disambut, dalam bahasa Inggris atau Vietnam.

| Mulai dari sini | Yang Anda dapatkan |
|---|---|
| [CONTRIBUTING.md](../../../CONTRIBUTING.md) | Setup, menjalankan test (`python tests/run.py`), konvensi kode |
| [ARCHITECTURE.md](../../../ARCHITECTURE.md) | Bagaimana bagian-bagiannya saling terhubung, dan peta modul server |
| [docs/dev/GLOSSARY.md](../../../docs/dev/GLOSSARY.md) | Codebase-nya ditulis dalam bahasa Vietnam: file ini menerjemahkan nama seperti `nhac_hen` (pengingat) |
| [docs/dev/adding-a-language.md](../../../docs/dev/adding-a-language.md) | Menerjemahkan Javis ke bahasa Anda, langkah demi langkah |
| [Template issue](https://github.com/blogminhquy/javis-os/issues/new/choose) | Laporan bug, permintaan fitur, tawaran terjemahan |

Mohon ikuti [Code of Conduct](../../../CODE_OF_CONDUCT.md), dan laporkan masalah keamanan secara privat seperti dijelaskan di [SECURITY.md](../../../SECURITY.md).

Jika Javis bermanfaat bagi Anda, satu ⭐ di repo ini membantu orang lain menemukannya.

[![Star History Chart](https://api.star-history.com/svg?repos=blogminhquy/javis-os&type=Date)](https://star-history.com/#blogminhquy/javis-os&Date)

---

## 🙏 Kredit

- **Otak:** [Claude Code](https://claude.com/claude-code) dan [Claude Agent SDK](https://docs.claude.com/en/api/agent-sdk/overview) (Anthropic), [Codex CLI](https://developers.openai.com/codex/cli) (OpenAI), [Grok Build](https://x.ai) (xAI), [Antigravity](https://antigravity.google) (Google), ditambah API dari [OpenRouter](https://openrouter.ai), OpenAI, [Google Gemini](https://ai.google.dev), Anthropic, [Groq](https://groq.com) dan [Ollama](https://ollama.com).
- **Standar tool:** [Model Context Protocol](https://modelcontextprotocol.io). Seluruh toko koneksi Javis berjalan di atasnya.
- Pola Second Brain dan Bullet Journal digital.

## 📄 Lisensi

Open source di bawah **MIT License**: bebas digunakan, dimodifikasi, dan didistribusikan, cukup pertahankan pemberitahuan hak cipta. Lihat [LICENSE](../../../LICENSE).

---

## ☕ Dukung Javis OS

Javis OS gratis dan open source, dan masih satu orang yang menulis kodenya sekaligus membayar server uji coba. Jika Javis membantu pekerjaan atau hidup Anda, donasi kecil memberi lebih banyak waktu untuk perbaikan bug dan fitur baru.

- 🌍 **PayPal**: [paypal.me/quy01](https://paypal.me/quy01)
- 🏦 **MB Bank** (Vietnam): `6636966369`
- 📱 **Dompet MoMo** (Vietnam): `0372752740`

Tidak bisa berdonasi? Menggunakan Javis, mengirim masukan, atau membuka pull request juga termasuk dukungan.

<div align="center">
<br>
Dibuat dengan ☕ di Vietnam oleh <b><a href="https://minhquy.vn">Minh Quý</a></b>
</div>
