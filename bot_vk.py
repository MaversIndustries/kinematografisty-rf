#!/usr/bin/env python3
"""
КИНЕМАТОГРАФИСТЫ.РФ — VK бот для напоминаний о дедлайнах.

Настройка:
  1. Создай сообщество ВКонтакте
  2. В настройках сообщества → Боты → Создать бота
  3. Скопируй токен бота
  4. Создай vk_config.json (см. vk_config.example.json)
  5. Запусти: python bot_vk.py

Зависимости:
  pip install vk_api requests
"""

import json
import sys
import os
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

try:
    import vk_api
    from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
    from vk_api.utils import get_random_id
except ImportError:
    print("Установите зависимости: pip install vk_api requests")
    sys.exit(1)


SCRIPT_DIR = Path(__file__).parent
DATA_FILE = SCRIPT_DIR / "festivals.json"
CONFIG_FILE = SCRIPT_DIR / "vk_config.json"
SUBSCRIBERS_FILE = SCRIPT_DIR / ".vk_subscribers.json"

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
        f"🎬 {f['name']}",
        f"📍 {f['city']}, {f['country']}",
        f"🎯 {f['focus']}",
    ]
    if f.get("festivalDates"):
        lines.append(f"📅 {f['festivalDates']}")
    if f.get("website"):
        lines.append(f"🔗 {f['website']}")
    return "\n".join(lines)


def format_deadline_msg(f: dict, days: int) -> str:
    if days < 0:
        time_left = "дедлайн прошёл"
    elif days == 0:
        time_left = "🔴 ДЕДЛАЙН СЕГОДНЯ"
    elif days == 1:
        time_left = "🔴 ДЕДЛАЙН ЗАВТРА"
    else:
        time_left = f"⏰ через {days} дн"

    msg = f"🎬 {f['name']}\n"
    msg += f"📍 {f['city']}\n"
    msg += f"⏰ {time_left}\n"
    if f.get("submissionDeadline"):
        msg += f"📅 Дедлайн: {f['submissionDeadline']}\n"
    if f.get("website"):
        msg += f"🔗 {f['website']}\n"
    return msg


def send_message(vk, user_id: int, text: str):
    vk.messages.send(
        user_id=user_id,
        message=text,
        random_id=get_random_id(),
    )


def handle_command(vk, event) -> Optional[str]:
    user_id = event.obj.message["from_id"]
    text = event.obj.message.get("text", "").strip().lower()
    args = text.split()

    if not args:
        return None

    cmd = args[0]

    if cmd == "/start" or cmd == "начать":
        subs = load_subscribers()
        uid = str(user_id)
        if uid not in subs["users"]:
            subs["users"][uid] = {
                "track": [],
                "subscribed_at": datetime.now(timezone.utc).isoformat(),
            }
            save_subscribers(subs)

        return (
            "👋 Добро пожаловать в КИНЕМАТОГРАФИСТЫ.РФ!\n\n"
            "Я напоминаю о дедлайнах подачи заявок на кинофестивали.\n\n"
            "📌 Команды:\n"
            "/list — все фестивали\n"
            "/add ID — добавить в отслеживание\n"
            "/remove ID — убрать из отслеживания\n"
            "/track — мои отслеживаемые\n"
            "/status — ближайшие дедлайны\n"
            "/help — справка\n\n"
            "Начните с /list чтобы выбрать фестивали."
        )

    elif cmd == "/stop" or cmd == "стоп":
        subs = load_subscribers()
        uid = str(user_id)
        if uid in subs["users"]:
            del subs["users"][uid]
            save_subscribers(subs)
        return "👋 Вы отписаны от уведомлений."

    elif cmd == "/list" or cmd == "список":
        festivals = load_festivals()
        track = get_user_tracking(user_id)

        lines = ["📋 Все фестивали:\n"]
        for f in festivals:
            marker = "✅" if f["id"] in track else "  "
            status_emoji = {"active": "🟢", "paused": "🟡", "cancelled": "🔴", "unknown": "⚪"}.get(f["status"], "⚪")
            dl = f.get("submissionDeadline", "")
            dl_info = f" | ⏰ {dl}" if dl else ""
            lines.append(f"{marker} {f['id']:>2}. {status_emoji} {f['name']} — {f['city']}{dl_info}")

        text = "\n".join(lines)
        if len(text) > 4000:
            text = text[:3900] + "\n\n... (список обрезан)"
        return text

    elif cmd == "/add" or cmd == "добавить":
        if len(args) < 2:
            return "Использование: /add ID\nID фестиваля из списка /list"

        try:
            fid = int(args[1])
        except ValueError:
            return "ID должен быть числом."

        f = get_festival_by_id(fid)
        if not f:
            return f"Фестиваль с ID {fid} не найден."

        added, action = toggle_user_tracking(user_id, fid)
        if added:
            return (
                f"✅ Добавлено: {f['name']}\n"
                f"Буду напоминать о дедлайне ({f.get('submissionDeadline', 'не задан')})."
            )
        else:
            return f"❌ Убрано: {f['name']}"

    elif cmd == "/remove" or cmd == "убрать":
        if len(args) < 2:
            return "Использование: /remove ID"

        try:
            fid = int(args[1])
        except ValueError:
            return "ID должен быть числом."

        f = get_festival_by_id(fid)
        if not f:
            return f"Фестиваль с ID {fid} не найден."

        removed = toggle_user_tracking(user_id, fid)
        if removed[1] == "removed":
            return f"❌ Убрано: {f['name']}"
        else:
            return "Этот фестиваль не в вашем списке."

    elif cmd == "/track" or cmd == "мои":
        track = get_user_tracking(user_id)
        if not track:
            return "📭 Вы пока не отслеживаете ни одного фестиваля.\nИспользуйте /list чтобы выбрать."

        lines = ["📌 Ваши фестивали:\n"]
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
                lines.append(f"{f['id']:>2}. {status_emoji} {f['name']} — {dl_info}")

        return "\n".join(lines)

    elif cmd == "/status" or cmd == "дедлайны":
        track = get_user_tracking(user_id)
        if not track:
            return "📭 Отслеживаемых фестивалей нет.\nИспользуйте /list."

        festivals = load_festivals()
        tracked = [f for f in festivals if f["id"] in track and f.get("submissionDeadline")]

        if not tracked:
            return "📅 У отслеживаемых фестивалей нет заданных дедлайнов."

        upcoming = []
        for f in tracked:
            days = days_until_deadline(f["submissionDeadline"])
            if days is not None and days >= 0:
                upcoming.append((days, f))

        upcoming.sort(key=lambda x: x[0])

        if not upcoming:
            return "📅 Ближайших дедлайнов нет (все прошли)."

        lines = ["📅 Ближайшие дедлайны:\n"]
        for days, f in upcoming[:10]:
            lines.append(format_deadline_msg(f, days))

        return "\n\n".join(lines)

    elif cmd == "/help" or cmd == "помощь":
        return (
            "📌 КИНЕМАТОГРАФИСТЫ.РФ — Напоминания\n\n"
            "Я слежу за дедлайнами кинофестивалей и напоминаю о них.\n\n"
            "/start — подписаться\n"
            "/stop — отписаться\n"
            "/list — все фестивали\n"
            "/add 5 — добавить фестиваль #5\n"
            "/remove 5 — убрать фестиваль #5\n"
            "/track — мои отслеживаемые\n"
            "/status — ближайшие дедлайны\n\n"
            "Автоматические напоминания приходят за 30, 14, 7, 3 и 1 день до дедлайна."
        )

    return None


def check_deadlines(vk):
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
                    send_message(vk, int(uid), msg)
                    user_data[sent_key] = now.isoformat()
                    save_subscribers(subs)
                    logger.info(f"Sent reminder to {uid} for {f['name']} ({days}d)")
                except Exception as e:
                    logger.error(f"Failed to send to {uid}: {e}")


def create_example_config():
    example = {
        "token": "YOUR_COMMUNITY_TOKEN",
        "group_id": 0,
        "check_interval_hours": 12,
        "reminder_days": [30, 14, 7, 3, 1],
    }
    example_path = SCRIPT_DIR / "vk_config.example.json"
    with open(example_path, "w", encoding="utf-8") as f:
        json.dump(example, f, ensure_ascii=False, indent=2)
    print(f"Создан пример конфига: {example_path}")


def main():
    config = load_config()

    if not config.get("token") or config["token"] == "YOUR_COMMUNITY_TOKEN":
        print("⚠️  Создай vk_config.json с токеном сообщества.")
        print("   Пример: python bot_vk.py --init")
        if "--init" in sys.argv:
            create_example_config()
        return

    if "--init" in sys.argv:
        create_example_config()
        return

    token = config["token"]
    group_id = config.get("group_id", 0)
    interval_hours = config.get("check_interval_hours", 12)

    vk_session = vk_api.VkApi(token=token)
    vk = vk_session.get_api()

    longpoll = VkBotLongPoll(vk_session, group_id)

    logger.info(f"VK бот запущен. Группа: {group_id}")

    last_deadline_check = datetime.now(timezone.utc)

    for event in longpoll.listen():
        if event.type == VkBotEventType.MESSAGE_NEW:
            user_id = event.obj.message["from_id"]
            text = event.obj.message.get("text", "").strip()

            if not text:
                continue

            logger.info(f"Message from {user_id}: {text}")

            response = handle_command(vk, event)
            if response:
                send_message(vk, user_id, response)

        now = datetime.now(timezone.utc)
        if (now - last_deadline_check).total_seconds() >= interval_hours * 3600:
            logger.info("Checking deadlines...")
            check_deadlines(vk)
            last_deadline_check = now


if __name__ == "__main__":
    main()
