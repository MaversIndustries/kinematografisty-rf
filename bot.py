#!/usr/bin/env python3
"""
КИНЕМАТОГРАФИСТЫ.РФ — Telegram-бот для напоминаний о дедлайнах.

Функции:
  /start     — подписка на уведомления
  /stop      — отписка
  /list      — список отслеживаемых фестивалей
  /add ID    — добавить фестиваль в отслеживание
  /remove ID — убрать фестиваль из отслеживания
  /status    — ближайшие дедлайны
  /help      — справка

Настройка:
  1. Создайте бота через @BotFather, получите токен
  2. Создайте файл config.json (см. config.example.json)
  3. Запустите: python bot.py

Зависимости:
  pip install python-telegram-bot requests
"""

import json
import sys
import os
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

try:
    from telegram import Update, BotCommand
    from telegram.ext import (
        Application, CommandHandler, MessageHandler,
        ContextTypes, filters
    )
except ImportError:
    print("Установите зависимости: pip install python-telegram-bot requests")
    sys.exit(1)


SCRIPT_DIR = Path(__file__).parent
DATA_FILE = SCRIPT_DIR / "festivals.json"
CONFIG_FILE = SCRIPT_DIR / "bot_config.json"
SUBSCRIBERS_FILE = SCRIPT_DIR / ".bot_subscribers.json"

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


def get_user_tracking(user_id: int) -> list:
    subs = load_subscribers()
    user = subs["users"].get(str(user_id), {})
    return user.get("track", [])


def set_user_tracking(user_id: int, track: list):
    subs = load_subscribers()
    uid = str(user_id)
    if uid not in subs["users"]:
        subs["users"][uid] = {}
    subs["users"][uid]["track"] = track
    save_subscribers(subs)


def add_user_tracking(user_id: int, festival_id: int) -> bool:
    track = get_user_tracking(user_id)
    if festival_id not in track:
        track.append(festival_id)
        set_user_tracking(user_id, track)
        return True
    return False


def remove_user_tracking(user_id: int, festival_id: int) -> bool:
    track = get_user_tracking(user_id)
    if festival_id in track:
        track.remove(festival_id)
        set_user_tracking(user_id, track)
        return True
    return False


def toggle_user_tracking(user_id: int, festival_id: int) -> tuple:
    track = get_user_tracking(user_id)
    if festival_id in track:
        track.remove(festival_id)
        set_user_tracking(user_id, track)
        return False, "removed"
    else:
        track.append(festival_id)
        set_user_tracking(user_id, track)
        return True, "added"


def get_festival_by_id(festival_id: int) -> Optional[dict]:
    festivals = load_festivals()
    for f in festivals:
        if f["id"] == festival_id:
            return f
    return None


def days_until_deadline(date_str: str) -> Optional[int]:
    try:
        deadline = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = deadline - now
        return delta.days
    except Exception:
        return None


def format_festival_brief(f: dict) -> str:
    lines = [
        f"🎬 *{_escape_md(f['name'])}*",
        f"📍 {_escape_md(f['city'])}, {f['country']}",
        f"🎯 {_escape_md(f['focus'])}",
    ]
    if f.get("festivalDates"):
        lines.append(f"📅 {_escape_md(f['festivalDates'])}")
    if f.get("website"):
        lines.append(f"🔗 {f['website']}")
    return "\n".join(lines)


def format_deadline_msg(f: dict, days: int) -> str:
    if days < 0:
        time_left = "дедлайн прошёл"
    elif days == 0:
        time_left = "⚠️ дедлайн СЕГОДНЯ"
    elif days == 1:
        time_left = "⚠️ дедлайн ЗАВТРА"
    else:
        time_left = f"через {days} дн"

    msg = f"🎬 *{_escape_md(f['name'])}*\n"
    msg += f"📍 {_escape_md(f['city'])}\n"
    msg += f"⏰ {_escape_md(time_left)}\n"
    if f.get("submissionDeadline"):
        msg += f"📅 Дедлайн: {f['submissionDeadline']}\n"
    if f.get("website"):
        msg += f"🔗 {f['website']}\n"
    return msg


def _escape_md(text: str) -> str:
    specials = ["_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"]
    for ch in specials:
        text = text.replace(ch, f"\\{ch}")
    return text


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    subs = load_subscribers()
    uid = str(user_id)

    if uid not in subs["users"]:
        subs["users"][uid] = {
            "track": [],
            "username": update.effective_user.username or "",
            "first_name": update.effective_user.first_name or "",
            "subscribed_at": datetime.now(timezone.utc).isoformat(),
        }
        save_subscribers(subs)

    text = (
        "👋 Добро пожаловать в КИНЕМАТОГРАФИСТЫ.РФ!\n\n"
        "Я напоминаю о дедлайнах подачи заявок на кинофестивали.\n\n"
        "📌 *Команды:*\n"
        "/list — все фестивали\n"
        "/add ID — добавить в отслеживание\n"
        "/remove ID — убрать из отслеживания\n"
        "/track — мои отслеживаемые\n"
        "/status — ближайшие дедлайны\n"
        "/help — справка\n\n"
        "Начните с /list чтобы выбрать фестивали."
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    subs = load_subscribers()
    uid = str(user_id)

    if uid in subs["users"]:
        del subs["users"][uid]
        save_subscribers(subs)

    await update.message.reply_text("👋 Вы отписаны от уведомлений.")


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    festivals = load_festivals()
    track = get_user_tracking(update.effective_user.id)

    lines = ["📋 *Все фестивали:*\n"]
    for f in festivals:
        marker = "✅" if f["id"] in track else "  "
        status_emoji = {"active": "🟢", "paused": "🟡", "cancelled": "🔴", "unknown": "⚪"}.get(f["status"], "⚪")
        dl = f.get("submissionDeadline", "")
        dl_info = f" | ⏰ {dl}" if dl else ""
        lines.append(f"{marker} `{f['id']:>2}` {status_emoji} {_escape_md(f['name'])} — {_escape_md(f['city'])}{dl_info}")

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3900] + "\n\n... (список обрезан)"

    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Использование: /add ID\nID фестиваля из списка /list")
        return

    try:
        fid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID должен быть числом.")
        return

    f = get_festival_by_id(fid)
    if not f:
        await update.message.reply_text(f"Фестиваль с ID {fid} не найден.")
        return

    added, action = toggle_user_tracking(update.effective_user.id, fid)
    if added:
        await update.message.reply_text(
            f"✅ Добавлено: {_escape_md(f['name'])}\n"
            f"Буду напоминать о дедлайне ({f.get('submissionDeadline', 'не задан')}).",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(f"❌ Убрано: {_escape_md(f['name'])}", parse_mode="Markdown")


async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Использование: /remove ID")
        return

    try:
        fid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID должен быть числом.")
        return

    f = get_festival_by_id(fid)
    if not f:
        await update.message.reply_text(f"Фестиваль с ID {fid} не найден.")
        return

    removed = remove_user_tracking(update.effective_user.id, fid)
    if removed:
        await update.message.reply_text(f"❌ Убрано: {_escape_md(f['name'])}", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"Этот фестиваль не в вашем списке.")


async def cmd_track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track = get_user_tracking(update.effective_user.id)
    if not track:
        await update.message.reply_text("📭 Вы пока не отслеживаете ни одного фестиваля.\nИспользуйте /list чтобы выбрать.")
        return

    lines = ["📌 *Ваши фестивали:*\n"]
    for fid in track:
        f = get_festival_by_id(fid)
        if f:
            dl = f.get("submissionDeadline")
            if dl:
                days = days_until_deadline(dl)
                if days is not None:
                    if days < 0:
                        dl_info = "⏰ дедлайн прошёл"
                    elif days == 0:
                        dl_info = "🔴 дедлайн СЕГОДНЯ"
                    elif days <= 7:
                        dl_info = f"🟡 через {days} дн"
                    else:
                        dl_info = f"через {days} дн"
                else:
                    dl_info = dl
            else:
                dl_info = "дедлайн не задан"

            status_emoji = {"active": "🟢", "paused": "🟡", "cancelled": "🔴", "unknown": "⚪"}.get(f["status"], "⚪")
            lines.append(f"`{f['id']:>2}` {status_emoji} {_escape_md(f['name'])} — {dl_info}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track = get_user_tracking(update.effective_user.id)
    if not track:
        await update.message.reply_text("📭 Отслеживаемых фестивалей нет.\nИспользуйте /list.")
        return

    festivals = load_festivals()
    tracked = [f for f in festivals if f["id"] in track and f.get("submissionDeadline")]

    if not tracked:
        await update.message.reply_text("📅 У отслеживаемых фестивалей нет заданных дедлайнов.")
        return

    upcoming = []
    for f in tracked:
        days = days_until_deadline(f["submissionDeadline"])
        if days is not None and days >= 0:
            upcoming.append((days, f))

    upcoming.sort(key=lambda x: x[0])

    if not upcoming:
        await update.message.reply_text("📅 Ближайших дедлайнов нет (все прошли).")
        return

    lines = ["📅 *Ближайшие дедлайны:*\n"]
    for days, f in upcoming[:10]:
        lines.append(format_deadline_msg(f, days))

    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📌 *КИНЕМАТОГРАФИСТЫ.РФ — Бот напоминаний*\n\n"
        "Я слежу за дедлайнами кинофестивалей и напоминаю о них.\n\n"
        "/start — подписаться на уведомления\n"
        "/stop — отписаться\n"
        "/list — все фестивали (нажмите /add ID)\n"
        "/add 5 — добавить фестиваль #5\n"
        "/remove 5 — убрать фестиваль #5\n"
        "/track — мои отслеживаемые\n"
        "/status — ближайшие дедлайны\n\n"
        "Автоматические напоминания приходят за 30, 14, 7, 3 и 1 день до дедлайна."
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def check_deadlines(context: ContextTypes.DEFAULT_TYPE):
    """Проверяет дедлайны и отправляет напоминания подписчикам."""
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
                sent_key = f"sent_{fid}_{days}"
                if user_data.get(sent_key):
                    continue

                msg = format_deadline_msg(f, days)
                try:
                    await context.bot.send_message(
                        chat_id=int(uid),
                        text=msg,
                        parse_mode="Markdown",
                    )
                    user_data[sent_key] = now.isoformat()
                    save_subscribers(subs)
                    logger.info(f"Sent reminder to {uid} for {f['name']} ({days}d)")
                except Exception as e:
                    logger.error(f"Failed to send to {uid}: {e}")


def create_example_config():
    example = {
        "token": "YOUR_BOT_TOKEN_FROM_BOTFATHER",
        "check_interval_hours": 12,
        "reminder_days": [30, 14, 7, 3, 1],
    }
    example_path = SCRIPT_DIR / "bot_config.example.json"
    with open(example_path, "w", encoding="utf-8") as f:
        json.dump(example, f, ensure_ascii=False, indent=2)
    print(f"Создан пример конфига: {example_path}")


def main():
    config = load_config()

    if not config.get("token") or config["token"] == "YOUR_BOT_TOKEN_FROM_BOTFATHER":
        print("⚠️  Создайте bot_config.json с токеном бота.")
        print("   Пример: python bot.py --init")
        if "--init" in sys.argv:
            create_example_config()
        return

    if "--init" in sys.argv:
        create_example_config()
        return

    token = config["token"]
    interval_hours = config.get("check_interval_hours", 12)

    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("stop", cmd_stop))
    application.add_handler(CommandHandler("list", cmd_list))
    application.add_handler(CommandHandler("add", cmd_add))
    application.add_handler(CommandHandler("remove", cmd_remove))
    application.add_handler(CommandHandler("track", cmd_track))
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(CommandHandler("help", cmd_help))

    job_queue = application.job_queue
    job_queue.run_repeating(
        check_deadlines,
        interval=timedelta(hours=interval_hours),
        first=timedelta(minutes=1),
    )

    logger.info(f"Бот запущен. Проверка дедлайнов каждые {interval_hours} ч.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
