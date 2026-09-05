import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

URL = "https://codes.yar.gg/"
STATE_FILE = Path("data/codes.json")
WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
BOT_NAME = "尾兒大人忠誠的狗🐕"
TEST_NOTIFICATION = os.environ.get("TEST_NOTIFICATION", "").lower() == "true"

# Reasonable coupon-code validation:
# - 5..32 chars
# - ASCII letters/numbers plus - and _
# - excludes obvious UI placeholders
CODE_RE = re.compile(r"^[A-Za-z0-9_-]{5,32}$")
BLOCKLIST = {
    "CODE123", "Search", "Submit", "Cancel", "Confirm",
    "Unused", "Expired", "Active", "Previous", "Next"
}

def normalize_code(value: str) -> str | None:
    value = (value or "").strip()
    if not value or value in BLOCKLIST:
        return None
    if not CODE_RE.fullmatch(value):
        return None
    # Real WWM codes are displayed uppercase; normalize for stable deduplication.
    return value.upper()

def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"initialized": False, "active_codes": [], "last_checked": None}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("state is not an object")
        data.setdefault("initialized", bool(data.get("active_codes")))
        data.setdefault("active_codes", [])
        data.setdefault("last_checked", None)
        return data
    except Exception as exc:
        print(f"[WARN] Could not read state file: {exc}")
        return {"initialized": False, "active_codes": [], "last_checked": None}

def save_state(codes: list[str]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "initialized": True,
        "active_codes": codes,
        "last_checked": datetime.now(timezone.utc).isoformat()
    }
    STATE_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )

def scrape_active_codes() -> list[str]:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1440, "height": 1200},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/152.0.0.0 Safari/537.36"
            ),
        )

        print(f"[INFO] Opening {URL}")
        page.goto(URL, wait_until="domcontentloaded", timeout=90_000)

        # The page is client-rendered. Wait until the active-code counter is populated,
        # but don't fail solely because wording/layout changes slightly.
        try:
            page.wait_for_function(
                """() => {
                    const t = document.body?.innerText || "";
                    return /\\d+\\s+left/i.test(t) &&
                           !/\\b0\\s+left\\b/i.test(t);
                }""",
                timeout=45_000,
            )
        except Exception:
            print("[WARN] Active counter did not become non-zero; trying DOM extraction anyway.")

        page.wait_for_timeout(2500)

        # Extract form-control values that are physically/DOM-positioned between
        # the "Active codes" marker and "Confirmed expired" marker.
        # This avoids depending on fragile CSS class names.
        raw = page.evaluate(
            r"""() => {
                const all = Array.from(document.querySelectorAll("*"));
                const norm = s => (s || "").replace(/\s+/g, " ").trim();

                const activeMarker = all.find(el => {
                    const t = norm(el.textContent);
                    return t === "Active codes";
                });

                const expiredMarker = all.find(el => {
                    const t = norm(el.textContent);
                    return t.startsWith("Confirmed expired");
                });

                const candidates = [];
                for (const el of document.querySelectorAll("input, button, [data-code], [value]")) {
                    if (activeMarker &&
                        !(activeMarker.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING)) {
                        continue;
                    }
                    if (expiredMarker &&
                        !(expiredMarker.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_PRECEDING)) {
                        continue;
                    }

                    const vals = [
                        el.getAttribute("data-code"),
                        el.getAttribute("value"),
                        el.value,
                        norm(el.textContent)
                    ].filter(Boolean);

                    for (const v of vals) candidates.push(v);
                }
                return candidates;
            }"""
        )

        # Fallback: collect all inputs if the marker-based extraction produced too little.
        if len(raw) < 1:
            print("[WARN] Marker extraction empty; using all input values as fallback.")
            raw = page.eval_on_selector_all(
                "input",
                "els => els.map(e => e.value || e.getAttribute('value') || '').filter(Boolean)"
            )

        browser.close()

    codes = []
    seen = set()
    for item in raw:
        code = normalize_code(str(item))
        if code and code not in seen:
            seen.add(code)
            codes.append(code)

    # Safety: if extraction unexpectedly collapses, do NOT overwrite a good state.
    if not codes:
        raise RuntimeError(
            "No active codes were extracted. Site structure/loading may have changed; "
            "state will not be overwritten."
        )

    print(f"[INFO] Extracted {len(codes)} active-code candidates.")
    print("[INFO] First few:", ", ".join(codes[:8]))
    return codes

def send_discord(code: str, test: bool = False) -> None:
    if not WEBHOOK:
        raise RuntimeError("DISCORD_WEBHOOK_URL is missing.")

    title = "🐕 尾兒大人忠誠的狗發現新的燕雲激活碼！"
    if test:
        title = "🧪 尾兒大人的狗狗巡邏測試成功"

    payload = {
        "username": BOT_NAME,
        "content": None,
        "embeds": [
            {
                "title": title,
                "description": f"🎁 **兌換碼：**\n```{code}```",
                "url": URL,
                "fields": [
                    {
                        "name": "來源",
                        "value": "[Where Winds Meet Codes](https://codes.yar.gg/)",
                        "inline": True
                    },
                    {
                        "name": "狀態",
                        "value": "✅ Active" if not test else "✅ GitHub Actions / Discord Webhook 正常",
                        "inline": True
                    }
                ],
                "footer": {
                    "text": "尾兒大人忠誠的狗🐕 • 自動巡邏中"
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        ],
        "allowed_mentions": {"parse": []},
    }

    r = requests.post(WEBHOOK, json=payload, timeout=25)
    if r.status_code not in (200, 204):
        raise RuntimeError(f"Discord webhook failed: HTTP {r.status_code} {r.text[:300]}")
    print(f"[INFO] Discord notification sent for {code}")

def main() -> int:
    if TEST_NOTIFICATION:
        send_discord("DOGGO-TEST-OK", test=True)
        return 0

    state = load_state()
    old_codes = {normalize_code(x) for x in state.get("active_codes", [])}
    old_codes.discard(None)

    current = scrape_active_codes()
    current_set = set(current)

    if not state.get("initialized", False):
        print(
            f"[INFO] First run: saving {len(current)} current active codes as baseline. "
            "No Discord notifications will be sent."
        )
        save_state(current)
        return 0

    new_codes = [c for c in current if c not in old_codes]
    disappeared = sorted(old_codes - current_set)

    if disappeared:
        print(f"[INFO] {len(disappeared)} previously-active code(s) are no longer active:")
        print("       " + ", ".join(disappeared))

    if not new_codes:
        print("[INFO] No new active codes.")
        save_state(current)
        return 0

    print(f"[INFO] Found {len(new_codes)} NEW code(s): {', '.join(new_codes)}")

    # Notify one embed per code, making each code easy to copy on Discord.
    # Save state only after notifications succeed, so a transient webhook failure
    # can be retried on the next Actions run.
    for code in new_codes:
        send_discord(code)

    save_state(current)
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise
