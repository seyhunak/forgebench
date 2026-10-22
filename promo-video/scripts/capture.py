#!/usr/bin/env python3
"""Capture 2x full-page textures + layout.json from the live ForgeBench dashboard.

Three-piece output (same contract as the shotcraft capture template):
  1. public/textures/live/<name>-full.png   viewport/fullPage @ deviceScaleFactor 2
  2. layout.json                            element bboxes in page CSS px (shared coord system)
No secrets: the dashboard runs locally with mock/synthetic runs only.
"""
import json
import pathlib
import sys
import time

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8501"
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "public" / "textures" / "live"
LAYOUT = ROOT / "src" / "live-layout.json"
VIEWPORT = {"width": 1920, "height": 1080, "deviceScaleFactor": 2}
SETTLE_MS = 700

OUT.mkdir(parents=True, exist_ok=True)
LAYOUT.parent.mkdir(parents=True, exist_ok=True)

layout = {"pageW": VIEWPORT["width"], "scale": 2}


def settle(page, extra=SETTLE_MS):
    page.evaluate("document.fonts.ready")
    page.wait_for_timeout(extra)


def boxes(page, selector, *, all_=True, max_=None):
    els = page.locator(selector)
    n = els.count()
    if not all_:
        n = 1
    if max_ is not None:
        n = min(n, max_)
    out = []
    for i in range(n):
        bb = els.nth(i).bounding_box()
        if bb:
            out.append({k: round(v, 1) for k, v in
                        {"x": bb["x"], "y": bb["y"], "w": bb["width"], "h": bb["height"]}.items()})
    return out if all_ else (out[0] if out else None)


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": VIEWPORT["width"], "height": VIEWPORT["height"]},
                            device_scale_factor=2)
    page.goto(BASE, wait_until="networkidle")
    settle(page)

    # ---- 1. results (single-run grid, default state) ----
    page.click('[data-view="results"]')
    page.wait_for_timeout(900)
    settle(page)
    e = {"pageH": page.evaluate("document.documentElement.scrollHeight")}
    page.screenshot(path=str(OUT / "results-full.png"), full_page=True)
    e["boxes"] = {
        "run_cards": boxes(page, "#runs-grid article", max_=8),
        "tabs": boxes(page, "#mode-single, #mode-compare, #mode-history"),
        "topbar": boxes(page, "header, .topbar", all_=False),
        "rail": boxes(page, "aside nav, .rail", all_=False),
    }
    layout["results"] = e
    print("results-full", e["pageH"], {k: len(v) if isinstance(v, list) else v
                                        for k, v in e["boxes"].items()})

    # ---- 2. compare view: ci-baseline (first = baseline) vs ci-prompt ----
    page.click("#mode-compare")
    page.wait_for_timeout(500)
    page.evaluate(
        """() => {
        const sel = document.getElementById('compare-select');
        const find = (w) => Array.from(sel.options).find(o => o.textContent.includes(w));
        const base = find('ci-baseline'), cand = find('ci-prompt');
        // baseline = FIRST selected option in DOM order → ci-baseline must lead
        if (base && cand && Array.from(sel.options).indexOf(base) >
                           Array.from(sel.options).indexOf(cand)) {
          sel.insertBefore(base, cand);
        }
        for (const o of sel.options) o.selected = false;
        if (base) base.selected = true;
        if (cand) cand.selected = true;
        // align scroll to whole option lines (no half-cut row at the top)
        const LINE = 17.4;
        sel.scrollTop = Math.round(sel.scrollTop / LINE) * LINE;
    }"""
    )
    page.wait_for_timeout(200)
    page.click("#btn-compare")
    page.wait_for_selector("#compare-view-container table tr", timeout=15000)
    page.wait_for_timeout(900)
    settle(page)
    e = {"pageH": page.evaluate("document.documentElement.scrollHeight")}
    page.screenshot(path=str(OUT / "compare-full.png"), full_page=True)
    e["boxes"] = {
        "rows": boxes(page, "#compare-view-container table tr"),
        "head_cells": boxes(page, "#compare-view-container thead th"),
        "metric_cells": boxes(page, "#compare-view-container tbody td:first-child"),
        "container": boxes(page, "#compare-view-container", all_=False),
        "tabs": boxes(page, "#mode-single, #mode-compare, #mode-history"),
    }
    layout["compare"] = e
    rows = e["boxes"].get("rows") or []
    print("compare-full", e["pageH"], "rows:", len(rows))
    for i, r in enumerate(rows):
        print("   row", i, r)

    # ---- 3. run-detail modal (report of ci-prompt) ----
    ok = page.evaluate("() => { if (window.viewRunReport) { viewRunReport('runs/ci-prompt'); return true; } return false; }")
    if not ok:
        sys.exit("viewRunReport not exposed")
    page.wait_for_selector("#btn-modal-close", timeout=15000)
    page.wait_for_timeout(900)
    settle(page)
    e = {"pageH": VIEWPORT["height"]}
    page.screenshot(path=str(OUT / "report-full.png"))  # viewport: modal is fixed overlay
    e["boxes"] = {
        "modal": boxes(page, ".modal-panel", all_=False),
        "head": boxes(page, ".modal-head", all_=False),
        "meta_chips": boxes(page, ".modal-meta", all_=False),
        "actions": boxes(page, ".modal-actions", all_=False),
        "body": boxes(page, "#run-modal-body", all_=False),
        "close": boxes(page, "#btn-modal-close", all_=False),
    }
    layout["report"] = e
    print("report-full", e["boxes"]["modal"])

    # ---- 4. datasets ----
    page.evaluate("() => document.getElementById('btn-modal-close').click()")
    page.wait_for_timeout(300)
    page.click('[data-view="datasets"]')
    page.wait_for_timeout(900)
    settle(page)
    e = {"pageH": page.evaluate("document.documentElement.scrollHeight")}
    page.screenshot(path=str(OUT / "datasets-full.png"), full_page=True)
    e["boxes"] = {
        "table_rows": boxes(page, "#dataset-table tbody tr", max_=12),
        "info": boxes(page, "#dataset-info", all_=False),
        "table": boxes(page, "#dataset-table", all_=False),
    }
    layout["datasets"] = e
    print("datasets-full", e["pageH"])

    browser.close()

LAYOUT.write_text(json.dumps(layout, indent=1))
print("wrote", LAYOUT)
