#!/usr/bin/env python3
"""
КИНЕМАТОГРАФИСТЫ.РФ — автообновление данных о фестивалях.

Проверяет сайты фестивалей на наличие ключевых слов, связанных с приёмом заявок.
Обновляет festivals.json при обнаружении изменений.

Запуск:
    python update.py            — проверка всех фестивалей
    python update.py --check 5  — проверить только фестиваль с id=5
    python update.py --dry-run  — показать что изменится, не сохраняя
    python update.py --report   — вывести отчёт о доступности сайтов

Зависимости: нет (стандартная библиотека Python)
"""

import json
import sys
import os
import re
import time
import hashlib
import ssl
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).parent
DATA_FILE = SCRIPT_DIR / "festivals.json"
CACHE_DIR = SCRIPT_DIR / ".update_cache"
LOG_FILE = SCRIPT_DIR / ".update_log.json"

TIMEOUT = 12
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}

SUBMISSION_KEYWORDS = [
    "приём заявок", "прием заявок", "подача заявок", "регистрация",
    "принимаем фильмы", "open call", "submit", "submission",
    "подаёт фильмы", "принимает заявки", "заявки принимаются",
    "дедлайн", "deadline", "последний срок",
]

ACTIVE_KEYWORDS = [
    "программа", "кинопрограмма", "фильмы", "афиша",
    "расписание", "киносалон", "показы", "кинотеатр",
    "фестиваль состоялся", "прошёл", "закрытие", "победители",
    "лауреаты", "жюри",
]

PAUSED_KEYWORDS = [
    "приостановлен", "пауза", "отменён", "отмена",
    "не проводится", "в следующем году", "перерыв",
    "отложен", " задержк",
]


def load_data() -> dict:
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_cache_path(festival_id: int) -> Path:
    CACHE_DIR.mkdir(exist_ok=True)
    return CACHE_DIR / ("%d.txt" % festival_id)


def get_cache_hash(festival_id: int) -> Optional[str]:
    path = get_cache_path(festival_id)
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return None


def set_cache_hash(festival_id: int, content_hash: str):
    path = get_cache_path(festival_id)
    path.write_text(content_hash, encoding="utf-8")


def fetch_page(url: str) -> Optional[str]:
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        req = urllib.request.Request(url, headers=HEADERS)
        resp = urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx)
        data = resp.read()

        encoding = resp.headers.get_content_charset() or "utf-8"
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            return data.decode("utf-8", errors="ignore")
    except Exception:
        return None


def extract_text(html: str) -> str:
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<noscript[^>]*>.*?</noscript>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<footer[^>]*>.*?</footer>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<nav[^>]*>.*?</nav>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text[:10000].strip()


def detect_status(text: str) -> dict:
    text_lower = text.lower()
    result = {
        "submission_open": False,
        "submission_mentioned": False,
        "active_mentioned": False,
        "paused_mentioned": False,
        "keywords_found": [],
    }

    for kw in SUBMISSION_KEYWORDS:
        if kw in text_lower:
            result["submission_mentioned"] = True
            result["keywords_found"].append(kw)

    for kw in ACTIVE_KEYWORDS:
        if kw in text_lower:
            result["active_mentioned"] = True
            result["keywords_found"].append(kw)

    for kw in PAUSED_KEYWORDS:
        if kw in text_lower:
            result["paused_mentioned"] = True
            result["keywords_found"].append(kw)

    return result


def check_festival(festival: dict, dry_run: bool = False) -> dict:
    fid = festival["id"]
    name = festival["name"]
    website = festival.get("website")

    result = {
        "id": fid,
        "name": name,
        "website": website,
        "status": "unknown",
        "reachable": False,
        "changed": False,
        "detection": None,
        "error": None,
    }

    if not website:
        result["error"] = "Нет сайта"
        return result

    html = fetch_page(website)
    if html is None:
        result["error"] = "Сайт недоступен"
        return result

    result["reachable"] = True

    content_hash = hashlib.md5(html.encode("utf-8", errors="ignore")).hexdigest()
    cached = get_cache_hash(fid)

    if cached == content_hash:
        result["status"] = "unchanged"
        return result

    text = extract_text(html)
    detection = detect_status(text)
    result["detection"] = detection

    if detection["paused_mentioned"] and not detection["active_mentioned"]:
        new_status = "paused"
    elif detection["submission_mentioned"]:
        new_status = "active"
    elif detection["active_mentioned"]:
        new_status = "active"
    else:
        new_status = festival.get("status", "unknown")

    old_status = festival.get("status", "unknown")
    if new_status != old_status and new_status != "unknown":
        result["changed"] = True
        result["status"] = "%s -> %s" % (old_status, new_status)
        if not dry_run:
            festival["status"] = new_status
            set_cache_hash(fid, content_hash)
    else:
        result["status"] = "unchanged"
        if not dry_run:
            set_cache_hash(fid, content_hash)

    return result


def run_update(festival_ids=None, dry_run=False, report=False):
    data = load_data()
    festivals = data["festivals"]

    if festival_ids:
        festivals = [f for f in festivals if f["id"] in festival_ids]

    results = []
    total = len(festivals)

    for i, festival in enumerate(festivals, 1):
        name = festival["name"]
        sys.stdout.write("[%d/%d] %s... " % (i, total, name))
        sys.stdout.flush()
        result = check_festival(festival, dry_run=dry_run)
        results.append(result)

        if result["error"]:
            print("x %s" % result["error"])
        elif result["reachable"]:
            if result["changed"]:
                print("~ %s" % result["status"])
            else:
                print("ok")
        else:
            print("?")

        time.sleep(1.5)

    if not dry_run:
        data["lastUpdated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        save_data(data)

    print("\n" + "=" * 50)
    print("REPORT")
    print("=" * 50)

    reachable = sum(1 for r in results if r["reachable"])
    unreachable = sum(1 for r in results if not r["reachable"] and r["error"])
    changed = sum(1 for r in results if r["changed"])

    print("Total checked:   %d" % len(results))
    print("Site available:  %d" % reachable)
    print("Site unavailable:%d" % unreachable)
    if not dry_run:
        print("Updated:         %d" % changed)

    if report:
        print("\nDETAILS:")
        for r in results:
            status_icon = "v" if r["reachable"] else "x"
            changed_icon = "~" if r["changed"] else " "
            print("  [%s%s] id=%d %s: %s" % (status_icon, changed_icon, r["id"], r["name"], r.get("error") or r["status"]))
            if r.get("detection") and r["detection"]["keywords_found"]:
                print("       Keywords: %s" % ", ".join(r["detection"]["keywords_found"][:5]))

    if dry_run:
        print("\nDRY RUN - changes NOT saved")

    return results


def log_run(results: list):
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checked": len(results),
        "reachable": sum(1 for r in results if r["reachable"]),
        "changed": sum(1 for r in results if r["changed"]),
    }

    log = []
    if LOG_FILE.exists():
        try:
            log = json.loads(LOG_FILE.read_text(encoding="utf-8"))
        except Exception:
            log = []

    log.append(log_entry)
    log = log[-50:]

    LOG_FILE.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    report = "--report" in args

    festival_ids = None
    if "--check" in args:
        idx = args.index("--check")
        if idx + 1 < len(args):
            festival_ids = [int(args[idx + 1])]

    print("KINEMATOGRAFISTY.RF - auto-update")
    print("Date: %s" % datetime.now().strftime("%Y-%m-%d %H:%M"))
    print("Mode: %s" % ("dry-run" if dry_run else "update"))
    print()

    results = run_update(festival_ids=festival_ids, dry_run=dry_run, report=report)

    if not dry_run:
        log_run(results)
