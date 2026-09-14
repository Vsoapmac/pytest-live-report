# pytest-live-report

A pytest plugin that writes its HTML report **while your tests run**, one card per
test case, straight into a single self-contained file.

Open `report.html` in a browser and refresh: finished tests are already there. No
Java, no template directory to configure, no "wait for the whole suite to finish"
step — and if you hit `Ctrl+C`, everything that already ran is still in the report.

```console
$ pip install pytest-live-report
$ pytest --live-report-path report.html
```

That is the whole setup. The plugin registers itself through its pytest11 entry
point, so there is no `conftest.py` edit and no configuration file.

## What you get

- **One card per test case**, written the moment the case finishes, with the run's
  start/end time, wall-clock duration, function name, and its docstring as the
  description.
- **Status filtering and name search** on the page, plus a donut chart of
  passed / failed / skipped so a long run is scannable.
- **The failure traceback is already in the card**, so you do not have to scroll the
  terminal to find what broke.
- **A single HTML file**: the stylesheet, the page script and any screenshots you
  attach are inlined. Mail it, archive it, open it offline — it works.
- **Structured data for scripts**: every page carries a machine-readable run
  manifest and a JSON record per test case (see
  [Reading the report from a script](#reading-the-report-from-a-script)).
- **pytest-xdist support**: with `-n`, workers hand their cards to the controller,
  which is the only process that writes the file.

## Writing content from a test

```python
from pytest_live_report import live_report


def test_login():
    """Verify the login flow."""
    live_report.log("POST /login as admin")
    live_report.log("status", 200, live_report.span_html("OK", bold=True, code=True))

    live_report.case_name("Login flow")           # override the card title
    live_report.case_desc("Covers the redirect")  # override the docstring
    live_report.save_image("screenshots/home.png", caption="after login")

    assert True
```

| Method | What it does |
|---|---|
| `live_report.log(*parts)` | Appends a log line to the current card. `*parts` are joined with spaces like `print`; newlines become separate lines; everything is HTML-escaped. |
| `live_report.span_html(text, *, bold=False, code=False)` | Renders an inline fragment (bold / monospace). Pass the result to `live_report.log()` to have it embedded as-is. The only entry point you may call outside a test case. |
| `live_report.case_name(text)` | Overrides the card title. A parametrized suffix is kept: `test_login[admin]` shows as `Login flow[admin]`. |
| `live_report.case_desc(text)` | Overrides the card description (default: the test function's docstring). |
| `live_report.save_image(path, caption=None)` | Inlines an image as a base64 data URI. Raises `FileNotFoundError` if the path is not an existing file. |

Calling any of these outside a test case only emits a warning; it never fails your
run. The report system never raises into your tests — a broken report becomes a
warning and the report is disabled for that session.

## Command line options

| Option | Meaning |
|---|---|
| `--live-report-path PATH` | Where to write the report. Relative paths resolve against `rootdir`. **Without this option the plugin does nothing at all.** |
| `--live-report-title TITLE` | Report title (default: `pytest report`). |

## How statuses are counted

pytest has more outcomes than the three the report shows, so they are folded in:

| Report status | Comes from |
|---|---|
| `passed` | passed |
| `failed` | `failed` **and** `error` — a broken fixture (setup error) or a failing teardown counts as a failed case |
| `skipped` | `skipped` **and** `xfail` |

A case is written only once all three of its phases are done, so a case that is still
running is simply not in the report yet. A case interrupted by `Ctrl+C` is dropped as
well — you never get a half-written card.

## pytest-xdist

```console
$ pytest -n 4 --live-report-path report.html
```

Workers never touch the report file: each worker attaches its finished card to the
test report, xdist ships it back, and the controller writes it. The result has the
same cards, counts and content as a single-process run.

One difference: **cards appear in the order workers finish, not in test order.** Sort
or group by the `nodeid` in each card's JSON record if you need a stable order.

## Reading the report from a script

Two kinds of JSON blocks are embedded in the page, so you never have to parse HTML:

```python
import json
import re
from pathlib import Path

html = Path("report.html").read_text(encoding="utf-8")

# The run manifest: its presence means the run finished.
manifest = json.loads(
    re.search(r'<script type="application/json" id="rpt-run">(.*?)</script>', html).group(1)
)
print(manifest["counts"])       # {'total': 42, 'passed': 40, 'failed': 1, 'skipped': 1}
print(manifest["exitstatus"])

# One record per test case.
records = [
    json.loads(block)
    for block in re.findall(
        r'<script type="application/json" class="rpt-case-json">(.*?)</script>', html
    )
]
```

The manifest is written only when the session finishes normally. If pytest was
interrupted, the file has no manifest — that is how the page (and your script) can
tell a finished report from a truncated one.

## Requirements

- Python 3.10+
- pytest 7.4+
- `pytest-xdist` is optional: `pip install pytest-live-report[xdist]`
