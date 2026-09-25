Aparat Bulk Downloader - Professional Windows GUI
============================================================================
 A Tkinter front-end around the Aparat public API, inspired by the apyrat
 project (https://github.com/CodeWithEmad/apyrat).

 Highlights
 ----------
 * Add one or many Aparat URLs at once.
 * Pick MULTIPLE qualities via checkboxes -> one task per (URL x quality).
 * Two concurrent downloads (ThreadPoolExecutor, max_workers=2).
 * Per-task + overall progress bars, live speed, and expected file size.
 * Persistent queue (queue.json) with HTTP Range resume support.
 * Download history (history.json) with duplicate confirmation.
 * Settings persistence (settings.json): folder, qualities, window geometry.
 * Full log on screen and in apyrat_gui.log.
 * Right-click Cut / Copy / Paste / Select-All on text widgets.
 * Mouse-wheel scrolling works over the entire queue area.
 * New tasks are auto-started if the queue is currently running.

 The code is organised in clearly commented sections:
   1.  Configuration constants
   2.  Logging
   3.  Small utility helpers
   4.  Aparat API wrapper
   5.  Download task data class
   6.  Download manager (thread pool + persistence)
   7.  Custom UI widgets (scrollable frame, quality selector)
   8.  Main application (menus, layout, events)
