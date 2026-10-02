# -*- coding: utf-8 -*-
"""
============================================================================
 AparatChi - Professional Windows GUI for Aparat video downloads
============================================================================
 Version 1.5.0 - New features:
   * Graceful shutdown: active downloads are safely paused on exit.
   * Queue file now stores the app version for forward compatibility.
   * Stale "Downloading" tasks become "Paused" on next launch.
   * Auto-resume option: continue unfinished downloads on startup.
   * Changelog window in the Help menu.
   * All features from v1.4.0 (channel folder, open file/folder, etc).
 Project website: https://github.com/reza1399707/AparatChi
============================================================================
"""

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------
import tkinter as tk                              # ساخت رابط گرافیکی (پنجره، دکمه، لیبل و ...)
from tkinter import ttk                           # ویجت‌های مدرن‌تر Tkinter (Progressbar و ...)
from tkinter import filedialog                    # پنجره انتخاب پوشه
from tkinter import messagebox                    # پنجره‌های پیام (هشدار، تأیید، خطا)
from tkinter import scrolledtext                  # جعبه متن با اسکرول (برای نمایش لاگ)

import threading                                  # Event برای Pause/Resume
from concurrent.futures import ThreadPoolExecutor # اجرای همزمان دانلودها در پس‌زمینه

import requests                                   # ارسال درخواست HTTP به API آپارات و دانلود
import json                                       # خواندن/نوشتن فایل‌های JSON
import os                                         # کار با مسیرها، پوشه‌ها و فایل‌ها
import re                                         # Regular Expression برای پاکسازی نام فایل
import html                                       # تبدیل HTML entities (مثل &raquo; به »)
import sys                                        # تشخیص سیستم‌عامل
import time                                       # محاسبه سرعت دانلود
import shutil                                     # بررسی فضای آزاد دیسک
import logging                                    # ثبت لاگ

from urllib.parse import urlparse                 # جدا کردن پسوند فایل از URL
from datetime import datetime                     # تاریخ/ساعت برای تاریخچه و لاگ


# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------
APP_NAME    = "AparatChi"
APP_VERSION = "1.5.0"
APP_AUTHOR  = "AparatChi"
APP_YEAR    = datetime.now().year
APP_WEBSITE = "https://github.com/reza1399707/AparatChi"

API_BASE_URL = "https://www.aparat.com/api/fa/v1"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0 Safari/537.36"
    )
}

QUEUE_FILE    = "queue.json"
HISTORY_FILE  = "history.json"
SETTINGS_FILE = "settings.json"
COUNTER_FILE  = "counter.json"
LOG_FILE      = "apyrat_gui.log"

CHUNK_SIZE   = 1024 * 64
MAX_WORKERS  = 2

STANDARD_QUALITIES = ["144p", "240p", "360p", "480p", "720p", "1080p"]
DEFAULT_SELECTED   = ["720p"]

DEFAULT_SETTINGS = {
    "download_dir":       os.path.expanduser("~\\Downloads"),
    "qualities":          DEFAULT_SELECTED,
    "geometry":           "1180x920",
    "reserve_space":      True,
    "use_channel_folder": False,
    "auto_resume":        True,
}


# ---------------------------------------------------------------------------
# Changelog - shown in the Help menu
# ---------------------------------------------------------------------------
CHANGELOG = [
    {
        "version": "1.5.0",
        "date": "2026-10-02",
        "changes": [
            "Graceful shutdown: unfinished downloads are safely paused on exit.",
            "Queue format stores app version for forward compatibility.",
            "Stale 'Downloading' statuses become 'Paused' on next launch.",
            "Auto-resume option: continue unfinished downloads on startup.",
            "New Changelog window in the Help menu.",
            "Confirmation dialog if you close while downloads are active.",
        ],
    },
    {
        "version": "1.4.0",
        "date": "2026-09-30",
        "changes": [
            "Fixed quality list resetting when adding new URLs.",
            "Auto-fallback to closest lower quality when requested is missing.",
            "Extract channel name from Aparat API.",
            "Optional: save each video inside a folder named after its channel.",
            "New 'Open Folder' button on every queue card.",
            "New 'Open File' button on completed downloads.",
        ],
    },
    {
        "version": "1.3.1",
        "date": "2026-09-29",
        "changes": [
            "Fixed disk reservation being wiped by opening the file with 'wb'.",
            "Fixed resume mis-detecting a leftover sparse file as complete.",
            "Fixed Stop button not working while a task was paused.",
            "Speed calculation now uses only bytes from this session.",
        ],
    },
    {
        "version": "1.3.0",
        "date": "2026-09-25",
        "changes": [
            "Initial public release.",
            "Add multiple URLs and multiple qualities.",
            "Concurrent downloads (2 workers).",
            "Persistent queue, history and counter.",
            "Disk space reservation option.",
            "Bismillah 786 banner and About window.",
        ],
    },
]


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------
def format_bytes(n: float) -> str:
    if not n or n <= 0:
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def format_speed(bps: float) -> str:
    if not bps or bps <= 0:
        return "-"
    return f"{format_bytes(bps)}/s"


def quality_color(quality: str) -> tuple:
    try:
        n = int(quality.rstrip("p"))
    except ValueError:
        n = 0
    if n >= 1080:
        return "#6a1b9a", "#f3e5f5"
    if n >= 720:
        return "#2e7d32", "#e8f5e9"
    if n >= 480:
        return "#ef6c00", "#fff3e0"
    return "#455a64", "#eceff1"


def parse_size(value) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def sanitize_title(title: str) -> str:
    if not title:
        return "untitled"
    title = html.unescape(title)
    title = re.sub(r'[\\/*?:"<>|]', "_", title)
    title = re.sub(r"\s+", " ", title).strip().rstrip(". ")
    return title[:100] or "untitled"


def attach_text_menu(widget: tk.Text):
    menu = tk.Menu(widget, tearoff=0)
    menu.add_command(label="Cut",        command=lambda: widget.event_generate("<<Cut>>"))
    menu.add_command(label="Copy",       command=lambda: widget.event_generate("<<Copy>>"))
    menu.add_command(label="Paste",      command=lambda: widget.event_generate("<<Paste>>"))
    menu.add_separator()
    menu.add_command(label="Select All", command=lambda: widget.tag_add("sel", "1.0", "end"))

    def _popup(event):
        try:
            widget.focus_set()
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    widget.bind("<Button-3>", _popup)
    widget.bind("<Control-a>", lambda e: (widget.tag_add("sel", "1.0", "end"), "break"))
    widget.bind("<Control-A>", lambda e: (widget.tag_add("sel", "1.0", "end"), "break"))


def open_path(path: str):
    try:
        if os.name == "nt":
            os.startfile(path)
        elif sys.platform == "darwin":
            import subprocess
            subprocess.Popen(["open", path])
        else:
            import subprocess
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        logger.error(f"Cannot open {path}: {e}")


def free_disk_space(path: str) -> int:
    probe = path
    while probe and not os.path.exists(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    try:
        return shutil.disk_usage(probe).free
    except Exception:
        return 0


def reserve_disk_space(partial_path: str, size: int, thorough: bool = False):
    """
    Reserve disk space for a partial download by creating a sparse file
    whose logical size is `size`.
    Caller must open the file afterwards with mode "r+b", NOT "wb".
    """
    if size <= 0:
        return
    if thorough:
        chunk = b"\x00" * (4 * 1024 * 1024)
        remaining = size
        with open(partial_path, "wb") as f:
            while remaining > 0:
                to_write = min(len(chunk), remaining)
                f.write(chunk[:to_write])
                remaining -= to_write
    else:
        with open(partial_path, "wb") as f:
            f.truncate(size)


# ---------------------------------------------------------------------------
# Aparat API wrapper
# ---------------------------------------------------------------------------
class AparatAPI:

    @staticmethod
    def _clean_url(url: str) -> str:
        url = url.replace("https://", "").replace("http://", "")
        url = url.replace("www.", "").rstrip("/")
        return url.split("?", 1)[0]

    @staticmethod
    def is_valid_url(url: str) -> bool:
        clean = AparatAPI._clean_url(url)
        return (clean.startswith("aparat.com/v/") or
                clean.startswith("aparat.com/playlist/"))

    @staticmethod
    def get_video_info(video_uid: str) -> dict:
        url = f"{API_BASE_URL}/video/video/show/videohash/{video_uid}"
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        return r.json()["data"]["attributes"]

    @staticmethod
    def get_available_qualities(attrs: dict) -> list:
        return sorted(
            {a.get("profile") for a in attrs.get("file_link_all", [])
             if a.get("profile")},
            key=lambda x: int(x.rstrip("p")),
        )

    @staticmethod
    def get_title(attrs: dict) -> str:
        raw = attrs.get("title", "untitled") or "untitled"
        return html.unescape(raw)

    @staticmethod
    def get_channel_name(attrs: dict) -> str:
        for key in ("username", "sender_name", "user_name",
                    "channel", "owner", "user"):
            val = attrs.get(key)
            if isinstance(val, str) and val.strip():
                return html.unescape(val.strip())
            if isinstance(val, dict):
                for sub in ("username", "name", "title"):
                    subv = val.get(sub)
                    if isinstance(subv, str) and subv.strip():
                        return html.unescape(subv.strip())
        return ""

    @staticmethod
    def closest_quality(available: list, target: str) -> str:
        try:
            target_n = int(target.rstrip("p"))
        except (ValueError, AttributeError):
            return ""
        nums = []
        for q in available:
            try:
                nums.append((int(q.rstrip("p")), q))
            except (ValueError, AttributeError):
                continue
        if not nums:
            return ""
        below = [x for x in nums if x[0] <= target_n]
        if below:
            return max(below)[1]
        return min(nums)[1]

    @staticmethod
    def head_size(url: str) -> int:
        try:
            r = requests.head(url, headers=HEADERS,
                              allow_redirects=True, timeout=10)
            return int(r.headers.get("Content-Length", 0))
        except Exception:
            return 0

    @staticmethod
    def get_link_info(attrs: dict, quality: str):
        links = attrs.get("file_link_all", [])

        def _resolve(entry):
            url = (entry.get("urls") or [None])[0]
            size = parse_size(entry.get("size"))
            if not size and url:
                size = AparatAPI.head_size(url)
            ext = ".mp4"
            if url:
                ext = os.path.splitext(urlparse(url).path)[1] or ".mp4"
            return url, size, ext

        for l in links:
            if l.get("profile") == quality:
                return _resolve(l)

        available = AparatAPI.get_available_qualities(attrs)
        fallback = AparatAPI.closest_quality(available, quality)
        if fallback:
            for l in links:
                if l.get("profile") == fallback:
                    return _resolve(l)
        return None, 0, ".mp4"


# ---------------------------------------------------------------------------
# Download task
# ---------------------------------------------------------------------------
class DownloadTask:

    def __init__(self, url, quality, title="", filename="",
                 expected_size=0, number=0, save_dir="",
                 channel=""):
        self.url              = url.strip()
        self.quality          = quality
        self.title            = title
        self.filename         = filename
        self.number           = number
        self.save_dir         = save_dir
        self.channel          = channel
        self.progress         = 0.0
        self.status           = "Waiting"
        self.total_bytes      = 0
        self.downloaded_bytes = 0
        self.expected_size    = expected_size
        self.speed            = 0.0
        self.pause_event      = threading.Event(); self.pause_event.set()
        self.stop_flag        = False
        self.download_url     = ""
        self.partial_file     = ""

    def to_dict(self):
        return {
            "url": self.url, "quality": self.quality, "title": self.title,
            "filename": self.filename, "number": self.number,
            "save_dir": self.save_dir, "channel": self.channel,
            "progress": self.progress, "status": self.status,
            "total_bytes": self.total_bytes,
            "downloaded_bytes": self.downloaded_bytes,
            "expected_size": self.expected_size,
        }

    @classmethod
    def from_dict(cls, d):
        t = cls(d["url"], d["quality"], d.get("title", ""),
                d.get("filename", ""), d.get("expected_size", 0),
                d.get("number", 0), d.get("save_dir", ""),
                d.get("channel", ""))
        t.progress         = d.get("progress", 0.0)
        t.status           = d.get("status", "Waiting")
        t.total_bytes      = d.get("total_bytes", 0)
        t.downloaded_bytes = d.get("downloaded_bytes", 0)
        return t


# ---------------------------------------------------------------------------
# Download manager
# ---------------------------------------------------------------------------
class DownloadManager:

    def __init__(self, log_callback=None):
        self.queue             = []
        self.history           = []
        self.log_callback      = log_callback or (lambda m: None)
        self.executor          = ThreadPoolExecutor(max_workers=MAX_WORKERS)
        self.futures           = {}
        self._counter          = 0
        self.download_dir      = os.path.expanduser("~\\Downloads")
        self.reserve_space     = True

        self.load_counter()
        self.load_queue()
        self.load_history()

    # ---- persistence -----------------------------------------------------
    def load_counter(self):
        if os.path.isfile(COUNTER_FILE):
            try:
                with open(COUNTER_FILE, encoding="utf-8") as f:
                    self._counter = int(json.load(f).get("counter", 0))
            except Exception:
                self._counter = 0

    def save_counter(self):
        try:
            with open(COUNTER_FILE, "w", encoding="utf-8") as f:
                json.dump({"counter": self._counter}, f)
        except Exception as e:
            self.log(f"Failed to save counter: {e}")

    def next_number(self) -> int:
        self._counter += 1
        self.save_counter()
        return self._counter

    def load_queue(self):
        """
        Load queue.json. Supports BOTH:
          - old format (a plain list of tasks)  -> v1.3.x and v1.4.x
          - new format (a dict with "app_version" + "tasks") -> v1.5.0+
        Any task whose status was "Downloading" (i.e. was killed by a
        crash or forced close) becomes "Paused" so the user can resume
        it cleanly.
        """
        if not os.path.isfile(QUEUE_FILE):
            return
        try:
            with open(QUEUE_FILE, encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, list):
                tasks_data = data
                saved_version = "1.3.x/1.4.x"
            elif isinstance(data, dict):
                tasks_data = data.get("tasks", [])
                saved_version = data.get("app_version", "unknown")
            else:
                self.log("Queue file has unknown structure - ignoring.")
                return

            self.queue = [DownloadTask.from_dict(d) for d in tasks_data]

            # Fix stale statuses from previous crashes / forced closes.
            fixed = 0
            for t in self.queue:
                if t.status == "Downloading":
                    t.status = "Paused"
                    fixed += 1

            highest = max((t.number for t in self.queue), default=0)
            if highest > self._counter:
                self._counter = highest
                self.save_counter()

            self.log(f"Loaded {len(self.queue)} tasks "
                     f"(queue from v{saved_version}).")
            if fixed:
                self.log(f"Marked {fixed} interrupted task(s) as Paused.")
        except Exception as e:
            self.log(f"Failed to load queue: {e}")

    def save_queue(self):
        try:
            with open(QUEUE_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "app_version": APP_VERSION,
                    "saved_at":    datetime.now().isoformat(),
                    "tasks":       [t.to_dict() for t in self.queue],
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.log(f"Failed to save queue: {e}")

    def load_history(self):
        if os.path.isfile(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, encoding="utf-8") as f:
                    self.history = json.load(f)
            except Exception as e:
                self.log(f"Failed to load history: {e}")

    def save_history(self):
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(self.history, f, indent=2, ensure_ascii=False)

    def is_duplicate(self, url, quality) -> bool:
        return any(h.get("url") == url and h.get("quality") == quality
                   for h in self.history)

    def add_to_history(self, url, quality):
        self.history.append({"url": url, "quality": quality,
                             "timestamp": datetime.now().isoformat()})
        self.save_history()

    # ---- logging ---------------------------------------------------------
    def log(self, msg: str):
        logger.info(msg)
        self.log_callback(msg)

    # ---- queue operations ------------------------------------------------
    def add_task(self, task: DownloadTask):
        self.queue.append(task)
        self.save_queue()
        self.log(f"Added: {task.url} ({task.quality})")

    def delete_task(self, task: DownloadTask):
        try:
            self.stop_task(task)
        except Exception:
            pass
        if task in self.queue:
            self.queue.remove(task)
            self.save_queue()
            self.log(f"Deleted from queue: {task.url} ({task.quality})")
        if task.partial_file and os.path.isfile(task.partial_file):
            try:
                os.remove(task.partial_file)
                self.log(f"Removed partial file: {task.partial_file}")
            except Exception as e:
                self.log(f"Could not remove partial file: {e}")

    def start_download(self, task: DownloadTask):
        if task.status in ("Downloading", "Completed"):
            return
        task.stop_flag = False
        task.pause_event.set()
        self.futures[task] = self.executor.submit(self._worker, task)

    def pause_task(self, task: DownloadTask):
        task.pause_event.clear()
        task.status = "Paused"
        self.log(f"Paused: {task.url}")

    def resume_task(self, task: DownloadTask):
        if task.status == "Paused":
            task.pause_event.set()
            task.status = "Downloading"
            self.log(f"Resumed: {task.url}")

    def stop_task(self, task: DownloadTask):
        task.stop_flag = True
        task.pause_event.set()
        if task.status not in ("Completed", "Error"):
            task.status = "Stopped"
            self.log(f"Stopped: {task.url}")

    def stop_all_for_shutdown(self):
        """
        Signal every active task to stop and mark it as Paused so it can
        be resumed on next launch. Called from the app's on-close handler.
        """
        for t in self.queue:
            if t.status in ("Downloading", "Waiting"):
                t.stop_flag = True
                t.pause_event.set()
                t.status = "Paused"
        self.save_queue()

    # ---- worker ----------------------------------------------------------
    def _worker(self, task: DownloadTask):
        try:
            task.status = "Downloading"
            self.log(f"Downloading: {task.title} [{task.quality}]")

            # -- 1. Metadata -------------------------------------------------
            if not task.download_url:
                clean = AparatAPI._clean_url(task.url)
                if "/v/" not in clean:
                    raise ValueError("Only single-video URLs are supported.")
                uid   = clean.rsplit("/", 1)[-1]
                attrs = AparatAPI.get_video_info(uid)
                task.title = AparatAPI.get_title(attrs)
                url, size, ext = AparatAPI.get_link_info(attrs, task.quality)
                if not url:
                    raise ValueError(f"Quality {task.quality} is not available.")
                task.download_url = url
                if size and not task.expected_size:
                    task.expected_size = size
            else:
                ext = os.path.splitext(urlparse(task.download_url).path)[1] or ".mp4"

            # -- 2. Filename / folder ---------------------------------------
            if not task.filename:
                if not task.number:
                    task.number = self.next_number()
                safe = sanitize_title(task.title)
                task.filename = f"{task.number:03d}_{safe}_{task.quality}{ext}"
            if not task.save_dir:
                task.save_dir = self.download_dir

            os.makedirs(task.save_dir, exist_ok=True)
            filepath = os.path.join(task.save_dir, task.filename)
            task.partial_file = filepath + ".part"

            # -- 3. Free space check ----------------------------------------
            if task.expected_size > 0:
                free = free_disk_space(task.save_dir)
                needed = task.expected_size + 50 * 1024 * 1024
                if free and free < needed:
                    raise IOError(
                        f"Not enough disk space. Free: {format_bytes(free)}, "
                        f"needed: {format_bytes(needed)}."
                    )

            # -- 4. Decide start mode ---------------------------------------
            file_exists = os.path.isfile(task.partial_file)
            real_size   = os.path.getsize(task.partial_file) if file_exists else 0
            downloaded  = 0

            if (file_exists and task.expected_size > 0
                    and real_size == task.expected_size):
                self.log(f"Reusing reserved space for {task.filename}")
                downloaded = 0
                mode = "r+b"
            elif file_exists and real_size > 0:
                self.log(f"Resuming {task.filename} from {format_bytes(real_size)}")
                downloaded = real_size
                mode = "r+b"
            else:
                mode = "w+b"
                if self.reserve_space and task.expected_size > 0:
                    try:
                        reserve_disk_space(task.partial_file, task.expected_size)
                        mode = "r+b"
                        self.log(f"Reserved {format_bytes(task.expected_size)} "
                                 f"for {task.filename}")
                    except Exception as e:
                        self.log(f"Reservation failed (continuing): {e}")
                        mode = "w+b"

            headers = dict(HEADERS)
            if downloaded > 0:
                headers["Range"] = f"bytes={downloaded}-"

            # -- 5. Stream ---------------------------------------------------
            resp = requests.get(task.download_url, headers=headers,
                                stream=True, timeout=30)
            resp.raise_for_status()

            if downloaded > 0 and resp.status_code == 200:
                self.log("Server ignored Range - restarting from 0")
                downloaded = 0
                mode = "w+b"

            total = int(resp.headers.get("content-length", 0)) + downloaded
            task.total_bytes      = total
            task.downloaded_bytes = downloaded
            task.progress         = (downloaded / total * 100) if total else 0

            start_time  = time.time()
            start_bytes = downloaded

            with open(task.partial_file, mode) as f:
                f.seek(downloaded)
                for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                    if task.stop_flag:
                        task.status = "Paused"
                        return
                    task.pause_event.wait()
                    if task.stop_flag:
                        task.status = "Paused"
                        return
                    if not chunk:
                        continue
                    f.write(chunk)
                    task.downloaded_bytes += len(chunk)
                    if total:
                        task.progress = min(
                            100.0, task.downloaded_bytes / total * 100)
                    elapsed = time.time() - start_time
                    if elapsed > 0:
                        task.speed = (task.downloaded_bytes - start_bytes) / elapsed

            # -- 6. Rename ---------------------------------------------------
            if os.path.isfile(filepath):
                os.remove(filepath)
            os.rename(task.partial_file, filepath)

            task.progress = 100.0
            task.status   = "Completed"
            task.speed    = 0.0
            self.add_to_history(task.url, task.quality)
            self.log(f"Completed: {task.filename}")

        except Exception as e:
            task.status = "Error"
            self.log(f"Error {task.url}: {e}")
        finally:
            self.save_queue()


# ---------------------------------------------------------------------------
# Custom widgets
# ---------------------------------------------------------------------------
class ScrollableFrame(ttk.Frame):

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0,
                                bg="#f5f5f5")
        sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)

        self.inner.bind("<Configure>",
                        lambda e: self.canvas.configure(
                            scrollregion=self.canvas.bbox("all")))
        self._win = self.canvas.create_window((0, 0), window=self.inner,
                                              anchor="nw")
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self._bind_wheel_recursive(self.canvas)
        self._bind_wheel_recursive(self.inner)

    def _on_canvas_resize(self, event):
        self.canvas.itemconfig(self._win, width=event.width)

    def _on_wheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _bind_wheel_recursive(self, widget):
        widget.bind("<MouseWheel>", self._on_wheel)
        for child in widget.winfo_children():
            self._bind_wheel_recursive(child)

    def refresh_mousewheel(self):
        self._bind_wheel_recursive(self.inner)


class QualitySelector(ttk.Frame):
    """Grid of checkboxes for quality selection. Set of qualities is fixed."""

    def __init__(self, parent, qualities=None, selected=None, cols=6, **kw):
        super().__init__(parent, **kw)
        self.vars  = {}
        self._cols = cols
        self.set_qualities(qualities or STANDARD_QUALITIES,
                           selected if selected is not None else DEFAULT_SELECTED)

    def set_qualities(self, qualities, selected=None):
        for w in self.winfo_children():
            w.destroy()
        self.vars.clear()
        selected = set(selected or [])
        for i, q in enumerate(qualities):
            v = tk.BooleanVar(value=(q in selected))
            self.vars[q] = v
            r, c = divmod(i, self._cols)
            ttk.Checkbutton(self, text=q, variable=v).grid(
                row=r, column=c, sticky="w", padx=6, pady=2)

    def get_selected(self):
        return [q for q, v in self.vars.items() if v.get()]

    def select_all(self):
        for v in self.vars.values():
            v.set(True)

    def select_none(self):
        for v in self.vars.values():
            v.set(False)


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------
class AparatChiApp:

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_NAME)

        self.settings = self._load_settings()
        self.root.geometry(self.settings.get("geometry",
                                             DEFAULT_SETTINGS["geometry"]))
        self.root.minsize(1120, 860)

        self.manager = DownloadManager(log_callback=self._log_from_thread)
        self.manager.download_dir = self.settings["download_dir"]
        self.manager.reserve_space = bool(self.settings.get("reserve_space", True))

        self.download_dir       = tk.StringVar(value=self.manager.download_dir)
        self.reserve_var        = tk.BooleanVar(value=self.manager.reserve_space)
        self.channel_folder_var = tk.BooleanVar(
            value=bool(self.settings.get("use_channel_folder", False)))
        self.auto_resume_var    = tk.BooleanVar(
            value=bool(self.settings.get("auto_resume", True)))

        self.processing   = False
        self._queue_dirty = True
        self._closing     = False

        self._setup_style()
        self._build_menubar()
        self._build_ui()

        self._refresh_queue_ui()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Control-Return>", lambda e: self._add_to_queue())
        self.root.bind("<Delete>",         lambda e: self._delete_selected())

        # Auto-resume unfinished downloads if the user enabled it.
        if self.auto_resume_var.get():
            self.root.after(1000, self._auto_resume)

    # ---- settings --------------------------------------------------------
    def _load_settings(self) -> dict:
        s = dict(DEFAULT_SETTINGS)
        if os.path.isfile(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, encoding="utf-8") as f:
                    s.update(json.load(f))
            except Exception:
                pass
        if not s.get("download_dir") or not os.path.isdir(s["download_dir"]):
            s["download_dir"] = DEFAULT_SETTINGS["download_dir"]
        return s

    def _save_settings(self):
        self.settings["download_dir"]       = self.download_dir.get()
        self.settings["qualities"]          = self.quality_selector.get_selected()
        self.settings["geometry"]           = self.root.geometry()
        self.settings["reserve_space"]      = bool(self.reserve_var.get())
        self.settings["use_channel_folder"] = bool(self.channel_folder_var.get())
        self.settings["auto_resume"]        = bool(self.auto_resume_var.get())
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self._log(f"Failed to save settings: {e}")

    # ---- styling ---------------------------------------------------------
    def _setup_style(self):
        s = ttk.Style()
        s.theme_use("clam")

        s.configure(".", font=("Segoe UI", 9), background="#f5f5f5")
        s.configure("TFrame", background="#f5f5f5")
        s.configure("TLabel", background="#f5f5f5", foreground="#202020")
        s.configure("TCheckbutton", background="#f5f5f5")
        s.configure("TLabelframe", background="#f5f5f5",
                    borderwidth=1, relief="solid")
        s.configure("TLabelframe.Label", background="#f5f5f5",
                    foreground="#0078d7", font=("Segoe UI", 9, "bold"))

        s.configure("TEntry",
                    fieldbackground="white",
                    bordercolor="#c0c0c0",
                    lightcolor="#c0c0c0",
                    darkcolor="#c0c0c0",
                    padding=4)

        s.configure("TButton", padding=(10, 5), relief="flat")
        s.map("TButton", background=[("active", "#e1e1e1")])

        s.configure("Accent.TButton", background="#0078d7",
                    foreground="white", font=("Segoe UI", 9, "bold"))
        s.map("Accent.TButton",
              background=[("active", "#005a9e"), ("pressed", "#004578")])

        s.configure("Danger.TButton", background="#d32f2f",
                    foreground="white", font=("Segoe UI", 9, "bold"))
        s.map("Danger.TButton", background=[("active", "#b71c1c")])

        s.configure("Small.TButton", padding=(6, 2), font=("Segoe UI", 8))

        s.configure("Banner.TFrame", background="#0a5d2e")
        s.configure("Banner.TLabel", background="#0a5d2e",
                    foreground="#ffffff", font=("Segoe UI", 10, "italic"))
        s.configure("Header.TFrame", background="#0d47a1")
        s.configure("Header.TLabel", background="#0d47a1",
                    foreground="white", font=("Segoe UI", 14, "bold"))
        s.configure("HeaderSub.TLabel", background="#0d47a1",
                    foreground="#bbdefb", font=("Segoe UI", 9))

        s.configure("Overall.Horizontal.TProgressbar",
                    thickness=16, background="#0078d7",
                    troughcolor="#e0e0e0")
        s.configure("Row.Horizontal.TProgressbar",
                    thickness=10, background="#43a047",
                    troughcolor="#e0e0e0")

    # ---- menu bar --------------------------------------------------------
    def _build_menubar(self):
        menubar = tk.Menu(self.root)

        m_file = tk.Menu(menubar, tearoff=0)
        m_file.add_command(label="Add URLs to Queue", accelerator="Ctrl+Enter",
                           command=self._add_to_queue)
        m_file.add_command(label="Open Download Folder",
                           command=self._open_download_folder)
        m_file.add_separator()
        m_file.add_command(label="Exit", command=self._on_close)
        menubar.add_cascade(label="File", menu=m_file)

        m_edit = tk.Menu(menubar, tearoff=0)
        m_edit.add_command(label="Clear URL box",
                           command=lambda: self.url_text.delete("1.0", "end"))
        m_edit.add_command(label="Clear Log", command=self._clear_log)
        m_edit.add_command(label="Clear Completed Downloads",
                           command=self._clear_completed)
        m_edit.add_separator()
        m_edit.add_command(label="Delete Selected Task", accelerator="Delete",
                           command=self._delete_selected)
        menubar.add_cascade(label="Edit", menu=m_edit)

        m_view = tk.Menu(menubar, tearoff=0)
        m_view.add_command(label="Open Log File",
                           command=lambda: open_path(LOG_FILE))
        m_view.add_command(label="Open Queue File",
                           command=lambda: open_path(QUEUE_FILE))
        m_view.add_command(label="Open History File",
                           command=lambda: open_path(HISTORY_FILE))
        m_view.add_command(label="Open Project Website",
                           command=lambda: open_path(APP_WEBSITE))
        menubar.add_cascade(label="View", menu=m_view)

        m_help = tk.Menu(menubar, tearoff=0)
        m_help.add_command(label="Changelog", command=self._show_changelog)
        m_help.add_command(label="About",     command=self._show_about)
        menubar.add_cascade(label="Help", menu=m_help)

        self.root.config(menu=menubar)

    # ---- main layout -----------------------------------------------------
    def _build_ui(self):

        banner = ttk.Frame(self.root, style="Banner.TFrame", padding=(10, 8))
        banner.pack(fill="x")
        ttk.Label(
            banner,
            text="In the name of Allah, the Most Gracious, the Most Merciful.  786",
            style="Banner.TLabel", anchor="center",
        ).pack(fill="x")

        header = ttk.Frame(self.root, style="Header.TFrame", padding=(14, 10))
        header.pack(fill="x")
        ttk.Label(header, text=f"\u2B07  {APP_NAME}",
                  style="Header.TLabel").pack(side="left")
        ttk.Label(header, text=f"v{APP_VERSION}",
                  style="HeaderSub.TLabel").pack(side="right", padx=(0, 4))

        top = ttk.LabelFrame(self.root, text="  Add Videos  ", padding=12)
        top.pack(fill="x", padx=12, pady=(12, 6))

        ttk.Label(top, text="Video URLs (one per line):").grid(
            row=0, column=0, sticky="nw")
        self.url_text = tk.Text(top, height=4, width=70, font=("Consolas", 9),
                                relief="solid", borderwidth=1,
                                highlightthickness=0)
        self.url_text.grid(row=0, column=1, columnspan=3, sticky="ew",
                           padx=(8, 0), pady=(0, 4))
        attach_text_menu(self.url_text)
        top.columnconfigure(1, weight=1)
        top.columnconfigure(3, weight=1)

        qbox = ttk.LabelFrame(top,
                              text="  Qualities (select one or more)  ",
                              padding=8)
        qbox.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        self.quality_selector = QualitySelector(
            qbox, selected=self.settings.get("qualities", DEFAULT_SELECTED))
        self.quality_selector.pack(side="left", fill="x", expand=True)

        qbtns = ttk.Frame(qbox)
        qbtns.pack(side="right", padx=(10, 0))
        ttk.Button(qbtns, text="All",  width=6,
                   command=self.quality_selector.select_all).pack(pady=1)
        ttk.Button(qbtns, text="None", width=6,
                   command=self.quality_selector.select_none).pack(pady=1)

        row2 = ttk.Frame(top)
        row2.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(10, 0))

        ttk.Label(row2, text="Download folder (for NEW tasks):").pack(side="left")
        ttk.Entry(row2, textvariable=self.download_dir, width=52).pack(
            side="left", padx=8, fill="x", expand=True)
        ttk.Button(row2, text="Browse...",
                   command=self._browse_folder).pack(side="left")

        # Options row
        row3 = ttk.Frame(top)
        row3.grid(row=3, column=0, columnspan=4, sticky="w", pady=(8, 0))
        ttk.Checkbutton(
            row3,
            text="Reserve disk space before download (recommended)",
            variable=self.reserve_var,
            command=self._on_reserve_toggle,
        ).pack(side="left")

        ttk.Checkbutton(
            row3,
            text="Save each video in a folder named after its channel",
            variable=self.channel_folder_var,
            command=self._on_channel_toggle,
        ).pack(side="left", padx=(20, 0))

        ttk.Checkbutton(
            row3,
            text="Auto-resume unfinished downloads on startup",
            variable=self.auto_resume_var,
            command=self._on_auto_resume_toggle,
        ).pack(side="left", padx=(20, 0))

        ttk.Button(top, text="+  Add to Queue", style="Accent.TButton",
                   command=self._add_to_queue).grid(
            row=4, column=0, columnspan=4, sticky="e", pady=(12, 0))

        mid = ttk.LabelFrame(self.root, text="  Download Queue  ", padding=12)
        mid.pack(fill="both", expand=True, padx=12, pady=6)

        overall = ttk.Frame(mid)
        overall.pack(fill="x", pady=(0, 10))
        ttk.Label(overall, text="Overall progress:").pack(side="left")
        self.overall_pb = ttk.Progressbar(
            overall, style="Overall.Horizontal.TProgressbar",
            maximum=100, mode="determinate")
        self.overall_pb.pack(side="left", fill="x", expand=True, padx=(10, 10))
        self.overall_lbl = ttk.Label(overall, text="0 / 0  -  0.0%",
                                     width=24, anchor="e")
        self.overall_lbl.pack(side="right")

        self.queue_canvas = ScrollableFrame(mid)
        self.queue_canvas.pack(fill="both", expand=True)

        ctrl = ttk.Frame(mid)
        ctrl.pack(fill="x", pady=(10, 0))
        ttk.Button(ctrl, text="\u25B6  Start All", style="Accent.TButton",
                   command=self._start_all).pack(side="left", padx=2)
        ttk.Button(ctrl, text="\u23F8  Pause All",
                   command=self._pause_all).pack(side="left", padx=2)
        ttk.Button(ctrl, text="\u23F9  Stop All", style="Danger.TButton",
                   command=self._stop_all).pack(side="left", padx=2)
        ttk.Button(ctrl, text="\U0001F5D1  Clear Completed",
                   command=self._clear_completed).pack(side="left", padx=2)

        bot = ttk.LabelFrame(self.root, text="  Log  ", padding=6)
        bot.pack(fill="both", padx=12, pady=(6, 12))
        self.log_text = scrolledtext.ScrolledText(
            bot, height=8, state="disabled",
            font=("Consolas", 8), bg="#1e1e1e", fg="#dcdcdc",
            insertbackground="#dcdcdc", relief="flat", borderwidth=0)
        self.log_text.pack(fill="both", expand=True)
        attach_text_menu(self.log_text)

        self.task_widgets = {}
        self.selected_task = None

    # ---- logging helpers -------------------------------------------------
    def _log(self, msg: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{msg}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _log_from_thread(self, msg: str):
        self.root.after(0, self._log, msg)

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    # ---- file / folder helpers ------------------------------------------
    def _browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self.download_dir.get())
        if folder:
            self.download_dir.set(folder)
            self.manager.download_dir = folder
            self._save_settings()
            self._log(f"New tasks will be saved to: {folder}")

    def _open_download_folder(self):
        open_path(self.download_dir.get())

    def _on_reserve_toggle(self):
        self.manager.reserve_space = bool(self.reserve_var.get())
        self._save_settings()
        state = "enabled" if self.reserve_var.get() else "disabled"
        self._log(f"Disk space reservation {state}.")

    def _on_channel_toggle(self):
        self._save_settings()
        state = "enabled" if self.channel_folder_var.get() else "disabled"
        self._log(f"Save in channel folder {state}.")

    def _on_auto_resume_toggle(self):
        self._save_settings()
        state = "enabled" if self.auto_resume_var.get() else "disabled"
        self._log(f"Auto-resume on startup {state}.")

    # ---- auto-resume -----------------------------------------------------
    def _auto_resume(self):
        """
        Called at startup if auto_resume is enabled.
        Restarts every task that was left in Paused / Stopped / Waiting.
        """
        resumable = [t for t in self.manager.queue
                     if t.status in ("Paused", "Stopped", "Waiting")]
        if not resumable:
            return
        self._log(f"Auto-resuming {len(resumable)} unfinished download(s)...")
        self.processing = True
        for t in resumable:
            t.status = "Waiting"
            self.manager.start_download(t)

    # ---- adding to the queue --------------------------------------------
    def _add_to_queue(self):
        raw = self.url_text.get("1.0", "end").strip()
        if not raw:
            messagebox.showwarning("No URLs", "Please enter at least one URL.")
            return

        qualities = self.quality_selector.get_selected()
        if not qualities:
            messagebox.showwarning("No quality",
                                   "Please select at least one quality.")
            return

        batch_folder = self.download_dir.get()
        os.makedirs(batch_folder, exist_ok=True)
        self.manager.download_dir = batch_folder

        urls  = [u.strip() for u in raw.splitlines() if u.strip()]
        added = 0

        for url in urls:
            if not AparatAPI.is_valid_url(url):
                self._log(f"Invalid URL skipped: {url}")
                continue

            try:
                clean = AparatAPI._clean_url(url)
                uid   = clean.rsplit("/", 1)[-1]
                attrs = AparatAPI.get_video_info(uid)
                title   = AparatAPI.get_title(attrs)
                channel = AparatAPI.get_channel_name(attrs)
                avail   = AparatAPI.get_available_qualities(attrs)
            except Exception as e:
                self._log(f"Failed to fetch info for {url}: {e}")
                title, attrs, channel, avail = "unknown", None, "", []

            if avail:
                self._log(f"Available qualities for '{title}': "
                          f"{', '.join(avail)}")

            task_folder = batch_folder
            if self.channel_folder_var.get() and channel:
                safe_channel = sanitize_title(channel)
                task_folder = os.path.join(batch_folder, safe_channel)
                os.makedirs(task_folder, exist_ok=True)
                self._log(f"Channel folder: {task_folder}")

            url_number = self.manager.next_number()
            created = set()

            for q in qualities:
                actual_q = q
                if attrs is not None and avail and q not in avail:
                    fallback = AparatAPI.closest_quality(avail, q)
                    if not fallback:
                        self._log(f"Quality {q} unavailable for '{title}' - skipped")
                        continue
                    actual_q = fallback
                    self._log(f"Quality {q} unavailable for '{title}' - "
                              f"using {actual_q}")

                if actual_q in created:
                    continue
                created.add(actual_q)

                if self.manager.is_duplicate(url, actual_q):
                    if not messagebox.askyesno(
                        "Duplicate",
                        f"Already downloaded:\n{url}\nQuality: {actual_q}\n\n"
                        "Do you want to download it again?"):
                        continue

                task = DownloadTask(url, actual_q, title=title,
                                    number=url_number,
                                    save_dir=task_folder,
                                    channel=channel)

                ext = ".mp4"
                if attrs is not None:
                    direct, size, ext = AparatAPI.get_link_info(attrs, actual_q)
                    if direct:
                        task.download_url = direct
                    task.expected_size = size

                safe = sanitize_title(title)
                task.filename = f"{url_number:03d}_{safe}_{actual_q}{ext}"

                self.manager.add_task(task)

                if self.processing:
                    self.manager.start_download(task)

                added += 1

        if added:
            self.url_text.delete("1.0", "end")
            self._queue_dirty = True
            self._save_settings()

    # ---- queue rendering -------------------------------------------------
    def _rebuild_queue_ui(self):
        for w in self.queue_canvas.inner.winfo_children():
            w.destroy()
        self.task_widgets.clear()
        for idx, task in enumerate(self.manager.queue):
            self._build_queue_row(self.queue_canvas.inner, idx, task)
        self.queue_canvas.refresh_mousewheel()

    def _build_queue_row(self, parent, idx: int, task: DownloadTask):
        card = tk.Frame(parent, bg="white",
                        highlightbackground="#d0d0d0", highlightthickness=1)
        card.pack(fill="x", padx=6, pady=4)

        def _select(event=None, t=task):
            self._select_task(t)
        card.bind("<Button-1>", _select)

        left = tk.Frame(card, bg="white")
        left.pack(side="left", fill="x", expand=True, padx=10, pady=8)
        left.bind("<Button-1>", _select)

        title_row = tk.Frame(left, bg="white")
        title_row.pack(anchor="w", fill="x")
        title_row.bind("<Button-1>", _select)

        num_txt = f"{task.number:03d}." if task.number else f"{idx+1:03d}."
        tk.Label(title_row, text=num_txt, bg="white", fg="#888",
                 font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Label(title_row, text=task.title, bg="white", fg="#1a1a1a",
                 font=("Segoe UI", 10, "bold")).pack(side="left", padx=(6, 8))

        qfg, qbg = quality_color(task.quality)
        tk.Label(title_row, text=f" {task.quality} ", bg=qbg, fg=qfg,
                 font=("Segoe UI", 8, "bold")).pack(side="left")

        if task.channel:
            tk.Label(title_row, text=f"  \U0001F464 {task.channel}",
                     bg="white", fg="#6a1b9a",
                     font=("Segoe UI", 8, "bold")).pack(side="left", padx=(4, 0))

        size_txt = format_bytes(task.expected_size) if task.expected_size else "size ?"
        tk.Label(title_row, text=f"  {size_txt}", bg="white", fg="#666",
                 font=("Segoe UI", 8)).pack(side="left", padx=(6, 0))

        save_path = os.path.join(task.save_dir or "?", task.filename or "?")
        save_row = tk.Frame(left, bg="white")
        save_row.pack(anchor="w", fill="x", pady=(4, 0))
        save_row.bind("<Button-1>", _select)
        tk.Label(save_row, text="\U0001F4C1", bg="white", fg="#0d47a1",
                 font=("Segoe UI", 9)).pack(side="left")
        tk.Label(save_row, text=save_path, bg="white", fg="#0d47a1",
                 font=("Segoe UI", 8), anchor="w",
                 justify="left").pack(side="left", padx=(4, 0))

        url_row = tk.Frame(left, bg="white")
        url_row.pack(anchor="w", fill="x", pady=(2, 0))
        url_row.bind("<Button-1>", _select)
        tk.Label(url_row, text="\U0001F517", bg="white", fg="#7a7a7a",
                 font=("Segoe UI", 8)).pack(side="left")
        tk.Label(url_row, text=task.url, bg="white", fg="#7a7a7a",
                 font=("Segoe UI", 8), anchor="w").pack(side="left", padx=(4, 0))

        mid = tk.Frame(card, bg="white")
        mid.pack(side="left", fill="x", expand=True, padx=10)
        mid.bind("<Button-1>", _select)

        pb = ttk.Progressbar(mid, style="Row.Horizontal.TProgressbar",
                             length=240, maximum=100)
        pb.pack(fill="x")
        pb["value"] = task.progress

        status_lbl = tk.Label(mid, text=self._status_text(task),
                              bg="white", fg="#555",
                              font=("Segoe UI", 8), anchor="w")
        status_lbl.pack(anchor="w", pady=(2, 0))

        btns = tk.Frame(card, bg="white")
        btns.pack(side="right", padx=10, pady=8)

        ctrl_row = tk.Frame(btns, bg="white")
        ctrl_row.pack(anchor="e")
        ttk.Button(ctrl_row, text="\u23F9 Stop", width=8, style="Small.TButton",
                   command=lambda t=task: self.manager.stop_task(t)).pack(
            side="left", padx=2)
        ttk.Button(ctrl_row, text="\u25B6 Resume", width=10, style="Small.TButton",
                   command=lambda t=task: self._resume_task(t)).pack(
            side="left", padx=2)
        ttk.Button(ctrl_row, text="\U0001F5D1 Delete", width=10,
                   style="Danger.TButton",
                   command=lambda t=task: self._delete_task(t)).pack(
            side="left", padx=2)

        open_row = tk.Frame(btns, bg="white")
        open_row.pack(anchor="e", pady=(4, 0))
        ttk.Button(open_row, text="\U0001F4C1 Open Folder", width=14,
                   style="Small.TButton",
                   command=lambda t=task: self._open_task_folder(t)).pack(
            side="left", padx=2)
        open_file_btn = ttk.Button(
            open_row, text="\u25B6 Open File", width=12,
            style="Small.TButton",
            command=lambda t=task: self._open_task_file(t))
        open_file_btn.pack(side="left", padx=2)
        if task.status != "Completed":
            open_file_btn.state(["disabled"])

        self.task_widgets[task] = {
            "progress":  pb,
            "status":    status_lbl,
            "save":      save_path,
            "card":      card,
            "open_file": open_file_btn,
        }

    @staticmethod
    def _status_text(task: DownloadTask) -> str:
        pct = f"{task.progress:5.1f}%"
        if task.status == "Downloading":
            return f"{pct}   -   {format_speed(task.speed)}"
        if task.status == "Paused":
            return f"{pct}   -   Paused"
        if task.status == "Completed":
            return "100.0%   -   Done"
        if task.status == "Error":
            return "Error"
        if task.status == "Stopped":
            return f"{pct}   -   Stopped"
        return f"{task.status}"

    # ---- open task folder / file ----------------------------------------
    def _open_task_folder(self, task: DownloadTask):
        folder = task.save_dir
        if folder and os.path.isdir(folder):
            open_path(folder)
        else:
            messagebox.showerror("Folder not found",
                                 f"Folder does not exist:\n{folder}")

    def _open_task_file(self, task: DownloadTask):
        if task.status != "Completed":
            messagebox.showinfo("Not ready",
                                "This download has not completed yet.")
            return
        filepath = os.path.join(task.save_dir or "", task.filename or "")
        if filepath and os.path.isfile(filepath):
            open_path(filepath)
        else:
            messagebox.showerror("File not found",
                                 f"File does not exist:\n{filepath}")

    # ---- selection / delete ---------------------------------------------
    def _select_task(self, task: DownloadTask):
        if self.selected_task and self.selected_task in self.task_widgets:
            try:
                self.task_widgets[self.selected_task]["card"].configure(
                    highlightbackground="#d0d0d0", highlightthickness=1)
            except tk.TclError:
                pass
        self.selected_task = task
        if task in self.task_widgets:
            try:
                self.task_widgets[task]["card"].configure(
                    highlightbackground="#0078d7", highlightthickness=2)
            except tk.TclError:
                pass

    def _delete_task(self, task: DownloadTask):
        if not messagebox.askyesno(
            "Delete task",
            f"Remove this task from the queue?\n\n{task.title}\n[{task.quality}]"
        ):
            return
        self.manager.delete_task(task)
        if self.selected_task is task:
            self.selected_task = None
        self._queue_dirty = True

    def _delete_selected(self):
        if self.selected_task:
            self._delete_task(self.selected_task)

    # ---- periodic refresh -----------------------------------------------
    def _refresh_queue_ui(self):
        if self._closing:
            return
        if self._queue_dirty:
            self._rebuild_queue_ui()
            self._queue_dirty = False

        for task, w in list(self.task_widgets.items()):
            try:
                w["progress"]["value"] = task.progress
                w["status"].configure(text=self._status_text(task))
                if task.status == "Completed":
                    w["open_file"].state(["!disabled"])
                else:
                    w["open_file"].state(["disabled"])
            except tk.TclError:
                pass

        self._update_overall_progress()
        self.root.after(500, self._refresh_queue_ui)

    def _update_overall_progress(self):
        tasks = self.manager.queue
        if not tasks:
            self.overall_pb["value"] = 0
            self.overall_lbl.configure(text="0 / 0  -  0.0%")
            return
        avg       = sum(t.progress for t in tasks) / len(tasks)
        completed = sum(1 for t in tasks if t.status == "Completed")
        self.overall_pb["value"] = avg
        self.overall_lbl.configure(
            text=f"{completed} / {len(tasks)}  -  {avg:.1f}%")

    # ---- task control handlers ------------------------------------------
    def _resume_task(self, task):
        if task.status == "Paused":
            self.manager.resume_task(task)
        elif task.status in ("Stopped", "Error", "Waiting"):
            self.manager.start_download(task)

    def _start_all(self):
        self.processing = True
        for t in self.manager.queue:
            if t.status in ("Waiting", "Stopped", "Error"):
                self.manager.start_download(t)

    def _pause_all(self):
        for t in self.manager.queue:
            if t.status == "Downloading":
                self.manager.pause_task(t)

    def _stop_all(self):
        self.processing = False
        for t in self.manager.queue:
            self.manager.stop_task(t)

    def _clear_completed(self):
        self.manager.queue = [t for t in self.manager.queue
                              if t.status != "Completed"]
        self.manager.save_queue()
        self._queue_dirty = True

    # ---- changelog window -----------------------------------------------
    def _show_changelog(self):
        win = tk.Toplevel(self.root)
        win.title(f"{APP_NAME} - Changelog")
        win.geometry("700x620")
        win.transient(self.root)
        win.grab_set()

        hdr = tk.Frame(win, bg="#0d47a1", height=60)
        hdr.pack(fill="x")
        tk.Label(hdr, text=f"\U0001F4DC  Changelog - {APP_NAME}",
                 bg="#0d47a1", fg="white",
                 font=("Segoe UI", 13, "bold")).pack(pady=16)

        body = tk.Frame(win, bg="white")
        body.pack(fill="both", expand=True)

        txt = scrolledtext.ScrolledText(
            body, wrap="word", font=("Segoe UI", 9),
            bg="white", fg="#1a1a1a", relief="flat", borderwidth=0,
            padx=14, pady=10)
        txt.pack(fill="both", expand=True)

        txt.tag_configure("ver", font=("Segoe UI", 12, "bold"),
                          foreground="#0d47a1", spacing1=10, spacing3=4)
        txt.tag_configure("date", font=("Segoe UI", 8, "italic"),
                          foreground="#888", spacing3=6)
        txt.tag_configure("item", font=("Segoe UI", 9),
                          lmargin1=20, lmargin2=32, spacing3=3)

        for entry in CHANGELOG:
            txt.insert("end", f"Version {entry['version']}\n", "ver")
            txt.insert("end", f"{entry['date']}\n", "date")
            for ch in entry["changes"]:
                txt.insert("end", f"\u2022  {ch}\n", "item")
            txt.insert("end", "\n")

        txt.configure(state="disabled")

        ttk.Button(win, text="Close", command=win.destroy).pack(pady=10)

    # ---- about dialog ---------------------------------------------------
    def _show_about(self):
        about = tk.Toplevel(self.root)
        about.title(f"About {APP_NAME}")
        about.geometry("560x640")
        about.resizable(False, False)
        about.transient(self.root)
        about.grab_set()

        hdr = tk.Frame(about, bg="#0a5d2e", height=40)
        hdr.pack(fill="x")
        tk.Label(hdr,
                 text="In the name of Allah, the Most Gracious, the Most Merciful.  786",
                 bg="#0a5d2e", fg="white",
                 font=("Segoe UI", 10, "italic")).pack(pady=10)

        hdr2 = tk.Frame(about, bg="#0d47a1", height=70)
        hdr2.pack(fill="x")
        tk.Label(hdr2, text=f"\u2B07  {APP_NAME}",
                 bg="#0d47a1", fg="white",
                 font=("Segoe UI", 14, "bold")).pack(pady=18)

        body = tk.Frame(about, bg="white")
        body.pack(fill="both", expand=True)

        tk.Label(body, text=f"Version {APP_VERSION}",
                 bg="white", fg="#333",
                 font=("Segoe UI", 11, "bold")).pack(pady=(14, 4))

        desc = (
            "A friendly Windows GUI for downloading Aparat videos\n"
            "in one or many qualities at once.\n\n"
            "Built with Python + Tkinter.\n"
            "Uses the public Aparat JSON API only.\n"
        )
        tk.Label(body, text=desc, bg="white", fg="#555",
                 font=("Segoe UI", 9), justify="center").pack(pady=(0, 10))

        site_frame = tk.Frame(body, bg="white")
        site_frame.pack(pady=(0, 10))
        tk.Label(site_frame, text="Project website:",
                 bg="white", fg="#333",
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 4))
        link = tk.Label(site_frame, text=APP_WEBSITE,
                        bg="white", fg="#0d47a1",
                        font=("Segoe UI", 9, "underline"),
                        cursor="hand2")
        link.pack(side="left")
        link.bind("<Button-1>", lambda e: open_path(APP_WEBSITE))

        shortcuts = (
            "Shortcuts\n"
            "  Ctrl + Enter    Add URLs to the queue\n"
            "  Delete          Delete selected task\n"
            "  Ctrl + A        Select all in a text box\n"
            "  Mouse wheel     Scroll the queue\n"
            "  Right-click     Cut / Copy / Paste in text boxes"
        )
        tk.Label(body, text=shortcuts, bg="white", fg="#333",
                 font=("Consolas", 8), justify="left").pack(pady=(6, 10))

        tk.Label(body, text=f"\u00A9 {APP_YEAR} {APP_AUTHOR}  -  MIT License",
                 bg="white", fg="#999",
                 font=("Segoe UI", 8)).pack(pady=(0, 8))

        ttk.Button(body, text="Close",
                   command=about.destroy).pack(pady=(0, 14))

    # ---- shutdown --------------------------------------------------------
    def _on_close(self):
        """
        Graceful shutdown:
          1. If downloads are active, ask for confirmation.
          2. Signal all workers to stop and mark them as Paused.
          3. Save queue.json + settings.json.
          4. Destroy the window and force-exit the process.
        The .part files remain on disk so the next launch can resume.
        """
        active = [t for t in self.manager.queue
                  if t.status in ("Downloading", "Paused", "Waiting")]

        if active:
            if not messagebox.askyesno(
                "Active downloads",
                f"{len(active)} download(s) are still in progress.\n\n"
                "Close the program anyway?\n"
                "They will be saved as Paused and can be resumed later."
            ):
                return

        self._closing = True

        # Ask all workers to stop and mark them Paused so resume is clean.
        self.manager.stop_all_for_shutdown()

        # Persist settings.
        self._save_settings()

        # Give workers a brief moment, then destroy + force exit.
        self.root.after(300, self._force_exit)

    def _force_exit(self):
        try:
            self.root.destroy()
        except Exception:
            pass
        # Force-exit so daemonized ThreadPoolExecutor threads cannot hang
        # the process. All state has already been written to disk.
        os._exit(0)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    root = tk.Tk()
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    AparatChiApp(root)
    root.mainloop()