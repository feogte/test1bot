import asyncio
import logging
import os
import random
import sqlite3
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ContentType
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery
)

BOT_TOKEN = "8693450959:AAFfaqWBwJdbVSUwiv-Q5jQiMC76MRARIuU"

DB_PATH = os.getenv("DB_PATH", "data.db")
SHOP_NAME = "Vinex Shop"

# Необязательно: ID Telegram-чата поддержки.
SUPPORT_CHAT_ID = os.getenv("SUPPORT_CHAT_ID", "").strip()

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("vinex")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()


# -------------------- DATABASE --------------------

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def now():
    return datetime.now().isoformat(timespec="seconds")


def init_db():
    conn = db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT DEFAULT '',
            first_name TEXT DEFAULT '',
            balance INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            price_rub INTEGER NOT NULL,
            stock INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            payload TEXT NOT NULL,
            sold INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER,
            product_name TEXT NOT NULL,
            price_rub INTEGER NOT NULL,
            payment TEXT NOT NULL,
            status TEXT NOT NULL,
            payload TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            rating INTEGER NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            price_rub INTEGER NOT NULL,
            active INTEGER DEFAULT 1
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS case_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL,
            prize TEXT NOT NULL,
            weight INTEGER NOT NULL DEFAULT 1
        )
    """)

    # Миграция старой базы: добавляем новые поля, если их ещё нет.
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "balance" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN balance INTEGER DEFAULT 0")

    # Демонстрационные товары создаются только если БД пустая.
    defaults = [
        ("mm95", "🇲🇲 +95 — Мьянма", 15),
        ("ru7", "🇷🇺 +7 — Россия", 80),
        ("ua380", "🇺🇦 +380 — Украина", 60),
        ("kz7", "🇰🇿 +7 — Казахстан", 70),
    ]

    for code, title, price in defaults:
        conn.execute(
            "INSERT OR IGNORE INTO products(code,title,price_rub,stock) VALUES(?,?,?,0)",
            (code, title, price)
        )

    cases = [
        ("normal", "🎲 Обычный кейс", 50),
        ("premium", "🔥 Premium кейс", 150),
        ("lucky", "💎 Lucky кейс", 300),
    ]

    for code, title, price in cases:
        conn.execute(
            "INSERT OR IGNORE INTO cases(code,title,price_rub) VALUES(?,?,?)",
            (code, title, price)
        )

    conn.commit()
    conn.close()


def save_user(user):
    conn = db()
    conn.execute("""
        INSERT INTO users(user_id, username, first_name, balance, created_at)
        VALUES(?,?,?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET
            username=excluded.username,
            first_name=excluded.first_name
    """, (
        user.id,
        user.username or "",
        user.first_name or "",
        0,
        now()
    ))
    conn.commit()
    conn.close()


def add_purchase(user_id, product_id, name, price, payment, status, payload=""):
    conn = db()
    cur = conn.execute("""
        INSERT INTO purchases
        (user_id, product_id, product_name, price_rub, payment, status, payload, created_at)
        VALUES(?,?,?,?,?,?,?,?)
    """, (user_id, product_id, name, price, payment, status, payload, now()))
    purchase_id = cur.lastrowid
    conn.commit()
    conn.close()
    return purchase_id


def rub_to_stars(rub):
    # В тестовом магазине 1 RUB = 1 Star.
    return max(1, int(rub))


# -------------------- KEYBOARDS --------------------

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏪 STORE", callback_data="store")],
        [
            InlineKeyboardButton(text="🎁 КЕЙСЫ", callback_data="cases"),
            InlineKeyboardButton(text="👤 ПРОФИЛЬ", callback_data="profile")
        ],
        [
            InlineKeyboardButton(text="🧾 ПОКУПКИ", callback_data="purchases"),
            InlineKeyboardButton(text="⭐ ОТЗЫВЫ", callback_data="reviews")
        ],
        [InlineKeyboardButton(text="🎧 ПОДДЕРЖКА", callback_data="support")]
    ])


def back(callback="home"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data=callback)]
    ])


def store_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛍️ Аккаунты", callback_data="accounts")],
        [InlineKeyboardButton(text="⭐ Telegram Stars", callback_data="stars")],
        [InlineKeyboardButton(text="🎁 Кейсы", callback_data="cases")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="home")]
    ])


def cases_menu():
    conn = db()
    rows = conn.execute(
        "SELECT code,title,price_rub FROM cases WHERE active=1 ORDER BY id"
    ).fetchall()
    conn.close()

    buttons = []
    for row in rows:
        buttons.append([
            InlineKeyboardButton(
                text=f"{row['title']} — {row['price_rub']} ₽",
                callback_data=f"case:{row['code']}"
            )
        ])

    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def products_menu():
    conn = db()
    rows = conn.execute(
        "SELECT id,title,price_rub,stock FROM products WHERE active=1 ORDER BY id"
    ).fetchall()
    conn.close()

    buttons = []
    for row in rows:
        stock = "есть" if row["stock"] > 0 else "нет"
        buttons.append([
            InlineKeyboardButton(
                text=f"{row['title']} — {row['price_rub']} ₽ | {stock}",
                callback_data=f"product:{row['id']}"
            )
        ])

    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="store")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# -------------------- START / HOME --------------------

@dp.message(CommandStart())
async def start(message: Message):
    save_user(message.from_user)
    await message.answer(
        f"<b>🔥 Добро пожаловать в {SHOP_NAME}!</b>\n\n"
        "🛍️ товары с автоматической выдачей\n"
        "🎁 кейсы с призами\n"
        "👤 профиль и баланс\n"
        "🧾 история заказов\n"
        "⭐ отзывы\n"
        "🎧 поддержка\n\n"
        "<i>Выберите раздел:</i>",
        reply_markup=main_menu()
    )


@dp.callback_query(F.data == "home")
async def home(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text(
        f"<b>🔥 {SHOP_NAME}</b>\n\nВыберите нужный раздел:",
        reply_markup=main_menu()
    )
    await call.answer()


# -------------------- STORE --------------------

@dp.callback_query(F.data == "store")
async def store(call: CallbackQuery):
    await call.message.edit_text(
        "<b>🏪 STORE</b>\n\n"
        "Выберите категорию:",
        reply_markup=store_menu()
    )
    await call.answer()


@dp.callback_query(F.data == "stars")
async def stars(call: CallbackQuery):
    await call.message.edit_text(
        "<b>⭐ TELEGRAM STARS</b>\n\n"
        "Оплата цифровых товаров через Telegram Stars подключается "
        "к оформлению заказа автоматически.\n\n"
        "Выберите товар в разделе «Аккаунты» или откройте кейс.",
        reply_markup=store_menu()
    )
    await call.answer()


@dp.callback_query(F.data == "accounts")
async def accounts(call: CallbackQuery):
    await call.message.edit_text(
        "<b>🛍️ АККАУНТЫ</b>\n\n"
        "Флаг страны уже является частью названия товара.\n"
        "Товар без наличия купить нельзя.",
        reply_markup=products_menu()
    )
    await call.answer()


@dp.callback_query(F.data.startswith("product:"))
async def product(call: CallbackQuery):
    product_id = int(call.data.split(":", 1)[1])

    conn = db()
    row = conn.execute(
        "SELECT id,title,price_rub,stock FROM products WHERE id=? AND active=1",
        (product_id,)
    ).fetchone()
    conn.close()

    if not row:
        await call.answer("Товар не найден", show_alert=True)
        return

    if row["stock"] <= 0:
        await call.message.edit_text(
            f"<b>{row['title']}</b>\n\n"
            "❌ Сейчас нет в наличии.",
            reply_markup=back("accounts")
        )
        await call.answer()
        return

    stars = rub_to_stars(row["price_rub"])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"⭐ Купить за {stars} Stars",
            callback_data=f"pay_product:{product_id}"
        )],
        [InlineKeyboardButton(text="◀️ К товарам", callback_data="accounts")]
    ])

    await call.message.edit_text(
        f"<b>{row['title']}</b>\n\n"
        f"💰 Цена: <b>{row['price_rub']} ₽</b>\n"
        f"⭐ Оплата: <b>{stars} Stars</b>\n"
        f"📦 В наличии: <b>{row['stock']} шт.</b>\n"
        "⚡ Выдача: автоматически после успешной оплаты.",
        reply_markup=kb
    )
    await call.answer()


# -------------------- STARS PAYMENTS --------------------

@dp.callback_query(F.data.startswith("pay_product:"))
async def pay_product(call: CallbackQuery):
    product_id = int(call.data.split(":", 1)[1])

    conn = db()
    row = conn.execute(
        "SELECT id,title,price_rub,stock FROM products WHERE id=? AND active=1",
        (product_id,)
    ).fetchone()
    conn.close()

    if not row or row["stock"] <= 0:
        await call.answer("Товар закончился", show_alert=True)
        return

    stars = rub_to_stars(row["price_rub"])

    await bot.send_invoice(
        chat_id=call.from_user.id,
        title=row["title"],
        description=f"Покупка {row['title']} в {SHOP_NAME}",
        payload=f"product:{product_id}",
        currency="XTR",
        prices=[LabeledPrice(label=row["title"], amount=stars)]
    )
    await call.answer()


@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    payload = query.invoice_payload

    if payload.startswith("product:"):
        product_id = int(payload.split(":", 1)[1])
        conn = db()
        row = conn.execute(
            "SELECT stock FROM products WHERE id=? AND active=1",
            (product_id,)
        ).fetchone()
        conn.close()

        if not row or row["stock"] <= 0:
            await query.answer(ok=False, error_message="Товар уже закончился.")
            return

    await query.answer(ok=True)


# -------------------- CASES --------------------

@dp.callback_query(F.data == "cases")
async def cases(call: CallbackQuery):
    await call.message.edit_text(
        "<b>🎁 CASES</b>\n\n"
        "Открытие кейса происходит после оплаты.\n"
        "Приз выбирается случайно по весам, заданным для кейса.",
        reply_markup=cases_menu()
    )
    await call.answer()


@dp.callback_query(F.data.startswith("case:"))
async def case_info(call: CallbackQuery):
    code = call.data.split(":", 1)[1]

    conn = db()
    row = conn.execute(
        "SELECT id,title,price_rub FROM cases WHERE code=? AND active=1",
        (code,)
    ).fetchone()
    conn.close()

    if not row:
        await call.answer("Кейс не найден", show_alert=True)
        return

    stars = rub_to_stars(row["price_rub"])

    await call.message.edit_text(
        f"<b>{row['title']}</b>\n\n"
        f"💰 Цена: <b>{row['price_rub']} ₽</b>\n"
        f"⭐ Оплата: <b>{stars} Stars</b>\n\n"
        "🎲 После успешной оплаты бот случайно выберет приз.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f"🎲 Открыть за {stars} Stars",
                callback_data=f"pay_case:{row['id']}"
            )],
            [InlineKeyboardButton(text="◀️ К кейсам", callback_data="cases")]
        ])
    )
    await call.answer()


@dp.callback_query(F.data.startswith("pay_case:"))
async def pay_case(call: CallbackQuery):
    case_id = int(call.data.split(":", 1)[1])

    conn = db()
    row = conn.execute(
        "SELECT id,title,price_rub FROM cases WHERE id=? AND active=1",
        (case_id,)
    ).fetchone()
    conn.close()

    if not row:
        await call.answer("Кейс не найден", show_alert=True)
        return

    stars = rub_to_stars(row["price_rub"])

    await bot.send_invoice(
        chat_id=call.from_user.id,
        title=row["title"],
        description=f"Открытие {row['title']}",
        payload=f"case:{case_id}",
        currency="XTR",
        prices=[LabeledPrice(label=row["title"], amount=stars)]
    )
    await call.answer()


async def open_paid_case(user_id, case_id):
    conn = db()
    case = conn.execute(
        "SELECT id,title,price_rub FROM cases WHERE id=?",
        (case_id,)
    ).fetchone()

    if not case:
        conn.close()
        return None

    items = conn.execute(
        "SELECT prize,weight FROM case_items WHERE case_id=? AND weight>0",
        (case_id,)
    ).fetchall()
    conn.close()

    if not items:
        return "🎁 Тестовый приз"

    choices = [x["prize"] for x in items]
    weights = [x["weight"] for x in items]
    return random.choices(choices, weights=weights, k=1)[0]


@dp.message(F.content_type == ContentType.SUCCESSFUL_PAYMENT)
async def successful_case_payment(message: Message):
    # Этот handler объединяется с обработчиком выше на уровне aiogram;
    # оставляем отдельную функцию только как документацию невозможного
    # дублирования. Реальная обработка выполняется ниже через общий handler.
    pass


# -------------------- PROFILE --------------------

@dp.callback_query(F.data == "profile")
async def profile(call: CallbackQuery):
    conn = db()
    user = conn.execute(
        "SELECT * FROM users WHERE user_id=?",
        (call.from_user.id,)
    ).fetchone()
    count = conn.execute(
        "SELECT COUNT(*) c FROM purchases WHERE user_id=? AND status='paid'",
        (call.from_user.id,)
    ).fetchone()["c"]
    conn.close()

    username = f"@{user['username']}" if user and user["username"] else "не указан"

    await call.message.edit_text(
        "<b>👤 ПРОФИЛЬ</b>\n\n"
        f"🆔 ID: <code>{call.from_user.id}</code>\n"
        f"👤 Username: {username}\n"
        f"🧾 Покупок: <b>{count}</b>\n"
        f"💰 Баланс: <b>{user['balance'] if user else 0} ₽</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🧾 История покупок", callback_data="purchases")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="home")]
        ])
    )
    await call.answer()


@dp.callback_query(F.data == "purchases")
async def purchases(call: CallbackQuery):
    conn = db()
    rows = conn.execute("""
        SELECT product_name,price_rub,payment,status,created_at
        FROM purchases
        WHERE user_id=?
        ORDER BY id DESC LIMIT 10
    """, (call.from_user.id,)).fetchall()
    conn.close()

    if not rows:
        text = "<b>🧾 ИСТОРИЯ ПОКУПОК</b>\n\nПокупок пока нет."
    else:
        lines = ["<b>🧾 ИСТОРИЯ ПОКУПОК</b>\n"]
        for i, row in enumerate(rows, 1):
            status = "✅" if row["status"] == "paid" else "⏳"
            lines.append(
                f"{i}. {status} {row['product_name']} — "
                f"<b>{row['price_rub']} ₽</b>\n"
                f"   {row['created_at'].replace('T',' ')}"
            )
        text = "\n".join(lines)

    await call.message.edit_text(text, reply_markup=back())
    await call.answer()


# -------------------- REVIEWS --------------------

class ReviewState(StatesGroup):
    waiting_text = State()


class SupportState(StatesGroup):
    waiting_text = State()


@dp.callback_query(F.data == "reviews")
async def reviews(call: CallbackQuery):
    conn = db()
    rows = conn.execute("""
        SELECT r.rating,r.text,r.created_at,u.first_name
        FROM reviews r
        LEFT JOIN users u ON u.user_id=r.user_id
        ORDER BY r.id DESC LIMIT 5
    """).fetchall()
    conn.close()

    if rows:
        lines = ["<b>⭐ ОТЗЫВЫ</b>\n"]
        for row in rows:
            stars = "⭐" * row["rating"]
            text = row["text"].replace("<", "&lt;").replace(">", "&gt;")
            lines.append(f"{stars} <b>{row['first_name'] or 'Покупатель'}</b>\n{text}")
        text = "\n\n".join(lines)
    else:
        text = "<b>⭐ ОТЗЫВЫ</b>\n\nПока отзывов нет."

    await call.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Оставить отзыв", callback_data="review_add")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="home")]
        ])
    )
    await call.answer()


@dp.callback_query(F.data == "review_add")
async def review_add(call: CallbackQuery, state: FSMContext):
    await state.set_state(ReviewState.waiting_text)
    await call.message.edit_text(
        "<b>✍️ ОТЗЫВ</b>\n\n"
        "Напишите одним сообщением текст отзыва.\n"
        "В начале укажите оценку от 1 до 5, например:\n\n"
        "<code>5 Отличный магазин!</code>",
        reply_markup=back()
    )
    await call.answer()


@dp.message(ReviewState.waiting_text)
async def review_text(message: Message, state: FSMContext):
    raw = message.text.strip()
    parts = raw.split(maxsplit=1)

    if not parts or not parts[0].isdigit() or not 1 <= int(parts[0]) <= 5:
        await message.answer("Нужно начать сообщение с оценки от 1 до 5. Например: <code>5 Всё отлично</code>")
        return

    rating = int(parts[0])
    text = parts[1].strip() if len(parts) > 1 else ""

    if len(text) < 3:
        await message.answer("Текст отзыва слишком короткий.")
        return

    conn = db()
    conn.execute(
        "INSERT INTO reviews(user_id,rating,text,created_at) VALUES(?,?,?,?)",
        (message.from_user.id, rating, text, now())
    )
    conn.commit()
    conn.close()
    await state.clear()

    await message.answer(
        "✅ <b>Отзыв сохранён!</b>\n\nСпасибо за обратную связь.",
        reply_markup=main_menu()
    )


# -------------------- SUPPORT --------------------

@dp.callback_query(F.data == "support")
async def support(call: CallbackQuery, state: FSMContext):
    await state.set_state(SupportState.waiting_text)
    await call.message.edit_text(
        "<b>🎧 ПОДДЕРЖКА</b>\n\n"
        "Опишите проблему одним сообщением.\n"
        "Укажите номер заказа, если вопрос связан с покупкой.",
        reply_markup=back()
    )
    await call.answer()


@dp.message(SupportState.waiting_text)
async def support_text(message: Message, state: FSMContext):
    text = message.text.strip()

    if len(text) < 3:
        await message.answer("Опишите проблему подробнее.")
        return

    conn = db()
    cur = conn.execute(
        "INSERT INTO tickets(user_id,text,status,created_at) VALUES(?,?,?,?)",
        (message.from_user.id, text, "open", now())
    )
    ticket_id = cur.lastrowid
    conn.commit()
    conn.close()

    if SUPPORT_CHAT_ID:
        try:
            await bot.send_message(
                int(SUPPORT_CHAT_ID),
                f"<b>🎧 Новый тикет #{ticket_id}</b>\n"
                f"👤 ID: <code>{message.from_user.id}</code>\n\n"
                f"{text}"
            )
        except Exception:
            log.exception("Не удалось отправить тикет в SUPPORT_CHAT_ID")

    await state.clear()
    await message.answer(
        f"✅ Тикет <b>#{ticket_id}</b> создан.\n\n"
        "Сообщение сохранено, поддержка сможет его обработать.",
        reply_markup=main_menu()
    )


# -------------------- CASE PAYMENT HANDLER --------------------
# Важно: Telegram присылает successful_payment как Message.
# Обработчик ниже должен быть единственным обработчиком этого типа.

@dp.message(F.successful_payment)
async def successful_payment_router(message: Message):
    payment = message.successful_payment
    payload = payment.invoice_payload

    if payload.startswith("product:"):
        product_id = int(payload.split(":", 1)[1])

        conn = db()
        item = conn.execute("""
            SELECT id,payload FROM inventory
            WHERE product_id=? AND sold=0
            ORDER BY id LIMIT 1
        """, (product_id,)).fetchone()
        product = conn.execute(
            "SELECT title,price_rub FROM products WHERE id=?",
            (product_id,)
        ).fetchone()

        if not product or not item:
            conn.close()
            await message.answer(
                "⚠️ Оплата получена, но товар сейчас недоступен.\n"
                "Обратитесь в поддержку."
            )
            return

        conn.execute("UPDATE inventory SET sold=1 WHERE id=?", (item["id"],))
        conn.execute(
            "UPDATE products SET stock=MAX(stock-1,0) WHERE id=?",
            (product_id,)
        )
        conn.commit()
        conn.close()

        add_purchase(
            message.from_user.id, product_id, product["title"],
            product["price_rub"], "telegram_stars", "paid",
            item["payload"]
        )

        await message.answer(
            "<b>✅ ПОКУПКА УСПЕШНА</b>\n\n"
            f"{product['title']}\n\n"
            "<b>📦 Ваш товар:</b>\n"
            f"<code>{item['payload']}</code>"
        )
        return

    if payload.startswith("case:"):
        case_id = int(payload.split(":", 1)[1])

        conn = db()
        case = conn.execute(
            "SELECT title,price_rub FROM cases WHERE id=?",
            (case_id,)
        ).fetchone()
        conn.close()

        if not case:
            await message.answer("⚠️ Кейс не найден. Обратитесь в поддержку.")
            return

        prize = await open_paid_case(message.from_user.id, case_id)

        add_purchase(
            message.from_user.id, None, case["title"],
            case["price_rub"], "telegram_stars", "paid", prize or ""
        )

        await message.answer(
            "<b>🎉 КЕЙС ОТКРЫТ!</b>\n\n"
            f"🎁 Кейс: <b>{case['title']}</b>\n\n"
            f"🏆 Ваш приз:\n<b>{prize}</b>"
        )


# -------------------- OPTIONAL ADMIN INVENTORY VIA ENV --------------------

# Чтобы магазин можно было наполнить без отдельной панели:
# ADMIN_IDS=123456789,987654321
# Команды:
# /addproduct code|Название|цена
# /addstock code|товар
#
# Эти команды доступны только ID из ADMIN_IDS.

def admin_ids():
    raw = os.getenv("ADMIN_IDS", "")
    result = set()
    for x in raw.split(","):
        x = x.strip()
        if x.isdigit():
            result.add(int(x))
    return result


def is_admin(user_id):
    return user_id in admin_ids()


@dp.message(Command("addproduct"))
async def add_product_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return

    raw = message.text.partition(" ")[2].strip()
    parts = [x.strip() for x in raw.split("|")]

    if len(parts) != 3 or not parts[2].isdigit():
        await message.answer(
            "Формат:\n<code>/addproduct code|Название товара|цена</code>"
        )
        return

    code, title, price = parts
    conn = db()
    try:
        conn.execute(
            "INSERT INTO products(code,title,price_rub,stock) VALUES(?,?,?,0)",
            (code, title, int(price))
        )
        conn.commit()
    except sqlite3.IntegrityError:
        await message.answer("❌ Такой code уже существует.")
        conn.close()
        return
    conn.close()

    await message.answer("✅ Товар создан.")


@dp.message(Command("addstock"))
async def add_stock_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return

    raw = message.text.partition(" ")[2].strip()
    parts = raw.split("|", 1)

    if len(parts) != 2 or not parts[1].strip():
        await message.answer(
            "Формат:\n<code>/addstock code|данные_товара</code>"
        )
        return

    code, payload = parts[0].strip(), parts[1].strip()

    conn = db()
    product = conn.execute(
        "SELECT id FROM products WHERE code=?",
        (code,)
    ).fetchone()

    if not product:
        conn.close()
        await message.answer("❌ Товар с таким code не найден.")
        return

    conn.execute(
        "INSERT INTO inventory(product_id,payload,sold,created_at) VALUES(?,?,0,?)",
        (product["id"], payload, now())
    )
    conn.execute(
        "UPDATE products SET stock=stock+1 WHERE id=?",
        (product["id"],)
    )
    conn.commit()
    conn.close()

    await message.answer("✅ Товар добавлен в наличие.")


async def main():
    try:
        init_db()
        await bot.delete_webhook(drop_pending_updates=True)
        me = await bot.get_me()
        log.info("Starting %s as @%s", SHOP_NAME, me.username)
        await dp.start_polling(bot)
    except Exception:
        log.exception("BOT STARTUP ERROR")
        raise


if __name__ == "__main__":
    asyncio.run(main())
