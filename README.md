<div align="center">

# 🎬 AparatChi

**A professional Windows GUI for downloading Aparat videos in multiple qualities at once.**

[![Version](https://img.shields.io/badge/version-1.5.0-blue.svg)]()
[![Python](https://img.shields.io/badge/python-3.10%2B-yellow.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)]()
[![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)]()

[English](README.md) · [فارسی](README.fa.md)

</div>

---

## 📖 Overview

**AparatChi** is a lightweight, native Windows desktop application for downloading videos from [Aparat](https://www.aparat.com) — Iran's largest video-sharing platform. It provides a clean and modern graphical interface built with **Python** and **Tkinter**, with a powerful download engine supporting queue management, resume, multi-quality selection, and channel-based organization.

> ⚠️ AparatChi uses only the **public Aparat JSON API**. It does not bypass any access controls, does not require a login, and does not support private or restricted content.

---

## ✨ Features

### 🎯 Download
- Download one **or many URLs** at the same time (one per line).
- Select **multiple qualities** simultaneously (`144p`, `240p`, `360p`, `480p`, `720p`, `1080p`).
- One task per **URL × quality** combination.
- **Two concurrent downloads** (ThreadPoolExecutor, 2 workers).
- Automatic **fallback** to the closest lower quality if the requested one is not available.
- **HTTP Range resume** — continue interrupted downloads from where they stopped.
- Optional **disk space reservation** before starting a download (sparse file).
- **Duplicate detection** per `(URL, quality)` pair with confirmation dialog.

### 📂 Organization
- **Per-task save folder** — each task keeps the folder that was active when it was added.
- **Channel folder option** — automatically save each video inside a folder named after its Aparat channel.
- Sequential, persistent **numbering** (`001_`, `002_`, ...) shared per source URL across all qualities.

### 🖥 Interface
- Modern header with Bismillah 786 banner.
- **Per-task progress bar** + **overall progress bar**.
- Live **speed** (MB/s), **expected size**, and **save location** shown on each card.
- **Stop / Resume / Delete / Open Folder / Open File** buttons per task.
- **Right-click Cut / Copy / Paste** in text areas, mouse-wheel scrolling.
- Full **log panel** on screen + `apyrat_gui.log` file.

### 💾 Persistence & Recovery
- **Persistent queue** (`queue.json`) — survives app restarts and updates.
- **Graceful shutdown** — active downloads are safely paused on exit and can be resumed next time.
- **Auto-resume** option — continue unfinished downloads automatically on startup.
- Stale `Downloading` tasks (from a crash) become `Paused` automatically on next launch.
- **Download history** (`history.json`) and **settings** (`settings.json`) persisted.

### 📜 Changelog
- Built-in **Changelog viewer** in the `Help` menu, showing all changes per version.

---

## 🖼 Screenshots

> _Add your screenshots here._
>
> ```
> docs/screenshot-main.png
> docs/screenshot-queue.png
> ```

---

## 🚀 Installation

### Option 1 — Run from source

**Requirements:** Python 3.10 or later.

```bash
# 1. Clone the repository
git clone https://github.com/reza1399707/AparatChi.git
cd AparatChi

# 2. Install dependencies
pip install requests

# 3. Run
python aparat_chi.py