#!/usr/bin/env python3
"""
КИНЕМАТОГРАФИСТЫ.РФ — Telegram бот для напоминаний о дедлайнах.

Зависимости: нет (стандартная библиотека Python)

Настройка:
  1. Создай бота через @BotFather, получи токен
  2. Создай bot_config.json: {"token": "YOUR_TOKEN"}
  3. Запусти: python bot.py
"""

import json
import sys
import os
import time
import logging
import ssl
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).parent
DATA_FILE = SCRIPT_DIR / "festivals.json"
CONFIG_FILE = SCRIPT_DIR / "bot_config.json"
SUBSCRIBERS_FILE = SCRIPT_DIR / ".bot_subscribers.json"

REMIND_DAYS = [30, 14, 7, 3, 1]
TELEGRAM_API = "https://api.telegram.org/bot%s"

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def load_festivals():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)["festivals"]


def load_subscribers():
    if SUBSCRIBERS_FILE.exists():
        with open(SUBSCRIBERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"users": {}}


def save_subscribers(data):
    with open(SUBSCRIBERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def tg_api(token, method, params=None):
    url = TELEGRAM_API % token + "/" + method
    data = None
    if params:
        data = urllib.parse.urlencode(params).encode("utf-8")
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, data=data)
        resp = urllib.request.urlopen(req, timeout=30, context=ctx)
        return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.error("Telegram API error: %s" % e)
        return None


def send_message(token, chat_id, text):
    tg_api(token, "sendMessage", {
        "chat_id": chat_id,
        "text": text,
    })


def get_user_tracking(user_id):
    subs = load_subscribers()
    user = subs["users"].get(str(user_id), {})
    return user.get("track", [])


def set_user_tracking(user_id, track):
    subs = load_subscribers()
    uid = str(user_id)
    if uid not in subs["users"]:
        subs["users"][uid] = {}
    subs["users"][uid]["track"] = track
    save_subscribers(subs)


def toggle_user_tracking(user_id, festival_id):
    track = get_user_tracking(user_id)
    if festival_id in track:
        track.remove(festival_id)
        set_user_tracking(user_id, track)
        return False
    else:
        track.append(festival_id)
        set_user_tracking(user_id, track)
        return True


def get_festival_by_id(festival_id):
    festivals = load_festivals()
    for f in festivals:
        if f["id"] == festival_id:
            return f
    return None


def days_until_deadline(date_str):
    try:
        deadline = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return (deadline - now).days
    except Exception:
        return None


def format_deadline_msg(f, days):
    if days < 0:
        time_left = "deadline proshel"
    elif days == 0:
        time_left = "DEDLAYN SEGODNYA"
    elif days == 1:
        time_left = "DEDLAYN ZAVTRA"
    else:
        time_left = "cherez %d dn" % days

    msg = "%s\n" % f["name"]
    msg += "%s\n" % f["city"]
    msg += "%s\n" % time_left
    if f.get("submissionDeadline"):
        msg += "Dedlayn: %s\n" % f["submissionDeadline"]
    if f.get("website"):
        msg += "%s\n" % f["website"]
    return msg


def handle_command(token, chat_id, text):
    text = text.strip().lower()
    args = text.split()

    if not args:
        return

    cmd = args[0]

    if cmd in ("/start", "начать"):
        subs = load_subscribers()
        uid = str(chat_id)
        if uid not in subs["users"]:
            subs["users"][uid] = {
                "track": [],
                "subscribed_at": datetime.now(timezone.utc).isoformat(),
            }
            save_subscribers(subs)

        send_message(token, chat_id,
            "Добro pozhalovat' v KINEMATOGRAFISTY.RF!\n\n"
            "Ya napominau o dedlaynah podachi zayavok na kinofestivali.\n\n"
            "Komandy:\n"
            "/list — vse festivali\n"
            "/add ID — dobavit' v otslezhivanie\n"
            "/remove ID — ubrat'\n"
            "/track — moi otslezhivaemye\n"
            "/status — blizhajshie dedlayny\n"
            "/help — spravka"
        )

    elif cmd in ("/stop", "стоп"):
        subs = load_subscribers()
        uid = str(chat_id)
        if uid in subs["users"]:
            del subs["users"][uid]
            save_subscribers(subs)
        send_message(token, chat_id, "Vy otpisany ot uvedomlenij.")

    elif cmd in ("/list", "список"):
        festivals = load_festivals()
        track = get_user_tracking(chat_id)

        lines = ["Vse festivali:\n"]
        for f in festivals:
            marker = "+" if f["id"] in track else " "
            dl = f.get("submissionDeadline", "")
            dl_info = " | %s" % dl if dl else ""
            lines.append("%s %2d. %s — %s%s" % (marker, f["id"], f["name"], f["city"], dl_info))

        text_out = "\n".join(lines)
        if len(text_out) > 4000:
            text_out = text_out[:3900] + "\n..."
        send_message(token, chat_id, text_out)

    elif cmd == "/add" or cmd == "добавить":
        if len(args) < 2:
            send_message(token, chat_id, "Ispol'zovanie: /add ID")
            return

        try:
            fid = int(args[1])
        except ValueError:
            send_message(token, chat_id, "ID dolzhen byt' chislom.")
            return

        f = get_festival_by_id(fid)
        if not f:
            send_message(token, chat_id, "Festival s ID %d ne nayden." % fid)
            return

        added = toggle_user_tracking(chat_id, fid)
        if added:
            send_message(token, chat_id,
                "Dobavleno: %s\nBudu napominat' o dedlayne (%s)." % (
                    f["name"], f.get("submissionDeadline", "ne zadan")))
        else:
            send_message(token, chat_id, "Ubano: %s" % f["name"])

    elif cmd == "/remove" or cmd == "убрать":
        if len(args) < 2:
            send_message(token, chat_id, "Ispol'zovanie: /remove ID")
            return

        try:
            fid = int(args[1])
        except ValueError:
            send_message(token, chat_id, "ID dolzhen byt' chislom.")
            return

        f = get_festival_by_id(fid)
        if not f:
            send_message(token, chat_id, "Festival s ID %d ne nayden." % fid)
            return

        removed = toggle_user_tracking(chat_id, fid)
        if not removed:
            send_message(token, chat_id, "Ubano: %s" % f["name"])
        else:
            send_message(token, chat_id, "Etot festival ne v vashem spiske.")

    elif cmd in ("/track", "мои"):
        track = get_user_tracking(chat_id)
        if not track:
            send_message(token, chat_id, "Vy poka ne otslezhivaete ni odnogo festivala.\nIspol'zujte /list.")
            return

        lines = ["Vashi festivali:\n"]
        for fid in track:
            f = get_festival_by_id(fid)
            if f:
                dl = f.get("submissionDeadline")
                if dl:
                    days = days_until_deadline(dl)
                    if days is not None:
                        if days < 0:
                            dl_info = "dedlayn proshel"
                        elif days == 0:
                            dl_info = "DEDLAYN SEGODNYA"
                        elif days <= 7:
                            dl_info = "cherez %d dn" % days
                        else:
                            dl_info = "cherez %d dn" % days
                    else:
                        dl_info = dl
                else:
                    dl_info = "dedlayn ne zadan"
                lines.append("%2d. %s — %s" % (f["id"], f["name"], dl_info))

        send_message(token, chat_id, "\n".join(lines))

    elif cmd in ("/status", "дедлайны"):
        track = get_user_tracking(chat_id)
        if not track:
            send_message(token, chat_id, "Otslezhivaemyh festivalov net.\nIspol'zujte /list.")
            return

        festivals = load_festivals()
        tracked = [f for f in festivals if f["id"] in track and f.get("submissionDeadline")]

        if not tracked:
            send_message(token, chat_id, "U otslezhivaemyh festivalov net dedlaynov.")
            return

        upcoming = []
        for f in tracked:
            days = days_until_deadline(f["submissionDeadline"])
            if days is not None and days >= 0:
                upcoming.append((days, f))

        upcoming.sort(key=lambda x: x[0])

        if not upcoming:
            send_message(token, chat_id, "Blizhajshih dedlaynov net (vse proshli).")
            return

        lines = ["Blizhajshie dedlayny:\n"]
        for days, f in upcoming[:10]:
            lines.append(format_deadline_msg(f, days))

        send_message(token, chat_id, "\n\n".join(lines))

    elif cmd in ("/help", "помощь"):
        send_message(token, chat_id,
            "KINEMATOGRAFISTY.RF — Napominaniya\n\n"
            "Ya slezhu za dedlaynami kinofestival'j.\n\n"
            "/start — podpisat'sya\n"
            "/stop — otpisat'sya\n"
            "/list — vse festivali\n"
            "/add 5 — dobavit' #5\n"
            "/remove 5 — ubrat' #5\n"
            "/track — moi otslezhivaemye\n"
            "/status — blizhajshie dedlayny\n\n"
            "Napominaniya prikhodyat za 30, 14, 7, 3 i 1 den' do dedlayna."
        )


def check_deadlines(token):
    subs = load_subscribers()
    festivals = load_festivals()
    now = datetime.now(timezone.utc)

    for uid, user_data in subs["users"].items():
        track = user_data.get("track", [])
        if not track:
            continue

        for fid in track:
            f = next((x for x in festivals if x["id"] == fid), None)
            if not f or not f.get("submissionDeadline"):
                continue

            days = days_until_deadline(f["submissionDeadline"])
            if days is None or days < 0:
                continue

            if days in REMIND_DAYS:
                sent_key = "sent_%d_%d" % (fid, days)
                if user_data.get(sent_key):
                    continue

                msg = format_deadline_msg(f, days)
                try:
                    send_message(token, int(uid), msg)
                    user_data[sent_key] = now.isoformat()
                    save_subscribers(subs)
                    logger.info("Reminder to %s for %s (%dd)" % (uid, f["name"], days))
                except Exception as e:
                    logger.error("Failed to send to %s: %s" % (uid, e))


def get_updates(token, offset=None):
    params = {"timeout": 30}
    if offset:
        params["offset"] = offset
    return tg_api(token, "getUpdates", params)


def main():
    config = load_config()

    if not config.get("token") or config["token"] == "YOUR_BOT_TOKEN_FROM_BOTFATHER":
        print("Sozhdajte bot_config.json s tokenom bota.")
        print("Primer: {\"token\": \"123456:ABC...\"}")
        return

    token = config["token"]
    logger.info("Bot zapushchen")

    offset = None
    last_check = datetime.now(timezone.utc)

    while True:
        try:
            result = get_updates(token, offset)
            if result and result.get("ok"):
                for update in result.get("result", []):
                    offset = update["update_id"] + 1
                    msg = update.get("message")
                    if msg and msg.get("text"):
                        chat_id = msg["chat"]["id"]
                        text = msg["text"]
                        logger.info("Message from %s: %s" % (chat_id, text))
                        handle_command(token, chat_id, text)

            now = datetime.now(timezone.utc)
            if (now - last_check).total_seconds() >= 12 * 3600:
                logger.info("Checking deadlines...")
                check_deadlines(token)
                last_check = now

        except KeyboardInterrupt:
            logger.info("Bot ostanovlen")
            break
        except Exception as e:
            logger.error("Error: %s" % e)
            time.sleep(5)


if __name__ == "__main__":
    main()
