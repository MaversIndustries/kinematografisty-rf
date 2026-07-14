#!/usr/bin/env python3
"""
КИНЕМАТОГРАФИСТЫ.РФ — Email напоминания через Mail.ru.

Настройка:
  1. Включи двухфакторную аутентификацию на Mail.ru
  2. Создай пароль приложения: Настройки → Безопасность → Пароли приложений
  3. Создай email_config.json (см. email_config.example.json)
  4. Запусти: python bot_email.py

Зависимости: нет (всё встроенное)
"""

import json
import smtplib
import ssl
import sys
import logging
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).parent
DATA_FILE = SCRIPT_DIR / "festivals.json"
CONFIG_FILE = SCRIPT_DIR / "email_config.json"
SUBSCRIBERS_FILE = SCRIPT_DIR / ".email_subscribers.json"

REMIND_DAYS = [30, 14, 7, 3, 1]

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def load_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def load_festivals() -> list:
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)["festivals"]


def load_subscribers() -> dict:
    if SUBSCRIBERS_FILE.exists():
        with open(SUBSCRIBERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"users": {}}


def save_subscribers(data: dict):
    with open(SUBSCRIBERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def days_until_deadline(date_str: str) -> Optional[int]:
    try:
        deadline = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return (deadline - now).days
    except Exception:
        return None


def send_email(config: dict, to_email: str, subject: str, html_body: str):
    msg = MIMEMultipart("alternative")
    msg["From"] = config["from_email"]
    msg["To"] = to_email
    msg["Subject"] = subject

    msg.attach(MIMEText(html_body, "html", "utf-8"))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.mail.ru", 465, context=context) as server:
        server.login(config["login"], config["password"])
        server.sendmail(config["from_email"], to_email, msg.as_string())


def build_reminder_html(f: dict, days: int) -> str:
    if days == 0:
        badge_color = "#e53935"
        time_text = "ДЕДЛАЙН СЕГОДНЯ"
    elif days == 1:
        badge_color = "#e53935"
        time_text = "ДЕДЛАЙН ЗАВТРА"
    elif days <= 7:
        badge_color = "#f57c00"
        time_text = f"через {days} дней"
    else:
        badge_color = "#43a047"
        time_text = f"через {days} дней"

    website_link = ""
    if f.get("website"):
        website_link = f'<p><a href="{f["website"]}" style="color:#1a73e8;">Сайт фестиваля →</a></p>'

    submit_link = ""
    if f.get("submissionUrl"):
        submit_link = f'<p><a href="{f["submissionUrl"]}" style="color:#1a73e8;">Подать заявку →</a></p>'

    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family:Arial,sans-serif;background:#1a1a1a;color:#e0e0e0;padding:40px 20px;">
      <div style="max-width:500px;margin:0 auto;background:#2a2a2a;border-radius:12px;padding:32px;">
        <div style="text-align:center;margin-bottom:24px;">
          <span style="background:{badge_color};color:#fff;padding:6px 16px;border-radius:20px;font-size:13px;font-weight:600;">
            {time_text}
          </span>
        </div>
        <h1 style="margin:0 0 8px;font-size:22px;color:#fff;">🎬 {f['name']}</h1>
        <p style="margin:0 0 16px;color:#999;">📍 {f['city']}, {f['country']}</p>
        <p style="margin:0 0 8px;color:#bbb;">🎯 {f['focus']}</p>
        {f'<p style="margin:0 0 16px;color:#bbb;">📅 Дедлайн: {f["submissionDeadline"]}</p>' if f.get("submissionDeadline") else ''}
        {f'<p style="margin:0 0 16px;color:#bbb;">📅 Фестиваль: {f["festivalDates"]}</p>' if f.get("festivalDates") else ''}
        {website_link}
        {submit_link}
      </div>
      <p style="text-align:center;color:#666;font-size:12px;margin-top:24px;">
        КИНЕМАТОГРАФИСТЫ.РФ — Напоминания о фестивалях
      </p>
    </body>
    </html>
    """


def send_reminders(config: dict):
    subscribers = load_subscribers()
    festivals = load_festivals()
    now = datetime.now(timezone.utc)

    for uid, user_data in subscribers["users"].items():
        email = user_data.get("email")
        if not email:
            continue

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
                sent_key = f"sent_{fid}_{days}"
                if user_data.get(sent_key):
                    continue

                subject = f"🎬 {f['name']} — дедлайн через {days} дн" if days > 0 else f"🔴 {f['name']} — дедлайн СЕГОДНЯ"
                html = build_reminder_html(f, days)

                try:
                    send_email(config, email, subject, html)
                    user_data[sent_key] = now.isoformat()
                    save_subscribers(subscribers)
                    logger.info(f"Email sent to {email} for {f['name']} ({days}d)")
                except Exception as e:
                    logger.error(f"Failed to send to {email}: {e}")


def create_example_config():
    example = {
        "login": "your_login@mail.ru",
        "password": "APP_PASSWORD_HERE",
        "from_email": "your_login@mail.ru",
        "check_interval_hours": 12,
        "reminder_days": [30, 14, 7, 3, 1],
    }
    example_path = SCRIPT_DIR / "email_config.example.json"
    with open(example_path, "w", encoding="utf-8") as f:
        json.dump(example, f, ensure_ascii=False, indent=2)
    print(f"Создан пример конфига: {example_path}")


def main():
    if "--init" in sys.argv:
        create_example_config()
        return

    if "--subscribe" in sys.argv:
        idx = sys.argv.index("--subscribe")
        if idx + 1 >= len(sys.argv):
            print("Использование: python bot_email.py --subscribe user_id email")
            return

        user_id = sys.argv[idx + 1]
        email = sys.argv[idx + 2] if idx + 2 < len(sys.argv) else None
        if not email:
            print("Использование: python bot_email.py --subscribe user_id email")
            return

        subs = load_subscribers()
        if user_id not in subs["users"]:
            subs["users"][user_id] = {"track": []}
        subs["users"][user_id]["email"] = email
        save_subscribers(subs)
        print(f"✅ {user_id} → {email}")
        return

    config = load_config()
    if not config.get("login"):
        print("⚠️  Создай email_config.json с данными Mail.ru.")
        print("   Пример: python bot_email.py --init")
        return

    send_reminders(config)
    print("✅ Проверка дедлайнов завершена.")


if __name__ == "__main__":
    main()
