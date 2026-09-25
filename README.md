
============================================================================
 AparatChi - Professional Windows GUI for Aparat video downloads
============================================================================
 Project website: https://github.com/reza1399707/AparatChi

Aparat.com Bulk Downloader - Professional Windows GUI
 Features
 --------
 * Add one or many Aparat URLs at once.
 * Pick MULTIPLE qualities via checkboxes -> one task per (URL x quality).
 * Two concurrent downloads (ThreadPoolExecutor, max_workers=2).
 * Per-task + overall progress bars, live speed, expected file size.
 * Save location shown on every queue card.
 * Delete any task from the queue with one click.
 * Each task keeps the download folder that was active when it was added,
   so changing the folder only affects NEW tasks.
 * Optional disk-space reservation before each download.
 * Persistent queue (queue.json) with HTTP Range resume support.
 * Persistent numbering across sessions (counter.json), one number per URL.
 * Download history (history.json) with duplicate confirmation per (url, quality).
 * Settings persistence (settings.json): folder, qualities, window geometry.
 * Full log on screen and in apyrat_gui.log.
 * Right-click Cut / Copy / Paste / Select-All on text widgets.
 * Mouse-wheel scrolling works over the entire queue area.
 * New tasks auto-start if the queue is currently running.
 * Bismillah 786 banner at the top of the window and About dialog.
============================================================================
