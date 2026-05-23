# crawl-the-threads

End-to-end automation for the **scrape Threads bookmarks → classify → unsave AI posts → produce markdown notes** workflow.

Bundles the entire pipeline into a single project that orchestrates two existing repos **without modifying them**:

- [`threads-scriber`](../threads-scriber/) — original userscript (fork lives here)
- [`PROJECT_threads-to-note`](../PROJECT_threads-to-note/) — markdown note generator (invoked as subprocess)

---

## What it does

```
[Browser scrape via forked userscript] ─→ catch.json (fixed path)
                                              │
                                              ▼ (mtime + debounce)
                          scripts/watch_pipeline.py
                                              │
                          ┌───────────────────┴───────────────────┐
                          ▼                                       ▼
   scripts/classify_to_scribe_ai.py            subprocess: python app.py
   (Gemini classifier, AI+科技 filter)          (PROJECT_threads-to-note)
                          │                                       │
                          ▼                                       ▼
                  unsave.json                          markdown notes
                          │
                          ▼ (FS Access API poll lastModified)
   forked userscript: auto-load + auto-unsave
```

After setup, **the only manual step is starting a scrape from the browser panel**.

---

## Prerequisites

| Requirement | Why needed |
| --- | --- |
| Python 3.11+ | watcher, classifier, note generator |
| Node.js 18+ | `chrome-ws` CLI (agent driver) |
| Google Chrome / Edge | browser automation via Chrome DevTools Protocol |
| Tampermonkey extension | userscript injection |
| Claude Code with superpowers-chrome plugin | provides the `chrome-ws` CDP CLI used by `agent_driver.py` |

---

## Install

### 0. superpowers-chrome (CDP automation, required for `agent_driver.py`)

`agent_driver.py` drives the browser through the **superpowers-chrome** plugin, which ships a `chrome-ws` Node.js CLI for Chrome DevTools Protocol commands.

#### A. Install the plugin

In Claude Code, install the `superpowers-chrome` plugin from the superpowers marketplace (version 2.1.0 or later). After installation the CLI lands at:

```
C:\Users\<you>\.claude\plugins\cache\superpowers-marketplace\superpowers-chrome\2.1.0\skills\browsing\chrome-ws
```

Verify Node can run it:

```powershell
node "C:\Users\<you>\.claude\plugins\cache\superpowers-marketplace\superpowers-chrome\2.1.0\skills\browsing\chrome-ws" --help
```

#### B. Set `CHROME_WS_PATH` in `.env`

`agent_driver.py` requires `CHROME_WS_PATH` — there is no default. Set it in `.env`:

```dotenv
CHROME_WS_PATH=C:\Users\<you>\.claude\plugins\cache\superpowers-marketplace\superpowers-chrome\2.1.0\skills\browsing\chrome-ws
```

#### C. Enable Chrome remote debugging

Chrome must be launched with `--remote-debugging-port=9222` **before** running any `agent_driver.py` commands.

**Option 1 — shortcut (recommended)**

1. Copy the Chrome shortcut on your desktop / taskbar.
2. Right-click → Properties → Target, append ` --remote-debugging-port=9222`.
3. Always open Chrome through this shortcut.

```
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
```

**Option 2 — PowerShell one-liner (temporary)**

```powershell
Start-Process "chrome.exe" "--remote-debugging-port=9222"
```

Verify the port is open:

```powershell
Invoke-WebRequest http://localhost:9222/json | Select-Object -Expand Content
```

Should return a JSON list of open tabs.

#### D. Agent hooks guard this preflight

This repo contains local hooks for both agent environments:

- `.claude/settings.json` runs `.claude/hooks/check-chrome-debug.ps1` before Claude Code shell commands.
- `.codex/hooks.json` runs `.codex/check-chrome-debug.ps1` through `.codex/check-chrome-debug.cmd` before Codex shell commands.

Both hooks only target `agent_driver.py` and `push_userscript.py`. They block those commands when `127.0.0.1:9222` is not reachable, so agents do not fall back to Edge, a fresh non-debug Chrome window, or manual Tampermonkey edits.

---

### 1. Python side

```powershell
cd path\to\crawl-the-threads
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# edit .env: fill GEMINI_API_KEY and CHROME_WS_PATH; verify CATCH_PATH / UNSAVE_PATH / MARKDOWN_PATH
```

The note project must already be set up (its own `.env`, `THREADS_GEMINI_*` keys, output dir, etc.). See `PROJECT_threads-to-note/README.md`.

### 2. Browser side

1. Launch Chrome with `--remote-debugging-port=9222` (see above).
2. Navigate to `https://www.threads.com/saved` and keep this tab open.
3. Install [Tampermonkey](https://www.tampermonkey.net/) in Chrome / Edge.
4. Disable the original `threads-scriber.user.js` if it is installed.
5. Open `userscripts/threads-scriber-auto.user.js` and click "Install" in Tampermonkey.
6. Reload the `/saved` tab. A floating panel "crawl-the-threads · Auto AI Sync" appears bottom-right.
7. In the **Threads Scriber panel**: click **設定自動存檔** → pick `data/catch.json`. (Write permission, persists across reloads.)
8. In the **AutoAiSync panel**: click **綁定 unsave.json** → pick `data/unsave.json`. (Read permission, one-time per profile.)
9. Tick **自動載入 unsave.json** and **載入後自動取消儲存** when ready for the fully automated flow.
10. Confirm setup: `python scripts/agent_driver.py probe` should print `OK: panel ready for agent-driven scrape`.

---

## Daily usage SOP

### Terminal A — start the watcher (keep running)

```powershell
cd path\to\crawl-the-threads
.\start_pipeline.ps1
```

Logs stream to console and `pipeline.log`. Stop with `Ctrl+C`.

---

### Terminal B — agent-driven scrape

#### Step 1 · Verify panel readiness

```powershell
python scripts/agent_driver.py probe
```

Expected output ends with `OK: panel ready for agent-driven scrape`.

**If it reports problems:**

| Problem | Fix |
| --- | --- |
| `panel missing` | Reload the `/saved` tab; wait for Tampermonkey to inject |
| `scriptVersion=X expected 0.3.0` | Re-install `userscripts/threads-scriber-auto.user.js` in Tampermonkey |
| `autosave (catch.json) not bound` | Click **設定自動存檔** in the panel, pick `data/catch.json`; re-run probe |
| `unsave.json handle not bound in AutoAiSync panel` | Click **綁定 unsave.json** in the AutoAiSync panel, pick `data/unsave.json`; re-run probe |
| `AutoAiSync panel missing` | Reload `/saved` tab |

#### Step 2 · Trigger scrape

```powershell
# Capture everything since 2010 (all saves):
python scripts/agent_driver.py scrape --cutoff 2010-01-01 --wait-seconds 300

# Or limit to a recent window (faster, fewer Gemini tokens):
python scripts/agent_driver.py scrape --cutoff 2025-01-01 --wait-seconds 120
```

`--cutoff` sets the date input in the panel before clicking 開始抓取.  
Each `scrape` run first clicks **清空結果** so `catch.json` contains only the current run, not stale panel/localStorage items from an earlier cutoff.
`--wait-seconds` polls `狀態` until idle (`待機中` / `完成` / `已停止`) or timeout.

#### Step 3 · Wait for pipeline

Watch Terminal A. After `catch.json` stabilises, the watcher fires both jobs:

```
pipeline starting: items=N
[classify] exit code: 0
[notes]    exit code: 0
```

`unsave.json` and markdown notes are both ready at this point.

#### Step 4 · AutoAiSync auto-unsave

The forked userscript polls `unsave.json` every 3 s. When `lastModified` changes it auto-loads the AI results. If **載入後自動取消儲存** is ticked, the unsave flow starts immediately — no further action needed.

To verify the load happened, check the AutoAiSync panel status line; it should show the loaded `generatedAt` timestamp and the count of AI-tagged items.

---

### Quick-check commands

```powershell
# Dump raw panel state:
python scripts/agent_driver.py status

# Click an arbitrary panel button (e.g. stop):
python scripts/agent_driver.py click unsave-selected
```

---

## Configuration

### `.env` — secrets and machine-specific paths

| Key | Default | Used by |
| --- | --- | --- |
| `CATCH_PATH` | `data/catch.json` | classifier, watcher, userscript handle |
| `UNSAVE_PATH` | `data/unsave.json` | classifier, watcher, userscript handle |
| `MARKDOWN_PATH` | `..\PROJECT_threads-to-note` | watcher (subprocess cwd) |
| `GEMINI_API_KEY` | _required_ | classifier |
| `CHROME_WS_PATH` | _required_ | agent_driver — path to the `chrome-ws` CLI |
| `CLASSIFIER_MODEL` | `gemini-2.5-flash` | classifier |
| `DEBOUNCE_SECONDS` | `2.0` | watcher |
| `POLL_SECONDS` | `1.0` | watcher |

### `classify_config.json` — classification logic

Edit this file to customise categories without touching Python.

| Key | Description |
| --- | --- |
| `categories` | Ordered list of categories the Gemini classifier can output |
| `unsaved-categories` | Subset of `categories` that map to `decision="ai"` — posts in these categories get auto-unsaved |
| `hints` | Free-text rules injected into the Gemini prompt to guide priority decisions between categories |

Override `unsaved-categories` for a single run: `python scripts/classify_to_scribe_ai.py --unsaved-categories AI,科技`

---

## Tests

```powershell
cd path\to\crawl-the-threads
.\.venv\Scripts\Activate.ps1
pip install pytest
pytest tests/
```

Tests cover:
- `classify_to_scribe_ai.py` — category filter, output schema, error / unsure buckets, custom categories
- `watch_pipeline.py` — debounce, missing-file handling, `.env` loader

---

## Known limitations

- **Browser must be open + on the saved page** for auto-unsave to fire. The watcher will still produce `unsave.json` and markdown notes regardless, but the unsave step is a no-op until you visit `/saved`.
- **File System Access permission may expire** after a browser restart. The userscript panel will show "handle: not bound" and ignore polls until you re-bind via the button.
- **Classifier duplication**: this project runs its own Gemini classifier whose categories and hints live in `classify_config.json`. If you change the prompt in `PROJECT_threads-to-note/services/category_classifier.py`, sync the category list in `classify_config.json` manually.
- **Gemini quota**: each scrape triggers two Gemini-using subprocesses (this project's classifier + the note project's own classifier inside `app.py`). The shared category list is intentional — both run on the full scrape so neither blocks the other.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Watcher prints "missing required config" | `.env` not loaded or paths empty | Verify `.env` exists next to `start_pipeline.ps1`; check key names match table above |
| `catch.json` written but watcher idle | mtime change happened during the debounce window of another run | Wait `DEBOUNCE_SECONDS`; or shrink `POLL_SECONDS` |
| `classify` subprocess fails with `GEMINI_API_KEY missing` | env not propagated to subprocess | Confirm key is in `.env` (not just shell), restart watcher |
| Userscript panel never shows "auto-loaded" | handle not bound, permission revoked, or `autoLoad` off | Click 綁定 unsave.json again; tick the toggle; check browser console for `[crawl-the-threads]` warnings |
| Auto-unsave skipped with "not on saved page" | Tab navigated away | Switch the tab back to `/saved` |
| `probe` reports autosave not bound after browser restart | FS Access write permission revoked | Click **設定自動存檔** in panel to re-grant; permission is profile-scoped, not session-scoped — only lapses after profile wipe or extension update |
| `scrape` exits 2 with timeout | Scrape still running (large backlog) or panel stalled | Increase `--wait-seconds`; check panel status with `python scripts/agent_driver.py status` |
| `catch.json` stays 0 bytes after scrape | Autosave handle not bound | Re-grant via 設定自動存檔, then re-run scrape |
