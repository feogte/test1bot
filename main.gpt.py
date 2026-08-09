import asyncio
import logging
import sqlite3
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)

BOT_TOKEN = "8693450959:AAFfaqWBwJdbVSUwiv-Q5jQiMC76MRARIuU"

DB_PATH = "data.db"
SHOP_NAME = "Vinex Shop"

logging.basicConfig(level=logging.INFO)

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product TEXT NOT NULL,
            price TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def save_user(user):
    conn = db()
    conn.execute("""
        INSERT INTO users(user_id, username, first_name, created_at)
        VALUES(?,?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET
            username=excluded.username,
            first_name=excluded.first_name
    """, (
        user.id,
        user.username or "",
        user.first_name or "",
        datetime.now().isoformat(timespec="seconds")
    ))
    conn.commit()
    conn.close()


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


def back_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="home")]
    ])


def store_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Telegram Stars", callback_data="stars")],
        [InlineKeyboardButton(text="🛍️ Аккаунты", callback_data="accounts")],
        [InlineKeyboardButton(text="🎁 Кейсы", callback_data="cases")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="home")]
    ])


def cases_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Обычный кейс — 50 ₽", callback_data="case_50")],
        [InlineKeyboardButton(text="🔥 Premium кейс — 150 ₽", callback_data="case_150")],
        [InlineKeyboardButton(text="💎 Lucky кейс — 300 ₽", callback_data="case_300")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="home")]
    ])


def products_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇲🇲 +95 — Мьянма | 15 ₽", callback_data="product_mm")],
        [InlineKeyboardButton(text="🇷🇺 +7 — Россия | 80 ₽", callback_data="product_ru")],
        [InlineKeyboardButton(text="🇺🇦 +380 — Украина | 60 ₽", callback_data="product_ua")],
        [InlineKeyboardButton(text="🇰🇿 +7 — Казахстан | 70 ₽", callback_data="product_kz")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="store")]
    ])


@dp.message(CommandStart())
async def start(message: Message):
    save_user(message.from_user)
    await message.answer(
        f"<b>🔥 Добро пожаловать в {SHOP_NAME}!</b>\n\n"
        "Здесь всё построено проще и быстрее:\n"
        "🎁 кейсы\n"
        "🛍️ товары\n"
        "👤 профиль\n"
        "🧾 история покупок\n"
        "⭐ отзывы\n"
        "🎧 поддержка\n\n"
        "<i>Выберите раздел ниже.</i>",
        reply_markup=main_menu()
    )


@dp.callback_query(F.data == "home")
async def home(call: CallbackQuery):
    await call.message.edit_text(
        f"<b>🔥 {SHOP_NAME}</b>\n\nВыберите нужный раздел:",
        reply_markup=main_menu()
    )
    await call.answer()


@dp.callback_query(F.data == "store")
async def store(call: CallbackQuery):
    await call.message.edit_text(
        "<b>🏪 STORE</b>\n\n"
        "Выберите категорию:\n\n"
        "⭐ Stars — цифровые товары\n"
        "🛍️ Аккаунты — доступные позиции\n"
        "🎁 Кейсы — шанс получить редкий приз",
        reply_markup=store_menu()
    )
    await call.answer()


@dp.callback_query(F.data == "stars")
async def stars(call: CallbackQuery):
    await call.message.edit_text(
        "<b>⭐ TELEGRAM STARS</b>\n\n"
        "Каталог Stars пока находится в подготовке.\n"
        "Раздел уже создан и готов для подключения оплаты.",
        reply_markup=back_menu()
    )
    await call.answer()


@dp.callback_query(F.data == "accounts")
async def accounts(call: CallbackQuery):
    await call.message.edit_text(
        "<b>🛍️ АККАУНТЫ</b>\n\n"
        "Выберите страну.\n"
        "Флаг отображается непосредственно в названии товара.",
        reply_markup=products_menu()
    )
    await call.answer()


@dp.callback_query(F.data.startswith("product_"))
async def product(call: CallbackQuery):
    products = {
        "product_mm": ("🇲🇲 +95 — Мьянма", "15 ₽"),
        "product_ru": ("🇷🇺 +7 — Россия", "80 ₽"),
        "product_ua": ("🇺🇦 +380 — Украина", "60 ₽"),
        "product_kz": ("🇰🇿 +7 — Казахстан", "70 ₽"),
    }
    name, price = products.get(call.data, ("Товар", "0 ₽"))
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🛒 Купить за {price}", callback_data=f"buy:{name}:{price}")],
        [InlineKeyboardButton(text="◀️ К товарам", callback_data="accounts")]
    ])
    await call.message.edit_text(
        f"<b>{name}</b>\n\n"
        f"💰 Цена: <b>{price}</b>\n"
        "📦 Наличие: <b>есть</b>\n"
        "⚡ Выдача: после подключения оплаты\n\n"
        "<i>Это демонстрационная позиция — реальную выдачу можно подключить позже.</i>",
        reply_markup=kb
    )
    await call.answer()


@dp.callback_query(F.data.startswith("buy:"))
async def buy(call: CallbackQuery):
    _, product_name, price = call.data.split(":", 2)
    conn = db()
    conn.execute(
        "INSERT INTO purchases(user_id, product, price, created_at) VALUES(?,?,?,?)",
        (call.from_user.id, product_name, price, datetime.now().isoformat(timespec="seconds"))
    )
    conn.commit()
    conn.close()

    await call.message.edit_text(
        "<b>🛒 ЗАКАЗ СОЗДАН</b>\n\n"
        f"Товар: <b>{product_name}</b>\n"
        f"Цена: <b>{price}</b>\n\n"
        "Оплата пока не подключена, поэтому заказ сохранён как тестовая покупка.\n"
        "Когда подключим оплату и автовыдачу, здесь будет полноценная выдача товара.",
        reply_markup=back_menu()
    )
    await call.answer("Заказ создан")


@dp.callback_query(F.data == "cases")
async def cases(call: CallbackQuery):
    await call.message.edit_text(
        "<b>🎁 CASES</b>\n\n"
        "Главная новая механика магазина — кейсы.\n\n"
        "Открываешь кейс → получаешь случайный приз из набора.\n"
        "Вероятности и реальные призы можно настроить отдельно.",
        reply_markup=cases_menu()
    )
    await call.answer()


@dp.callback_query(F.data.startswith("case_"))
async def open_case(call: CallbackQuery):
    prices = {
        "case_50": "50 ₽",
        "case_150": "150 ₽",
        "case_300": "300 ₽",
    }
    price = prices[call.data]
    await call.message.edit_text(
        "<b>🎲 ОТКРЫТИЕ КЕЙСА</b>\n\n"
        f"Стоимость: <b>{price}</b>\n\n"
        "Пока это тестовый режим.\n"
        "Реальный рандомайзер, список призов, вероятности и выдачу можно подключить следующим этапом.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎲 Открыть (тест)", callback_data="case_demo")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="cases")]
        ])
    )
    await call.answer()


@dp.callback_query(F.data == "case_demo")
async def case_demo(call: CallbackQuery):
    await call.message.edit_text(
        "<b>✨ КЕЙС ОТКРЫТ!</b>\n\n"
        "🎉 Тестовый приз: <b>BONUS DROP</b>\n\n"
        "В полноценной версии сюда подключается таблица призов и автоматическая выдача.",
        reply_markup=back_menu()
    )
    await call.answer("Кейс открыт!")


@dp.callback_query(F.data == "profile")
async def profile(call: CallbackQuery):
    conn = db()
    user = conn.execute("SELECT * FROM users WHERE user_id=?", (call.from_user.id,)).fetchone()
    count = conn.execute("SELECT COUNT(*) AS c FROM purchases WHERE user_id=?", (call.from_user.id,)).fetchone()["c"]
    conn.close()

    username = f"@{user['username']}" if user and user["username"] else "не указан"
    await call.message.edit_text(
        "<b>👤 ПРОФИЛЬ</b>\n\n"
        f"🆔 ID: <code>{call.from_user.id}</code>\n"
        f"👤 Username: {username}\n"
        f"🧾 Покупок: <b>{count}</b>\n"
        "💰 Баланс: <b>0 ₽</b>\n\n"
        "<i>Баланс можно подключить позже.</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🧾 История покупок", callback_data="purchases")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="home")]
        ])
    )
    await call.answer()


@dp.callback_query(F.data == "purchases")
async def purchases(call: CallbackQuery):
    conn = db()
    rows = conn.execute(
        "SELECT product, price, created_at FROM purchases WHERE user_id=? ORDER BY id DESC LIMIT 10",
        (call.from_user.id,)
    ).fetchall()
    conn.close()

    if not rows:
        text = "<b>🧾 ИСТОРИЯ ПОКУПОК</b>\n\nПокупок пока нет."
    else:
        lines = ["<b>🧾 ИСТОРИЯ ПОКУПОК</b>\n"]
        for i, row in enumerate(rows, 1):
            date = row["created_at"].replace("T", " ")
            lines.append(f"{i}. {row['product']} — <b>{row['price']}</b>\n   {date}")
        text = "\n".join(lines)

    await call.message.edit_text(text, reply_markup=back_menu())
    await call.answer()


@dp.callback_query(F.data == "reviews")
async def reviews(call: CallbackQuery):
    await call.message.edit_text(
        "<b>⭐ ОТЗЫВЫ</b>\n\n"
        "Здесь будет лента отзывов покупателей.\n\n"
        "Можно добавить:\n"
        "⭐ оценку\n"
        "💬 текст\n"
        "🕐 дату\n"
        "🛒 купленный товар",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Оставить отзыв", callback_data="review_add")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="home")]
        ])
    )
    await call.answer()


@dp.callback_query(F.data == "review_add")
async def review_add(call: CallbackQuery):
    await call.message.edit_text(
        "<b>✍️ ОТЗЫВ</b>\n\n"
        "Форма отзывов будет подключена следующим этапом.\n"
        "Сейчас бот работает без сложной админской части.",
        reply_markup=back_menu()
    )
    await call.answer()


@dp.callback_query(F.data == "support")
async def support(call: CallbackQuery):
    await call.message.edit_text(
        "<b>🎧 ПОДДЕРЖКА</b>\n\n"
        "Если возникла проблема с заказом — напишите в поддержку.\n\n"
        "👨‍💻 Контакт поддержки: <i>указать позже</i>\n\n"
        "При подключении можно сделать тикеты прямо внутри бота.",
        reply_markup=back_menu()
    )
    await call.answer()


async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
