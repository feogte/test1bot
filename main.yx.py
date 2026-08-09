import asyncio
import logging
import os
import random
import sqlite3
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

# Load local .env when present. Environment variables still take precedence.
load_dotenv()

# ============================================================
# Island Game Bot — aiogram 3 + SQLite
# Python 3.10+
#
# Install:
#   pip install aiogram
#
# Environment:
#   BOT_TOKEN="123:ABC..."
#   ADMIN_IDS="123456789,987654321"
# ============================================================

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = {
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().lstrip("-").isdigit()
}

if not BOT_TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN. Укажите токен бота в переменной окружения BOT_TOKEN.")

DB_PATH = os.getenv("ISLAND_DB", "island_game.sqlite3")

# -----------------------------
# Game balance
# -----------------------------
START_COINS = 100
START_WOOD = 20
START_STONE = 10
START_FOOD = 15

COOLDOWNS = {
    "mine": 25,
    "farm": 30,
    "fish": 35,
    "explore": 60,
}

BUILDINGS = {
    "hut": {
        "name": "🏠 Хижина",
        "cost": {"wood": 25, "stone": 10},
        "income": 4,
        "score": 15,
        "desc": "Уютное жильё. Даёт немного монет при сборе дохода.",
    },
    "farm": {
        "name": "🌾 Ферма",
        "cost": {"wood": 35, "stone": 15},
        "income": 7,
        "score": 25,
        "desc": "Производит еду и увеличивает доход.",
    },
    "sawmill": {
        "name": "🪵 Лесопилка",
        "cost": {"wood": 50, "stone": 25},
        "income": 10,
        "score": 35,
        "desc": "Ускоряет развитие острова и приносит монеты.",
    },
    "quarry": {
        "name": "⛏ Каменоломня",
        "cost": {"wood": 60, "stone": 40},
        "income": 13,
        "score": 45,
        "desc": "Большая каменоломня для добычи камня.",
    },
    "lighthouse": {
        "name": "🗼 Маяк",
        "cost": {"wood": 90, "stone": 70},
        "income": 20,
        "score": 80,
        "desc": "Редкое здание. Сильно повышает престиж острова.",
    },
}

TERRITORIES = {
    1: {"name": "🌴 Пляж", "cost": 0, "score": 5},
    2: {"name": "🌲 Лес", "cost": 250, "score": 30},
    3: {"name": "⛰ Горы", "cost": 700, "score": 70},
    4: {"name": "🌋 Вулкан", "cost": 1600, "score": 150},
    5: {"name": "💎 Древние руины", "cost": 3500, "score": 300},
}

ITEMS = {
    "shell": ("🐚 Ракушка", 8),
    "pearl": ("🦪 Жемчужина", 80),
    "map": ("🗺 Старая карта", 120),
    "crystal": ("💎 Кристалл", 250),
    "idol": ("🗿 Древний идол", 500),
}

DAILY_REWARDS = [100, 120, 150, 180, 220, 280, 500]

QUESTS = {
    "collect": {
        "name": "🪵 Лесоруб",
        "desc": "Добудь 50 дерева",
        "target": 50,
        "reward": 100,
        "type": "wood",
    },
    "stone": {
        "name": "⛏ Каменщик",
        "desc": "Добудь 35 камня",
        "target": 35,
        "reward": 130,
        "type": "stone",
    },
    "build": {
        "name": "🏗 Строитель",
        "desc": "Построй 3 здания",
        "target": 3,
        "reward": 200,
        "type": "buildings",
    },
    "explore": {
        "name": "🧭 Исследователь",
        "desc": "Совершить 5 экспедиций",
        "target": 5,
        "reward": 250,
        "type": "explores",
    },
    "wealth": {
        "name": "💰 Капиталист",
        "desc": "Накопить 1000 монет",
        "target": 1000,
        "reward": 300,
        "type": "coins",
    },
}

ACHIEVEMENTS = {
    "first_build": ("🏗 Первый дом", "Построй первое здание", 50),
    "rich": ("💰 Богач", "Накопи 1000 монет", 150),
    "explorer": ("🧭 Мореплаватель", "Соверши 10 экспедиций", 200),
    "territory": ("🗺 Землевладелец", "Открой 3 территории", 250),
    "collector": ("💎 Коллекционер", "Найди редкий предмет", 300),
    "empire": ("👑 Империя", "Построй 10 зданий", 500),
}

EVENTS = [
    ("🌊 Шторм", "Шторм выбросил на берег полезные материалы.", {"wood": 12, "stone": 6}),
    ("🐠 Богатый улов", "Рыбаки нашли косяк рыбы.", {"food": 20}),
    ("🧭 Потерянный сундук", "На пляже обнаружен старый сундук.", {"coins": 90}),
    ("☀️ Хорошая погода", "Идеальный день для работ на острове.", {"coins": 50, "food": 10}),
]

# -----------------------------
# SQLite
# -----------------------------
db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.row_factory = sqlite3.Row
db.execute("PRAGMA journal_mode=WAL")
db.execute("PRAGMA foreign_keys=ON")


def now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def init_db():
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY,
            username TEXT DEFAULT '',
            first_name TEXT DEFAULT '',
            coins INTEGER DEFAULT 100,
            wood INTEGER DEFAULT 20,
            stone INTEGER DEFAULT 10,
            food INTEGER DEFAULT 15,
            territory INTEGER DEFAULT 1,
            buildings INTEGER DEFAULT 0,
            explores INTEGER DEFAULT 0,
            created_at INTEGER NOT NULL,
            last_daily INTEGER DEFAULT 0,
            daily_streak INTEGER DEFAULT 0,
            last_income INTEGER DEFAULT 0,
            score_bonus INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS buildings (
            user_id INTEGER NOT NULL,
            building TEXT NOT NULL,
            amount INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, building),
            FOREIGN KEY (user_id) REFERENCES players(user_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS inventory (
            user_id INTEGER NOT NULL,
            item TEXT NOT NULL,
            amount INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, item),
            FOREIGN KEY (user_id) REFERENCES players(user_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS cooldowns (
            user_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            until_ts INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, action),
            FOREIGN KEY (user_id) REFERENCES players(user_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS quests (
            user_id INTEGER NOT NULL,
            quest TEXT NOT NULL,
            progress INTEGER DEFAULT 0,
            claimed INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, quest),
            FOREIGN KEY (user_id) REFERENCES players(user_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS achievements (
            user_id INTEGER NOT NULL,
            achievement TEXT NOT NULL,
            claimed INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, achievement),
            FOREIGN KEY (user_id) REFERENCES players(user_id) ON DELETE CASCADE
        );
        """
    )
    db.commit()


def ensure_player(user_id: int, username: str = "", first_name: str = ""):
    row = db.execute("SELECT user_id FROM players WHERE user_id=?", (user_id,)).fetchone()
    if row:
        db.execute(
            "UPDATE players SET username=?, first_name=? WHERE user_id=?",
            (username or "", first_name or "", user_id),
        )
        db.commit()
        return False

    db.execute(
        """
        INSERT INTO players
        (user_id, username, first_name, coins, wood, stone, food, territory,
         buildings, explores, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0, 0, ?)
        """,
        (
            user_id,
            username or "",
            first_name or "",
            START_COINS,
            START_WOOD,
            START_STONE,
            START_FOOD,
            now_ts(),
        ),
    )

    for quest_id in QUESTS:
        db.execute(
            "INSERT INTO quests(user_id, quest, progress, claimed) VALUES (?, ?, 0, 0)",
            (user_id, quest_id),
        )

    for ach_id in ACHIEVEMENTS:
        db.execute(
            "INSERT INTO achievements(user_id, achievement, claimed) VALUES (?, ?, 0)",
            (user_id, ach_id),
        )

    db.commit()
    return True


def get_player(user_id: int):
    return db.execute("SELECT * FROM players WHERE user_id=?", (user_id,)).fetchone()


def add_resources(user_id: int, **kwargs):
    allowed = {"coins", "wood", "stone", "food"}
    parts = []
    values = []
    for key, value in kwargs.items():
        if key in allowed and value:
            parts.append(f"{key} = {key} + ?")
            values.append(int(value))
    if not parts:
        return
    values.append(user_id)
    db.execute(f"UPDATE players SET {', '.join(parts)} WHERE user_id=?", values)
    db.commit()


def set_resource(user_id: int, key: str, value: int):
    if key not in {"coins", "wood", "stone", "food"}:
        return
    db.execute(f"UPDATE players SET {key}=? WHERE user_id=?", (max(0, value), user_id))
    db.commit()


def get_buildings(user_id: int):
    return db.execute(
        "SELECT building, amount FROM buildings WHERE user_id=? ORDER BY building",
        (user_id,),
    ).fetchall()


def building_count(user_id: int, building: str) -> int:
    row = db.execute(
        "SELECT amount FROM buildings WHERE user_id=? AND building=?",
        (user_id, building),
    ).fetchone()
    return int(row["amount"]) if row else 0


def total_buildings(user_id: int) -> int:
    row = db.execute(
        "SELECT COALESCE(SUM(amount),0) AS n FROM buildings WHERE user_id=?",
        (user_id,),
    ).fetchone()
    return int(row["n"])


def add_building(user_id: int, building: str):
    db.execute(
        """
        INSERT INTO buildings(user_id, building, amount) VALUES (?, ?, 1)
        ON CONFLICT(user_id, building)
        DO UPDATE SET amount=amount+1
        """,
        (user_id, building),
    )
    db.execute("UPDATE players SET buildings=buildings+1 WHERE user_id=?", (user_id,))
    db.commit()


def add_item(user_id: int, item: str, amount: int = 1):
    db.execute(
        """
        INSERT INTO inventory(user_id, item, amount) VALUES (?, ?, ?)
        ON CONFLICT(user_id, item)
        DO UPDATE SET amount=amount+excluded.amount
        """,
        (user_id, item, amount),
    )
    db.commit()


def get_inventory(user_id: int):
    return db.execute(
        "SELECT item, amount FROM inventory WHERE user_id=? AND amount>0 ORDER BY item",
        (user_id,),
    ).fetchall()


def get_cd(user_id: int, action: str) -> int:
    row = db.execute(
        "SELECT until_ts FROM cooldowns WHERE user_id=? AND action=?",
        (user_id, action),
    ).fetchone()
    return int(row["until_ts"]) if row else 0


def set_cd(user_id: int, action: str, seconds: int):
    until = now_ts() + seconds
    db.execute(
        """
        INSERT INTO cooldowns(user_id, action, until_ts) VALUES (?, ?, ?)
        ON CONFLICT(user_id, action)
        DO UPDATE SET until_ts=excluded.until_ts
        """,
        (user_id, action, until),
    )
    db.commit()


def cooldown_text(user_id: int, action: str) -> str | None:
    remaining = get_cd(user_id, action) - now_ts()
    if remaining <= 0:
        return None
    m, s = divmod(remaining, 60)
    return f"{m}м {s}с" if m else f"{s}с"


def update_quest_progress(user_id: int, quest_type: str, amount: int = 1):
    quest = next((k for k, q in QUESTS.items() if q["type"] == quest_type), None)
    if not quest:
        return
    db.execute(
        """
        UPDATE quests
        SET progress = MIN(progress + ?, ?)
        WHERE user_id=? AND quest=? AND claimed=0
        """,
        (amount, QUESTS[quest]["target"], user_id, quest),
    )
    db.commit()


def quest_rows(user_id: int):
    return db.execute(
        "SELECT quest, progress, claimed FROM quests WHERE user_id=?",
        (user_id,),
    ).fetchall()


def unlock_achievement(user_id: int, achievement: str) -> bool:
    row = db.execute(
        "SELECT claimed FROM achievements WHERE user_id=? AND achievement=?",
        (user_id, achievement),
    ).fetchone()
    if not row or row["claimed"]:
        return False
    db.execute(
        "UPDATE achievements SET claimed=1 WHERE user_id=? AND achievement=?",
        (user_id, achievement),
    )
    db.commit()
    return True


def check_achievements(user_id: int):
    p = get_player(user_id)
    if not p:
        return []

    unlocked = []

    checks = {
        "first_build": total_buildings(user_id) >= 1,
        "rich": p["coins"] >= 1000,
        "explorer": p["explores"] >= 10,
        "territory": p["territory"] >= 3,
        "collector": any(
            row["item"] in {"pearl", "crystal", "idol"} for row in get_inventory(user_id)
        ),
        "empire": total_buildings(user_id) >= 10,
    }

    for key, ok in checks.items():
        if ok and unlock_achievement(user_id, key):
            reward = ACHIEVEMENTS[key][2]
            add_resources(user_id, coins=reward)
            unlocked.append((key, reward))

    return unlocked


def island_score(user_id: int) -> int:
    p = get_player(user_id)
    if not p:
        return 0

    score = (
        p["coins"] // 10
        + p["wood"]
        + p["stone"]
        + p["food"]
        + p["territory"] * 50
        + p["buildings"] * 25
        + p["explores"] * 5
        + p["score_bonus"]
    )

    for row in get_buildings(user_id):
        data = BUILDINGS.get(row["building"])
        if data:
            score += data["score"] * row["amount"]

    return int(score)


# -----------------------------
# UI
# -----------------------------
def kb_main():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🏝 Остров", callback_data="island"),
                InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
            ],
            [
                InlineKeyboardButton(text="⛏ Добыча", callback_data="gather"),
                InlineKeyboardButton(text="🏗 Строительство", callback_data="build"),
            ],
            [
                InlineKeyboardButton(text="🗺 Территории", callback_data="territory"),
                InlineKeyboardButton(text="🎒 Инвентарь", callback_data="inventory"),
            ],
            [
                InlineKeyboardButton(text="🎁 Награда", callback_data="daily"),
                InlineKeyboardButton(text="📜 Задания", callback_data="quests"),
            ],
            [
                InlineKeyboardButton(text="🏆 Достижения", callback_data="achievements"),
                InlineKeyboardButton(text="🥇 Рейтинг", callback_data="rating"),
            ],
        ]
    )


def kb_gather():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🪓 Рубить", callback_data="gather:mine"),
                InlineKeyboardButton(text="⛏ Камень", callback_data="gather:stone"),
            ],
            [
                InlineKeyboardButton(text="🎣 Рыбалка", callback_data="gather:fish"),
                InlineKeyboardButton(text="🧭 Исследовать", callback_data="gather:explore"),
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="home")],
        ]
    )


def kb_build():
    rows = []
    for key, data in BUILDINGS.items():
        cost = ", ".join(f"{k} {v}" for k, v in data["cost"].items())
        rows.append(
            [InlineKeyboardButton(
                text=f"{data['name']} — {cost}",
                callback_data=f"build:{key}"
            )]
        )
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_territory():
    rows = []
    for level, data in TERRITORIES.items():
        if level == 1:
            continue
        rows.append(
            [InlineKeyboardButton(
                text=f"{data['name']} — {data['cost']}💰",
                callback_data=f"territory:{level}"
            )]
        )
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_back():
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="home")]]
    )


def kb_admin():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats")],
            [InlineKeyboardButton(text="🎁 Выдать монеты", callback_data="admin:coins")],
            [InlineKeyboardButton(text="📣 Рассылка", callback_data="admin:broadcast")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="home")],
        ]
    )


def fmt_time(ts: int) -> str:
    if not ts:
        return "никогда"
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%d.%m.%Y %H:%M UTC")


def player_name(row) -> str:
    return f"@{row['username']}" if row["username"] else (row["first_name"] or str(row["user_id"]))


# -----------------------------
# Text screens
# -----------------------------
def home_text(user_id: int):
    p = get_player(user_id)
    return (
        "🏝 <b>ОСТРОВ</b>\n\n"
        f"💰 Монеты: <b>{p['coins']}</b>\n"
        f"🪵 Дерево: <b>{p['wood']}</b>\n"
        f"🪨 Камень: <b>{p['stone']}</b>\n"
        f"🍎 Еда: <b>{p['food']}</b>\n"
        f"🗺 Территория: <b>{TERRITORIES[p['territory']]['name']}</b>\n"
        f"🏗 Зданий: <b>{p['buildings']}</b>\n"
        f"⭐ Очки: <b>{island_score(user_id)}</b>\n\n"
        "Развивай остров, добывай ресурсы и поднимайся в рейтинге!"
    )


async def show_home(message_or_callback):
    user = message_or_callback.from_user
    ensure_player(user.id, user.username, user.first_name)
    text = home_text(user.id)

    if isinstance(message_or_callback, CallbackQuery):
        await message_or_callback.message.edit_text(text, reply_markup=kb_main())
    else:
        await message_or_callback.answer(text, reply_markup=kb_main())


# -----------------------------
# Bot
# -----------------------------
dp = Dispatcher()


@dp.message(CommandStart())
async def cmd_start(message: Message):
    is_new = ensure_player(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
    )
    if is_new:
        await message.answer(
            "🌴 <b>Добро пожаловать на остров!</b>\n\n"
            "У тебя есть небольшой участок земли, немного ресурсов и 100 монет.\n"
            "Твоя задача — превратить его в процветающий остров.\n\n"
            "Начни с добычи ресурсов и первых построек.",
        )
    await message.answer(home_text(message.from_user.id), reply_markup=kb_main())


@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📖 <b>Команды</b>\n\n"
        "/start — начать игру\n"
        "/island — остров\n"
        "/profile — профиль\n"
        "/admin — админ-панель (только для администраторов)\n\n"
        "Все основные действия доступны через inline-кнопки."
    )


@dp.message(Command("island"))
async def cmd_island(message: Message):
    ensure_player(message.from_user.id, message.from_user.username, message.from_user.first_name)
    await message.answer(home_text(message.from_user.id), reply_markup=kb_main())


@dp.message(Command("profile"))
async def cmd_profile(message: Message):
    ensure_player(message.from_user.id, message.from_user.username, message.from_user.first_name)
    await send_profile(message, message.from_user.id)


async def send_profile(target, user_id: int):
    p = get_player(user_id)
    text = (
        f"👤 <b>Профиль</b>\n\n"
        f"Игрок: <b>{player_name(p)}</b>\n"
        f"ID: <code>{p['user_id']}</code>\n\n"
        f"💰 Монеты: {p['coins']}\n"
        f"🪵 Дерево: {p['wood']}\n"
        f"🪨 Камень: {p['stone']}\n"
        f"🍎 Еда: {p['food']}\n"
        f"🏗 Зданий: {p['buildings']}\n"
        f"🧭 Экспедиций: {p['explores']}\n"
        f"🗺 Территория: {p['territory']}\n"
        f"⭐ Очки: {island_score(user_id)}\n"
        f"🔥 Серия ежедневных наград: {p['daily_streak']}"
    )
    await target.answer(text, reply_markup=kb_back())


@dp.callback_query(F.data == "home")
async def cb_home(callback: CallbackQuery):
    await callback.answer()
    await show_home(callback)


@dp.callback_query(F.data == "island")
async def cb_island(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(home_text(callback.from_user.id), reply_markup=kb_main())


@dp.callback_query(F.data == "profile")
async def cb_profile(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        f"👤 <b>Профиль</b>\n\n"
        f"{home_text(callback.from_user.id).replace('🏝 <b>ОСТРОВ</b>', '').strip()}\n\n"
        f"🧭 Экспедиций: {get_player(callback.from_user.id)['explores']}\n"
        f"🔥 Серия наград: {get_player(callback.from_user.id)['daily_streak']}",
        reply_markup=kb_back(),
    )


@dp.callback_query(F.data == "gather")
async def cb_gather(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    text = (
        "⛏ <b>Добыча</b>\n\n"
        "У каждого действия свой cooldown, поэтому можно комбинировать добычу.\n\n"
        f"🪓 Рубка: {cooldown_text(user_id, 'mine') or 'готово'}\n"
        f"⛏ Камень: {cooldown_text(user_id, 'farm') or 'готово'}\n"
        f"🎣 Рыбалка: {cooldown_text(user_id, 'fish') or 'готово'}\n"
        f"🧭 Экспедиция: {cooldown_text(user_id, 'explore') or 'готово'}"
    )
    await callback.message.edit_text(text, reply_markup=kb_gather())


@dp.callback_query(F.data.startswith("gather:"))
async def cb_gather_action(callback: CallbackQuery):
    user_id = callback.from_user.id
    action = callback.data.split(":", 1)[1]

    if action not in COOLDOWNS:
        await callback.answer("Неизвестное действие.", show_alert=True)
        return

    remaining = cooldown_text(user_id, action)
    if remaining:
        await callback.answer(f"⏳ Подожди ещё {remaining}.", show_alert=True)
        return

    p = get_player(user_id)

    if action == "mine":
        wood = random.randint(8, 16)
        stone = random.randint(1, 4)
        add_resources(user_id, wood=wood, stone=stone)
        update_quest_progress(user_id, "wood", wood)
        set_cd(user_id, "mine", COOLDOWNS["mine"])
        msg = f"🪓 Ты срубил деревья.\n\n🪵 +{wood}\n🪨 +{stone}"

    elif action == "stone":
        stone = random.randint(7, 14)
        wood = random.randint(1, 4)
        add_resources(user_id, stone=stone, wood=wood)
        update_quest_progress(user_id, "stone", stone)
        set_cd(user_id, "farm", COOLDOWNS["farm"])
        msg = f"⛏ Ты добыл камень.\n\n🪨 +{stone}\n🪵 +{wood}"

    elif action == "fish":
        food = random.randint(8, 18)
        coins = random.randint(5, 25)
        add_resources(user_id, food=food, coins=coins)
        set_cd(user_id, "fish", COOLDOWNS["fish"])
        msg = f"🎣 Отличный улов!\n\n🍎 +{food}\n💰 +{coins}"

    else:
        set_cd(user_id, "explore", COOLDOWNS["explore"])
        db.execute("UPDATE players SET explores=explores+1 WHERE user_id=?", (user_id,))
        db.commit()

        roll = random.random()
        if roll < 0.07:
            item = random.choice(["crystal", "idol"])
            name, value = ITEMS[item]
            add_item(user_id, item)
            add_resources(user_id, coins=value)
            update_quest_progress(user_id, "explores", 1)
            msg = f"💎 <b>Редкая находка!</b>\n\nТы нашёл: {name}\n💰 Стоимость находки: {value}"
        elif roll < 0.22:
            item = random.choice(["pearl", "map"])
            name, value = ITEMS[item]
            add_item(user_id, item)
            update_quest_progress(user_id, "explores", 1)
            msg = f"🧭 Экспедиция удалась!\n\nТы нашёл: {name}\n💎 Ценность: {value}"
        elif roll < 0.45:
            coins = random.randint(50, 140)
            add_resources(user_id, coins=coins)
            update_quest_progress(user_id, "explores", 1)
            msg = f"🧭 Ты нашёл старый тайник!\n\n💰 +{coins}"
        else:
            wood = random.randint(4, 12)
            stone = random.randint(2, 8)
            add_resources(user_id, wood=wood, stone=stone)
            update_quest_progress(user_id, "explores", 1)
            msg = f"🧭 Экспедиция завершена.\n\n🪵 +{wood}\n🪨 +{stone}"

    achievements = check_achievements(user_id)
    if achievements:
        msg += "\n\n🏆 <b>Новое достижение!</b>"
        for key, reward in achievements:
            msg += f"\n{ACHIEVEMENTS[key][0]} — +{reward}💰"

    await callback.answer("Готово!")
    await callback.message.edit_text(msg, reply_markup=kb_gather())


@dp.callback_query(F.data == "build")
async def cb_build(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    p = get_player(user_id)

    lines = ["🏗 <b>Строительство</b>\n"]
    for key, data in BUILDINGS.items():
        count = building_count(user_id, key)
        cost = ", ".join(f"{v} {k}" for k, v in data["cost"].items())
        lines.append(
            f"{data['name']} ×{count}\n"
            f"Цена: {cost}\n"
            f"Доход: +{data['income']}💰\n"
            f"<i>{data['desc']}</i>\n"
        )

    lines.append(
        f"Твои ресурсы: 🪵 {p['wood']} | 🪨 {p['stone']} | 💰 {p['coins']}"
    )
    await callback.message.edit_text("\n".join(lines), reply_markup=kb_build())


@dp.callback_query(F.data.startswith("build:"))
async def cb_build_action(callback: CallbackQuery):
    user_id = callback.from_user.id
    key = callback.data.split(":", 1)[1]
    data = BUILDINGS.get(key)

    if not data:
        await callback.answer("Неизвестное здание.", show_alert=True)
        return

    p = get_player(user_id)

    missing = []
    for resource, cost in data["cost"].items():
        if p[resource] < cost:
            missing.append(f"{resource}: {cost - p[resource]}")

    if missing:
        await callback.answer("Не хватает: " + ", ".join(missing), show_alert=True)
        return

    for resource, cost in data["cost"].items():
        set_resource(user_id, resource, p[resource] - cost)

    add_building(user_id, key)
    update_quest_progress(user_id, "build", 1)
    achievements = check_achievements(user_id)

    msg = f"🏗 Ты построил <b>{data['name']}</b>!"
    if achievements:
        msg += "\n\n🏆 <b>Достижения:</b>"
        for ach, reward in achievements:
            msg += f"\n{ACHIEVEMENTS[ach][0]} — +{reward}💰"

    await callback.answer("Построено!")
    await callback.message.edit_text(msg, reply_markup=kb_build())


@dp.callback_query(F.data == "territory")
async def cb_territory(callback: CallbackQuery):
    await callback.answer()
    p = get_player(callback.from_user.id)
    current = p["territory"]

    lines = [
        "🗺 <b>Территории</b>\n",
        f"Текущая: {TERRITORIES[current]['name']}\n",
        "Открытие территории даёт очки и новые возможности.\n",
    ]
    for level, data in TERRITORIES.items():
        if level == 1:
            continue
        status = "✅ открыта" if current >= level else f"💰 {data['cost']}"
        lines.append(f"{level}. {data['name']} — {status}")

    await callback.message.edit_text("\n".join(lines), reply_markup=kb_territory())


@dp.callback_query(F.data.startswith("territory:"))
async def cb_territory_action(callback: CallbackQuery):
    user_id = callback.from_user.id
    level = int(callback.data.split(":", 1)[1])
    p = get_player(user_id)

    if level <= p["territory"]:
        await callback.answer("Эта территория уже открыта.", show_alert=True)
        return

    if level != p["territory"] + 1:
        await callback.answer("Сначала открой предыдущую территорию.", show_alert=True)
        return

    cost = TERRITORIES[level]["cost"]
    if p["coins"] < cost:
        await callback.answer(f"Нужно ещё {cost - p['coins']} монет.", show_alert=True)
        return

    set_resource(user_id, "coins", p["coins"] - cost)
    db.execute("UPDATE players SET territory=? WHERE user_id=?", (level, user_id))
    db.commit()

    achievements = check_achievements(user_id)
    msg = f"🗺 <b>Новая территория открыта!</b>\n\n{TERRITORIES[level]['name']}"
    if achievements:
        msg += "\n\n🏆 Получено достижение!"

    await callback.answer("Территория открыта!")
    await callback.message.edit_text(msg, reply_markup=kb_territory())


@dp.callback_query(F.data == "inventory")
async def cb_inventory(callback: CallbackQuery):
    await callback.answer()
    rows = get_inventory(callback.from_user.id)
    if not rows:
        text = "🎒 <b>Инвентарь</b>\n\nПока пусто.\nОтправляйся в экспедиции — там можно найти редкие предметы."
    else:
        text = "🎒 <b>Инвентарь</b>\n\n"
        for row in rows:
            name, value = ITEMS.get(row["item"], (row["item"], 0))
            text += f"{name} ×{row['amount']} — ценность {value}💰\n"
    await callback.message.edit_text(text, reply_markup=kb_back())


@dp.callback_query(F.data == "daily")
async def cb_daily(callback: CallbackQuery):
    user_id = callback.from_user.id
    p = get_player(user_id)
    now = now_ts()

    if p["last_daily"] and now - p["last_daily"] < 86400:
        remaining = 86400 - (now - p["last_daily"])
        h = remaining // 3600
        m = (remaining % 3600) // 60
        await callback.answer(f"⏳ Следующая награда через {h}ч {m}м.", show_alert=True)
        return

    if p["last_daily"] and now - p["last_daily"] <= 172800:
        streak = min(p["daily_streak"] + 1, len(DAILY_REWARDS))
    else:
        streak = 1

    reward = DAILY_REWARDS[streak - 1]
    add_resources(user_id, coins=reward)
    db.execute(
        "UPDATE players SET last_daily=?, daily_streak=? WHERE user_id=?",
        (now, streak, user_id),
    )
    db.commit()

    await callback.answer(f"🎁 +{reward} монет!", show_alert=True)
    await callback.message.edit_text(
        "🎁 <b>Ежедневная награда</b>\n\n"
        f"🔥 День серии: <b>{streak}</b>\n"
        f"💰 Получено: <b>+{reward}</b>\n\n"
        "Заходи каждый день, чтобы увеличить награду.",
        reply_markup=kb_back(),
    )


@dp.callback_query(F.data == "quests")
async def cb_quests(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    rows = {r["quest"]: r for r in quest_rows(user_id)}

    text = "📜 <b>Задания</b>\n\n"
    for key, q in QUESTS.items():
        row = rows[key]
        progress = row["progress"]
        if row["claimed"]:
            status = "✅ выполнено"
        elif progress >= q["target"]:
            status = "🎁 награда готова"
        else:
            status = f"{progress}/{q['target']}"

        text += f"{q['name']}\n{q['desc']}\nПрогресс: {status}\nНаграда: {q['reward']}💰\n\n"

    buttons = []
    for key, q in QUESTS.items():
        row = rows[key]
        if row["progress"] >= q["target"] and not row["claimed"]:
            buttons.append([
                InlineKeyboardButton(
                    text=f"🎁 Забрать: {q['name']}",
                    callback_data=f"quest:{key}",
                )
            ])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="home")])

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@dp.callback_query(F.data.startswith("quest:"))
async def cb_quest_claim(callback: CallbackQuery):
    user_id = callback.from_user.id
    key = callback.data.split(":", 1)[1]
    q = QUESTS.get(key)

    if not q:
        await callback.answer("Нет такого задания.", show_alert=True)
        return

    row = db.execute(
        "SELECT progress, claimed FROM quests WHERE user_id=? AND quest=?",
        (user_id, key),
    ).fetchone()

    if not row or row["claimed"] or row["progress"] < q["target"]:
        await callback.answer("Награда пока недоступна.", show_alert=True)
        return

    db.execute(
        "UPDATE quests SET claimed=1 WHERE user_id=? AND quest=?",
        (user_id, key),
    )
    db.commit()
    add_resources(user_id, coins=q["reward"])

    await callback.answer(f"+{q['reward']} монет!")
    await cb_quests(callback)


@dp.callback_query(F.data == "achievements")
async def cb_achievements(callback: CallbackQuery):
    await callback.answer()
    rows = {
        r["achievement"]: r
        for r in db.execute(
            "SELECT achievement, claimed FROM achievements WHERE user_id=?",
            (callback.from_user.id,),
        ).fetchall()
    }

    text = "🏆 <b>Достижения</b>\n\n"
    for key, (name, desc, reward) in ACHIEVEMENTS.items():
        status = "✅" if rows.get(key, {"claimed": 0})["claimed"] else "🔒"
        text += f"{status} <b>{name}</b>\n{desc}\nНаграда: {reward}💰\n\n"

    await callback.message.edit_text(text, reply_markup=kb_back())


@dp.callback_query(F.data == "rating")
async def cb_rating(callback: CallbackQuery):
    await callback.answer()
    rows = db.execute(
        "SELECT * FROM players ORDER BY "
        "(coins/10 + wood + stone + food + territory*50 + buildings*25 + explores*5 + score_bonus) DESC "
        "LIMIT 10"
    ).fetchall()

    text = "🥇 <b>Рейтинг островов</b>\n\n"
    for i, row in enumerate(rows, 1):
        score = island_score(row["user_id"])
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
        text += f"{medal} {player_name(row)} — <b>{score}</b> очков\n"

    await callback.message.edit_text(text, reply_markup=kb_back())


# -----------------------------
# Admin
# -----------------------------
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён.")
        return
    await message.answer("🛠 <b>Админ-панель</b>", reply_markup=kb_admin())


@dp.callback_query(F.data == "admin:stats")
async def admin_stats(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    users = db.execute("SELECT COUNT(*) AS n FROM players").fetchone()["n"]
    coins = db.execute("SELECT COALESCE(SUM(coins),0) AS n FROM players").fetchone()["n"]
    buildings = db.execute("SELECT COALESCE(SUM(amount),0) AS n FROM buildings").fetchone()["n"]

    await callback.answer()
    await callback.message.edit_text(
        "📊 <b>Статистика</b>\n\n"
        f"👥 Игроков: {users}\n"
        f"💰 Монет на счетах: {coins}\n"
        f"🏗 Зданий: {buildings}",
        reply_markup=kb_admin(),
    )


@dp.callback_query(F.data == "admin:coins")
async def admin_coins(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    await callback.answer()
    await callback.message.edit_text(
        "🎁 <b>Выдача монет</b>\n\n"
        "Используй команду:\n"
        "<code>/give ID количество</code>\n\n"
        "Например:\n"
        "<code>/give 123456789 500</code>",
        reply_markup=kb_admin(),
    )


@dp.message(Command("give"))
async def cmd_give(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён.")
        return

    parts = message.text.split()
    if len(parts) != 3 or not parts[1].lstrip("-").isdigit() or not parts[2].lstrip("-").isdigit():
        await message.answer("Использование: /give ID количество")
        return

    user_id = int(parts[1])
    amount = int(parts[2])

    if amount <= 0:
        await message.answer("Количество должно быть больше 0.")
        return

    if not get_player(user_id):
        await message.answer("Игрок не найден.")
        return

    add_resources(user_id, coins=amount)
    await message.answer(f"✅ Игроку <code>{user_id}</code> выдано {amount} монет.")


@dp.callback_query(F.data == "admin:broadcast")
async def admin_broadcast(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    await callback.answer()
    await callback.message.edit_text(
        "📣 <b>Рассылка</b>\n\n"
        "Используй команду:\n"
        "<code>/broadcast Текст сообщения</code>",
        reply_markup=kb_admin(),
    )


@dp.message(Command("broadcast"))
async def cmd_broadcast(message: Message, bot: Bot):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён.")
        return

    text = message.text.partition(" ")[2].strip()
    if not text:
        await message.answer("Использование: /broadcast Текст")
        return

    users = db.execute("SELECT user_id FROM players").fetchall()
    success = 0
    failed = 0

    for row in users:
        try:
            await bot.send_message(row["user_id"], f"📣 <b>Сообщение от администрации</b>\n\n{text}")
            success += 1
            await asyncio.sleep(0.04)
        except Exception:
            failed += 1

    await message.answer(f"📣 Рассылка завершена.\n\n✅ {success}\n❌ {failed}")


# -----------------------------
# Random island events
# -----------------------------
async def random_event_for_player(user_id: int) -> str | None:
    if random.random() > 0.035:
        return None

    title, description, rewards = random.choice(EVENTS)
    add_resources(user_id, **rewards)

    reward_text = []
    for key, value in rewards.items():
        icon = {"coins": "💰", "wood": "🪵", "stone": "🪨", "food": "🍎"}[key]
        reward_text.append(f"{icon} +{value}")

    return f"{title}\n{description}\n\n" + " | ".join(reward_text)


# -----------------------------
# Catch-all callback safety
# -----------------------------
@dp.callback_query()
async def unknown_callback(callback: CallbackQuery):
    await callback.answer("Это действие больше недоступно.", show_alert=True)


async def main():
    init_db()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    me = await bot.get_me()
    logging.info("Bot started: @%s", me.username)

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
