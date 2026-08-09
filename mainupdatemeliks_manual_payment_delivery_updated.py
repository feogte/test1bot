"""
Telegram-магазин — обновление 3.1 в одном файле.
Python 3.11+
aiogram 3.x
SQLite

Установка:
    python -m pip install -U aiogram tzdata

Запуск:
    1. Переименуйте файл в main.py (необязательно, но удобно).
    2. Заполните блок НАСТРОЙКИ ниже.
    3. Запустите: python main.py

Важно:
- Автовыдачи нет.
- Автоматической проверки оплаты нет.
- Оплата внутри бота не используется.
- При оплате рублями бот показывает номер телефона для перевода через Т-Банк / СБП.
- Оплата товара может проходить рублями через Т-Банк, вручную Stars владельцу,
  а также вручную USDT или GRAM, если для товара указана соответствующая цена.
- Раздел «Купить Stars» работает как отдельный склад: у пакета задаются количество Stars
  в одном заказе, цена в рублях, общий остаток Stars и способ выдачи.
- Stars можно выдавать подарком или вручную на аккаунт покупателя.
- После оплаты покупатель отправляет в бота чек или скрин подтверждения.
- Заявка с прикреплённым скрином приходит владельцу в личные сообщения через бота.
- После нажатия владельцем «Выдать» заказ подтверждается, остаток уменьшается,
  покупатель получает уведомление, а заказ сохраняется в статистику.
- Заказы ни в какие каналы не публикуются.
- Склад открывается постранично и объединяет аккаунты, Premium и оба вида Stars.
- Есть автоматические временные блокировки пользователей и переключатель наличия «Крипта».
"""

from __future__ import annotations

import asyncio
import html
import logging
import math
import re
import sqlite3
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder


# ==========================================================
# НАСТРОЙКИ — ЗАПОЛНИТЕ ПЕРЕД ЗАПУСКОМ
# ==========================================================

BOT_TOKEN = "8882402552:AAF6QVAmtMqGN0SpF_suLVKcuGl349AAd38"

# Telegram ID владельца. Узнать можно через @userinfobot.
OWNER_ID = 8872934046

# Заявки на выдачу бот отправляет только владельцу в личные сообщения.
# Владелец должен хотя бы один раз открыть бота и нажать /start.

# Ссылка на канал с отзывами.
REVIEWS_CHANNEL_URL = "https://t.me/repacrisov"

# Username администратора без @. Кнопка поддержки откроет личный чат.
SUPPORT_USERNAME = "vinexsupp"

# Ручная оплата рублями переводом по номеру телефона через Т-Банк / СБП.
# Впишите номер телефона, который дал клиент, и имя получателя.
# Номер карты нигде не используется.
T_BANK_PHONE = "+79313716777"
T_BANK_RECIPIENT = "Тимур/Наталья"
T_BANK_NAME = "Т-Банк"

# Ручная оплата криптовалютой. Автоматической проверки платежей нет.
# Укажите сеть и адрес USDT, а также адрес/username для GRAM.
USDT_NETWORK = "TON"
USDT_WALLET = "UQCeC3VIuW66xUH3wOD1_RtgKjkiGEDzAC1DPhHmK9iSPLnv"
GRAM_WALLET = "UQCeC3VIuW66xUH3wOD1_RtgKjkiGEDzAC1DPhHmK9iSPLnv"
# Необязательный комментарий/мемо. Оставьте пустую строку, если он не нужен.
CRYPTO_PAYMENT_COMMENT = ""

# Username владельца без @. Сюда покупатель перейдёт для ручной передачи Stars.
STARS_RECEIVER_USERNAME = "fegote"

# Часовой пояс для дат и статистики «за сегодня».
TIMEZONE_NAME = "Europe/Riga"

# Путь к базе данных.
DB_PATH = Path(__file__).with_name("shop_bot.sqlite3")

# Обязательная подписка при первом входе.
SUBSCRIPTION_CHANNEL_ID = -1004372552910
# Для публичного канала можно вписать https://t.me/username. Для приватного — пригласительную ссылку.
# Если оставить пустым, бот попробует получить username/invite_link канала автоматически.
SUBSCRIPTION_CHANNEL_URL = "https://t.me/vinex_shop"


# Автоматические блокировки.
# /ban @username причина — бан на 24 часа.
# /ban @username 7d причина — бан на 7 дней.
# /ban @username forever причина — постоянный бан.
DEFAULT_BAN_HOURS = 24
AUTO_UNBAN_CHECK_SECONDS = 60
BAN_SUPPORT_USERNAME = "vinexsupp"

# Комиссии при пополнении внутреннего рублёвого баланса.
# Рубли: комиссия 5% -> зачисляется 95%.
# Stars: комиссия 20% -> зачисляется 80% от отправленного количества.
RUB_TOPUP_CREDIT_PERCENT = 95
STARS_TOPUP_CREDIT_PERCENT = 80

# ==========================================================
# ФОТОГРАФИИ ДЛЯ ПОЛЬЗОВАТЕЛЬСКИХ СООБЩЕНИЙ
# ==========================================================
#
# Вставляйте сюда настоящий Telegram file_id, который выдаёт команда /photoid.
# Пример: MENU_IMAGE = "AgACAgIAAxkBAA..."
# Пустая строка означает, что для этого экрана изображение пока не задано.
# Админ-панель намеренно работает без изображений.

GENERAL_IMAGE = ""              # Любой пользовательский текст без отдельной картинки
MENU_IMAGE = ""                 # /start и главное меню
STORE_IMAGE = ""                # Экран Store
BALANCE_IMAGE = ""              # Баланс пользователя
BALANCE_HISTORY_IMAGE = ""      # История пополнений и списаний
TOPUP_METHODS_IMAGE = ""        # Выбор способа пополнения
TOPUP_RECEIPT_IMAGE = ""        # Просьба прислать чек пополнения
TOPUP_PENDING_IMAGE = ""        # Пополнение отправлено на проверку
TOPUP_APPROVED_IMAGE = ""       # Пополнение подтверждено
TOPUP_CANCELLED_IMAGE = ""      # Пополнение отклонено
SUBSCRIPTION_IMAGE = ""         # Требование подписаться
BLOCKED_IMAGE = ""              # Сообщение о блокировке
ACCOUNTS_IMAGE = ""             # Каталог аккаунтов
ACCOUNT_PRODUCT_IMAGE = ""      # Карточка аккаунта/товара
STARS_IMAGE = ""                # Главный раздел Stars
STARS_METHOD_IMAGE = ""         # Выбор: на аккаунт / подарком
STARS_GIFT_IMAGE = ""           # Stars подарком
STARS_ACCOUNT_IMAGE = ""        # Stars на аккаунт
STARS_AMOUNT_IMAGE = ""         # Ввод количества Stars
STARS_RUBLES_IMAGE = ""         # Оплата Stars рублями
PREMIUM_IMAGE = ""              # Раздел Telegram Premium
TARIFF_IMAGE = ""               # Выбор тарифа Premium
PROMO_IMAGE = ""                # Ввод/применение промокода
PAYMENT_METHODS_IMAGE = ""      # Выбор способа оплаты
PAYMENT_TBANK_IMAGE = ""        # Реквизиты Т-Банка
PAYMENT_STARS_IMAGE = ""        # Ручная оплата Telegram Stars
PAYMENT_USDT_IMAGE = ""         # Оплата USDT
PAYMENT_GRAM_IMAGE = ""         # Оплата GRAM
RECEIPT_REQUEST_IMAGE = ""      # Просьба отправить чек
RECEIPT_SENT_IMAGE = ""         # Чек отправлен администратору
ORDER_PENDING_IMAGE = ""        # Заказ ожидает решения
ORDER_CONFIRMED_IMAGE = ""      # Заказ подтверждён
ORDER_CANCELLED_IMAGE = ""      # Заказ отменён
OUT_OF_STOCK_IMAGE = ""         # Нет в наличии
REVIEWS_IMAGE = ""              # Отзывы
SUPPORT_IMAGE = ""              # Поддержка
MY_ORDERS_IMAGE = ""            # История заказов пользователя
ERROR_IMAGE = ""                # Ошибки ввода и неизвестные команды

PHOTO_SLOT_NAMES = (
    "GENERAL_IMAGE", "MENU_IMAGE", "STORE_IMAGE", "BALANCE_IMAGE", "BALANCE_HISTORY_IMAGE",
    "TOPUP_METHODS_IMAGE", "TOPUP_RECEIPT_IMAGE", "TOPUP_PENDING_IMAGE",
    "TOPUP_APPROVED_IMAGE", "TOPUP_CANCELLED_IMAGE",
    "SUBSCRIPTION_IMAGE", "BLOCKED_IMAGE",
    "ACCOUNTS_IMAGE", "ACCOUNT_PRODUCT_IMAGE", "STARS_IMAGE",
    "STARS_METHOD_IMAGE", "STARS_GIFT_IMAGE", "STARS_ACCOUNT_IMAGE",
    "STARS_AMOUNT_IMAGE", "STARS_RUBLES_IMAGE", "PREMIUM_IMAGE",
    "TARIFF_IMAGE", "PROMO_IMAGE", "PAYMENT_METHODS_IMAGE",
    "PAYMENT_TBANK_IMAGE", "PAYMENT_STARS_IMAGE", "PAYMENT_USDT_IMAGE",
    "PAYMENT_GRAM_IMAGE", "RECEIPT_REQUEST_IMAGE",
    "RECEIPT_SENT_IMAGE", "ORDER_PENDING_IMAGE", "ORDER_CONFIRMED_IMAGE",
    "ORDER_CANCELLED_IMAGE", "OUT_OF_STOCK_IMAGE", "REVIEWS_IMAGE",
    "SUPPORT_IMAGE", "MY_ORDERS_IMAGE", "ERROR_IMAGE",
)

# Сколько товаров показывать на одной странице склада.
# Пагинация защищает меню от лимитов Telegram по длине сообщения и числу кнопок.
STOCK_PAGE_SIZE = 8

# Разрешённые количества Stars для ручного ввода. Список можно дополнять без изменения логики.
ALLOWED_GIFT_STAR_AMOUNTS = (
    15, 25, 30, 40, 45, 50, 65, 75, 80, 100,
    150, 200, 215, 220, 250, 300, 350, 400, 500, 750, 1000,
)

# Примерные аккаунты при первом запуске.
# Stars добавляются владельцем командой:
# /newstars 100 | 150₽/1.8usdt/1.2gram | подарком
# После запуска цену и количество можно менять через /admin.
SEED_PRODUCTS = [
    # category, code, name, price_rub, price_stars, stock, visible
    ("accounts", "ru", "🇷🇺 Россия", 60, 60, 48, 1),
    ("accounts", "kz", "🇰🇿 Казахстан", 60, 60, 16, 1),
    ("accounts", "ua", "🇺🇦 Украина", 60, 60, 5, 1),
]


# ==========================================================
# ОБЩИЕ НАСТРОЙКИ
# ==========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("shop_bot")

TZ = ZoneInfo(TIMEZONE_NAME)
router = Router()

CATEGORY_TITLES = {
    "accounts": "🛒 Купить аккаунты",
    "stars": "⭐ Купить Stars",
    "premium": "💎 Купить Premium",
}

ORDER_STATUS_LABELS = {
    "pending": "⏳ Ожидает решения",
    "approved": "✅ Выдан",
    "cancelled": "❌ Отменён",
}

PAYMENT_METHOD_LABELS = {
    "card": "💳 Оплата рублями",
    "stars": "⭐ Оплата Telegram Stars",
}

BALANCE_CURRENCY_LABELS = {
    "rub": "₽ Рубли",
    "stars": "⭐ Stars",
    "usdt": "💵 USDT",
    "gram": "🪙 GRAM",
}

STAR_DELIVERY_LABELS = {
    "gift": "🎁 Подарком",
    "account": "👤 На аккаунт",
    "standard": "—",
}

PROMO_CATEGORY_LABELS = {
    "all": "Все",
    "stars": "Звезды",
    "accounts": "Аккаунты",
    "premium": "Premium",
}

SECTION_IMAGES = {
    "menu": MENU_IMAGE,
    "store": STORE_IMAGE,
    "balance": BALANCE_IMAGE,
    "balance_history": BALANCE_HISTORY_IMAGE,
    "accounts": ACCOUNTS_IMAGE,
    "stars": STARS_IMAGE,
    "premium": PREMIUM_IMAGE,
    "admin": "",
    "reviews": REVIEWS_IMAGE,
    "support": SUPPORT_IMAGE,
}

FLOW_IMAGES = {
    "topup_methods": TOPUP_METHODS_IMAGE,
    "topup_receipt": TOPUP_RECEIPT_IMAGE,
    "topup_pending": TOPUP_PENDING_IMAGE,
    "topup_approved": TOPUP_APPROVED_IMAGE,
    "topup_cancelled": TOPUP_CANCELLED_IMAGE,
    "promo": PROMO_IMAGE,
    "payment_methods": PAYMENT_METHODS_IMAGE,
    "payment_tbank": PAYMENT_TBANK_IMAGE,
    "payment_stars": PAYMENT_STARS_IMAGE,
    "payment_usdt": PAYMENT_USDT_IMAGE,
    "payment_gram": PAYMENT_GRAM_IMAGE,
    "receipt_request": RECEIPT_REQUEST_IMAGE,
    "receipt_sent": RECEIPT_SENT_IMAGE,
    "order_pending": ORDER_PENDING_IMAGE,
    "order_cancelled": ORDER_CANCELLED_IMAGE,
    "order_confirmed": ORDER_CONFIRMED_IMAGE,
    "out_of_stock": OUT_OF_STOCK_IMAGE,
    "stars_method": STARS_METHOD_IMAGE,
    "stars_gift": STARS_GIFT_IMAGE,
    "stars_account": STARS_ACCOUNT_IMAGE,
    "tariff": TARIFF_IMAGE,
    "stars_amount": STARS_AMOUNT_IMAGE,
    "stars_rubles": STARS_RUBLES_IMAGE,
    "my_orders": MY_ORDERS_IMAGE,
    "error": ERROR_IMAGE,
}


def _plain_text(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value or "").lower().replace("ё", "е")


def is_admin_panel_text(chat_id: int, text: str) -> bool:
    """Админ-панель и служебные ответы владельцу остаются без картинок."""
    if chat_id != OWNER_ID:
        return False
    value = _plain_text(text)
    markers = (
        "админ-панель", "склад и товары", "управление товаром",
        "статистика магазина", "история заказов", "рассылка",
        "управление промокодами", "заблокированные пользователи",
        "режим крипта", "товар добавлен", "остаток изменен",
        "цена изменена", "название изменено", "товар удален",
        "использование: /", "команды владельца", "владельца бота",
    )
    return any(marker in value for marker in markers)


def is_admin_reply_markup(reply_markup: Any) -> bool:
    """Определяет кнопки админ-панели по callback_data."""
    if not isinstance(reply_markup, InlineKeyboardMarkup):
        return False
    for row in reply_markup.inline_keyboard:
        for button in row:
            callback_data = button.callback_data or ""
            if callback_data.startswith(("admin:", "stock:", "promo_admin:", "broadcast:")):
                return True
    return False


def image_for_user_text(chat_id: int, text: str) -> str:
    """Выбирает фото для любого пользовательского текста; админка исключена."""
    if is_admin_panel_text(chat_id, text):
        return ""

    value = _plain_text(text)
    if "заблокирован" in value or "блокировка" in value:
        return BLOCKED_IMAGE or ERROR_IMAGE or GENERAL_IMAGE
    if "подпис" in value and ("канал" in value or "доступ" in value):
        return SUBSCRIPTION_IMAGE or GENERAL_IMAGE
    if "нет в наличии" in value or "товар закончился" in value:
        return OUT_OF_STOCK_IMAGE or ERROR_IMAGE or GENERAL_IMAGE
    if "заказ отмен" in value or "оплата не подтверждена" in value:
        return ORDER_CANCELLED_IMAGE or GENERAL_IMAGE
    if "заказ подтвержден" in value or "заказ выдан" in value:
        return ORDER_CONFIRMED_IMAGE or GENERAL_IMAGE
    if "ожидает" in value and ("заказ" in value or "провер" in value):
        return ORDER_PENDING_IMAGE or GENERAL_IMAGE
    if "чек отправлен" in value or "отправлен администратору" in value:
        return RECEIPT_SENT_IMAGE or GENERAL_IMAGE
    if "отправьте чек" in value or "пришлите чек" in value or "скрин оплаты" in value:
        return RECEIPT_REQUEST_IMAGE or GENERAL_IMAGE
    if "выберите способ оплаты" in value or "способ оплаты" in value:
        return PAYMENT_METHODS_IMAGE or GENERAL_IMAGE
    if "т-банк" in value or "номер телефона" in value or "сбп" in value:
        return PAYMENT_TBANK_IMAGE or PAYMENT_METHODS_IMAGE or GENERAL_IMAGE
    if "оплата telegram stars" in value or "передать stars" in value:
        return PAYMENT_STARS_IMAGE or PAYMENT_METHODS_IMAGE or GENERAL_IMAGE
    if "пополн" in value and "баланс" in value:
        if "подтвержден" in value or "зачислен" in value:
            return TOPUP_APPROVED_IMAGE or BALANCE_IMAGE or GENERAL_IMAGE
        if "отклон" in value or "отмен" in value:
            return TOPUP_CANCELLED_IMAGE or BALANCE_IMAGE or GENERAL_IMAGE
        if "провер" in value or "заявк" in value:
            return TOPUP_PENDING_IMAGE or BALANCE_IMAGE or GENERAL_IMAGE
        if "чек" in value or "скрин" in value:
            return TOPUP_RECEIPT_IMAGE or BALANCE_IMAGE or GENERAL_IMAGE
        return TOPUP_METHODS_IMAGE or BALANCE_IMAGE or GENERAL_IMAGE
    if "история баланса" in value or "движение средств" in value:
        return BALANCE_HISTORY_IMAGE or BALANCE_IMAGE or GENERAL_IMAGE
    if "ваш баланс" in value or "баланс:" in value:
        return BALANCE_IMAGE or GENERAL_IMAGE
    if "store" in value or "магазин" in value and "выберите" in value:
        return STORE_IMAGE or MENU_IMAGE or GENERAL_IMAGE
    if "usdt" in value:
        return PAYMENT_USDT_IMAGE or PAYMENT_METHODS_IMAGE or GENERAL_IMAGE
    if "gram" in value:
        return PAYMENT_GRAM_IMAGE or PAYMENT_METHODS_IMAGE or GENERAL_IMAGE
    if "промокод" in value:
        return PROMO_IMAGE or GENERAL_IMAGE
    if "отзыв" in value:
        return REVIEWS_IMAGE or GENERAL_IMAGE
    if "поддерж" in value:
        return SUPPORT_IMAGE or GENERAL_IMAGE
    if "мои заказы" in value or "ваши заказы" in value or "история покупок" in value:
        return MY_ORDERS_IMAGE or GENERAL_IMAGE
    if "выберите тариф" in value or "3 месяца" in value or "6 месяцев" in value or "1 год" in value:
        return TARIFF_IMAGE or PREMIUM_IMAGE or GENERAL_IMAGE
    if "premium" in value or "премиум" in value:
        return PREMIUM_IMAGE or GENERAL_IMAGE
    if "способ получения звезд" in value or ("на аккаунт" in value and "подар" in value):
        return STARS_METHOD_IMAGE or STARS_IMAGE or GENERAL_IMAGE
    if "введите количество" in value and ("star" in value or "звезд" in value):
        return STARS_AMOUNT_IMAGE or STARS_IMAGE or GENERAL_IMAGE
    if "stars на аккаунт" in value or "звезды на аккаунт" in value:
        return STARS_ACCOUNT_IMAGE or STARS_IMAGE or GENERAL_IMAGE
    if "подарком" in value and ("star" in value or "звезд" in value):
        return STARS_GIFT_IMAGE or STARS_IMAGE or GENERAL_IMAGE
    if "star" in value or "звезд" in value:
        return STARS_IMAGE or GENERAL_IMAGE
    if "аккаунт" in value or "товар" in value:
        return ACCOUNT_PRODUCT_IMAGE or ACCOUNTS_IMAGE or GENERAL_IMAGE
    if "добро пожаловать" in value or "главное меню" in value or "выберите раздел" in value:
        return MENU_IMAGE or GENERAL_IMAGE
    if any(word in value for word in ("ошибка", "невер", "нельзя", "укажите", "введите", "не найден")):
        return ERROR_IMAGE or GENERAL_IMAGE
    return GENERAL_IMAGE


PREMIUM_TARIFF_NAMES = {
    3: "Telegram Premium — 3 месяца",
    6: "Telegram Premium — 6 месяцев",
    12: "Telegram Premium — 1 год",
}


# ==========================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================================


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def safe_edit_text(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> bool:
    """Безопасно обновляет сообщение без создания дубликата."""
    admin_output = is_admin_panel_text(message.chat.id, text) or is_admin_reply_markup(reply_markup)
    if not admin_output:
        await render_user_screen(
            message,
            image_for_user_text(message.chat.id, text),
            text,
            reply_markup=reply_markup,
        )
        return True

    try:
        await message.edit_text(text, reply_markup=reply_markup)
        return True
    except TelegramBadRequest as error:
        if "message is not modified" in str(error).lower():
            return False
        raise


def local_now() -> datetime:
    return datetime.now(TZ)


def today_utc_bounds() -> tuple[str, str]:
    current_date = local_now().date()
    start_local = datetime.combine(current_date, time.min, tzinfo=TZ)
    end_local = datetime.combine(current_date, time.max, tzinfo=TZ)
    return (
        start_local.astimezone(timezone.utc).isoformat(timespec="seconds"),
        end_local.astimezone(timezone.utc).isoformat(timespec="seconds"),
    )


def format_datetime(value: str | None) -> str:
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(TZ).strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return value


def money(value: int) -> str:
    return f"{int(value):,}".replace(",", " ") + " ₽"


def stars(value: int) -> str:
    return f"{int(value):,}".replace(",", " ") + " ⭐"


def decimal_amount(value: Any) -> Decimal:
    try:
        result = Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")
    return result if result >= 0 else Decimal("0")


def decimal_text(value: Any) -> str:
    amount = decimal_amount(value)
    text = format(amount.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def usdt(value: Any) -> str:
    return f"{decimal_text(value)} USDT"


def gram(value: Any) -> str:
    return f"{decimal_text(value)} GRAM"


def row_value(row: sqlite3.Row, key: str, default: Any = 0) -> Any:
    try:
        return row[key] if key in row.keys() else default
    except (KeyError, TypeError, AttributeError):
        return default


def format_prices(
    price_rub: int,
    price_stars: int,
    price_usdt: Any = "0",
    price_gram: Any = "0",
) -> str:
    parts: list[str] = []
    if price_rub > 0:
        parts.append(money(price_rub))
    if price_stars > 0:
        parts.append(stars(price_stars))
    if decimal_amount(price_usdt) > 0:
        parts.append(usdt(price_usdt))
    if decimal_amount(price_gram) > 0:
        parts.append(gram(price_gram))
    return " / ".join(parts) if parts else "Бесплатно"


def product_prices(product: sqlite3.Row) -> str:
    return format_prices(
        int(product["price_rub"]),
        int(product["price_stars"]),
    )


def order_amount(order: sqlite3.Row) -> str:
    method = str(order["payment_method"])
    if method in {"stars", "balance_stars"}:
        return stars(int(order["final_price_stars"]))
    if method in {"usdt", "balance_usdt"}:
        return usdt(row_value(order, "final_price_usdt", "0"))
    if method in {"gram", "balance_gram"}:
        return gram(row_value(order, "final_price_gram", "0"))
    return money(int(order["final_price_rub"]))


def format_user_balance(row: sqlite3.Row | None) -> str:
    # Пользовательский баланс Vinex Shop теперь только в рублях.
    if not row:
        return "0 ₽"
    return money(int(row_value(row, "balance_rub", 0)))


def rub_topup_credit_rub(amount: Any) -> int:
    """Сколько рублей зачислить при пополнении рублями с комиссией 5%."""
    rub_sent = int(decimal_amount(amount))
    return max(0, rub_sent * RUB_TOPUP_CREDIT_PERCENT // 100)


def stars_topup_credit_rub(amount: Any) -> int:
    """Сколько рублей зачислить за пополнение Stars с комиссией 20%."""
    stars_sent = int(decimal_amount(amount))
    return max(0, stars_sent * STARS_TOPUP_CREDIT_PERCENT // 100)


def balance_payment_currency(method: str) -> str | None:
    return {
        "balance_rub": "rub",
        "balance_stars": "stars",
        "balance_usdt": "usdt",
        "balance_gram": "gram",
    }.get(method)


def parse_topup_amount(currency: str, value: str) -> str | None:
    normalized = (value or "").strip().replace(",", ".")
    match = re.search(r"\d+(?:\.\d+)?", normalized)
    if not match:
        return None
    raw = match.group(0)
    try:
        if currency in {"rub", "stars"}:
            if "." in raw:
                return None
            amount = int(raw)
            return str(amount) if amount > 0 else None
        amount_dec = Decimal(raw)
        return decimal_text(amount_dec) if amount_dec > 0 else None
    except (ValueError, InvalidOperation):
        return None


def parse_prices(value: str) -> tuple[int, int, str, str] | None:
    """
    Понимает форматы:
    100₽
    100₽/100звезд
    50₽/60звезд/0.65usdt/0.45gram

    Рубли и Stars должны быть целыми, USDT и GRAM могут быть дробными.
    """
    normalized = value.strip().lower().replace("ё", "е").replace(",", ".")
    if not normalized:
        return None
    parts = [part.strip() for part in normalized.split("/")]
    if not 1 <= len(parts) <= 4:
        return None

    rub = 0
    star_price = 0
    usdt_price = Decimal("0")
    gram_price = Decimal("0")
    positional = ["rub", "stars", "usdt", "gram"]

    for index, part in enumerate(parts):
        if not part or re.search(r"-\s*\d", part):
            return None
        if "usdt" in part:
            kind = "usdt"
        elif "gram" in part:
            kind = "gram"
        elif "звезд" in part or "star" in part or "⭐" in part:
            kind = "stars"
        elif "₽" in part or "руб" in part:
            kind = "rub"
        else:
            kind = positional[index]

        number_match = re.search(r"\d+(?:\.\d+)?", part)
        if not number_match:
            return None
        number_text = number_match.group(0)

        try:
            if kind in {"rub", "stars"}:
                if "." in number_text:
                    return None
                number = int(number_text)
                if number < 0:
                    return None
                if kind == "rub":
                    rub = number
                else:
                    star_price = number
            elif kind == "usdt":
                usdt_price = Decimal(number_text)
                if usdt_price < 0:
                    return None
            else:
                gram_price = Decimal(number_text)
                if gram_price < 0:
                    return None
        except (ValueError, InvalidOperation):
            return None

    return rub, star_price, decimal_text(usdt_price), decimal_text(gram_price)


def parse_quantity(value: str) -> int | None:
    match = re.fullmatch(r"\s*(\d+)\s*(?:шт\.?|штук[аи]?)?\s*", value.lower())
    return int(match.group(1)) if match else None


def parse_quick_product_line(value: str) -> tuple[str, int, int, str, str, int] | None:
    parts = [part.strip() for part in value.split("|")]
    if len(parts) != 3 or not parts[0] or len(parts[0]) > 100:
        return None
    parsed_prices = parse_prices(parts[1])
    stock = parse_quantity(parts[2])
    if parsed_prices is None or stock is None:
        return None
    price_rub, price_stars, price_usdt, price_gram = parsed_prices
    return parts[0], price_rub, price_stars, price_usdt, price_gram, stock


def normalize_star_delivery(value: str) -> str | None:
    normalized = value.strip().lower().replace("ё", "е")
    normalized = re.sub(r"\s+", " ", normalized)
    if normalized in {"подарком", "подарок", "gift", "через подарок"}:
        return "gift"
    if normalized in {"на аккаунт", "аккаунт", "fragment", "через fragment", "на акк"}:
        return "account"
    return None


def parse_star_amount(value: str) -> int | None:
    normalized = value.strip().lower().replace("ё", "е")
    match = re.fullmatch(r"\s*(\d+)\s*(?:⭐|stars?|звезд[аы]?|звезд|шт\.?)?\s*", normalized)
    if not match:
        return None
    amount = int(match.group(1))
    return amount if amount > 0 else None


def parse_stars_product_line(value: str) -> tuple[int, int, int, str, str, int, str] | None:
    """
    Короткий формат: 100 | 150₽/1.8usdt/1.2gram | подарком.
    Расширенный формат: 100 | 150₽/1.8usdt/1.2gram | 1000 | подарком,
    где 100 — размер заказа, а 1000 — общий остаток Stars.
    """
    parts = [part.strip() for part in value.split("|")]
    if len(parts) == 3:
        package_amount = parse_star_amount(parts[0])
        prices = parse_prices(parts[1])
        stock = package_amount
        delivery_method = normalize_star_delivery(parts[2])
    elif len(parts) == 4:
        package_amount = parse_star_amount(parts[0])
        prices = parse_prices(parts[1])
        stock = parse_star_amount(parts[2])
        delivery_method = normalize_star_delivery(parts[3])
    else:
        return None
    if package_amount is None or prices is None or stock is None or delivery_method is None:
        return None
    price_rub, price_stars, price_usdt, price_gram = prices
    has_price = (
        price_rub > 0
        or price_stars > 0
        or decimal_amount(price_usdt) > 0
        or decimal_amount(price_gram) > 0
    )
    if not has_price or stock < package_amount:
        return None
    return package_amount, price_rub, price_stars, price_usdt, price_gram, stock, delivery_method


def product_unit_amount(product: sqlite3.Row) -> int:
    try:
        return max(1, int(product["unit_amount"]))
    except (IndexError, KeyError, TypeError, ValueError):
        return 1


def product_available(product: sqlite3.Row) -> int:
    return max(0, int(product["available"]))


def product_can_buy(product: sqlite3.Row) -> bool:
    has_price = (
        int(product["price_rub"]) > 0
        or int(product["price_stars"]) > 0
        or decimal_amount(row_value(product, "price_usdt", "0")) > 0
        or decimal_amount(row_value(product, "price_gram", "0")) > 0
    )
    return has_price and product_available(product) >= product_unit_amount(product)


def delivery_label(value: str | None) -> str:
    return STAR_DELIVERY_LABELS.get(value or "standard", html.escape(value or "—"))


def stock_label(product: sqlite3.Row, value: int | None = None) -> str:
    amount = product_available(product) if value is None else max(0, int(value))
    if product["category"] == "stars":
        return stars(amount)
    return f"{amount} шт."


def safe_username(username: str | None, user_id: int) -> str:
    if username:
        return f"@{html.escape(username)}"
    return f"<code>{user_id}</code>"


def valid_tme_url(url: str) -> bool:
    return bool(re.fullmatch(r"https://t\.me/[A-Za-z0-9_+\-/]+", url.strip()))


def category_title(category: str) -> str:
    return CATEGORY_TITLES.get(category, f"📁 {html.escape(category)}")


def normalize_promo_category(value: str) -> str | None:
    normalized = value.strip().lower().replace("ё", "е")
    aliases = {
        "все": "all", "all": "all",
        "звезды": "stars", "звезда": "stars", "stars": "stars",
        "аккаунты": "accounts", "аккаунт": "accounts", "accounts": "accounts",
        "premium": "premium", "премиум": "premium",
    }
    return aliases.get(normalized)


def is_allowed_gift_star_amount(amount: int) -> bool:
    return amount >= 15 and amount in ALLOWED_GIFT_STAR_AMOUNTS


def parse_ban_duration_token(value: str) -> timedelta | None:
    normalized = value.strip().lower().replace(" ", "")
    if normalized in {"forever", "permanent", "навсегда", "постоянно"}:
        return None
    match = re.fullmatch(r"(\d+)(m|h|d|w)", normalized)
    if not match:
        raise ValueError("Неверный срок")
    number = int(match.group(1))
    if number <= 0:
        raise ValueError("Срок должен быть больше нуля")
    unit = match.group(2)
    if unit == "m":
        return timedelta(minutes=number)
    if unit == "h":
        return timedelta(hours=number)
    if unit == "d":
        return timedelta(days=number)
    return timedelta(weeks=number)


def image_source(value: str) -> str:
    """Возвращает Telegram file_id или HTTPS-ссылку изображения."""
    return (value or "").strip()


# Последнее пользовательское экранное сообщение бота в каждом чате.
# После /start бот всегда отправляет НОВОЕ сообщение. Дальнейшие пользовательские
# переходы стараются редактировать это сообщение вместо удаления/создания новых.
LAST_USER_SCREEN_MESSAGE_ID: dict[int, int] = {}
LAST_USER_SCREEN_IS_PHOTO: dict[int, bool] = {}


def _can_edit_with_markup(reply_markup: Any) -> bool:
    """Редактирование Telegram-сообщения поддерживает только inline-клавиатуру."""
    return reply_markup is None or isinstance(reply_markup, InlineKeyboardMarkup)


async def _remember_user_screen(message: Message) -> Message:
    LAST_USER_SCREEN_MESSAGE_ID[message.chat.id] = message.message_id
    LAST_USER_SCREEN_IS_PHOTO[message.chat.id] = bool(message.photo)
    return message


async def _delete_previous_user_screen(chat_id: int, except_message_id: int | None = None) -> None:
    """Совместимость со старым кодом: пользовательские сообщения больше не удаляются."""
    return None


async def _edit_known_user_screen(
    chat_id: int,
    message_id: int,
    was_photo: bool,
    image: str,
    text: str,
    reply_markup: Any = None,
    **kwargs: Any,
) -> Message | None:
    """Редактирует уже показанный пользовательский экран без удаления сообщения."""
    clean_image = image_source(image)
    editable_markup = reply_markup if _can_edit_with_markup(reply_markup) else None
    try:
        if was_photo:
            # Фото-сообщение оставляем фото-сообщением. Если для нового экрана есть
            # file_id и подпись помещается в лимит Telegram — меняем и картинку.
            if clean_image and len(text) <= 1024:
                edited = await bot.edit_message_media(
                    chat_id=chat_id,
                    message_id=message_id,
                    media=InputMediaPhoto(media=clean_image, caption=text, parse_mode=ParseMode.HTML),
                    reply_markup=editable_markup,
                )
            elif len(text) <= 1024:
                edited = await bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=message_id,
                    caption=text,
                    reply_markup=editable_markup,
                    parse_mode=ParseMode.HTML,
                )
            else:
                # Нельзя превратить фото в длинное текстовое сообщение без удаления.
                # В этом редком случае сохраняем старое сообщение и создаём новое.
                LAST_USER_SCREEN_MESSAGE_ID.pop(chat_id, None)
                LAST_USER_SCREEN_IS_PHOTO.pop(chat_id, None)
                return None
        else:
            edited = await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=editable_markup,
                **kwargs,
            )
        if isinstance(edited, Message):
            return await _remember_user_screen(edited)
        # Bot API иногда возвращает True. ID всё равно остаётся тем же.
        LAST_USER_SCREEN_MESSAGE_ID[chat_id] = message_id
        LAST_USER_SCREEN_IS_PHOTO[chat_id] = was_photo
        return None
    except TelegramBadRequest as error:
        if "message is not modified" in str(error).lower():
            LAST_USER_SCREEN_MESSAGE_ID[chat_id] = message_id
            LAST_USER_SCREEN_IS_PHOTO[chat_id] = was_photo
            return None
        logger.warning("Не удалось отредактировать пользовательский экран: %s", error)
        LAST_USER_SCREEN_MESSAGE_ID.pop(chat_id, None)
        LAST_USER_SCREEN_IS_PHOTO.pop(chat_id, None)
        return None
    except Exception:
        logger.exception("Не удалось отредактировать пользовательский экран %s:%s", chat_id, message_id)
        LAST_USER_SCREEN_MESSAGE_ID.pop(chat_id, None)
        LAST_USER_SCREEN_IS_PHOTO.pop(chat_id, None)
        return None


async def render_user_screen(
    target: Message,
    image: str,
    text: str,
    reply_markup: Any = None,
    *,
    force_new: bool = False,
    **kwargs: Any,
) -> Message:
    """Показывает пользовательский экран.

    /start передаёт force_new=True и всегда создаёт новое сообщение.
    Остальные переходы редактируют текущее/последнее сообщение и ничего не удаляют.
    """
    chat_id = target.chat.id
    clean_image = image_source(image)
    use_photo = bool(clean_image) and len(text) <= 1024
    target_is_bot_message = bool(target.from_user and target.from_user.is_bot)

    if not force_new:
        # Callback: редактируем именно сообщение, на котором нажали кнопку.
        if target_is_bot_message:
            was_photo = bool(target.photo)
            edited = await _edit_known_user_screen(
                chat_id, target.message_id, was_photo, clean_image, text, reply_markup, **kwargs
            )
            if edited is not None or LAST_USER_SCREEN_MESSAGE_ID.get(chat_id) == target.message_id:
                return edited or target

        # Reply-кнопка/обычный текст: редактируем последний экран бота.
        previous_id = LAST_USER_SCREEN_MESSAGE_ID.get(chat_id)
        if previous_id:
            was_photo = LAST_USER_SCREEN_IS_PHOTO.get(chat_id, False)
            edited = await _edit_known_user_screen(
                chat_id, previous_id, was_photo, clean_image, text, reply_markup, **kwargs
            )
            if edited is not None:
                return edited
            # Если edit_message_* вернул True/"not modified", экран уже считается текущим.
            if LAST_USER_SCREEN_MESSAGE_ID.get(chat_id) == previous_id:
                # Возвращаем target только для совместимости с аннотацией; сообщение не удалялось.
                return target

    # Новое сообщение создаём при /start или когда Telegram технически не позволяет
    # отредактировать старое (например, подпись к фото длиннее 1024 символов).
    if use_photo:
        try:
            sent = await bot.send_photo(chat_id, clean_image, caption=text, reply_markup=reply_markup)
            return await _remember_user_screen(sent)
        except Exception:
            logger.exception("Не удалось отправить пользовательское изображение: %s", clean_image)

    sent = await bot.send_message(chat_id, text, reply_markup=reply_markup, **kwargs)
    return await _remember_user_screen(sent)


async def answer_user_message(
    message: Message,
    text: str,
    reply_markup: Any = None,
    **kwargs: Any,
) -> Message:
    """Редактирует пользовательский экран; админ-панель остаётся отдельной."""
    admin_output = is_admin_panel_text(message.chat.id, text) or is_admin_reply_markup(reply_markup)
    if admin_output:
        return await message.answer(text, reply_markup=reply_markup, **kwargs)
    return await render_user_screen(
        message,
        image_for_user_text(message.chat.id, text),
        text,
        reply_markup=reply_markup,
        **kwargs,
    )


async def send_user_message(
    chat_id: int,
    text: str,
    reply_markup: Any = None,
) -> Message:
    """Уведомление пользователю: редактирует последний пользовательский экран."""
    admin_output = is_admin_panel_text(chat_id, text) or is_admin_reply_markup(reply_markup)
    if admin_output:
        return await bot.send_message(chat_id, text, reply_markup=reply_markup)

    previous_id = LAST_USER_SCREEN_MESSAGE_ID.get(chat_id)
    if previous_id:
        was_photo = LAST_USER_SCREEN_IS_PHOTO.get(chat_id, False)
        edited = await _edit_known_user_screen(
            chat_id,
            previous_id,
            was_photo,
            image_for_user_text(chat_id, text),
            text,
            reply_markup,
        )
        if edited is not None:
            return edited

    image = image_for_user_text(chat_id, text)
    if image and len(text) <= 1024:
        try:
            sent = await bot.send_photo(chat_id, image_source(image), caption=text, reply_markup=reply_markup)
            return await _remember_user_screen(sent)
        except Exception:
            logger.exception("Не удалось отправить изображение пользователю %s", chat_id)
    sent = await bot.send_message(chat_id, text, reply_markup=reply_markup)
    return await _remember_user_screen(sent)


async def send_push_notification(
    chat_id: int,
    text: str,
    reply_markup: Any = None,
    image: str = "",
) -> Message:
    """Всегда отправляет НОВОЕ сообщение, чтобы Telegram показал уведомление.

    Не сохраняет его как навигационный экран: следующие кнопки продолжают
    редактировать основной экран пользователя, а не уведомление.
    """
    clean_image = image_source(image)
    if clean_image and len(text) <= 1024:
        try:
            return await bot.send_photo(
                chat_id,
                clean_image,
                caption=text,
                reply_markup=reply_markup,
            )
        except Exception:
            logger.exception("Не удалось отправить push-изображение пользователю %s", chat_id)
    return await bot.send_message(chat_id, text, reply_markup=reply_markup)


async def send_image_message(
    message: Message,
    image: str,
    text: str,
    reply_markup: Any = None,
    *,
    force_new: bool = False,
) -> Message:
    return await render_user_screen(
        message, image, text, reply_markup=reply_markup, force_new=force_new
    )


async def send_section_message(
    message: Message,
    section: str,
    text: str,
    reply_markup: Any = None,
    *,
    force_new: bool = False,
) -> Message:
    return await send_image_message(
        message,
        SECTION_IMAGES.get(section, ""),
        text,
        reply_markup=reply_markup,
        force_new=force_new,
    )


async def send_flow_message(
    message: Message,
    screen: str,
    text: str,
    reply_markup: Any = None,
) -> Message:
    return await send_image_message(
        message,
        FLOW_IMAGES.get(screen, ""),
        text,
        reply_markup=reply_markup,
    )


async def send_bot_image(
    chat_id: int,
    image: str,
    text: str,
    reply_markup: Any = None,
) -> Message:
    previous_id = LAST_USER_SCREEN_MESSAGE_ID.get(chat_id)
    if previous_id:
        was_photo = LAST_USER_SCREEN_IS_PHOTO.get(chat_id, False)
        edited = await _edit_known_user_screen(
            chat_id, previous_id, was_photo, image, text, reply_markup
        )
        if edited is not None:
            return edited
    clean_image = image_source(image)
    if clean_image and len(text) <= 1024:
        try:
            sent = await bot.send_photo(chat_id, clean_image, caption=text, reply_markup=reply_markup)
            return await _remember_user_screen(sent)
        except Exception:
            logger.exception("Не удалось отправить изображение пользователю %s", chat_id)
    sent = await bot.send_message(chat_id, text, reply_markup=reply_markup)
    return await _remember_user_screen(sent)


def calculate_custom_stars_price(product: sqlite3.Row, amount: int) -> int:
    """Рублёвая цена пропорционально тарифу, с округлением вверх."""
    unit = product_unit_amount(product)
    base = int(product["price_rub"])
    return max(1, math.ceil(base * amount / unit)) if base > 0 else 0


def calculate_custom_stars_integer_price(product: sqlite3.Row, key: str, amount: int) -> int:
    """Целочисленная цена Stars пропорционально базовому тарифу."""
    unit = product_unit_amount(product)
    base = int(row_value(product, key, 0))
    return max(1, math.ceil(base * amount / unit)) if base > 0 else 0


def calculate_custom_stars_decimal_price(product: sqlite3.Row, key: str, amount: int) -> str:
    """Дробная криптоцена пропорционально базовому тарифу."""
    unit = Decimal(product_unit_amount(product))
    base = decimal_amount(row_value(product, key, "0"))
    if base <= 0:
        return "0"
    value = base * Decimal(amount) / unit
    return decimal_text(value)


def apply_decimal_discount(value: Any, discount_percent: int) -> str:
    amount = decimal_amount(value)
    if amount <= 0:
        return "0"
    discounted = amount * Decimal(100 - discount_percent) / Decimal(100)
    return decimal_text(discounted)


def main_menu_keyboard(show_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="store 🛍️")],
        [KeyboardButton(text="Поддержка 🎧")],
        [KeyboardButton(text="Отзывы 📭")],
    ]
    if show_admin:
        rows.append([KeyboardButton(text="Админ панель")])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        input_field_placeholder="Выберите раздел",
    )


def store_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Аккаунты", callback_data="store:accounts")],
            [InlineKeyboardButton(text="⭐ Звезды", callback_data="store:stars")],
        ]
    )


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    # История, блокировки и переключатель крипты доступны владельцу командами
    # /history, /ban (/bans) и /cripta, поэтому в панели их нет.
    builder = InlineKeyboardBuilder()
    builder.button(text="📦 Склад и товары", callback_data="admin:stock")
    builder.button(text="📊 Статистика", callback_data="admin:stats")
    builder.button(text="🎟 Промокоды", callback_data="admin:promos")
    builder.button(text="📣 Рассылка", callback_data="admin:broadcast")
    builder.adjust(1)
    return builder.as_markup()


def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


# ==========================================================
# БАЗА ДАННЫХ
# Внутренние balance_* поля оставлены для совместимости со старой БД,
# но пользовательский баланс и оплата с баланса отключены.
# ==========================================================


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.lock = asyncio.Lock()

    async def initialize(self) -> None:
        async with self.lock:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    is_blocked INTEGER NOT NULL DEFAULT 0,
                    is_banned INTEGER NOT NULL DEFAULT 0,
                    ban_reason TEXT,
                    banned_until TEXT,
                    banned_at TEXT,
                    banned_by INTEGER,
                    subscription_verified INTEGER NOT NULL DEFAULT 0,
                    balance_rub INTEGER NOT NULL DEFAULT 0,
                    balance_stars INTEGER NOT NULL DEFAULT 0,
                    balance_usdt TEXT NOT NULL DEFAULT '0',
                    balance_gram TEXT NOT NULL DEFAULT '0'
                );

                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    code TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    name TEXT NOT NULL,
                    price_rub INTEGER NOT NULL DEFAULT 0 CHECK(price_rub >= 0),
                    price_stars INTEGER NOT NULL DEFAULT 0 CHECK(price_stars >= 0),
                    price_usdt TEXT NOT NULL DEFAULT '0',
                    price_gram TEXT NOT NULL DEFAULT '0',
                    stock INTEGER NOT NULL DEFAULT 0 CHECK(stock >= 0),
                    reserved INTEGER NOT NULL DEFAULT 0 CHECK(reserved >= 0),
                    unit_amount INTEGER NOT NULL DEFAULT 1 CHECK(unit_amount > 0),
                    delivery_method TEXT NOT NULL DEFAULT 'standard',
                    is_visible INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS promo_codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    discount_percent INTEGER NOT NULL CHECK(discount_percent BETWEEN 1 AND 100),
                    expires_on TEXT,
                    max_uses INTEGER,
                    uses INTEGER NOT NULL DEFAULT 0,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'all'
                );

                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    username TEXT,
                    product_id INTEGER,
                    product_code TEXT NOT NULL,
                    product_name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    base_price_rub INTEGER NOT NULL,
                    base_price_stars INTEGER NOT NULL DEFAULT 0,
                    base_price_usdt TEXT NOT NULL DEFAULT '0',
                    base_price_gram TEXT NOT NULL DEFAULT '0',
                    discount_percent INTEGER NOT NULL DEFAULT 0,
                    final_price_rub INTEGER NOT NULL,
                    final_price_stars INTEGER NOT NULL DEFAULT 0,
                    final_price_usdt TEXT NOT NULL DEFAULT '0',
                    final_price_gram TEXT NOT NULL DEFAULT '0',
                    promo_code TEXT,
                    payment_method TEXT NOT NULL,
                    stock_units INTEGER NOT NULL DEFAULT 1,
                    delivery_method TEXT NOT NULL DEFAULT 'standard',
                    receipt_file_id TEXT NOT NULL,
                    receipt_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    exclude_from_stats INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    processed_at TEXT,
                    processed_by INTEGER,
                    FOREIGN KEY(user_id) REFERENCES users(user_id),
                    FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS account_stock (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER NOT NULL,
                    phone TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'available',
                    order_id INTEGER,
                    created_at TEXT NOT NULL,
                    sold_at TEXT,
                    UNIQUE(product_id, phone),
                    FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS balance_topups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    username TEXT,
                    currency TEXT NOT NULL,
                    amount TEXT NOT NULL,
                    receipt_file_id TEXT NOT NULL,
                    receipt_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    processed_at TEXT,
                    processed_by INTEGER,
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                );

                CREATE TABLE IF NOT EXISTS balance_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    event TEXT NOT NULL,
                    amount_rub INTEGER NOT NULL,
                    description TEXT NOT NULL,
                    source_type TEXT,
                    source_id INTEGER,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(user_id),
                    UNIQUE(source_type, source_id, event)
                );

                CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
                CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
                CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at);
                CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
                CREATE INDEX IF NOT EXISTS idx_topups_user_id ON balance_topups(user_id);
                CREATE INDEX IF NOT EXISTS idx_topups_status ON balance_topups(status);
                CREATE INDEX IF NOT EXISTS idx_balance_history_user_id ON balance_history(user_id, id DESC);
                """
            )

            # Мягкая миграция старой SQLite-базы без удаления данных.
            user_columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(users)")}
            if "subscription_verified" not in user_columns:
                self.conn.execute(
                    "ALTER TABLE users ADD COLUMN subscription_verified INTEGER NOT NULL DEFAULT 0"
                )
            if "is_banned" not in user_columns:
                self.conn.execute("ALTER TABLE users ADD COLUMN is_banned INTEGER NOT NULL DEFAULT 0")
            if "ban_reason" not in user_columns:
                self.conn.execute("ALTER TABLE users ADD COLUMN ban_reason TEXT")
            if "banned_until" not in user_columns:
                self.conn.execute("ALTER TABLE users ADD COLUMN banned_until TEXT")
            if "banned_at" not in user_columns:
                self.conn.execute("ALTER TABLE users ADD COLUMN banned_at TEXT")
            if "banned_by" not in user_columns:
                self.conn.execute("ALTER TABLE users ADD COLUMN banned_by INTEGER")
            if "balance_rub" not in user_columns:
                self.conn.execute("ALTER TABLE users ADD COLUMN balance_rub INTEGER NOT NULL DEFAULT 0")
            if "balance_stars" not in user_columns:
                self.conn.execute("ALTER TABLE users ADD COLUMN balance_stars INTEGER NOT NULL DEFAULT 0")
            if "balance_usdt" not in user_columns:
                self.conn.execute("ALTER TABLE users ADD COLUMN balance_usdt TEXT NOT NULL DEFAULT '0'")
            if "balance_gram" not in user_columns:
                self.conn.execute("ALTER TABLE users ADD COLUMN balance_gram TEXT NOT NULL DEFAULT '0'")

            promo_columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(promo_codes)")}
            if "category" not in promo_columns:
                self.conn.execute(
                    "ALTER TABLE promo_codes ADD COLUMN category TEXT NOT NULL DEFAULT 'all'"
                )

            product_columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(products)")}
            if "price_stars" not in product_columns:
                self.conn.execute("ALTER TABLE products ADD COLUMN price_stars INTEGER NOT NULL DEFAULT 0")
                self.conn.execute("UPDATE products SET price_stars = price_rub WHERE price_stars = 0")
            if "price_usdt" not in product_columns:
                self.conn.execute("ALTER TABLE products ADD COLUMN price_usdt TEXT NOT NULL DEFAULT '0'")
            if "price_gram" not in product_columns:
                self.conn.execute("ALTER TABLE products ADD COLUMN price_gram TEXT NOT NULL DEFAULT '0'")
            if "unit_amount" not in product_columns:
                self.conn.execute("ALTER TABLE products ADD COLUMN unit_amount INTEGER NOT NULL DEFAULT 1")
            if "delivery_method" not in product_columns:
                self.conn.execute(
                    "ALTER TABLE products ADD COLUMN delivery_method TEXT NOT NULL DEFAULT 'standard'"
                )

            order_columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(orders)")}
            if "base_price_stars" not in order_columns:
                self.conn.execute("ALTER TABLE orders ADD COLUMN base_price_stars INTEGER NOT NULL DEFAULT 0")
            if "final_price_stars" not in order_columns:
                self.conn.execute("ALTER TABLE orders ADD COLUMN final_price_stars INTEGER NOT NULL DEFAULT 0")
            if "base_price_usdt" not in order_columns:
                self.conn.execute("ALTER TABLE orders ADD COLUMN base_price_usdt TEXT NOT NULL DEFAULT '0'")
            if "base_price_gram" not in order_columns:
                self.conn.execute("ALTER TABLE orders ADD COLUMN base_price_gram TEXT NOT NULL DEFAULT '0'")
            if "final_price_usdt" not in order_columns:
                self.conn.execute("ALTER TABLE orders ADD COLUMN final_price_usdt TEXT NOT NULL DEFAULT '0'")
            if "final_price_gram" not in order_columns:
                self.conn.execute("ALTER TABLE orders ADD COLUMN final_price_gram TEXT NOT NULL DEFAULT '0'")
            if "stock_units" not in order_columns:
                self.conn.execute("ALTER TABLE orders ADD COLUMN stock_units INTEGER NOT NULL DEFAULT 1")
            if "delivery_method" not in order_columns:
                self.conn.execute(
                    "ALTER TABLE orders ADD COLUMN delivery_method TEXT NOT NULL DEFAULT 'standard'"
                )
            if "exclude_from_stats" not in order_columns:
                self.conn.execute(
                    "ALTER TABLE orders ADD COLUMN exclude_from_stats INTEGER NOT NULL DEFAULT 0"
                )

            # Старые версии запрещали удалять товар из-за обязательного product_id.
            # Пересоздаём таблицу заказов: история сохраняется, а удалённый товар даёт product_id = NULL.
            order_info = list(self.conn.execute("PRAGMA table_info(orders)"))
            product_id_info = next((row for row in order_info if row["name"] == "product_id"), None)
            if product_id_info and int(product_id_info["notnull"]) == 1:
                self.conn.commit()
                self.conn.execute("PRAGMA foreign_keys=OFF")
                self.conn.executescript(
                    """
                    DROP TABLE IF EXISTS orders_new;
                    CREATE TABLE orders_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        username TEXT,
                        product_id INTEGER,
                        product_code TEXT NOT NULL,
                        product_name TEXT NOT NULL,
                        category TEXT NOT NULL,
                        base_price_rub INTEGER NOT NULL,
                        base_price_stars INTEGER NOT NULL DEFAULT 0,
                        base_price_usdt TEXT NOT NULL DEFAULT '0',
                        base_price_gram TEXT NOT NULL DEFAULT '0',
                        discount_percent INTEGER NOT NULL DEFAULT 0,
                        final_price_rub INTEGER NOT NULL,
                        final_price_stars INTEGER NOT NULL DEFAULT 0,
                        final_price_usdt TEXT NOT NULL DEFAULT '0',
                        final_price_gram TEXT NOT NULL DEFAULT '0',
                        promo_code TEXT,
                        payment_method TEXT NOT NULL,
                        stock_units INTEGER NOT NULL DEFAULT 1,
                        delivery_method TEXT NOT NULL DEFAULT 'standard',
                        receipt_file_id TEXT NOT NULL,
                        receipt_type TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        exclude_from_stats INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL,
                        processed_at TEXT,
                        processed_by INTEGER,
                        FOREIGN KEY(user_id) REFERENCES users(user_id),
                        FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE SET NULL
                    );
                    INSERT INTO orders_new (
                        id, user_id, username, product_id, product_code, product_name, category,
                        base_price_rub, base_price_stars, base_price_usdt, base_price_gram,
                        discount_percent, final_price_rub, final_price_stars, final_price_usdt,
                        final_price_gram, promo_code, payment_method, stock_units, delivery_method,
                        receipt_file_id, receipt_type, status, exclude_from_stats, created_at, processed_at, processed_by
                    )
                    SELECT
                        id, user_id, username, product_id, product_code, product_name, category,
                        base_price_rub, base_price_stars, base_price_usdt, base_price_gram,
                        discount_percent, final_price_rub, final_price_stars, final_price_usdt,
                        final_price_gram, promo_code, payment_method, stock_units, delivery_method,
                        receipt_file_id, receipt_type, status, exclude_from_stats, created_at, processed_at, processed_by
                    FROM orders;
                    DROP TABLE orders;
                    ALTER TABLE orders_new RENAME TO orders;
                    CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
                    CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
                    CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at);
                    """
                )
                self.conn.commit()
                self.conn.execute("PRAGMA foreign_keys=ON")

            now = utc_now_iso()
            for category, code, name, price_rub, price_stars, stock, visible in SEED_PRODUCTS:
                self.conn.execute(
                    """
                    INSERT OR IGNORE INTO products
                    (category, code, name, price_rub, price_stars, stock, reserved, is_visible, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
                    """,
                    (category, code.lower(), name, price_rub, price_stars, stock, visible, now, now),
                )

            for months, premium_name in PREMIUM_TARIFF_NAMES.items():
                self.conn.execute(
                    """
                    INSERT OR IGNORE INTO products
                    (category, code, name, price_rub, price_stars, stock, reserved,
                     unit_amount, delivery_method, is_visible, created_at, updated_at)
                    VALUES ('premium', ?, ?, 0, 0, 0, 0, 1, 'standard', 1, ?, ?)
                    """,
                    (f"premium_{months}m", premium_name, now, now),
                )

            self.conn.execute(
                """
                INSERT OR IGNORE INTO products
                (category, code, name, price_rub, price_stars, stock, reserved,
                 unit_amount, delivery_method, is_visible, created_at, updated_at)
                VALUES ('stars', 'stars_account', 'Telegram Stars на аккаунт',
                        0, 0, 0, 0, 50, 'account', 1, ?, ?)
                """,
                (now, now),
            )
            self.conn.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES ('crypto_mode', '0')"
            )

            # Одноразово восстанавливаем историю уже существующих операций.
            # UNIQUE(source_type, source_id, event) не даст создавать дубликаты при перезапуске.
            for topup in self.conn.execute(
                "SELECT * FROM balance_topups WHERE status = 'approved' ORDER BY id"
            ).fetchall():
                currency = str(topup["currency"])
                if currency == "rub":
                    credit_rub = int(decimal_amount(topup["amount"]))
                    description = f"Пополнение баланса рублями: {topup['amount']} ₽"
                elif currency == "stars":
                    credit_rub = stars_topup_credit_rub(topup["amount"])
                    description = f"Пополнение через Stars: {topup['amount']} ⭐"
                else:
                    continue
                if credit_rub > 0:
                    self._insert_balance_history(
                        int(topup["user_id"]),
                        "topup",
                        credit_rub,
                        description,
                        "topup",
                        int(topup["id"]),
                        str(topup["processed_at"] or topup["created_at"]),
                    )

            for order in self.conn.execute(
                "SELECT * FROM orders WHERE payment_method = 'balance_rub' ORDER BY id"
            ).fetchall():
                price = int(order["final_price_rub"] or 0)
                if price <= 0:
                    continue
                self._insert_balance_history(
                    int(order["user_id"]),
                    "purchase",
                    -price,
                    f"Покупка: {order['product_name']}",
                    "order",
                    int(order["id"]),
                    str(order["created_at"]),
                )
                if str(order["status"]) == "cancelled":
                    self._insert_balance_history(
                        int(order["user_id"]),
                        "refund",
                        price,
                        f"Возврат за отменённый заказ #{order['id']}: {order['product_name']}",
                        "order",
                        int(order["id"]),
                        str(order["processed_at"] or order["created_at"]),
                    )

            columns = {
                row["name"]
                for row in self.conn.execute("PRAGMA table_info(orders)").fetchall()
            }
            if "delivery_phone" not in columns:
                self.conn.execute("ALTER TABLE orders ADD COLUMN delivery_phone TEXT")

            self.conn.commit()

    async def upsert_telegram_user(self, user: Any) -> None:
        if not user:
            return
        now = utc_now_iso()
        async with self.lock:
            self.conn.execute(
                """
                INSERT INTO users (user_id, username, first_name, created_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username,
                    first_name = excluded.first_name,
                    last_seen_at = excluded.last_seen_at
                """,
                (user.id, user.username, user.first_name, now, now),
            )
            self.conn.commit()

    async def upsert_user(self, message: Message) -> None:
        await self.upsert_telegram_user(message.from_user)

    async def find_user(self, identifier: str) -> sqlite3.Row | None:
        clean = identifier.strip()
        async with self.lock:
            if clean.lstrip("-").isdigit():
                return self.conn.execute(
                    "SELECT * FROM users WHERE user_id = ?", (int(clean),)
                ).fetchone()
            username = clean.lstrip("@").lower()
            return self.conn.execute(
                "SELECT * FROM users WHERE LOWER(username) = ? ORDER BY last_seen_at DESC LIMIT 1",
                (username,),
            ).fetchone()

    async def ban_user(
        self,
        user_id: int,
        reason: str,
        banned_until: str | None,
        banned_by: int,
    ) -> tuple[bool, str]:
        clean_reason = reason.strip()
        if not clean_reason:
            return False, "Укажите причину блокировки."
        async with self.lock:
            user = self.conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if not user:
                return False, "Пользователь не найден в базе."
            self.conn.execute(
                """
                UPDATE users
                SET is_banned = 1, ban_reason = ?, banned_until = ?, banned_at = ?, banned_by = ?
                WHERE user_id = ?
                """,
                (clean_reason[:500], banned_until, utc_now_iso(), banned_by, user_id),
            )
            self.conn.commit()
            return True, "Пользователь заблокирован."

    async def unban_user(self, user_id: int) -> tuple[bool, str]:
        async with self.lock:
            row = self.conn.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if not row:
                return False, "Пользователь не найден."
            if not row["is_banned"]:
                return False, "Пользователь не заблокирован."
            self.conn.execute(
                """
                UPDATE users
                SET is_banned = 0, ban_reason = NULL, banned_until = NULL,
                    banned_at = NULL, banned_by = NULL
                WHERE user_id = ?
                """,
                (user_id,),
            )
            self.conn.commit()
            return True, "Блокировка снята."

    async def get_active_ban(self, user_id: int) -> sqlite3.Row | None:
        async with self.lock:
            row = self.conn.execute(
                "SELECT * FROM users WHERE user_id = ? AND is_banned = 1", (user_id,)
            ).fetchone()
            if not row:
                return None
            if row["banned_until"]:
                try:
                    until = datetime.fromisoformat(row["banned_until"])
                    if until.tzinfo is None:
                        until = until.replace(tzinfo=timezone.utc)
                    if until <= datetime.now(timezone.utc):
                        self.conn.execute(
                            """
                            UPDATE users SET is_banned = 0, ban_reason = NULL,
                                banned_until = NULL, banned_at = NULL, banned_by = NULL
                            WHERE user_id = ?
                            """,
                            (user_id,),
                        )
                        self.conn.commit()
                        return None
                except ValueError:
                    pass
            return row

    async def unban_expired(self) -> int:
        async with self.lock:
            cursor = self.conn.execute(
                """
                UPDATE users
                SET is_banned = 0, ban_reason = NULL, banned_until = NULL,
                    banned_at = NULL, banned_by = NULL
                WHERE is_banned = 1 AND banned_until IS NOT NULL AND banned_until <= ?
                """,
                (utc_now_iso(),),
            )
            self.conn.commit()
            return int(cursor.rowcount or 0)

    async def list_banned_users(self, limit: int = 100) -> list[sqlite3.Row]:
        await self.unban_expired()
        async with self.lock:
            return list(
                self.conn.execute(
                    """
                    SELECT * FROM users WHERE is_banned = 1
                    ORDER BY COALESCE(banned_until, '9999-12-31') ASC, banned_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            )

    async def get_setting(self, key: str, default: str = "") -> str:
        async with self.lock:
            row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            return str(row["value"]) if row else default

    async def set_setting(self, key: str, value: str) -> None:
        async with self.lock:
            self.conn.execute(
                """
                INSERT INTO settings(key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, str(value)),
            )
            self.conn.commit()

    async def crypto_mode_enabled(self) -> bool:
        return await self.get_setting("crypto_mode", "0") == "1"

    async def toggle_crypto_mode(self) -> bool:
        enabled = await self.crypto_mode_enabled()
        await self.set_setting("crypto_mode", "0" if enabled else "1")
        return not enabled

    async def quick_add_premium(
        self,
        months: int,
        price_rub: int,
        price_stars: int,
        price_usdt: str,
        price_gram: str,
        stock: int,
    ) -> tuple[bool, str]:
        if months not in PREMIUM_TARIFF_NAMES:
            return False, "Доступные сроки: 3, 6 или 12 месяцев."
        if stock < 0:
            return False, "Количество не может быть отрицательным."
        has_price = (
            price_rub > 0 or price_stars > 0
            or decimal_amount(price_usdt) > 0 or decimal_amount(price_gram) > 0
        )
        if not has_price:
            return False, "Укажите хотя бы одну цену."
        code = f"premium_{months}m"
        now = utc_now_iso()
        async with self.lock:
            self.conn.execute(
                """
                INSERT INTO products
                (category, code, name, price_rub, price_stars, price_usdt, price_gram, stock, reserved,
                 unit_amount, delivery_method, is_visible, created_at, updated_at)
                VALUES ('premium', ?, ?, ?, ?, ?, ?, ?, 0, 1, 'standard', 1, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    name = excluded.name, price_rub = excluded.price_rub,
                    price_stars = excluded.price_stars, price_usdt = excluded.price_usdt,
                    price_gram = excluded.price_gram, stock = excluded.stock,
                    is_visible = 1, updated_at = excluded.updated_at
                """,
                (
                    code, PREMIUM_TARIFF_NAMES[months], price_rub, price_stars,
                    decimal_text(price_usdt), decimal_text(price_gram), stock, now, now,
                ),
            )
            self.conn.commit()
            return True, (
                f"Тариф Premium обновлён: {PREMIUM_TARIFF_NAMES[months]}, "
                f"{format_prices(price_rub, price_stars, price_usdt, price_gram)}, {stock} шт."
            )

    async def configure_stars_account(
        self,
        base_amount: int,
        price_rub: int,
        price_stars: int,
        price_usdt: str,
        price_gram: str,
        stock: int,
    ) -> tuple[bool, str]:
        if base_amount < 50:
            return False, "Базовое количество не может быть меньше 50 Stars."
        if stock < 0:
            return False, "Остаток должен быть неотрицательным."
        has_price = (
            price_rub > 0 or price_stars > 0
            or decimal_amount(price_usdt) > 0 or decimal_amount(price_gram) > 0
        )
        if not has_price:
            return False, "Укажите хотя бы одну цену."
        now = utc_now_iso()
        async with self.lock:
            self.conn.execute(
                """
                INSERT INTO products
                (category, code, name, price_rub, price_stars, price_usdt, price_gram, stock, reserved,
                 unit_amount, delivery_method, is_visible, created_at, updated_at)
                VALUES ('stars', 'stars_account', 'Telegram Stars на аккаунт',
                        ?, ?, ?, ?, ?, 0, ?, 'account', 1, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    price_rub = excluded.price_rub, price_stars = excluded.price_stars,
                    price_usdt = excluded.price_usdt, price_gram = excluded.price_gram,
                    stock = excluded.stock, unit_amount = excluded.unit_amount,
                    delivery_method = 'account', is_visible = 1, updated_at = excluded.updated_at
                """,
                (
                    price_rub, price_stars, decimal_text(price_usdt), decimal_text(price_gram),
                    stock, base_amount, now, now,
                ),
            )
            self.conn.commit()
            return True, (
                f"Stars на аккаунт настроены: {stars(base_amount)} = "
                f"{format_prices(price_rub, price_stars, price_usdt, price_gram)}, "
                f"остаток {stars(stock)}."
            )

    async def set_subscription_verified(self, user_id: int, verified: bool) -> None:
        """Сохраняет текущее состояние подписки пользователя."""
        async with self.lock:
            self.conn.execute(
                "UPDATE users SET subscription_verified = ?, last_seen_at = ? WHERE user_id = ?",
                (1 if verified else 0, utc_now_iso(), user_id),
            )
            self.conn.commit()

    async def get_products(self, category: str | None = None, include_hidden: bool = False) -> list[sqlite3.Row]:
        conditions: list[str] = []
        params: list[Any] = []
        if category is not None:
            conditions.append("category = ?")
            params.append(category)
        if not include_hidden:
            conditions.append("is_visible = 1")
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"""
            SELECT *, MAX(stock - reserved, 0) AS available
            FROM products
            {where}
            ORDER BY category, id
        """
        async with self.lock:
            return list(self.conn.execute(query, params).fetchall())

    async def get_product(self, product_id: int) -> sqlite3.Row | None:
        async with self.lock:
            return self.conn.execute(
                "SELECT *, MAX(stock - reserved, 0) AS available FROM products WHERE id = ?",
                (product_id,),
            ).fetchone()

    async def get_product_by_code(self, code: str) -> sqlite3.Row | None:
        async with self.lock:
            return self.conn.execute(
                "SELECT *, MAX(stock - reserved, 0) AS available FROM products WHERE code = ? COLLATE NOCASE",
                (code.strip(),),
            ).fetchone()

    async def add_product(
        self,
        category: str,
        code: str,
        name: str,
        price_rub: int,
        price_stars: int,
        price_usdt: str,
        price_gram: str,
        stock: int,
    ) -> tuple[bool, str]:
        now = utc_now_iso()
        async with self.lock:
            try:
                self.conn.execute(
                    """
                    INSERT INTO products
                    (category, code, name, price_rub, price_stars, price_usdt, price_gram, stock, reserved, is_visible, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 1, ?, ?)
                    """,
                    (
                        category.lower(), code.lower(), name, price_rub, price_stars,
                        decimal_text(price_usdt), decimal_text(price_gram), stock, now, now,
                    ),
                )
                self.conn.commit()
                return True, "Товар добавлен."
            except sqlite3.IntegrityError:
                return False, "Товар с таким кодом уже существует."

    async def quick_add_product(
        self,
        name: str,
        price_rub: int,
        price_stars: int,
        price_usdt: str,
        price_gram: str,
        stock_to_add: int,
    ) -> tuple[bool, str]:
        """Создаёт товар accounts или пополняет товар с тем же названием."""
        if min(price_rub, price_stars, stock_to_add) < 0 or decimal_amount(price_usdt) < 0 or decimal_amount(price_gram) < 0:
            return False, "Цена и количество не могут быть отрицательными."
        now = utc_now_iso()
        async with self.lock:
            existing = self.conn.execute(
                "SELECT * FROM products WHERE category = 'accounts' AND name = ? COLLATE NOCASE",
                (name.strip(),),
            ).fetchone()
            if existing:
                self.conn.execute(
                    """
                    UPDATE products
                    SET price_rub = ?, price_stars = ?, price_usdt = ?, price_gram = ?,
                        stock = stock + ?, is_visible = 1, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        price_rub, price_stars, decimal_text(price_usdt), decimal_text(price_gram),
                        stock_to_add, now, existing["id"],
                    ),
                )
                self.conn.commit()
                return True, f"Товар обновлён. Теперь на складе: {existing['stock'] + stock_to_add} шт."

            code = "quick_" + local_now().strftime("%Y%m%d%H%M%S%f")
            self.conn.execute(
                """
                INSERT INTO products
                (category, code, name, price_rub, price_stars, price_usdt, price_gram, stock, reserved, is_visible, created_at, updated_at)
                VALUES ('accounts', ?, ?, ?, ?, ?, ?, ?, 0, 1, ?, ?)
                """,
                (
                    code, name.strip(), price_rub, price_stars, decimal_text(price_usdt),
                    decimal_text(price_gram), stock_to_add, now, now,
                ),
            )
            self.conn.commit()
            return True, f"Новый товар добавлен на склад: {stock_to_add} шт."

    async def quick_add_stars_product(
        self,
        package_amount: int,
        price_rub: int,
        price_stars: int,
        price_usdt: str,
        price_gram: str,
        stock_to_add: int,
        delivery_method: str,
    ) -> tuple[bool, str]:
        """Создаёт пакет Stars или пополняет совпадающий пакет."""
        has_price = (
            price_rub > 0 or price_stars > 0
            or decimal_amount(price_usdt) > 0 or decimal_amount(price_gram) > 0
        )
        if package_amount <= 0 or not has_price or stock_to_add <= 0:
            return False, "Количество Stars, цена и остаток должны быть больше нуля."
        if stock_to_add < package_amount:
            return False, "Остаток Stars не может быть меньше размера одного пакета."
        if delivery_method not in {"gift", "account"}:
            return False, "Неизвестный способ выдачи Stars."

        now = utc_now_iso()
        async with self.lock:
            existing = self.conn.execute(
                """
                SELECT * FROM products
                WHERE category = 'stars' AND unit_amount = ? AND delivery_method = ?
                ORDER BY id LIMIT 1
                """,
                (package_amount, delivery_method),
            ).fetchone()
            if existing:
                new_stock = int(existing["stock"]) + stock_to_add
                self.conn.execute(
                    """
                    UPDATE products
                    SET name = ?, price_rub = ?, price_stars = ?, price_usdt = ?, price_gram = ?,
                        stock = ?, is_visible = 1, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        f"{package_amount} Telegram Stars", price_rub, price_stars,
                        decimal_text(price_usdt), decimal_text(price_gram),
                        new_stock, now, existing["id"],
                    ),
                )
                self.conn.commit()
                return True, (
                    f"Пакет обновлён: {package_amount} Stars за "
                    f"{format_prices(price_rub, price_stars, price_usdt, price_gram)}. "
                    f"Общий остаток: {stars(new_stock)}. Выдача: {delivery_label(delivery_method)}."
                )

            suffix = "gift" if delivery_method == "gift" else "account"
            base_code = f"stars_{package_amount}_{suffix}"
            code = base_code
            counter = 2
            while self.conn.execute(
                "SELECT 1 FROM products WHERE code = ? COLLATE NOCASE", (code,)
            ).fetchone():
                code = f"{base_code}_{counter}"
                counter += 1

            self.conn.execute(
                """
                INSERT INTO products
                (category, code, name, price_rub, price_stars, price_usdt, price_gram, stock, reserved,
                 unit_amount, delivery_method, is_visible, created_at, updated_at)
                VALUES ('stars', ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, 1, ?, ?)
                """,
                (
                    code, f"{package_amount} Telegram Stars", price_rub, price_stars,
                    decimal_text(price_usdt), decimal_text(price_gram), stock_to_add,
                    package_amount, delivery_method, now, now,
                ),
            )
            self.conn.commit()
            return True, (
                f"Пакет Stars добавлен. Код: {code}. Размер: {stars(package_amount)}, "
                f"цена: {format_prices(price_rub, price_stars, price_usdt, price_gram)}, "
                f"остаток: {stars(stock_to_add)}, выдача: {delivery_label(delivery_method)}."
            )

    async def change_stock(self, product_id: int, mode: str, value: int) -> tuple[bool, str]:
        async with self.lock:
            row = self.conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
            if not row:
                return False, "Товар не найден."

            if mode == "add":
                new_stock = row["stock"] + value
            elif mode == "subtract":
                new_stock = row["stock"] - value
            elif mode == "set":
                new_stock = value
            else:
                return False, "Неизвестная операция."

            if new_stock < row["reserved"]:
                return False, f"Нельзя установить меньше зарезервированного количества: {row['reserved']}."
            if new_stock < 0:
                return False, "Количество не может быть отрицательным."

            self.conn.execute(
                "UPDATE products SET stock = ?, updated_at = ? WHERE id = ?",
                (new_stock, utc_now_iso(), product_id),
            )
            self.conn.commit()
            if row["category"] == "stars":
                return True, f"Новый остаток: {stars(new_stock)}."
            return True, f"Новое количество: {new_stock} шт."

    async def set_price(
        self,
        product_id: int,
        price_rub: int,
        price_stars: int = 0,
        price_usdt: str = "0",
        price_gram: str = "0",
    ) -> tuple[bool, str]:
        if price_rub < 0 or price_stars < 0:
            return False, "Цена не может быть отрицательной."
        usdt_value = decimal_text(price_usdt)
        gram_value = decimal_text(price_gram)
        async with self.lock:
            cursor = self.conn.execute(
                """
                UPDATE products
                SET price_rub = ?, price_stars = ?, price_usdt = ?, price_gram = ?, updated_at = ?
                WHERE id = ?
                """,
                (price_rub, price_stars, usdt_value, gram_value, utc_now_iso(), product_id),
            )
            self.conn.commit()
            if cursor.rowcount == 0:
                return False, "Товар не найден."
            return True, f"Новая цена: {format_prices(price_rub, price_stars, usdt_value, gram_value)}."

    async def toggle_product_visibility(self, product_id: int) -> tuple[bool, str]:
        async with self.lock:
            row = self.conn.execute("SELECT is_visible FROM products WHERE id = ?", (product_id,)).fetchone()
            if not row:
                return False, "Товар не найден."
            new_value = 0 if row["is_visible"] else 1
            self.conn.execute(
                "UPDATE products SET is_visible = ?, updated_at = ? WHERE id = ?",
                (new_value, utc_now_iso(), product_id),
            )
            self.conn.commit()
            return True, "Товар показан в каталоге." if new_value else "Товар скрыт из каталога."

    async def rename_product(self, product_id: int, new_name: str) -> tuple[bool, str]:
        clean_name = new_name.strip()
        if not clean_name or len(clean_name) > 100:
            return False, "Название должно содержать от 1 до 100 символов."
        async with self.lock:
            cursor = self.conn.execute(
                "UPDATE products SET name = ?, updated_at = ? WHERE id = ?",
                (clean_name, utc_now_iso(), product_id),
            )
            self.conn.commit()
            if cursor.rowcount == 0:
                return False, "Товар не найден."
            return True, f"Новое название: {clean_name}."

    async def delete_product(self, product_id: int) -> tuple[bool, str]:
        async with self.lock:
            row = self.conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
            if not row:
                return False, "Товар не найден."
            pending = self.conn.execute(
                "SELECT COUNT(*) AS count FROM orders WHERE product_id = ? AND status = 'pending'",
                (product_id,),
            ).fetchone()["count"]
            if pending or int(row["reserved"]) > 0:
                return False, "Нельзя удалить товар: по нему есть заявка на проверке. Сначала выдайте или отмените её."
            self.conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
            self.conn.commit()
            return True, "Товар полностью удалён со склада и из каталога. История завершённых заказов сохранена."

    async def validate_promo(
        self, code: str, product_category: str | None = None
    ) -> tuple[bool, str, sqlite3.Row | None]:
        normalized = code.strip().upper()
        async with self.lock:
            promo = self.conn.execute(
                "SELECT * FROM promo_codes WHERE code = ? COLLATE NOCASE",
                (normalized,),
            ).fetchone()

        if not promo:
            return False, "Промокод не найден.", None
        if not promo["is_active"]:
            return False, "Промокод отключён.", None
        if promo["expires_on"]:
            try:
                if date.fromisoformat(promo["expires_on"]) < local_now().date():
                    return False, "Срок действия промокода истёк.", None
            except ValueError:
                return False, "У промокода некорректный срок действия.", None
        if promo["max_uses"] is not None and promo["uses"] >= promo["max_uses"]:
            return False, "Лимит использований промокода исчерпан.", None
        promo_category = promo["category"] or "all"
        if product_category and promo_category not in {"all", product_category}:
            label = PROMO_CATEGORY_LABELS.get(promo_category, promo_category)
            return False, f"Промокод действует только для категории «{label}».", None
        return True, "Промокод применён.", promo

    async def create_promo(
        self,
        code: str,
        discount_percent: int,
        expires_on: str | None,
        max_uses: int | None,
        category: str,
    ) -> tuple[bool, str]:
        if not re.fullmatch(r"[A-Za-z0-9_-]{2,32}", code):
            return False, "Код: 2–32 символа, латиница, цифры, _ или -."
        if not 1 <= discount_percent <= 100:
            return False, "Скидка должна быть от 1 до 100%."
        if max_uses is not None and max_uses <= 0:
            return False, "Лимит использований должен быть больше нуля."
        if category not in PROMO_CATEGORY_LABELS:
            return False, "Категория: Все, Звезды, Аккаунты или Premium."
        if expires_on:
            try:
                expiration = date.fromisoformat(expires_on)
            except ValueError:
                return False, "Дата должна быть в формате ГГГГ-ММ-ДД."
            if expiration < local_now().date():
                return False, "Дата окончания уже прошла."

        async with self.lock:
            try:
                self.conn.execute(
                    """
                    INSERT INTO promo_codes
                    (code, discount_percent, expires_on, max_uses, uses, is_active, created_at, category)
                    VALUES (?, ?, ?, ?, 0, 1, ?, ?)
                    """,
                    (code.upper(), discount_percent, expires_on, max_uses, utc_now_iso(), category),
                )
                self.conn.commit()
                return True, "Промокод создан."
            except sqlite3.IntegrityError:
                return False, "Промокод с таким названием уже существует."

    async def get_promos(self) -> list[sqlite3.Row]:
        async with self.lock:
            return list(
                self.conn.execute(
                    "SELECT * FROM promo_codes ORDER BY is_active DESC, id DESC LIMIT 30"
                ).fetchall()
            )

    async def toggle_promo(self, promo_id: int) -> tuple[bool, str]:
        async with self.lock:
            promo = self.conn.execute("SELECT * FROM promo_codes WHERE id = ?", (promo_id,)).fetchone()
            if not promo:
                return False, "Промокод не найден."
            new_value = 0 if promo["is_active"] else 1
            self.conn.execute("UPDATE promo_codes SET is_active = ? WHERE id = ?", (new_value, promo_id))
            self.conn.commit()
            return True, "Промокод включён." if new_value else "Промокод отключён."

    async def create_pending_order(
        self,
        user_id: int,
        username: str | None,
        product_id: int,
        payment_method: str,
        receipt_file_id: str,
        receipt_type: str,
        promo_code: str | None,
        custom_stock_units: int | None = None,
    ) -> tuple[bool, str, sqlite3.Row | None]:
        """Создаёт заявку и резервирует нужное число складских единиц."""
        async with self.lock:
            try:
                self.conn.execute("BEGIN IMMEDIATE")
                product = self.conn.execute(
                    "SELECT *, (stock - reserved) AS available FROM products WHERE id = ?",
                    (product_id,),
                ).fetchone()
                if not product or not product["is_visible"]:
                    self.conn.rollback()
                    return False, "Товар больше недоступен.", None

                if product["category"] == "stars":
                    units = int(custom_stock_units or 0)
                    delivery_method = str(product["delivery_method"])
                    if delivery_method == "gift":
                        if not is_allowed_gift_star_amount(units):
                            self.conn.rollback()
                            return False, "Недопустимое количество Stars подарком.", None
                    elif delivery_method == "account":
                        if units < 50:
                            self.conn.rollback()
                            return False, "Минимум для Stars на аккаунт — 50.", None
                        crypto_row = self.conn.execute(
                            "SELECT value FROM settings WHERE key = 'crypto_mode'"
                        ).fetchone()
                        if crypto_row and str(crypto_row["value"]) == "1":
                            self.conn.rollback()
                            return False, "В данный момент товара нет в наличии.", None
                    else:
                        self.conn.rollback()
                        return False, "Неизвестный способ выдачи Stars.", None
                    base_price_rub = calculate_custom_stars_price(product, units)
                    base_price_stars = calculate_custom_stars_integer_price(product, "price_stars", units)
                    base_price_usdt = calculate_custom_stars_decimal_price(product, "price_usdt", units)
                    base_price_gram = calculate_custom_stars_decimal_price(product, "price_gram", units)
                    order_product_name = f"{units} Telegram Stars"
                else:
                    if product["category"] == "premium":
                        crypto_row = self.conn.execute(
                            "SELECT value FROM settings WHERE key = 'crypto_mode'"
                        ).fetchone()
                        if crypto_row and str(crypto_row["value"]) == "1":
                            self.conn.rollback()
                            return False, "В данный момент товара нет в наличии.", None
                    units = max(1, int(product["unit_amount"]))
                    base_price_rub = int(product["price_rub"])
                    base_price_stars = int(product["price_stars"])
                    base_price_usdt = decimal_text(row_value(product, "price_usdt", "0"))
                    base_price_gram = decimal_text(row_value(product, "price_gram", "0"))
                    order_product_name = product["name"]

                if int(product["available"]) < units:
                    self.conn.rollback()
                    return False, "Товар закончился или остатка недостаточно.", None

                discount = 0
                normalized_promo: str | None = None
                if promo_code:
                    normalized_promo = promo_code.strip().upper()
                    promo = self.conn.execute(
                        "SELECT * FROM promo_codes WHERE code = ? COLLATE NOCASE",
                        (normalized_promo,),
                    ).fetchone()
                    if not promo or not promo["is_active"]:
                        self.conn.rollback()
                        return False, "Промокод больше недоступен.", None
                    if promo["expires_on"] and date.fromisoformat(promo["expires_on"]) < local_now().date():
                        self.conn.rollback()
                        return False, "Срок действия промокода истёк.", None
                    if promo["max_uses"] is not None and promo["uses"] >= promo["max_uses"]:
                        self.conn.rollback()
                        return False, "Лимит промокода исчерпан.", None
                    promo_category = promo["category"] or "all"
                    if promo_category not in {"all", product["category"]}:
                        self.conn.rollback()
                        return False, "Промокод не подходит для этой категории.", None
                    discount = promo["discount_percent"]
                    self.conn.execute(
                        "UPDATE promo_codes SET uses = uses + 1 WHERE id = ?",
                        (promo["id"],),
                    )

                final_price_rub = max(0, round(base_price_rub * (100 - discount) / 100))
                final_price_stars = max(0, round(base_price_stars * (100 - discount) / 100))
                final_price_usdt = apply_decimal_discount(base_price_usdt, discount)
                final_price_gram = apply_decimal_discount(base_price_gram, discount)

                if payment_method == "card" and base_price_rub <= 0:
                    self.conn.rollback()
                    return False, "Для товара недоступна оплата рублями.", None
                if payment_method == "stars" and base_price_stars <= 0:
                    self.conn.rollback()
                    return False, "Для товара недоступна оплата Stars.", None
                if payment_method == "usdt" and decimal_amount(base_price_usdt) <= 0:
                    self.conn.rollback()
                    return False, "Для товара недоступна оплата USDT.", None
                if payment_method == "gram" and decimal_amount(base_price_gram) <= 0:
                    self.conn.rollback()
                    return False, "Для товара недоступна оплата GRAM.", None
                if product["category"] == "stars" and payment_method in {"stars", "balance_stars"}:
                    self.conn.rollback()
                    return False, "Покупка Stars не может оплачиваться Stars.", None

                balance_currency = balance_payment_currency(payment_method)
                if balance_currency:
                    user_balance = self.conn.execute(
                        "SELECT balance_rub, balance_stars, balance_usdt, balance_gram FROM users WHERE user_id = ?",
                        (user_id,),
                    ).fetchone()
                    if not user_balance:
                        self.conn.rollback()
                        return False, "Пользователь не найден. Нажмите /start и повторите.", None

                    if balance_currency == "rub":
                        required = final_price_rub
                        if required <= 0:
                            self.conn.rollback()
                            return False, "Для товара недоступна цена в рублях.", None
                        if int(user_balance["balance_rub"]) < required:
                            self.conn.rollback()
                            return False, "Недостаточно рублей на балансе.", None
                        self.conn.execute(
                            "UPDATE users SET balance_rub = balance_rub - ? WHERE user_id = ?",
                            (required, user_id),
                        )
                    elif balance_currency == "stars":
                        required = final_price_stars
                        if required <= 0:
                            self.conn.rollback()
                            return False, "Для товара недоступна цена в Stars.", None
                        if int(user_balance["balance_stars"]) < required:
                            self.conn.rollback()
                            return False, "Недостаточно Stars на балансе.", None
                        self.conn.execute(
                            "UPDATE users SET balance_stars = balance_stars - ? WHERE user_id = ?",
                            (required, user_id),
                        )
                    elif balance_currency == "usdt":
                        required_dec = decimal_amount(final_price_usdt)
                        current_dec = decimal_amount(user_balance["balance_usdt"])
                        if required_dec <= 0:
                            self.conn.rollback()
                            return False, "Для товара недоступна цена в USDT.", None
                        if current_dec < required_dec:
                            self.conn.rollback()
                            return False, "Недостаточно USDT на балансе.", None
                        self.conn.execute(
                            "UPDATE users SET balance_usdt = ? WHERE user_id = ?",
                            (decimal_text(current_dec - required_dec), user_id),
                        )
                    elif balance_currency == "gram":
                        required_dec = decimal_amount(final_price_gram)
                        current_dec = decimal_amount(user_balance["balance_gram"])
                        if required_dec <= 0:
                            self.conn.rollback()
                            return False, "Для товара недоступна цена в GRAM.", None
                        if current_dec < required_dec:
                            self.conn.rollback()
                            return False, "Недостаточно GRAM на балансе.", None
                        self.conn.execute(
                            "UPDATE users SET balance_gram = ? WHERE user_id = ?",
                            (decimal_text(current_dec - required_dec), user_id),
                        )

                now = utc_now_iso()
                cursor = self.conn.execute(
                    """
                    INSERT INTO orders (
                        user_id, username, product_id, product_code, product_name, category,
                        base_price_rub, base_price_stars, base_price_usdt, base_price_gram,
                        discount_percent, final_price_rub, final_price_stars,
                        final_price_usdt, final_price_gram, promo_code, payment_method,
                        stock_units, delivery_method, receipt_file_id, receipt_type, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                    """,
                    (
                        user_id, username, product["id"], product["code"], order_product_name,
                        product["category"], base_price_rub, base_price_stars, base_price_usdt,
                        base_price_gram, discount, final_price_rub, final_price_stars,
                        final_price_usdt, final_price_gram, normalized_promo, payment_method, units,
                        product["delivery_method"], receipt_file_id, receipt_type, now,
                    ),
                )
                order_id = cursor.lastrowid
                if payment_method == "balance_rub" and final_price_rub > 0:
                    self._insert_balance_history(
                        user_id,
                        "purchase",
                        -int(final_price_rub),
                        f"Покупка: {order_product_name}",
                        "order",
                        int(order_id),
                        now,
                    )
                self.conn.execute(
                    "UPDATE products SET reserved = reserved + ?, updated_at = ? WHERE id = ?",
                    (units, now, product_id),
                )
                self.conn.commit()
                order = self.conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
                return True, "Заявка создана.", order
            except Exception:
                self.conn.rollback()
                logger.exception("Не удалось создать заказ")
                return False, "Не удалось создать заказ. Попробуйте ещё раз.", None

    async def add_account_stock(self, product_id: int, phone: str) -> tuple[bool, str]:
        phone = phone.strip()
        if not phone:
            return False, "Номер не указан."
        async with self.lock:
            try:
                product = self.conn.execute(
                    "SELECT * FROM products WHERE id = ?",
                    (product_id,),
                ).fetchone()
                if not product or product["category"] != "accounts":
                    return False, "Товар не найден или это не категория аккаунтов."

                now = utc_now_iso()
                self.conn.execute(
                    """
                    INSERT INTO account_stock(product_id, phone, status, created_at)
                    VALUES (?, ?, 'available', ?)
                    """,
                    (product_id, phone, now),
                )
                self.conn.execute(
                    """
                    UPDATE products
                    SET stock = stock + 1, updated_at = ?
                    WHERE id = ?
                    """,
                    (now, product_id),
                )
                self.conn.commit()
                return True, "Аккаунт добавлен на склад."
            except sqlite3.IntegrityError:
                self.conn.rollback()
                return False, "Такой номер уже есть на складе."
            except Exception:
                self.conn.rollback()
                logger.exception("Не удалось добавить аккаунт на склад")
                return False, "Ошибка базы данных."

    async def get_order_delivery(self, order_id: int, user_id: int) -> sqlite3.Row | None:
        async with self.lock:
            return self.conn.execute(
                """
                SELECT *
                FROM orders
                WHERE id = ? AND user_id = ? AND status = 'approved'
                """,
                (order_id, user_id),
            ).fetchone()

    async def approve_order(self, order_id: int, admin_id: int) -> tuple[str, sqlite3.Row | None]:
        async with self.lock:
            try:
                self.conn.execute("BEGIN IMMEDIATE")
                order = self.conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
                if not order:
                    self.conn.rollback()
                    return "not_found", None
                if order["status"] != "pending":
                    self.conn.rollback()
                    return order["status"], order

                product = self.conn.execute("SELECT * FROM products WHERE id = ?", (order["product_id"],)).fetchone()
                if not product:
                    self.conn.rollback()
                    return "product_missing", order
                units = max(1, int(order["stock_units"]))
                if product["stock"] < units or product["reserved"] < units:
                    self.conn.rollback()
                    return "no_stock", order

                delivery_phone = None
                if product["category"] == "accounts":
                    account = self.conn.execute(
                        """
                        SELECT id, phone
                        FROM account_stock
                        WHERE product_id = ? AND status = 'available'
                        ORDER BY id
                        LIMIT 1
                        """,
                        (product["id"],),
                    ).fetchone()
                    if not account:
                        self.conn.rollback()
                        return "no_account_stock", order
                    delivery_phone = str(account["phone"])

                now = utc_now_iso()
                self.conn.execute(
                    """
                    UPDATE products
                    SET stock = stock - ?,
                        reserved = MAX(reserved - ?, 0),
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (units, units, now, order["product_id"]),
                )
                if product["category"] == "accounts":
                    self.conn.execute(
                        """
                        UPDATE account_stock
                        SET status = 'sold', order_id = ?, sold_at = ?
                        WHERE id = (
                            SELECT id
                            FROM account_stock
                            WHERE product_id = ? AND status = 'available'
                            ORDER BY id
                            LIMIT 1
                        )
                        """,
                        (order_id, now, product["id"]),
                    )

                self.conn.execute(
                    """
                    UPDATE orders
                    SET status = 'approved',
                        processed_at = ?,
                        processed_by = ?,
                        delivery_phone = ?
                    WHERE id = ?
                    """,
                    (now, admin_id, delivery_phone, order_id),
                )
                self.conn.commit()
                updated = self.conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
                return "approved", updated
            except Exception:
                self.conn.rollback()
                logger.exception("Не удалось подтвердить заказ %s", order_id)
                return "error", None

    async def cancel_order(self, order_id: int, admin_id: int) -> tuple[str, sqlite3.Row | None]:
        async with self.lock:
            try:
                self.conn.execute("BEGIN IMMEDIATE")
                order = self.conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
                if not order:
                    self.conn.rollback()
                    return "not_found", None
                if order["status"] != "pending":
                    self.conn.rollback()
                    return order["status"], order

                now = utc_now_iso()
                self.conn.execute(
                    """
                    UPDATE products
                    SET reserved = MAX(reserved - ?, 0), updated_at = ?
                    WHERE id = ?
                    """,
                    (max(1, int(order["stock_units"])), now, order["product_id"]),
                )
                if order["promo_code"]:
                    self.conn.execute(
                        """
                        UPDATE promo_codes
                        SET uses = MAX(uses - 1, 0)
                        WHERE code = ? COLLATE NOCASE
                        """,
                        (order["promo_code"],),
                    )

                balance_currency = balance_payment_currency(str(order["payment_method"]))
                if balance_currency == "rub":
                    refund_rub = int(order["final_price_rub"])
                    self.conn.execute(
                        "UPDATE users SET balance_rub = balance_rub + ? WHERE user_id = ?",
                        (refund_rub, order["user_id"]),
                    )
                    if refund_rub > 0:
                        self._insert_balance_history(
                            int(order["user_id"]),
                            "refund",
                            refund_rub,
                            f"Возврат за отменённый заказ #{order_id}: {order['product_name']}",
                            "order",
                            int(order_id),
                            now,
                        )
                elif balance_currency == "stars":
                    self.conn.execute(
                        "UPDATE users SET balance_stars = balance_stars + ? WHERE user_id = ?",
                        (int(order["final_price_stars"]), order["user_id"]),
                    )
                elif balance_currency == "usdt":
                    row = self.conn.execute(
                        "SELECT balance_usdt FROM users WHERE user_id = ?", (order["user_id"],)
                    ).fetchone()
                    current = decimal_amount(row["balance_usdt"] if row else "0")
                    self.conn.execute(
                        "UPDATE users SET balance_usdt = ? WHERE user_id = ?",
                        (decimal_text(current + decimal_amount(order["final_price_usdt"])), order["user_id"]),
                    )
                elif balance_currency == "gram":
                    row = self.conn.execute(
                        "SELECT balance_gram FROM users WHERE user_id = ?", (order["user_id"],)
                    ).fetchone()
                    current = decimal_amount(row["balance_gram"] if row else "0")
                    self.conn.execute(
                        "UPDATE users SET balance_gram = ? WHERE user_id = ?",
                        (decimal_text(current + decimal_amount(order["final_price_gram"])), order["user_id"]),
                    )

                self.conn.execute(
                    """
                    UPDATE orders
                    SET status = 'cancelled', processed_at = ?, processed_by = ?
                    WHERE id = ?
                    """,
                    (now, admin_id, order_id),
                )
                self.conn.commit()
                updated = self.conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
                return "cancelled", updated
            except Exception:
                self.conn.rollback()
                logger.exception("Не удалось отменить заказ %s", order_id)
                return "error", None

    async def get_order(self, order_id: int) -> sqlite3.Row | None:
        async with self.lock:
            return self.conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()

    async def get_user_orders(self, user_id: int, limit: int = 10) -> list[sqlite3.Row]:
        async with self.lock:
            return list(
                self.conn.execute(
                    "SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                    (user_id, limit),
                ).fetchall()
            )

    async def get_user_balance(self, user_id: int) -> sqlite3.Row | None:
        async with self.lock:
            return self.conn.execute(
                "SELECT user_id, balance_rub, balance_stars, balance_usdt, balance_gram FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()

    def _insert_balance_history(
        self,
        user_id: int,
        event: str,
        amount_rub: int,
        description: str,
        source_type: str | None = None,
        source_id: int | None = None,
        created_at: str | None = None,
    ) -> None:
        """Записывает движение рублёвого баланса в рамках текущей транзакции SQLite."""
        self.conn.execute(
            """
            INSERT OR IGNORE INTO balance_history
            (user_id, event, amount_rub, description, source_type, source_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(user_id),
                event,
                int(amount_rub),
                description,
                source_type,
                source_id,
                created_at or utc_now_iso(),
            ),
        )

    async def get_balance_history(self, user_id: int, limit: int = 20) -> list[sqlite3.Row]:
        async with self.lock:
            return list(
                self.conn.execute(
                    """
                    SELECT * FROM balance_history
                    WHERE user_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (int(user_id), max(1, min(int(limit), 50))),
                ).fetchall()
            )

    async def create_balance_topup(
        self,
        user_id: int,
        username: str | None,
        currency: str,
        amount: str,
        receipt_file_id: str,
        receipt_type: str,
    ) -> sqlite3.Row | None:
        if currency not in BALANCE_CURRENCY_LABELS:
            return None
        normalized_amount = parse_topup_amount(currency, amount)
        if not normalized_amount:
            return None
        async with self.lock:
            now = utc_now_iso()
            cursor = self.conn.execute(
                """
                INSERT INTO balance_topups
                (user_id, username, currency, amount, receipt_file_id, receipt_type, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (user_id, username, currency, normalized_amount, receipt_file_id, receipt_type, now),
            )
            self.conn.commit()
            return self.conn.execute(
                "SELECT * FROM balance_topups WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()

    async def get_balance_topup(self, topup_id: int) -> sqlite3.Row | None:
        async with self.lock:
            return self.conn.execute(
                "SELECT * FROM balance_topups WHERE id = ?", (topup_id,)
            ).fetchone()

    async def approve_balance_topup(
        self, topup_id: int, admin_id: int
    ) -> tuple[str, sqlite3.Row | None, sqlite3.Row | None]:
        async with self.lock:
            try:
                self.conn.execute("BEGIN IMMEDIATE")
                topup = self.conn.execute(
                    "SELECT * FROM balance_topups WHERE id = ?", (topup_id,)
                ).fetchone()
                if not topup:
                    self.conn.rollback()
                    return "not_found", None, None
                if topup["status"] != "pending":
                    user = self.conn.execute(
                        "SELECT * FROM users WHERE user_id = ?", (topup["user_id"],)
                    ).fetchone()
                    self.conn.rollback()
                    return str(topup["status"]), topup, user

                currency = str(topup["currency"])
                amount = str(topup["amount"])
                if currency == "rub":
                    credit_rub = rub_topup_credit_rub(amount)
                elif currency == "stars":
                    credit_rub = stars_topup_credit_rub(amount)
                else:
                    # Старые заявки в USDT/GRAM больше не зачисляются: баланс только рублёвый.
                    self.conn.rollback()
                    return "error", topup, None

                if credit_rub <= 0:
                    self.conn.rollback()
                    return "error", topup, None
                self.conn.execute(
                    "UPDATE users SET balance_rub = balance_rub + ? WHERE user_id = ?",
                    (credit_rub, topup["user_id"]),
                )

                now = utc_now_iso()
                if currency == "stars":
                    description = f"Пополнение через Stars: {amount} ⭐"
                else:
                    description = f"Пополнение рублями: оплачено {amount} ₽, комиссия 5%"
                self._insert_balance_history(
                    int(topup["user_id"]),
                    "topup",
                    credit_rub,
                    description,
                    "topup",
                    int(topup_id),
                    now,
                )
                self.conn.execute(
                    """UPDATE balance_topups
                       SET status = 'approved', processed_at = ?, processed_by = ?
                       WHERE id = ?""",
                    (now, admin_id, topup_id),
                )
                self.conn.commit()
                updated = self.conn.execute(
                    "SELECT * FROM balance_topups WHERE id = ?", (topup_id,)
                ).fetchone()
                user = self.conn.execute(
                    "SELECT * FROM users WHERE user_id = ?", (topup["user_id"],)
                ).fetchone()
                return "approved", updated, user
            except Exception:
                self.conn.rollback()
                logger.exception("Не удалось подтвердить пополнение %s", topup_id)
                return "error", None, None

    async def cancel_balance_topup(
        self, topup_id: int, admin_id: int
    ) -> tuple[str, sqlite3.Row | None]:
        async with self.lock:
            try:
                self.conn.execute("BEGIN IMMEDIATE")
                topup = self.conn.execute(
                    "SELECT * FROM balance_topups WHERE id = ?", (topup_id,)
                ).fetchone()
                if not topup:
                    self.conn.rollback()
                    return "not_found", None
                if topup["status"] != "pending":
                    self.conn.rollback()
                    return str(topup["status"]), topup
                now = utc_now_iso()
                self.conn.execute(
                    """UPDATE balance_topups
                       SET status = 'cancelled', processed_at = ?, processed_by = ?
                       WHERE id = ?""",
                    (now, admin_id, topup_id),
                )
                self.conn.commit()
                updated = self.conn.execute(
                    "SELECT * FROM balance_topups WHERE id = ?", (topup_id,)
                ).fetchone()
                return "cancelled", updated
            except Exception:
                self.conn.rollback()
                logger.exception("Не удалось отменить пополнение %s", topup_id)
                return "error", None

    async def get_statistics(self) -> dict[str, Any]:
        start, end = today_utc_bounds()
        async with self.lock:
            today = self.conn.execute(
                """
                SELECT COUNT(*) AS count,
                       COALESCE(SUM(CASE WHEN payment_method IN ('card','balance_rub') THEN final_price_rub ELSE 0 END), 0) AS revenue_rub,
                       COALESCE(SUM(CASE WHEN payment_method IN ('stars','balance_stars') THEN final_price_stars ELSE 0 END), 0) AS revenue_stars,
                       COALESCE(SUM(CASE WHEN payment_method IN ('usdt','balance_usdt') THEN CAST(final_price_usdt AS REAL) ELSE 0 END), 0) AS revenue_usdt,
                       COALESCE(SUM(CASE WHEN payment_method IN ('gram','balance_gram') THEN CAST(final_price_gram AS REAL) ELSE 0 END), 0) AS revenue_gram
                FROM orders
                WHERE status = 'approved' AND exclude_from_stats = 0
                  AND processed_at BETWEEN ? AND ?
                """,
                (start, end),
            ).fetchone()
            total = self.conn.execute(
                """
                SELECT COUNT(*) AS count,
                       COALESCE(SUM(CASE WHEN payment_method IN ('card','balance_rub') THEN final_price_rub ELSE 0 END), 0) AS revenue_rub,
                       COALESCE(SUM(CASE WHEN payment_method IN ('stars','balance_stars') THEN final_price_stars ELSE 0 END), 0) AS revenue_stars,
                       COALESCE(SUM(CASE WHEN payment_method IN ('usdt','balance_usdt') THEN CAST(final_price_usdt AS REAL) ELSE 0 END), 0) AS revenue_usdt,
                       COALESCE(SUM(CASE WHEN payment_method IN ('gram','balance_gram') THEN CAST(final_price_gram AS REAL) ELSE 0 END), 0) AS revenue_gram,
                       COALESCE(SUM(CASE WHEN payment_method IN ('card','balance_rub') THEN 1 ELSE 0 END), 0) AS rub_orders,
                       COALESCE(SUM(CASE WHEN payment_method IN ('stars','balance_stars') THEN 1 ELSE 0 END), 0) AS stars_orders,
                       COALESCE(SUM(CASE WHEN payment_method IN ('usdt','balance_usdt') THEN 1 ELSE 0 END), 0) AS usdt_orders,
                       COALESCE(SUM(CASE WHEN payment_method IN ('gram','balance_gram') THEN 1 ELSE 0 END), 0) AS gram_orders
                FROM orders
                WHERE status = 'approved' AND exclude_from_stats = 0
                """
            ).fetchone()
            pending = self.conn.execute(
                "SELECT COUNT(*) AS count FROM orders WHERE status = 'pending'"
            ).fetchone()
            users = self.conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()
            buyers = self.conn.execute(
                """
                SELECT COUNT(DISTINCT user_id) AS count
                FROM orders
                WHERE status = 'approved' AND exclude_from_stats = 0
                """
            ).fetchone()
            top = list(
                self.conn.execute(
                    """
                    SELECT product_name, COUNT(*) AS sold,
                           COALESCE(SUM(CASE WHEN payment_method IN ('card','balance_rub') THEN final_price_rub ELSE 0 END), 0) AS revenue_rub,
                           COALESCE(SUM(CASE WHEN payment_method IN ('stars','balance_stars') THEN final_price_stars ELSE 0 END), 0) AS revenue_stars,
                           COALESCE(SUM(CASE WHEN payment_method IN ('usdt','balance_usdt') THEN CAST(final_price_usdt AS REAL) ELSE 0 END), 0) AS revenue_usdt,
                           COALESCE(SUM(CASE WHEN payment_method IN ('gram','balance_gram') THEN CAST(final_price_gram AS REAL) ELSE 0 END), 0) AS revenue_gram
                    FROM orders
                    WHERE status = 'approved' AND exclude_from_stats = 0
                    GROUP BY product_id, product_name
                    ORDER BY sold DESC, revenue_rub DESC, revenue_stars DESC
                    LIMIT 5
                    """
                ).fetchall()
            )

        total_revenue_rub = int(total["revenue_rub"])
        total_revenue_stars = int(total["revenue_stars"])
        total_revenue_usdt = decimal_amount(total["revenue_usdt"])
        total_revenue_gram = decimal_amount(total["revenue_gram"])
        rub_orders = int(total["rub_orders"])
        stars_orders = int(total["stars_orders"])
        usdt_orders = int(total["usdt_orders"])
        gram_orders = int(total["gram_orders"])

        return {
            "today_count": int(today["count"]),
            "today_revenue_rub": int(today["revenue_rub"]),
            "today_revenue_stars": int(today["revenue_stars"]),
            "today_revenue_usdt": decimal_text(today["revenue_usdt"]),
            "today_revenue_gram": decimal_text(today["revenue_gram"]),
            "total_count": int(total["count"]),
            "total_revenue_rub": total_revenue_rub,
            "total_revenue_stars": total_revenue_stars,
            "total_revenue_usdt": decimal_text(total_revenue_usdt),
            "total_revenue_gram": decimal_text(total_revenue_gram),
            "average_revenue_rub": round(total_revenue_rub / rub_orders) if rub_orders else 0,
            "average_revenue_stars": round(total_revenue_stars / stars_orders) if stars_orders else 0,
            "average_revenue_usdt": decimal_text(total_revenue_usdt / usdt_orders) if usdt_orders else "0",
            "average_revenue_gram": decimal_text(total_revenue_gram / gram_orders) if gram_orders else "0",
            "pending_count": int(pending["count"]),
            "users_count": int(users["count"]),
            "buyers_count": int(buyers["count"]),
            "top": top,
        }

    async def get_order_history(self, page: int, page_size: int = 10) -> tuple[list[sqlite3.Row], int]:
        offset = max(page, 0) * page_size
        async with self.lock:
            total = self.conn.execute("SELECT COUNT(*) AS count FROM orders").fetchone()["count"]
            rows = list(
                self.conn.execute(
                    "SELECT * FROM orders ORDER BY id DESC LIMIT ? OFFSET ?",
                    (page_size, offset),
                ).fetchall()
            )
        return rows, total

    async def get_all_user_ids(self) -> list[int]:
        async with self.lock:
            return [
                row["user_id"]
                for row in self.conn.execute(
                    "SELECT user_id FROM users WHERE is_blocked = 0 AND is_banned = 0 ORDER BY user_id"
                ).fetchall()
            ]

    async def mark_user_blocked(self, user_id: int, blocked: bool = True) -> None:
        async with self.lock:
            self.conn.execute(
                "UPDATE users SET is_blocked = ? WHERE user_id = ?",
                (1 if blocked else 0, user_id),
            )
            self.conn.commit()


# ==========================================================
# СОСТОЯНИЯ FSM
# ==========================================================


class PurchaseStates(StatesGroup):
    waiting_stars_amount = State()
    waiting_stars_account_amount = State()
    waiting_promo = State()
    waiting_receipt = State()


class TopupStates(StatesGroup):
    waiting_amount = State()
    waiting_receipt = State()


class AdminStates(StatesGroup):
    waiting_stock_value = State()
    waiting_price = State()
    waiting_product_name = State()
    waiting_new_product = State()
    waiting_new_premium = State()
    waiting_stars_account_config = State()
    waiting_new_promo = State()
    waiting_broadcast = State()
    waiting_broadcast_confirmation = State()


# ==========================================================
# ФОРМАТИРОВАНИЕ СООБЩЕНИЙ
# ==========================================================


def topup_amount_text(currency: str, amount: Any) -> str:
    if currency == "rub":
        return money(int(decimal_amount(amount)))
    if currency == "stars":
        return stars(int(decimal_amount(amount)))
    if currency == "usdt":
        return usdt(amount)
    if currency == "gram":
        return gram(amount)
    return str(amount)


def build_topup_caption(topup: sqlite3.Row, status: str | None = None) -> str:
    username = safe_username(topup["username"], topup["user_id"])
    actual_status = status or str(topup["status"])
    currency = str(topup["currency"])
    amount = topup["amount"]
    if currency == "stars":
        paid_line = f"• Оплачено: <b>{topup_amount_text(currency, amount)}</b>"
        credit_line = f"• К зачислению: <b>{money(stars_topup_credit_rub(amount))}</b> (комиссия 20%)"
    else:
        paid_line = f"• Оплачено: <b>{topup_amount_text(currency, amount)}</b>"
        credit_line = f"• К зачислению: <b>{money(rub_topup_credit_rub(amount))}</b> (комиссия 5%)"
    lines = [
        f"<b>💳 Пополнение баланса #{topup['id']}</b>",
        "",
        f"• Пользователь: {username}",
        paid_line,
        credit_line,
        "• Баланс: <b>рубли</b>",
        "• Чек: прикреплён к заявке",
        f"• Дата и время: {format_datetime(topup['created_at'])}",
    ]
    if actual_status != "pending":
        labels = {"approved": "✅ Зачислено", "cancelled": "❌ Отклонено"}
        lines.append(f"• Статус: <b>{labels.get(actual_status, html.escape(actual_status))}</b>")
    return "\n".join(lines)


def topup_admin_keyboard(topup_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="✅ Зачислить", callback_data=f"topup_admin:approve:{topup_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"topup_admin:cancel:{topup_id}"),
        ]]
    )


def build_order_caption(order: sqlite3.Row, status: str | None = None) -> str:
    actual_status = status or order["status"]
    username = safe_username(order["username"], order["user_id"])
    lines = [
        f"<b>🧾 Заявка на выдачу #{order['id']}</b>",
        "",
        f"• Username покупателя: {username}",
        f"• Что купил: <b>{html.escape(order['product_name'])}</b>",
        f"• Цена: <b>{order_amount(order)}</b>",
        f"• Способ оплаты: {PAYMENT_METHOD_LABELS.get(order['payment_method'], html.escape(order['payment_method']))}",
    ]
    if order["category"] == "stars":
        lines.extend(
            [
                f"• Количество Stars: <b>{stars(int(order['stock_units']))}</b>",
                f"• Способ выдачи: <b>{delivery_label(order['delivery_method'])}</b>",
            ]
        )
    lines.append("• Скрин оплаты: прикреплён к заявке")
    lines.append(f"• Дата и время: {format_datetime(order['created_at'])}")
    if order["discount_percent"]:
        lines.append(
            f"• Промокод: <code>{html.escape(order['promo_code'] or '')}</code> "
            f"(скидка {order['discount_percent']}%)"
        )
    if actual_status != "pending":
        lines.append(f"• Статус: {ORDER_STATUS_LABELS.get(actual_status, html.escape(actual_status))}")
    return "\n".join(lines)


def order_admin_keyboard(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Выдать", callback_data=f"order:approve:{order_id}"),
                InlineKeyboardButton(text="❌ Отменить", callback_data=f"order:cancel:{order_id}"),
            ]
        ]
    )


def product_manage_keyboard(product: sqlite3.Row) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить", callback_data=f"stock:change:add:{product['id']}")
    builder.button(text="➖ Списать", callback_data=f"stock:change:subtract:{product['id']}")
    builder.button(text="✏️ Установить количество", callback_data=f"stock:change:set:{product['id']}")
    builder.button(text="💰 Изменить цену", callback_data=f"stock:price:{product['id']}")
    builder.button(text="✏️ Изменить название", callback_data=f"stock:name:{product['id']}")
    visibility_text = "🙈 Скрыть" if product["is_visible"] else "👁 Показать"
    builder.button(text=visibility_text, callback_data=f"stock:toggle:{product['id']}")
    builder.button(text="🗑 Удалить товар", callback_data=f"stock:delete:{product['id']}")
    builder.button(text="⬅️ К складу", callback_data="admin:stock")
    builder.adjust(2, 1, 1, 1, 1, 1, 1)
    return builder.as_markup()


def product_admin_text(product: sqlite3.Row) -> str:
    lines = [
        f"<b>⚙️ {html.escape(product['name'])}</b>",
        "",
        f"Код: <code>{html.escape(product['code'])}</code>",
        f"Категория: <code>{html.escape(product['category'])}</code>",
        f"Цена: <b>{product_prices(product)}</b>",
    ]
    if product["category"] == "stars":
        lines.extend(
            [
                f"Размер одного заказа: <b>{stars(product_unit_amount(product))}</b>",
                f"Способ выдачи: <b>{delivery_label(product['delivery_method'])}</b>",
            ]
        )
    lines.extend(
        [
            f"Всего на складе: <b>{stock_label(product, product['stock'])}</b>",
            f"Зарезервировано заявками: <b>{stock_label(product, product['reserved'])}</b>",
            f"Доступно для покупки: <b>{stock_label(product, product['available'])}</b>",
            f"Видимость: {'показывается' if product['is_visible'] else 'скрыт'}",
        ]
    )
    return "\n".join(lines)


# ==========================================================
# ПРОВЕРКА ОБЯЗАТЕЛЬНОЙ ПОДПИСКИ
# ==========================================================

_subscription_url_cache: str | None = None


async def resolve_subscription_url() -> str | None:
    global _subscription_url_cache
    if _subscription_url_cache:
        return _subscription_url_cache
    configured = SUBSCRIPTION_CHANNEL_URL.strip()
    if configured.startswith("https://t.me/"):
        _subscription_url_cache = configured
        return configured
    try:
        chat = await bot.get_chat(SUBSCRIPTION_CHANNEL_ID)
        if getattr(chat, "username", None):
            _subscription_url_cache = f"https://t.me/{chat.username}"
        elif getattr(chat, "invite_link", None):
            _subscription_url_cache = chat.invite_link
        else:
            invite = await bot.create_chat_invite_link(
                SUBSCRIPTION_CHANNEL_ID,
                name="Вход через магазин",
            )
            _subscription_url_cache = invite.invite_link
    except Exception:
        logger.exception("Не удалось получить ссылку канала обязательной подписки")
    return _subscription_url_cache


async def check_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(SUBSCRIPTION_CHANNEL_ID, user_id)
        status = getattr(member.status, "value", str(member.status))
        if status in {"creator", "administrator", "member"}:
            return True
        return status == "restricted" and bool(getattr(member, "is_member", False))
    except Exception:
        logger.exception("Не удалось проверить подписку пользователя %s", user_id)
        return False


async def subscription_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    url = await resolve_subscription_url()
    if url:
        rows.append([InlineKeyboardButton(text="📢 Подписаться на канал", url=url)])
    rows.append([InlineKeyboardButton(text="✅ Проверить подписку", callback_data="subscription:check")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def send_subscription_required(message: Message) -> None:
    await answer_user_message(message, 
        "<b>Для доступа к магазину нужна подписка</b>\n\n"
        "Подпишитесь на канал и нажмите «Проверить подписку». До успешной проверки функции бота недоступны.",
        reply_markup=await subscription_keyboard(),
    )


async def safe_callback_answer(
    callback: CallbackQuery,
    text: str | None = None,
    *,
    show_alert: bool = False,
    cache_time: int = 0,
) -> bool:
    """Безопасно закрывает индикатор кнопки Telegram.

    Telegram принимает answerCallbackQuery только ограниченное время. Если callback
    уже устарел или был отвечен раньше, исключение не должно ломать обработчик.
    """
    try:
        await safe_callback_answer(callback, text=text, show_alert=show_alert, cache_time=cache_time)
        return True
    except TelegramBadRequest as exc:
        message = str(exc).lower()
        if (
            "query is too old" in message
            or "query id is invalid" in message
            or "response timeout expired" in message
        ):
            logger.debug("Callback уже устарел/отвечен: %s", exc)
            return False
        logger.warning("Не удалось ответить на callback: %s", exc)
        return False
    except Exception as exc:
        logger.debug("Не удалось закрыть callback: %s", exc)
        return False


class BanMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if not user or is_owner(user.id):
            return await handler(event, data)

        # Закрываем индикатор кнопки сразу, до запросов SQLite/Telegram API.
        # Иначе getChatMember может задержать callback дольше допустимого Telegram.
        if isinstance(event, CallbackQuery):
            await safe_callback_answer(event)

        await db.upsert_telegram_user(user)
        ban = await db.get_active_ban(user.id)
        if not ban:
            return await handler(event, data)

        reason = html.escape(str(ban["ban_reason"] or "Причина не указана"))
        text = (
            "К сожалению, вы заблокированы в этом боте.\n"
            f"Причина: {reason}.\n"
            f"Подробности: @{html.escape(BAN_SUPPORT_USERNAME.lstrip('@'))}"
        )
        if ban["banned_until"]:
            text += f"\nСрок блокировки: до {format_datetime(ban['banned_until'])}."

        if isinstance(event, CallbackQuery):
            await safe_callback_answer(event, "Вы заблокированы в этом боте.", show_alert=True)
            if event.message:
                await answer_user_message(event.message, text)
        elif isinstance(event, Message):
            await event.answer(text)
        return None


class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if not user or is_owner(user.id):
            return await handler(event, data)

        await db.upsert_telegram_user(user)

        # Кнопка проверки подписки должна быть доступна даже неподписанному пользователю.
        if isinstance(event, CallbackQuery) and event.data == "subscription:check":
            return await handler(event, data)

        # Проверяем реальное членство при каждом действии. Если пользователь отписался,
        # доступ сразу блокируется до повторной подписки.
        subscribed = await check_subscription(user.id)
        await db.set_subscription_verified(user.id, subscribed)
        if subscribed:
            return await handler(event, data)

        if isinstance(event, CallbackQuery):
            await safe_callback_answer(event, "Вы не подписаны на обязательный канал.", show_alert=True)
            if event.message:
                await send_subscription_required(event.message)
        elif isinstance(event, Message):
            await send_subscription_required(event)
        return None


# ==========================================================
# ЭКЗЕМПЛЯРЫ БОТА И БАЗЫ
# ==========================================================


db = Database(DB_PATH)
bot: Bot
dp = Dispatcher()
router.message.outer_middleware(BanMiddleware())
router.callback_query.outer_middleware(BanMiddleware())
router.message.outer_middleware(SubscriptionMiddleware())
router.callback_query.outer_middleware(SubscriptionMiddleware())
dp.include_router(router)


# ==========================================================
# КАТАЛОГ И ПОКУПКА
# ==========================================================


async def show_stars_delivery_choice(message: Message) -> None:
    # В Vinex Shop Stars продаются только подарком.
    await show_stars_gift_tariffs(message)


async def show_stars_gift_tariffs(message: Message, edit: bool = False) -> None:
    products = [
        product for product in await db.get_products(category="stars")
        if product["delivery_method"] == "gift"
    ]
    builder = InlineKeyboardBuilder()
    lines = ["<b>🎁 Stars подарком</b>", "", "Выберите тариф. Затем бот попросит ввести количество Stars вручную."]
    if not products:
        lines.append("\nСейчас Stars подарком нет в наличии.")
    else:
        for product in products:
            available = product_available(product)
            lines.append(
                f"\n<b>{stars(product_unit_amount(product))}</b> = <b>{money(int(product['price_rub']))}</b>\n"
                f"Общий остаток: <b>{stars(available)}</b>"
            )
            if available >= 15:
                builder.button(
                    text=f"Выбрать тариф {product_unit_amount(product)} ⭐",
                    callback_data=f"stars:tariff:{product['id']}",
                )
    builder.button(text="⬅️ Назад", callback_data="stars:menu")
    builder.adjust(1)
    text = "\n".join(lines)
    await send_flow_message(message, "tariff", text, reply_markup=builder.as_markup())


async def ask_promo_for_product(message: Message, state: FSMContext, product: sqlite3.Row) -> None:
    data = await state.get_data()
    if product["category"] == "stars":
        amount = int(data.get("custom_stock_units", 0))
        price = calculate_custom_stars_price(product, amount)
        delivery_text = "подарком" if product["delivery_method"] == "gift" else "на аккаунт"
        description = f"Вы выбрали <b>{stars(amount)}</b> {delivery_text} за <b>{money(price)}</b>."
    else:
        description = f"Вы выбрали <b>{html.escape(product['name'])}</b> за <b>{product_prices(product)}</b>."
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎟 Ввести промокод", callback_data="promo:enter")],
            [InlineKeyboardButton(text="➡️ Продолжить без промокода", callback_data="promo:skip")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="purchase:cancel")],
        ]
    )
    await send_flow_message(
        message, "promo", description + "\n\nЕсть промокод?", reply_markup=keyboard
    )


async def show_catalog(target: Message, category: str, edit: bool = False) -> None:
    products = await db.get_products(category=category)
    title = category_title(category)

    if not products:
        text = (
            f"<b>{title}</b>\n\n"
            "Сейчас в этом разделе нет товаров. Администратор сможет добавить их через /admin."
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔄 Обновить", callback_data=f"catalog:{category}")]]
        )
    else:
        blocks: list[str] = [f"<b>{title}</b>"]
        builder = InlineKeyboardBuilder()
        for product in products:
            available = product_available(product)
            can_buy = product_can_buy(product)
            if category == "stars":
                product_lines = [
                    f"<b>⭐ {product_unit_amount(product)} Stars</b>",
                    f"Цена: <b>{product_prices(product) if product_prices(product) != 'Бесплатно' else 'не установлена'}</b>",
                    f"В наличии: <b>{stars(available)}</b>",
                    f"Выдача: <b>{delivery_label(product['delivery_method'])}</b>",
                ]
            else:
                availability = f"{available} шт." if available > 0 else "Нет в наличии"
                product_lines = [
                    f"<b>{html.escape(product['name'])}</b>",
                    f"Цена: <b>{product_prices(product) if product_prices(product) != 'Бесплатно' else 'не установлена'}</b>",
                    f"В наличии: <b>{availability}</b>",
                ]
            blocks.append("\n".join(product_lines))
            if can_buy:
                button_name = (
                    f"🛒 Купить {product_unit_amount(product)} ⭐"
                    if category == "stars"
                    else f"🛒 Купить — {product['name']}"
                )
                builder.button(text=button_name, callback_data=f"buy:{product['id']}")
            else:
                builder.button(text="❌ Нет в наличии", callback_data="noop:out_of_stock")
        builder.button(text="🔄 Обновить", callback_data=f"catalog:{category}")
        builder.adjust(1)
        text = "\n\n".join(blocks)
        keyboard = builder.as_markup()

    section = category if category in SECTION_IMAGES else "accounts"
    await send_section_message(target, section, text, reply_markup=keyboard)


async def show_payment_methods(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    product = await db.get_product(int(data["product_id"]))
    custom_units = int(data.get("custom_stock_units", product_unit_amount(product))) if product else 0
    enough_stock = bool(product and product_available(product) >= custom_units)
    if not product or not enough_stock or not product["is_visible"]:
        await state.clear()
        await answer_user_message(
            message,
            "❌ Товар уже закончился или был скрыт.",
            reply_markup=main_menu_keyboard(),
        )
        return

    promo_code = data.get("promo_code")
    discount = 0
    if promo_code:
        valid, _, promo = await db.validate_promo(promo_code, product["category"])
        if valid and promo:
            discount = promo["discount_percent"]
        else:
            await state.update_data(promo_code=None, discount_percent=0)
            promo_code = None

    if product["category"] == "stars":
        base_price_rub = calculate_custom_stars_price(product, custom_units)
        base_price_stars = calculate_custom_stars_integer_price(
            product, "price_stars", custom_units
        )
    else:
        base_price_rub = int(product["price_rub"])
        base_price_stars = int(product["price_stars"])

    final_price_rub = max(0, round(base_price_rub * (100 - discount) / 100))
    final_price_stars = max(0, round(base_price_stars * (100 - discount) / 100))

    await state.update_data(
        final_price_rub=final_price_rub,
        final_price_stars=final_price_stars,
        discount_percent=discount,
    )

    text_lines = [
        "<b>Оформление заказа</b>",
        "",
        f"📦 Товар: <b>{html.escape(product['name'])}</b>",
    ]

    if product["category"] == "stars":
        text_lines.extend(
            [
                f"⭐ Количество: <b>{stars(custom_units)}</b>",
                f"🚚 Выдача: <b>{delivery_label(product['delivery_method'])}</b>",
            ]
        )

    if promo_code:
        text_lines.append(
            f"🎟 Промокод: <code>{html.escape(promo_code)}</code> (−{discount}%)"
        )

    text_lines.extend(
        [
            "",
            "Выберите способ оплаты:",
        ]
    )

    payment_rows = []
    if final_price_stars > 0:
        payment_rows.append(
            [
                InlineKeyboardButton(
                    text=f"⭐ Оплатить {stars(final_price_stars)}",
                    callback_data="payment_method:stars",
                )
            ]
        )
    if final_price_rub > 0:
        payment_rows.append(
            [
                InlineKeyboardButton(
                    text=f"₽ Оплатить {money(final_price_rub)}",
                    callback_data="payment_method:card",
                )
            ]
        )
    payment_rows.append(
        [InlineKeyboardButton(text="❌ Отменить", callback_data="purchase:cancel")]
    )

    await send_flow_message(
        message,
        "payment_methods",
        "\n".join(text_lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=payment_rows),
    )


@router.callback_query(F.data == "subscription:check")
async def callback_check_subscription(callback: CallbackQuery, state: FSMContext) -> None:
    subscribed = await check_subscription(callback.from_user.id)
    await db.set_subscription_verified(callback.from_user.id, subscribed)
    if subscribed:
        await safe_callback_answer(callback, "Подписка подтверждена!")
        await state.clear()
        if callback.message:
            await send_section_message(
                callback.message,
                "menu",
                "<b>Приветствуем вас в Vinex shop! ❤️‍🔥</b>\nздесь вы можете приобрести разные товары",
                reply_markup=main_menu_keyboard(is_owner(callback.from_user.id)),
            )
    else:
        await safe_callback_answer(callback, "Подписка пока не найдена. Подпишитесь и попробуйте снова.", show_alert=True)


@router.message(CommandStart())
async def command_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await db.upsert_user(message)
    text = (
        "<b>Приветствуем вас в Vinex shop! ❤️‍🔥</b>\n"
        "здесь вы можете приобрести разные товары"
    )
    await send_section_message(
        message,
        "menu",
        text,
        reply_markup=main_menu_keyboard(bool(message.from_user and is_owner(message.from_user.id))),
        force_new=True,
    )


@router.message(F.text == "store 🛍️")
async def menu_store(message: Message, state: FSMContext) -> None:
    await state.clear()
    await db.upsert_user(message)
    await send_section_message(
        message,
        "store",
        "<b>store 🛍️</b>\n\nВыберите раздел магазина:",
        reply_markup=store_menu_keyboard(),
    )


@router.callback_query(F.data == "store:accounts")
async def store_accounts(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_callback_answer(callback)
    await state.clear()
    if callback.message:
        await show_catalog(callback.message, "accounts")


@router.callback_query(F.data == "store:premium")
async def store_premium(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_callback_answer(callback)
    await state.clear()
    if not callback.message:
        return
    if await db.crypto_mode_enabled():
        await answer_user_message(callback.message, "❌ В данный момент товара нет в наличии.")
        return
    await show_catalog(callback.message, "premium")


@router.callback_query(F.data == "store:stars")
async def store_stars(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_callback_answer(callback)
    await state.clear()
    if callback.message:
        await show_stars_gift_tariffs(callback.message)


async def show_balance_history(message: Message, user_id: int) -> None:
    balance = await db.get_user_balance(user_id)
    rows = await db.get_balance_history(user_id, 20)

    lines = [
        "<b>📜 История баланса</b>",
        "",
        f"Текущий баланс: <b>{format_user_balance(balance)}</b>",
        "",
    ]
    if not rows:
        lines.append("История пока пустая. Здесь появятся пополнения и списания за покупки.")
    else:
        for row in rows:
            amount = int(row["amount_rub"])
            icon = "🟢" if amount > 0 else "🔴"
            sign = "+" if amount > 0 else "−"
            lines.append(
                f"{icon} <b>{sign}{money(abs(amount))}</b> — {html.escape(str(row['description']))}\n"
                f"   <i>{format_datetime(row['created_at'])}</i>"
            )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="balance:back")],
        ]
    )
    await send_section_message(
        message,
        "balance_history",
        "\n\n".join(lines),
        reply_markup=keyboard,
    )


@router.callback_query(F.data == "balance:history")
async def callback_balance_history(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_callback_answer(callback)
    await state.clear()
    if callback.message and callback.from_user:
        await show_balance_history(callback.message, callback.from_user.id)


@router.callback_query(F.data == "balance:back")
async def callback_balance_back(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_callback_answer(callback)
    await state.clear()
    if not callback.message or not callback.from_user:
        return
    balance = await db.get_user_balance(callback.from_user.id)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="₽ Рубли — комиссия 5%", callback_data="topup:rub")],
            [InlineKeyboardButton(text="⭐ Stars — комиссия 20%", callback_data="topup:stars")],
            [InlineKeyboardButton(text="📜 История баланса", callback_data="balance:history")],
        ]
    )
    await send_section_message(
        callback.message,
        "balance",
        "<b>Пополнить баланс 💳</b>\n\n"
        f"Ваш баланс: <b>{format_user_balance(balance)}</b>\n\n"
        "Баланс хранится только в рублях.\n"
        "• Рубли: комиссия 5% — например, отправили 100 ₽, на баланс поступит 95 ₽.\n"
        "• Stars: комиссия 20% — например, отправили 100 ⭐, на баланс поступит 80 ₽.\n\n"
        "Выберите способ пополнения:",
        reply_markup=keyboard,
    )




@router.callback_query(F.data.startswith("topup:"))
async def callback_topup_currency_disabled(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_callback_answer(
        callback,
        "Внутренний баланс отключён. Выберите оплату рублями или Stars.",
        show_alert=True,
    )


@router.message(TopupStates.waiting_amount)
async def process_topup_amount(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    currency = str(data.get("topup_currency", ""))
    amount = parse_topup_amount(currency, message.text or "")
    if not amount:
        await answer_user_message(
            message,
            "❌ Укажите корректное положительное целое число.",
        )
        return
    await state.update_data(topup_amount=amount)

    if currency == "rub":
        phone = T_BANK_PHONE.strip()
        recipient = T_BANK_RECIPIENT.strip()
        if not phone or phone == "+7XXXXXXXXXX":
            await state.clear()
            await answer_user_message(message, "❌ Реквизиты СБП пока не настроены.")
            return
        credit_rub = rub_topup_credit_rub(amount)
        payment_text = (
            "<b>Пополнение баланса через СБП / Т-Банк</b>\n\n"
            f"Перевести: <b>{money(int(amount))}</b>\n"
            f"Комиссия: <b>5%</b>\n"
            f"На баланс поступит: <b>{money(credit_rub)}</b>\n"
            f"Банк: <b>{html.escape(T_BANK_NAME.strip() or 'Т-Банк')}</b>\n"
            f"Номер: <code>{html.escape(phone)}</code>\n"
            f"Получатель: <b>{html.escape(recipient or 'проверьте перед переводом')}</b>\n\n"
            "После перевода нажмите кнопку ниже и отправьте чек."
        )
    elif currency == "stars":
        receiver = STARS_RECEIVER_USERNAME.strip().lstrip("@")
        if not receiver:
            await state.clear()
            await answer_user_message(message, "❌ Получатель Stars пока не настроен.")
            return
        credit_rub = stars_topup_credit_rub(amount)
        if credit_rub <= 0:
            await answer_user_message(message, "❌ Сумма слишком маленькая для пополнения.")
            return
        payment_text = (
            "<b>Пополнение баланса через Telegram Stars</b>\n\n"
            f"Отправить: <b>{stars(int(amount))}</b>\n"
            f"Комиссия: <b>20%</b>\n"
            f"На баланс поступит: <b>{money(credit_rub)}</b>\n"
            f"Получатель: @{html.escape(receiver)}\n\n"
            "После оплаты нажмите кнопку ниже и отправьте скриншот подтверждения."
        )
    else:
        await state.clear()
        await answer_user_message(message, "❌ Этот способ пополнения отключён.")
        return

    await state.set_state(TopupStates.waiting_receipt)
    await send_flow_message(
        message,
        "topup_receipt",
        payment_text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📎 Отправить чек", callback_data="topup_receipt:ready")],
                [InlineKeyboardButton(text="❌ Отменить", callback_data="topup_receipt:cancel")],
            ]
        ),
    )


@router.callback_query(F.data == "topup_receipt:ready")
async def callback_topup_receipt_ready(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not data.get("topup_currency") or not data.get("topup_amount"):
        await safe_callback_answer(callback, "Начните пополнение заново.", show_alert=True)
        return
    await safe_callback_answer(callback)
    await state.set_state(TopupStates.waiting_receipt)
    if callback.message:
        await send_flow_message(
            callback.message,
            "topup_receipt",
            "Отправьте чек или скриншот оплаты одним сообщением — как фото или документ.",
        )


@router.callback_query(F.data == "topup_receipt:cancel")
async def callback_topup_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_callback_answer(callback, "Пополнение отменено.")
    await state.clear()
    if callback.message:
        await answer_user_message(
            callback.message,
            "Пополнение отменено.",
            reply_markup=main_menu_keyboard(is_owner(callback.from_user.id)),
        )


@router.message(TopupStates.waiting_receipt)
async def process_topup_receipt(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        return
    receipt_file_id: str | None = None
    receipt_type: str | None = None
    if message.photo:
        receipt_file_id = message.photo[-1].file_id
        receipt_type = "photo"
    elif message.document:
        receipt_file_id = message.document.file_id
        receipt_type = "document"
    if not receipt_file_id or not receipt_type:
        await answer_user_message(message, "❌ Отправьте чек как фото или документ.")
        return

    data = await state.get_data()
    currency = str(data.get("topup_currency", ""))
    amount = str(data.get("topup_amount", ""))
    if currency not in {"rub", "stars"} or not parse_topup_amount(currency, amount):
        await state.clear()
        await answer_user_message(message, "Сессия пополнения устарела. Начните заново.")
        return

    await db.upsert_user(message)
    topup = await db.create_balance_topup(
        message.from_user.id,
        message.from_user.username,
        currency,
        amount,
        receipt_file_id,
        receipt_type,
    )
    await state.clear()
    if not topup:
        await answer_user_message(message, "❌ Не удалось создать заявку на пополнение.")
        return

    caption = build_topup_caption(topup)
    try:
        if receipt_type == "photo":
            await bot.send_photo(OWNER_ID, receipt_file_id, caption=caption, reply_markup=topup_admin_keyboard(topup["id"]))
        else:
            await bot.send_document(OWNER_ID, receipt_file_id, caption=caption, reply_markup=topup_admin_keyboard(topup["id"]))
    except Exception:
        logger.exception("Не удалось отправить пополнение владельцу")
        await db.cancel_balance_topup(int(topup["id"]), OWNER_ID)
        await answer_user_message(message, "❌ Не удалось передать заявку владельцу. Попробуйте позже.")
        return

    credit_rub = rub_topup_credit_rub(amount) if currency == "rub" else stars_topup_credit_rub(amount)
    await send_flow_message(
        message,
        "topup_pending",
        f"✅ Заявка на пополнение <b>#{topup['id']}</b> отправлена на проверку.\n"
        f"Оплачено: <b>{topup_amount_text(currency, amount)}</b>.\n"
        f"После подтверждения на баланс поступит: <b>{money(credit_rub)}</b>.",
        reply_markup=main_menu_keyboard(False),
    )


@router.callback_query(F.data.startswith("topup_admin:approve:"))
async def callback_topup_approve(callback: CallbackQuery) -> None:
    if not is_owner(callback.from_user.id):
        await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
        return
    topup_id = int((callback.data or "").rsplit(":", 1)[1])
    status, topup, user = await db.approve_balance_topup(topup_id, callback.from_user.id)
    if status != "approved" or not topup:
        await safe_callback_answer(callback, "Заявка уже обработана или не найдена.", show_alert=True)
        return
    await safe_callback_answer(callback, "Баланс пополнен.")
    if callback.message:
        try:
            await callback.message.edit_caption(caption=build_topup_caption(topup, "approved"), reply_markup=None)
        except TelegramBadRequest:
            pass
    try:
        credit_rub = (
            rub_topup_credit_rub(topup["amount"])
            if str(topup["currency"]) == "rub"
            else stars_topup_credit_rub(topup["amount"])
        )
        await send_push_notification(
            int(topup["user_id"]),
            "✅ <b>Пополнение баланса подтверждено</b>\n\n"
            f"Зачислено: <b>{money(credit_rub)}</b>\n"
            f"Текущий баланс: <b>{format_user_balance(user)}</b>",
            reply_markup=main_menu_keyboard(False),
            image=FLOW_IMAGES.get("topup_approved", ""),
        )
    except Exception:
        logger.exception("Не удалось уведомить пользователя о пополнении")


@router.callback_query(F.data.startswith("topup_admin:cancel:"))
async def callback_topup_reject(callback: CallbackQuery) -> None:
    if not is_owner(callback.from_user.id):
        await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
        return
    topup_id = int((callback.data or "").rsplit(":", 1)[1])
    status, topup = await db.cancel_balance_topup(topup_id, callback.from_user.id)
    if status != "cancelled" or not topup:
        await safe_callback_answer(callback, "Заявка уже обработана или не найдена.", show_alert=True)
        return
    await safe_callback_answer(callback, "Пополнение отклонено.")
    if callback.message:
        try:
            await callback.message.edit_caption(caption=build_topup_caption(topup, "cancelled"), reply_markup=None)
        except TelegramBadRequest:
            pass
    try:
        await send_push_notification(
            int(topup["user_id"]),
            "❌ <b>Пополнение баланса отклонено</b>\n\n"
            "Если есть вопросы — обратитесь в поддержку.",
            reply_markup=main_menu_keyboard(False),
            image=FLOW_IMAGES.get("topup_cancelled", ""),
        )
    except Exception:
        logger.exception("Не удалось уведомить пользователя об отклонении пополнения")


@router.message(Command("cancel"))
async def command_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    await state.clear()
    if current:
        await answer_user_message(message, "Действие отменено.", reply_markup=main_menu_keyboard())
    else:
        await answer_user_message(message, "Нет активного действия.", reply_markup=main_menu_keyboard())


@router.message(Command("myorders"))
async def command_my_orders(message: Message) -> None:
    await db.upsert_user(message)
    if not message.from_user:
        return
    orders = await db.get_user_orders(message.from_user.id)
    if not orders:
        await answer_user_message(message, "У вас пока нет заказов.")
        return
    lines = ["<b>Ваши последние заказы</b>"]
    for order in orders:
        lines.append(
            f"\n<b>#{order['id']}</b> · {html.escape(order['product_name'])}\n"
            f"{order_amount(order)} · {ORDER_STATUS_LABELS.get(order['status'], order['status'])}\n"
            f"{format_datetime(order['created_at'])}"
        )
    await answer_user_message(message, "\n".join(lines))


@router.message(F.text == "🛒 Купить аккаунты")
async def menu_accounts(message: Message, state: FSMContext) -> None:
    await state.clear()
    await db.upsert_user(message)
    await show_catalog(message, "accounts")


@router.message(F.text == "⭐ Купить Stars")
async def menu_stars(message: Message, state: FSMContext) -> None:
    await state.clear()
    await db.upsert_user(message)
    await show_stars_gift_tariffs(message)


@router.callback_query(F.data == "stars:menu")
async def callback_stars_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_callback_answer(callback)
    await state.clear()
    if callback.message:
        await show_stars_gift_tariffs(callback.message)


@router.callback_query(F.data == "stars:gift")
async def callback_stars_gift(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_callback_answer(callback)
    await state.clear()
    if callback.message:
        await show_stars_gift_tariffs(callback.message, edit=True)


@router.callback_query(F.data == "stars:account")
async def callback_stars_account(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await safe_callback_answer(callback)
        return
    if await db.crypto_mode_enabled():
        await safe_callback_answer(callback, "В данный момент товара нет в наличии.", show_alert=True)
        await answer_user_message(callback.message, "❌ В данный момент товара нет в наличии.")
        return

    products = [
        product for product in await db.get_products(category="stars")
        if product["delivery_method"] == "account"
    ]
    product = products[0] if products else None
    if not product or not product_can_buy(product) or product_available(product) < 50:
        await safe_callback_answer(callback, "В данный момент товара нет в наличии.", show_alert=True)
        await answer_user_message(callback.message, "❌ В данный момент товара нет в наличии.")
        return

    await safe_callback_answer(callback)
    await state.clear()
    await state.update_data(product_id=int(product["id"]), promo_code=None, discount_percent=0)
    await state.set_state(PurchaseStates.waiting_stars_account_amount)
    await send_flow_message(
        callback.message,
        "stars_amount",
        "<b>👤 Stars на аккаунт</b>\n\n"
        f"Минимум: <b>50 ⭐</b>\n"
        f"Доступно: <b>{stars(product_available(product))}</b>\n"
        f"Базовый тариф: <b>{stars(product_unit_amount(product))} = {money(int(product['price_rub']))}</b>\n\n"
        "Введите нужное количество Stars целым числом. Для отмены: /cancel",
    )


@router.message(PurchaseStates.waiting_stars_account_amount, F.text)
async def process_stars_account_amount(message: Message, state: FSMContext) -> None:
    try:
        amount = int(message.text.strip())
    except ValueError:
        await answer_user_message(message, "Введите количество Stars целым числом.")
        return
    if amount < 50:
        await answer_user_message(message, "❌ Минимальное количество — 50 Stars.")
        return
    if await db.crypto_mode_enabled():
        await state.clear()
        await answer_user_message(message, "❌ В данный момент товара нет в наличии.")
        return
    data = await state.get_data()
    product = await db.get_product(int(data.get("product_id", 0)))
    if not product or product["delivery_method"] != "account":
        await state.clear()
        await answer_user_message(message, "Товар больше недоступен. Начните покупку заново.")
        return
    if amount > product_available(product):
        await answer_user_message(message, f"❌ На складе доступно только {stars(product_available(product))}.")
        return
    await state.update_data(custom_stock_units=amount)
    await state.set_state(None)
    await ask_promo_for_product(message, state, product)


@router.callback_query(F.data.startswith("stars:tariff:"))
async def callback_stars_tariff(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await safe_callback_answer(callback)
        return
    product_id = int(callback.data.rsplit(":", 1)[1])
    product = await db.get_product(product_id)
    if (
        not product or product["category"] != "stars" or product["delivery_method"] != "gift"
        or not product["is_visible"] or product_available(product) < 15
    ):
        await safe_callback_answer(callback, "Stars по этому тарифу закончились.", show_alert=True)
        return
    await safe_callback_answer(callback)
    await state.clear()
    await state.update_data(product_id=product_id, promo_code=None, discount_percent=0)
    await state.set_state(PurchaseStates.waiting_stars_amount)
    allowed = [amount for amount in ALLOWED_GIFT_STAR_AMOUNTS if amount <= product_available(product)]
    await send_flow_message(
        callback.message,
        "stars_amount",
        f"<b>🎁 Stars подарком</b>\n\n"
        f"Тариф: <b>{stars(product_unit_amount(product))} = {money(int(product['price_rub']))}</b>\n"
        f"Доступно: <b>{stars(product_available(product))}</b>\n\n"
        "Введите количество Stars одним числом.\n"
        "Минимум: <b>15 ⭐</b>. Нельзя вводить больше остатка.\n"
        f"Разрешённые значения сейчас: <code>{', '.join(map(str, allowed)) or 'нет доступных значений'}</code>\n\n"
        "Для отмены: /cancel",
    )


@router.message(PurchaseStates.waiting_stars_amount, F.text)
async def process_stars_amount(message: Message, state: FSMContext) -> None:
    try:
        amount = int(message.text.strip())
    except ValueError:
        await answer_user_message(message, "Введите количество Stars целым числом.")
        return
    data = await state.get_data()
    product = await db.get_product(int(data.get("product_id", 0)))
    if not product or product["category"] != "stars" or product["delivery_method"] != "gift":
        await state.clear()
        await answer_user_message(message, "Тариф больше недоступен. Начните покупку заново.")
        return
    available = product_available(product)
    if amount < 15:
        await answer_user_message(message, "❌ Нельзя заказать меньше 15 Stars.")
        return
    if amount > available:
        await answer_user_message(message, f"❌ На складе доступно только {stars(available)}.")
        return
    if not is_allowed_gift_star_amount(amount):
        allowed = [value for value in ALLOWED_GIFT_STAR_AMOUNTS if value <= available]
        await answer_user_message(message, 
            "❌ Такое количество недоступно. Выберите одно из значений:\n"
            f"<code>{', '.join(map(str, allowed))}</code>"
        )
        return
    await state.update_data(custom_stock_units=amount)
    await state.set_state(None)
    await ask_promo_for_product(message, state, product)


@router.message(F.text == "💎 Купить Premium")
async def menu_premium(message: Message, state: FSMContext) -> None:
    await state.clear()
    await db.upsert_user(message)
    if await db.crypto_mode_enabled():
        await send_section_message(
            message,
            "premium",
            "💎 <b>Telegram Premium</b>\n\n❌ В данный момент товара нет в наличии.",
        )
        return
    await show_catalog(message, "premium")


@router.message(F.text == "Отзывы 📭")
@router.message(F.text == "📝 Отзывы")
async def menu_reviews(message: Message) -> None:
    await db.upsert_user(message)
    url = REVIEWS_CHANNEL_URL if valid_tme_url(REVIEWS_CHANNEL_URL) else "https://t.me/telegram"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="📝 Открыть отзывы", url=url)]]
    )
    await send_section_message(
        message,
        "reviews",
        "Отзывы покупателей находятся в отдельном Telegram-канале.",
        reply_markup=keyboard,
    )


@router.message(F.text == "Поддержка 🎧")
@router.message(F.text == "👨‍💻 Поддержка")
async def menu_support(message: Message) -> None:
    await db.upsert_user(message)
    username = SUPPORT_USERNAME.lstrip("@").strip()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👨‍💻 Написать администратору", url=f"https://t.me/{username}")]
        ]
    )
    await send_section_message(
        message,
        "support",
        "Нажмите кнопку ниже, чтобы открыть чат с поддержкой.",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("catalog:"))
async def callback_catalog(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_callback_answer(callback)
    await state.clear()
    category = callback.data.split(":", 1)[1]
    if callback.message:
        if category == "stars":
            await show_stars_gift_tariffs(callback.message, edit=True)
        else:
            await show_catalog(callback.message, category, edit=True)


@router.callback_query(F.data == "noop:out_of_stock")
async def callback_out_of_stock(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback, "Товар закончился.", show_alert=True)


@router.callback_query(F.data.startswith("buy:"))
async def callback_buy(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not callback.message:
        await safe_callback_answer(callback)
        return
    product_id = int(callback.data.split(":", 1)[1])
    product = await db.get_product(product_id)
    if product and await db.crypto_mode_enabled():
        blocked_by_crypto = product["category"] == "premium" or (
            product["category"] == "stars" and product["delivery_method"] == "account"
        )
        if blocked_by_crypto:
            await safe_callback_answer(callback, "В данный момент товара нет в наличии.", show_alert=True)
            return
    if not product or not product["is_visible"] or not product_can_buy(product):
        await safe_callback_answer(callback, "Товар уже закончился.", show_alert=True)
        return

    await safe_callback_answer(callback)
    await state.clear()
    await state.update_data(product_id=product_id, promo_code=None, discount_percent=0)
    if product["category"] == "stars":
        await state.set_state(PurchaseStates.waiting_stars_amount)
        allowed = [amount for amount in ALLOWED_GIFT_STAR_AMOUNTS if amount <= product_available(product)]
        await send_flow_message(
            callback.message,
            "stars_amount",
            f"Введите количество Stars. Доступно: <b>{stars(product_available(product))}</b>.\n"
            f"Разрешённые значения: <code>{', '.join(map(str, allowed))}</code>",
        )
        return
    await ask_promo_for_product(callback.message, state, product)


@router.callback_query(F.data == "promo:enter")
async def callback_enter_promo(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_callback_answer(callback)
    data = await state.get_data()
    if "product_id" not in data:
        await safe_callback_answer(callback, "Начните покупку заново.", show_alert=True)
        return
    await state.set_state(PurchaseStates.waiting_promo)
    if callback.message:
        await send_flow_message(
            callback.message,
            "promo",
            "Введите промокод одним сообщением. Для отмены: /cancel",
        )


@router.message(PurchaseStates.waiting_promo, F.text)
async def process_promo(message: Message, state: FSMContext) -> None:
    code = message.text.strip().upper()
    data = await state.get_data()
    product = await db.get_product(int(data.get("product_id", 0)))
    if not product:
        await state.clear()
        await answer_user_message(message, "Товар больше недоступен. Начните покупку заново.")
        return
    valid, info, promo = await db.validate_promo(code, product["category"])
    if not valid or not promo:
        await answer_user_message(message, f"❌ {html.escape(info)}\nВведите другой код или нажмите /cancel.")
        return
    await state.update_data(promo_code=promo["code"], discount_percent=promo["discount_percent"])
    await state.set_state(None)
    await answer_user_message(message, f"✅ Промокод применён. Скидка: <b>{promo['discount_percent']}%</b>.")
    await show_payment_methods(message, state)


@router.callback_query(F.data == "promo:skip")
async def callback_skip_promo(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if "product_id" not in data:
        await safe_callback_answer(callback, "Начните покупку заново.", show_alert=True)
        return
    await safe_callback_answer(callback)
    await state.update_data(promo_code=None, discount_percent=0)
    if callback.message:
        await show_payment_methods(callback.message, state)




@router.callback_query(F.data.startswith("pay:"))
async def callback_payment_method(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await safe_callback_answer(callback)
        return

    method = callback.data.split(":", 1)[1]
    if method not in {"card", "stars"}:
        await safe_callback_answer(callback, "Этот способ оплаты отключён.", show_alert=True)
        return

    data = await state.get_data()
    if "product_id" not in data:
        await safe_callback_answer(callback, "Начните покупку заново.", show_alert=True)
        return

    product = await db.get_product(int(data["product_id"]))
    custom_units = int(data.get("custom_stock_units", product_unit_amount(product))) if product else 0
    if not product or product_available(product) < custom_units:
        await state.clear()
        await safe_callback_answer(
            callback,
            "Товар закончился или остатка недостаточно.",
            show_alert=True,
        )
        return

    final_price_rub = int(data.get("final_price_rub", product["price_rub"]))
    final_price_stars = int(data.get("final_price_stars", product["price_stars"]))

    if method == "card" and final_price_rub <= 0:
        await safe_callback_answer(
            callback,
            "Оплата рублями для этого товара недоступна.",
            show_alert=True,
        )
        return

    if method == "stars" and final_price_stars <= 0:
        await safe_callback_answer(
            callback,
            "Оплата Stars для этого товара недоступна.",
            show_alert=True,
        )
        return

    # Товар категории Stars нельзя оплачивать теми же Stars, которые покупаются.
    if product["category"] == "stars" and method == "stars":
        await safe_callback_answer(
            callback,
            "Покупка Stars не может оплачиваться Stars.",
            show_alert=True,
        )
        return

    await safe_callback_answer(callback)

    if method == "stars":
        receiver = STARS_RECEIVER_USERNAME.strip().lstrip("@") or "fegote"
        payment_text = (
            f"<b>⭐ Оплата Stars</b>\n\n"
            f"Оплатите <b>{stars(final_price_stars)}</b> владельцу "
            f"@{html.escape(receiver)}, после чего пришлите скриншот оплаты."
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"⭐ Перейти к @{receiver}",
                        url=f"https://t.me/{receiver}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="📎 Пришлите скриншот оплаты",
                        callback_data="receipt:start",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Отменить",
                        callback_data="purchase:cancel",
                    )
                ],
            ]
        )
        await state.update_data(payment_method="stars")
        await send_flow_message(
            callback.message,
            "payment_stars",
            payment_text,
            reply_markup=keyboard,
        )
        return

    phone = T_BANK_PHONE.strip()
    recipient = T_BANK_RECIPIENT.strip()
    bank_name = T_BANK_NAME.strip() or "Т-Банк"

    if not phone or phone == "+7XXXXXXXXXX":
        await safe_callback_answer(
            callback,
            "Реквизиты для оплаты рублями ещё не настроены владельцем.",
            show_alert=True,
        )
        return

    payment_text = (
        "<b>💳 Оплата рублями</b>\n\n"
        f"Сумма: <b>{money(final_price_rub)}</b>\n"
        f"Банк: <b>{html.escape(bank_name)}</b>\n"
        f"Номер телефона: <code>{html.escape(phone)}</code>\n"
        f"Получатель: <b>{html.escape(recipient or 'уточните перед переводом')}</b>\n\n"
        "Переведите точную сумму, после чего пришлите скриншот оплаты."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📎 Пришлите скриншот оплаты",
                    callback_data="receipt:start",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data="purchase:cancel",
                )
            ],
        ]
    )
    await state.update_data(payment_method="card")
    await send_flow_message(
        callback.message,
        "payment_tbank",
        payment_text,
        reply_markup=keyboard,
    )


@router.callback_query(F.data == "receipt:start")
async def callback_receipt_start(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if "payment_method" not in data or "product_id" not in data:
        await safe_callback_answer(callback, "Начните покупку заново.", show_alert=True)
        return
    await safe_callback_answer(callback)
    await state.set_state(PurchaseStates.waiting_receipt)
    if callback.message:
        method = str(data.get("payment_method"))
        prompts = {
            "stars": "Отправьте <b>скриншот оплаты Stars</b> одним сообщением.",
            "card": "Отправьте <b>скриншот оплаты рублями</b> одним сообщением.",
        }
        prompt = prompts.get(method, "Отправьте подтверждение оплаты одним сообщением.")
        await send_flow_message(
            callback.message,
            "receipt_request",
            prompt + "\n\nМожно отправить изображение как фото или документ.",
        )


@router.callback_query(F.data == "purchase:cancel")
async def callback_purchase_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_callback_answer(callback, "Покупка отменена.")
    await state.clear()
    if callback.message:
        await answer_user_message(callback.message, "Покупка отменена.", reply_markup=main_menu_keyboard())


@router.message(PurchaseStates.waiting_receipt)
async def process_receipt(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        return

    receipt_file_id: str | None = None
    receipt_type: str | None = None
    if message.photo:
        receipt_file_id = message.photo[-1].file_id
        receipt_type = "photo"
    elif message.document:
        receipt_file_id = message.document.file_id
        receipt_type = "document"

    if not receipt_file_id or not receipt_type:
        data = await state.get_data()
        method = str(data.get("payment_method"))
        names = {"stars": "скриншот оплаты Stars", "card": "скриншот оплаты рублями"}
        await answer_user_message(
            message,
            f"❌ Отправьте {names.get(method, 'подтверждение оплаты')} как фото или документ.",
        )
        return

    data = await state.get_data()
    product_id = data.get("product_id")
    payment_method = data.get("payment_method")
    if not product_id or payment_method not in PAYMENT_METHOD_LABELS:
        await state.clear()
        await answer_user_message(message, "Сессия покупки устарела. Начните заказ заново.", reply_markup=main_menu_keyboard())
        return

    await db.upsert_user(message)
    success, info, order = await db.create_pending_order(
        user_id=message.from_user.id,
        username=message.from_user.username,
        product_id=int(product_id),
        payment_method=payment_method,
        receipt_file_id=receipt_file_id,
        receipt_type=receipt_type,
        promo_code=data.get("promo_code"),
        custom_stock_units=data.get("custom_stock_units"),
    )
    await state.clear()

    if not success or not order:
        await answer_user_message(message, f"❌ {html.escape(info)}", reply_markup=main_menu_keyboard())
        return

    caption = build_order_caption(order)
    keyboard = order_admin_keyboard(order["id"])

    try:
        if receipt_type == "photo":
            await bot.send_photo(OWNER_ID, receipt_file_id, caption=caption, reply_markup=keyboard)
        else:
            await bot.send_document(OWNER_ID, receipt_file_id, caption=caption, reply_markup=keyboard)
    except Exception:
        logger.exception("Не удалось отправить заказ владельцу")
        # Освобождаем резерв, потому что владелец не получил заявку.
        await db.cancel_order(order["id"], OWNER_ID)
        await answer_user_message(message, 
            "❌ Не удалось передать заявку администратору. Заказ отменён, попробуйте позже.",
            reply_markup=main_menu_keyboard(),
        )
        return

    await send_flow_message(
        message,
        "receipt_sent",
        f"✅ Чек отправлен администратору.\n\nНомер заявки: <b>#{order['id']}</b>. "
        "После ручной проверки вам придёт уведомление.",
        reply_markup=main_menu_keyboard(),
    )


# ==========================================================
# ОБРАБОТКА ЗАКАЗОВ ВЛАДЕЛЬЦЕМ
# ==========================================================


async def edit_admin_order_message(callback: CallbackQuery, order: sqlite3.Row) -> None:
    if not callback.message:
        return
    try:
        await callback.message.edit_caption(caption=build_order_caption(order), reply_markup=None)
    except TelegramBadRequest:
        try:
            await safe_edit_text(callback.message, build_order_caption(order), reply_markup=None)
        except TelegramBadRequest:
            pass


@router.callback_query(F.data.startswith("order:approve:"))
async def callback_approve_order(callback: CallbackQuery) -> None:
    if not is_owner(callback.from_user.id):
        await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
        return

    order_id = int(callback.data.rsplit(":", 1)[1])
    result, order = await db.approve_order(order_id, callback.from_user.id)

    if result == "approved" and order:
        await edit_admin_order_message(callback, order)
        try:
            delivery_keyboard = None
            delivery_text = "Администратор подтвердил оплату."
            if order["category"] == "accounts" and order["delivery_phone"]:
                delivery_text += "\n\nНажмите кнопку ниже, чтобы получить номер аккаунта."
                delivery_keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="📱 Получить номер аккаунта",
                                callback_data=f"order_delivery:{order['id']}",
                            )
                        ]
                    ]
                )

            await send_bot_image(
                int(order["user_id"]),
                FLOW_IMAGES.get("order_confirmed", ""),
                f"✅ <b>Заказ #{order['id']} подтверждён!</b>\n\n"
                f"Товар: {html.escape(order['product_name'])}\n"
                f"Сумма: {order_amount(order)}\n\n"
                f"{delivery_text}",
                reply_markup=delivery_keyboard,
            )

        except Exception:
            logger.exception("Не удалось уведомить покупателя заказа #%s", order_id)

        await safe_callback_answer(callback, 
            "Заказ подтверждён, товар списан и покупатель уведомлён.",
            show_alert=True,
        )
        return

    messages = {
        "approved": "Этот заказ уже был подтверждён.",
        "cancelled": "Этот заказ уже отменён.",
        "not_found": "Заказ не найден.",
        "product_missing": "Товар удалён из базы.",
        "no_stock": "Нельзя подтвердить: проблема с остатком или резервом.",
        "no_account_stock": "Нельзя подтвердить: для этого товара нет свободного номера на складе.",
        "error": "Ошибка базы данных.",
    }
    await safe_callback_answer(callback, messages.get(result, "Не удалось обработать заказ."), show_alert=True)


@router.callback_query(F.data.startswith("order_delivery:"))
async def callback_order_delivery(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        await safe_callback_answer(callback)
        return

    try:
        order_id = int(callback.data.rsplit(":", 1)[1])
    except (TypeError, ValueError):
        await safe_callback_answer(callback, "Некорректный заказ.", show_alert=True)
        return

    order = await db.get_order_delivery(order_id, callback.from_user.id)
    if not order:
        await safe_callback_answer(
            callback,
            "Заказ не найден или ещё не подтверждён.",
            show_alert=True,
        )
        return

    phone = order["delivery_phone"]
    if not phone:
        await safe_callback_answer(
            callback,
            "Для этого заказа номер ещё не подготовлен.",
            show_alert=True,
        )
        return

    await safe_callback_answer(callback)
    await answer_user_message(
        callback.message,
        f"📱 <b>Номер аккаунта</b>\n\n"
        f"<code>{html.escape(str(phone))}</code>\n\n"
        "Используйте этот номер для входа в Telegram. "
        "Код авторизации бот автоматически не получает и не передаёт.",
    )


@router.callback_query(F.data.startswith("order:cancel:"))
async def callback_cancel_order(callback: CallbackQuery) -> None:
    if not is_owner(callback.from_user.id):
        await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
        return

    order_id = int(callback.data.rsplit(":", 1)[1])
    result, order = await db.cancel_order(order_id, callback.from_user.id)

    if result == "cancelled" and order:
        await edit_admin_order_message(callback, order)
        try:
            await send_bot_image(
                int(order["user_id"]),
                FLOW_IMAGES.get("order_cancelled", ""),
                f"❌ <b>Заказ #{order['id']} отменён.</b>\n\n"
                "Оплата не была подтверждена. По вопросам обратитесь в поддержку.",
            )
        except Exception:
            logger.exception("Не удалось уведомить покупателя об отмене #%s", order_id)
        await safe_callback_answer(callback, "Заказ отменён, резерв возвращён.", show_alert=True)
        return

    messages = {
        "approved": "Этот заказ уже подтверждён.",
        "cancelled": "Этот заказ уже отменён.",
        "not_found": "Заказ не найден.",
        "error": "Ошибка базы данных.",
    }
    await safe_callback_answer(callback, messages.get(result, "Не удалось отменить заказ."), show_alert=True)


# ==========================================================
# АДМИН-ПАНЕЛЬ
# ==========================================================


@router.message(Command("addaccount"))
async def command_add_account(message: Message) -> None:
    if not message.from_user or not is_owner(message.from_user.id):
        await answer_user_message(message, "❌ У вас нет доступа.")
        return

    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await answer_user_message(
            message,
            "Использование:\n<code>/addaccount КОД_ТОВАРА +79991234567</code>",
        )
        return

    product_code = parts[1].strip()
    phone = parts[2].strip()

    product = await db.get_product_by_code(product_code)
    if not product:
        await answer_user_message(message, "❌ Товар с таким кодом не найден.")
        return

    ok, info = await db.add_account_stock(int(product["id"]), phone)
    await answer_user_message(message, ("✅ " if ok else "❌ ") + html.escape(info))


@router.message(Command("admin"))
async def command_admin(message: Message, state: FSMContext) -> None:
    if not message.from_user or not is_owner(message.from_user.id):
        await answer_user_message(message, "❌ У вас нет доступа к админ-панели.")
        return
    await state.clear()
    await send_section_message(
        message,
        "admin",
        "<b>⚙️ Админ-панель</b>",
        reply_markup=admin_menu_keyboard(),
    )


@router.message(F.text == "Админ панель")
@router.message(F.text == "⚙️ Админ-панель")
async def menu_admin(message: Message, state: FSMContext) -> None:
    await command_admin(message, state)


@router.callback_query(F.data == "admin:menu")
async def callback_admin_menu(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
        return
    await safe_callback_answer(callback)
    await state.clear()
    if callback.message:
        await safe_edit_text(callback.message, "<b>⚙️ Админ-панель</b>", reply_markup=admin_menu_keyboard())


def _stock_button_name(value: str, limit: int = 38) -> str:
    """Короткое безопасное название для inline-кнопки."""
    clean = " ".join(str(value).split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "…"


async def render_stock(message: Message, page: int = 0, edit: bool = True) -> None:
    """Показывает склад постранично, не превышая лимиты Telegram."""
    try:
        all_products = await asyncio.wait_for(
            db.get_products(include_hidden=True),
            timeout=10,
        )
    except asyncio.TimeoutError as error:
        raise RuntimeError("База данных слишком долго отвечала при открытии склада") from error

    total_products = len(all_products)
    total_pages = max(1, math.ceil(total_products / STOCK_PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))
    start = page * STOCK_PAGE_SIZE
    products = all_products[start : start + STOCK_PAGE_SIZE]

    lines = [
        "<b>📦 Единый склад</b>",
        f"Товаров: <b>{total_products}</b> · Страница <b>{page + 1}/{total_pages}</b>",
        "",
    ]
    rows: list[list[InlineKeyboardButton]] = []

    if not products:
        lines.append("Товаров пока нет.")
    else:
        for product in products:
            visible = "👁" if product["is_visible"] else "🙈"
            product_name = html.escape(str(product["name"]))
            product_code = html.escape(str(product["code"]))
            product_category = html.escape(str(product["category"]))
            lines.extend(
                [
                    f"{visible} <b>{product_name}</b> (<code>{product_code}</code>)",
                    f"Категория: <code>{product_category}</code> · Цена: {product_prices(product)}",
                ]
            )
            if product["category"] == "stars":
                lines.append(
                    f"Пакет: {stars(product_unit_amount(product))} · "
                    f"Выдача: {delivery_label(product['delivery_method'])}"
                )
            lines.extend(
                [
                    f"Всего: {stock_label(product, product['stock'])} · "
                    f"Резерв: {stock_label(product, product['reserved'])} · "
                    f"Доступно: <b>{stock_label(product, product['available'])}</b>",
                    "",
                ]
            )
            rows.append(
                [
                    InlineKeyboardButton(
                        text=(
                            f"⚙️ {_stock_button_name(product['name'])} "
                            f"({stock_label(product, product['available'])})"
                        ),
                        callback_data=f"stock:product:{product['id']}",
                    )
                ]
            )

    if total_pages > 1:
        navigation: list[InlineKeyboardButton] = []
        if page > 0:
            navigation.append(
                InlineKeyboardButton(text="⬅️", callback_data=f"admin:stock:{page - 1}")
            )
        navigation.append(
            InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop:stock_page")
        )
        if page + 1 < total_pages:
            navigation.append(
                InlineKeyboardButton(text="➡️", callback_data=f"admin:stock:{page + 1}")
            )
        rows.append(navigation)

    rows.append([InlineKeyboardButton(text="➕ Добавить аккаунт / Stars подарком", callback_data="stock:new")])
    rows.append([InlineKeyboardButton(text="⬅️ Админ-панель", callback_data="admin:menu")])

    output_text = "\n".join(lines)
    markup = InlineKeyboardMarkup(inline_keyboard=rows)

    if edit:
        try:
            await safe_edit_text(message, output_text, reply_markup=markup)
            return
        except TelegramBadRequest as error:
            # Например, старое сообщение нельзя отредактировать. Отправляем новое.
            logger.warning("Не удалось отредактировать сообщение склада: %s", error)

    await answer_user_message(message, output_text, reply_markup=markup)


@router.callback_query(F.data.startswith("admin:stock"))
async def callback_admin_stock(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
        return

    # Сразу закрываем индикатор загрузки у кнопки.
    await safe_callback_answer(callback)
    await state.clear()

    page = 0
    data = callback.data or ""
    if data.startswith("admin:stock:"):
        try:
            page = max(0, int(data.rsplit(":", 1)[1]))
        except (TypeError, ValueError):
            page = 0

    if not callback.message:
        return

    try:
        await render_stock(callback.message, page=page)
    except Exception as error:
        logger.exception("Ошибка при открытии склада")
        await answer_user_message(callback.message, 
            "❌ Не удалось открыть склад. Перезапустите бота и попробуйте ещё раз. "
            f"Ошибка: <code>{html.escape(type(error).__name__)}</code>"
        )


@router.callback_query(F.data == "noop:stock_page")
async def callback_noop_stock_page(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback)


@router.callback_query(F.data.startswith("stock:product:"))
async def callback_stock_product(callback: CallbackQuery) -> None:
    if not is_owner(callback.from_user.id):
        await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
        return
    await safe_callback_answer(callback)
    product_id = int(callback.data.rsplit(":", 1)[1])
    product = await db.get_product(product_id)
    if not product or not callback.message:
        await safe_callback_answer(callback, "Товар не найден.", show_alert=True)
        return
    await safe_edit_text(
        callback.message,
        product_admin_text(product),
        reply_markup=product_manage_keyboard(product),
    )


@router.callback_query(F.data.startswith("stock:change:"))
async def callback_stock_change(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
        return
    await safe_callback_answer(callback)
    _, _, mode, product_id_raw = callback.data.split(":")
    product_id = int(product_id_raw)
    product = await db.get_product(product_id)
    if not product or not callback.message:
        await safe_callback_answer(callback, "Товар не найден.", show_alert=True)
        return

    unit_word = "Stars" if product["category"] == "stars" else "единиц товара"
    prompts = {
        "add": f"Введите, сколько {unit_word} добавить:",
        "subtract": f"Введите, сколько {unit_word} списать:",
        "set": f"Введите точное количество {unit_word} на складе:",
    }
    await state.set_state(AdminStates.waiting_stock_value)
    await state.update_data(stock_mode=mode, stock_product_id=product_id)
    await answer_user_message(callback.message, 
        f"<b>{html.escape(product['name'])}</b>\n{prompts[mode]}\n\nДля отмены: /cancel"
    )


@router.message(AdminStates.waiting_stock_value, F.text)
async def process_stock_value(message: Message, state: FSMContext) -> None:
    if not message.from_user or not is_owner(message.from_user.id):
        return
    try:
        value = int(message.text.strip())
        if value < 0:
            raise ValueError
    except ValueError:
        # Если владелец случайно отправил строку цены в окне количества,
        # не заставляем начинать заново — применяем её как цену товара.
        parsed_price = parse_prices(message.text)
        if parsed_price is not None:
            data = await state.get_data()
            price_rub, price_stars, price_usdt, price_gram = parsed_price
            success, info = await db.set_price(
                int(data["stock_product_id"]),
                price_rub,
                price_stars,
                price_usdt,
                price_gram,
            )
            await state.clear()
            await answer_user_message(message, 
                ("✅ " if success else "❌ ") + html.escape(info),
                reply_markup=admin_menu_keyboard(),
            )
            return
        await answer_user_message(message, 
            "Введите целое неотрицательное число. Для изменения цены нажмите "
            "«💰 Изменить цену» или отправьте, например: "
            "<code>50₽/60звезд/0.65usdt/0.45gram</code>."
        )
        return

    data = await state.get_data()
    success, info = await db.change_stock(
        int(data["stock_product_id"]),
        str(data["stock_mode"]),
        value,
    )
    await state.clear()
    await answer_user_message(message, ("✅ " if success else "❌ ") + html.escape(info), reply_markup=admin_menu_keyboard())


@router.callback_query(F.data.startswith("stock:price:"))
async def callback_stock_price(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
        return
    await safe_callback_answer(callback)
    product_id = int(callback.data.rsplit(":", 1)[1])
    product = await db.get_product(product_id)
    if not product or not callback.message:
        await safe_callback_answer(callback, "Товар не найден.", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_price)
    await state.update_data(price_product_id=product_id)
    await answer_user_message(callback.message, 
        f"Текущая цена <b>{html.escape(product['name'])}</b>: {product_prices(product)}.\n"
        "Введите цены в формате <code>50₽/60звезд/0.65usdt/0.45gram</code>.\n"
        "USDT и GRAM можно указывать дробными числами через точку или запятую.\n"
        "Можно указать только рубли: <code>100</code>. Для отмены: /cancel"
    )


@router.message(AdminStates.waiting_price, F.text)
async def process_price(message: Message, state: FSMContext) -> None:
    if not message.from_user or not is_owner(message.from_user.id):
        return
    parsed = parse_prices(message.text)
    if parsed is None:
        await answer_user_message(message, 
            "Введите цену, например: <code>50₽/60звезд/0.65usdt/0.45gram</code>."
        )
        return
    price_rub, price_stars, price_usdt, price_gram = parsed
    data = await state.get_data()
    success, info = await db.set_price(
        int(data["price_product_id"]), price_rub, price_stars, price_usdt, price_gram
    )
    await state.clear()
    await answer_user_message(message, ("✅ " if success else "❌ ") + html.escape(info), reply_markup=admin_menu_keyboard())


@router.callback_query(F.data.startswith("stock:name:"))
async def callback_stock_name(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
        return
    product_id = int(callback.data.rsplit(":", 1)[1])
    product = await db.get_product(product_id)
    if not product or not callback.message:
        await safe_callback_answer(callback, "Товар не найден.", show_alert=True)
        return
    await safe_callback_answer(callback)
    await state.set_state(AdminStates.waiting_product_name)
    await state.update_data(name_product_id=product_id)
    await answer_user_message(callback.message, 
        f"Текущее название: <b>{html.escape(product['name'])}</b>\n"
        "Введите новое название товара. Для отмены: /cancel"
    )


@router.message(AdminStates.waiting_product_name, F.text)
async def process_product_name(message: Message, state: FSMContext) -> None:
    if not message.from_user or not is_owner(message.from_user.id):
        return
    data = await state.get_data()
    success, info = await db.rename_product(int(data["name_product_id"]), message.text)
    if success:
        await state.clear()
    await answer_user_message(message, ("✅ " if success else "❌ ") + html.escape(info), reply_markup=admin_menu_keyboard())


@router.callback_query(F.data.startswith("stock:delete:"))
async def callback_stock_delete(callback: CallbackQuery) -> None:
    if not is_owner(callback.from_user.id):
        await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
        return
    product_id = int(callback.data.rsplit(":", 1)[1])
    product = await db.get_product(product_id)
    if not product or not callback.message:
        await safe_callback_answer(callback, "Товар не найден.", show_alert=True)
        return
    await safe_callback_answer(callback)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Да, удалить полностью", callback_data=f"stock:delete_confirm:{product_id}")],
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data=f"stock:product:{product_id}")],
        ]
    )
    await safe_edit_text(
        callback.message,
        f"<b>Удалить товар полностью?</b>\n\n"
        f"{html.escape(product['name'])}\n\n"
        "Товар исчезнет со склада и из каталога. Завершённая история заказов сохранится.",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("stock:delete_confirm:"))
async def callback_stock_delete_confirm(callback: CallbackQuery) -> None:
    if not is_owner(callback.from_user.id):
        await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
        return
    product_id = int(callback.data.rsplit(":", 1)[1])
    success, info = await db.delete_product(product_id)
    await safe_callback_answer(callback, info, show_alert=True)
    if callback.message:
        if success:
            await render_stock(callback.message)
        else:
            product = await db.get_product(product_id)
            if product:
                await safe_edit_text(
                    callback.message, product_admin_text(product),
                    reply_markup=product_manage_keyboard(product),
                )


@router.callback_query(F.data.startswith("stock:toggle:"))
async def callback_stock_toggle(callback: CallbackQuery) -> None:
    if not is_owner(callback.from_user.id):
        await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
        return
    product_id = int(callback.data.rsplit(":", 1)[1])
    success, info = await db.toggle_product_visibility(product_id)
    await safe_callback_answer(callback, info, show_alert=True)
    product = await db.get_product(product_id)
    if success and product and callback.message:
        await safe_edit_text(
            callback.message,
            product_admin_text(product),
            reply_markup=product_manage_keyboard(product),
        )


@router.callback_query(F.data == "stock:new")
async def callback_new_product(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
        return
    await safe_callback_answer(callback)
    await state.set_state(AdminStates.waiting_new_product)
    if callback.message:
        await answer_user_message(callback.message, 
            "<b>Быстрое добавление товара</b>\n\n"
            "<b>Аккаунт:</b>\n"
            "<code>+7 | 50₽/60звезд/0.65usdt/0.45gram | 1 шт</code>\n\n"
            "<b>Пакет Stars:</b>\n"
            "<code>100 | 150₽/1.8usdt/1.2gram | подарком</code>\n"
            "Так добавится один пакет на 100 Stars.\n"
            "Для общего остатка: <code>100 | 150₽/1.8usdt/1.2gram | 1000 | подарком</code>.\n"
            "Первое число — Stars в одном заказе, 1000 — общий остаток.\n"
            "Позже можно указать способ <code>на аккаунт</code>.\n\n"
            "Прямая команда для Stars:\n"
            "<code>/newstars 100 | 150₽/1.8usdt/1.2gram | подарком</code>\n\n"
            "Расширенный обычный формат:\n"
            "<code>категория | код | название | 50₽/60звезд/0.65usdt/0.45gram | количество</code>\n"
            "Для отмены: /cancel"
        )


@router.message(AdminStates.waiting_new_product, F.text)
async def process_new_product(message: Message, state: FSMContext) -> None:
    if not message.from_user or not is_owner(message.from_user.id):
        return

    stars_quick = parse_stars_product_line(message.text)
    if stars_quick:
        package_amount, price_rub, price_stars, price_usdt, price_gram, stock, delivery_method = stars_quick
        success, info = await db.quick_add_stars_product(
            package_amount, price_rub, price_stars, price_usdt, price_gram, stock, delivery_method
        )
        if success:
            await state.clear()
        await answer_user_message(message, ("✅ " if success else "❌ ") + html.escape(info), reply_markup=admin_menu_keyboard())
        return

    quick = parse_quick_product_line(message.text)
    if quick:
        name, price_rub, price_stars, price_usdt, price_gram, stock = quick
        success, info = await db.quick_add_product(
            name, price_rub, price_stars, price_usdt, price_gram, stock
        )
        if success:
            await state.clear()
        await answer_user_message(message, ("✅ " if success else "❌ ") + html.escape(info), reply_markup=admin_menu_keyboard())
        return

    parts = [part.strip() for part in message.text.split("|")]
    if len(parts) != 5:
        await answer_user_message(message, "Используйте формат: <code>+7 | 50₽/60звезд/0.65usdt/0.45gram | 1 шт</code>")
        return
    category, code, name, prices_raw, stock_raw = parts
    if not re.fullmatch(r"[a-zA-Z0-9_-]{2,32}", category):
        await answer_user_message(message, "Категория: 2–32 символа, латиница, цифры, _ или -.")
        return
    if not re.fullmatch(r"[a-zA-Z0-9_-]{2,32}", code):
        await answer_user_message(message, "Код товара: 2–32 символа, латиница, цифры, _ или -.")
        return
    if not name or len(name) > 100:
        await answer_user_message(message, "Название должно содержать от 1 до 100 символов.")
        return
    parsed_prices = parse_prices(prices_raw)
    stock = parse_quantity(stock_raw)
    if parsed_prices is None or stock is None:
        await answer_user_message(message, "Пример цен и количества: <code>50₽/60звезд/0.65usdt/0.45gram | 1 шт</code>")
        return
    price_rub, price_stars, price_usdt, price_gram = parsed_prices

    success, info = await db.add_product(
        category, code, name, price_rub, price_stars, price_usdt, price_gram, stock
    )
    if success:
        await state.clear()
    await answer_user_message(message, ("✅ " if success else "❌ ") + html.escape(info), reply_markup=admin_menu_keyboard())


@router.callback_query(F.data == "stock:newpremium")
async def callback_new_premium(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
        return
    await safe_callback_answer(callback)
    await state.set_state(AdminStates.waiting_new_premium)
    if callback.message:
        await answer_user_message(callback.message, 
            "<b>Настройка Telegram Premium</b>\n\n"
            "Формат: <code>срок | цена | количество</code>\n"
            "Примеры:\n"
            "<code>3 | 500₽ | 10</code>\n"
            "<code>6 | 900₽ | 5</code>\n"
            "<code>12 | 1500₽ | 3</code>\n\n"
            "Срок: 3, 6 или 12 месяцев. Для отмены: /cancel"
        )


@router.message(AdminStates.waiting_new_premium, F.text)
async def process_new_premium(message: Message, state: FSMContext) -> None:
    if not message.from_user or not is_owner(message.from_user.id):
        return
    parts = [part.strip() for part in message.text.split("|")]
    if len(parts) != 3:
        await answer_user_message(message, "Формат: <code>3 | 500₽ | 10</code>")
        return
    try:
        months_raw = re.sub(r"\D", "", parts[0])
        if not months_raw:
            raise ValueError
        months = int(months_raw)
        prices = parse_prices(parts[1])
        stock = parse_quantity(parts[2])
        if prices is None or stock is None:
            raise ValueError
    except ValueError:
        await answer_user_message(message, "Проверьте срок, цену и количество.")
        return
    success, info = await db.quick_add_premium(months, prices[0], prices[1], prices[2], prices[3], stock)
    if success:
        await state.clear()
    await answer_user_message(message, ("✅ " if success else "❌ ") + html.escape(info), reply_markup=admin_menu_keyboard())


@router.message(Command("newpremium"))
async def command_new_premium(message: Message, state: FSMContext) -> None:
    if not message.from_user or not is_owner(message.from_user.id):
        return
    payload = (message.text or "").split(maxsplit=1)
    if len(payload) == 1:
        await state.set_state(AdminStates.waiting_new_premium)
        await answer_user_message(message, "Формат: <code>/newpremium 3 | 500₽/6usdt/4gram | 10</code>")
        return
    parts = [part.strip() for part in payload[1].split("|")]
    if len(parts) != 3:
        await answer_user_message(message, "Формат: <code>/newpremium 3 | 500₽/6usdt/4gram | 10</code>")
        return
    try:
        months_raw = re.sub(r"\D", "", parts[0])
        if not months_raw:
            raise ValueError
        months = int(months_raw)
        prices = parse_prices(parts[1])
        stock = parse_quantity(parts[2])
        if prices is None or stock is None:
            raise ValueError
    except ValueError:
        await answer_user_message(message, "Проверьте срок, цену и количество.")
        return
    success, info = await db.quick_add_premium(months, prices[0], prices[1], prices[2], prices[3], stock)
    await answer_user_message(message, ("✅ " if success else "❌ ") + html.escape(info), reply_markup=admin_menu_keyboard())


@router.callback_query(F.data == "stock:stars_account")
async def callback_configure_stars_account(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
        return
    await safe_callback_answer(callback)
    await state.set_state(AdminStates.waiting_stars_account_config)
    if callback.message:
        await answer_user_message(callback.message, 
            "<b>Настройка Stars на аккаунт</b>\n\n"
            "Формат: <code>базовое количество | цена | общий остаток</code>\n"
            "Пример: <code>50 | 75₽ | 1000</code>\n\n"
            "Покупатель сможет ввести любое целое количество от 50 до остатка. "
            "Цена рассчитывается пропорционально базовому тарифу. Для отмены: /cancel"
        )


@router.message(AdminStates.waiting_stars_account_config, F.text)
async def process_configure_stars_account(message: Message, state: FSMContext) -> None:
    if not message.from_user or not is_owner(message.from_user.id):
        return
    parts = [part.strip() for part in message.text.split("|")]
    if len(parts) != 3:
        await answer_user_message(message, "Формат: <code>50 | 75₽ | 1000</code>")
        return
    try:
        amount_raw = re.sub(r"\D", "", parts[0])
        if not amount_raw:
            raise ValueError
        base_amount = int(amount_raw)
        prices = parse_prices(parts[1])
        stock = parse_star_amount(parts[2])
        if prices is None or stock is None:
            raise ValueError
    except ValueError:
        await answer_user_message(message, "Проверьте базовое количество, цену и остаток.")
        return
    success, info = await db.configure_stars_account(base_amount, prices[0], prices[1], prices[2], prices[3], stock)
    if success:
        await state.clear()
    await answer_user_message(message, ("✅ " if success else "❌ ") + html.escape(info), reply_markup=admin_menu_keyboard())


@router.message(Command("newstarsaccount"))
async def command_new_stars_account(message: Message) -> None:
    if not message.from_user or not is_owner(message.from_user.id):
        return
    payload = (message.text or "").split(maxsplit=1)
    if len(payload) != 2:
        await answer_user_message(message, "Формат: <code>/newstarsaccount 50 | 75₽/0.9usdt/0.6gram | 1000</code>")
        return
    parts = [part.strip() for part in payload[1].split("|")]
    if len(parts) != 3:
        await answer_user_message(message, "Формат: <code>/newstarsaccount 50 | 75₽/0.9usdt/0.6gram | 1000</code>")
        return
    try:
        amount_raw = re.sub(r"\D", "", parts[0])
        if not amount_raw:
            raise ValueError
        base_amount = int(amount_raw)
        prices = parse_prices(parts[1])
        stock = parse_star_amount(parts[2])
        if prices is None or stock is None:
            raise ValueError
    except ValueError:
        await answer_user_message(message, "Проверьте данные.")
        return
    success, info = await db.configure_stars_account(base_amount, prices[0], prices[1], prices[2], prices[3], stock)
    await answer_user_message(message, ("✅ " if success else "❌ ") + html.escape(info), reply_markup=admin_menu_keyboard())


@router.message(Command("newstars"))
async def command_new_stars_product(message: Message) -> None:
    if not message.from_user or not is_owner(message.from_user.id):
        return
    payload = (message.text or "").split(maxsplit=1)
    if len(payload) != 2:
        await answer_user_message(message, 
            "Использование:\n<code>/newstars 100 | 150₽/1.8usdt/1.2gram | подарком</code>"
        )
        return
    parsed = parse_stars_product_line(payload[1])
    if not parsed:
        await answer_user_message(message, 
            "Неверный формат. Пример:\n"
            "<code>/newstars 100 | 150₽/1.8usdt/1.2gram | подарком</code>\n\n"
            "Короткий формат создаёт один пакет. Для общего остатка используйте: "
            "<code>/newstars 100 | 150₽/1.8usdt/1.2gram | 1000 | подарком</code>.\n"
            "Способ: <code>подарком</code> или <code>на аккаунт</code>."
        )
        return
    package_amount, price_rub, price_stars, price_usdt, price_gram, stock, delivery_method = parsed
    success, info = await db.quick_add_stars_product(
        package_amount, price_rub, price_stars, price_usdt, price_gram, stock, delivery_method
    )
    await answer_user_message(message, ("✅ " if success else "❌ ") + html.escape(info), reply_markup=admin_menu_keyboard())


@router.message(Command("new"))
async def command_new_product(message: Message, state: FSMContext) -> None:
    if not message.from_user or not is_owner(message.from_user.id):
        return
    payload = (message.text or "").split(maxsplit=1)
    if len(payload) == 1:
        await state.set_state(AdminStates.waiting_new_product)
        await answer_user_message(message, 
            "Отправьте аккаунт так:\n<code>+7 | 50₽/60звезд/0.65usdt/0.45gram | 1 шт</code>\n\nДля Stars: <code>/newstars 100 | 150₽/1.8usdt/1.2gram | подарком</code>"
        )
        return
    quick = parse_quick_product_line(payload[1])
    if not quick:
        await answer_user_message(message, "Формат команды: <code>/new +7 | 50₽/60звезд/0.65usdt/0.45gram | 1 шт</code>")
        return
    name, price_rub, price_stars, price_usdt, price_gram, stock = quick
    success, info = await db.quick_add_product(
        name, price_rub, price_stars, price_usdt, price_gram, stock
    )
    await answer_user_message(message, ("✅ " if success else "❌ ") + html.escape(info), reply_markup=admin_menu_keyboard())


# ==========================================================
# КОМАНДЫ СКЛАДА
# ==========================================================


async def resolve_product_for_command(message: Message, command_name: str) -> tuple[sqlite3.Row | None, int | None]:
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) != 3:
        await answer_user_message(message, f"Использование: <code>/{command_name} код число</code>")
        return None, None
    product = await db.get_product_by_code(parts[1])
    if not product:
        await answer_user_message(message, "Товар с таким кодом не найден.")
        return None, None
    try:
        value = int(parts[2])
        if value < 0:
            raise ValueError
    except ValueError:
        await answer_user_message(message, "Число должно быть целым и неотрицательным.")
        return None, None
    return product, value


@router.message(Command("add"))
async def command_add_stock(message: Message) -> None:
    if not message.from_user or not is_owner(message.from_user.id):
        return
    product, value = await resolve_product_for_command(message, "add")
    if product is None or value is None:
        return
    success, info = await db.change_stock(product["id"], "add", value)
    await answer_user_message(message, ("✅ " if success else "❌ ") + html.escape(info))


@router.message(Command("set"))
async def command_set_stock(message: Message) -> None:
    if not message.from_user or not is_owner(message.from_user.id):
        return
    product, value = await resolve_product_for_command(message, "set")
    if product is None or value is None:
        return
    success, info = await db.change_stock(product["id"], "set", value)
    await answer_user_message(message, ("✅ " if success else "❌ ") + html.escape(info))


@router.message(Command("price"))
async def command_set_price(message: Message) -> None:
    if not message.from_user or not is_owner(message.from_user.id):
        return
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) != 3:
        await answer_user_message(message, "Использование: <code>/price код 50₽/60звезд/0.65usdt/0.45gram</code>")
        return
    product = await db.get_product_by_code(parts[1])
    if not product:
        await answer_user_message(message, "Товар с таким кодом не найден.")
        return
    parsed = parse_prices(parts[2])
    if parsed is None:
        await answer_user_message(message, "Цена должна быть в формате <code>50₽/60звезд/0.65usdt/0.45gram</code>.")
        return
    price_rub, price_stars, price_usdt, price_gram = parsed
    success, info = await db.set_price(
        product["id"], price_rub, price_stars, price_usdt, price_gram
    )
    await answer_user_message(message, ("✅ " if success else "❌ ") + html.escape(info))


# ==========================================================
# БЛОКИРОВКИ И РЕЖИМ «КРИПТА»
# ==========================================================


def ban_status_text(row: sqlite3.Row) -> str:
    username = safe_username(row["username"], row["user_id"])
    until = format_datetime(row["banned_until"]) if row["banned_until"] else "навсегда"
    return (
        f"{username} · <code>{row['user_id']}</code>\n"
        f"Причина: {html.escape(str(row['ban_reason'] or 'не указана'))}\n"
        f"До: {until}"
    )


@router.message(Command("ban"))
async def command_ban_user(message: Message) -> None:
    if not message.from_user or not is_owner(message.from_user.id):
        return
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) == 1:
        await render_bans(message)
        return
    if len(parts) < 3:
        await answer_user_message(message, 
            "Использование:\n"
            "<code>/ban @username причина</code> — бан на 24 часа\n"
            "<code>/ban @username 7d причина</code> — бан на 7 дней\n"
            "<code>/ban @username forever причина</code> — навсегда\n\n"
            "Для просмотра списка просто отправьте <code>/ban</code>."
        )
        return

    identifier = parts[1]
    tail = parts[2].strip()
    tail_parts = tail.split(maxsplit=1)
    duration: timedelta | None = timedelta(hours=DEFAULT_BAN_HOURS)
    reason = tail
    try:
        parsed_duration = parse_ban_duration_token(tail_parts[0])
        duration = parsed_duration
        if len(tail_parts) != 2 or not tail_parts[1].strip():
            await answer_user_message(message, "После срока укажите причину блокировки.")
            return
        reason = tail_parts[1].strip()
    except ValueError:
        pass

    user = await db.find_user(identifier)
    if not user:
        await answer_user_message(message, "Пользователь не найден. Он должен хотя бы один раз открыть бота.")
        return
    if int(user["user_id"]) == OWNER_ID:
        await answer_user_message(message, "Владельца бота заблокировать нельзя.")
        return

    banned_until = None
    if duration is not None:
        banned_until = (datetime.now(timezone.utc) + duration).isoformat(timespec="seconds")
    success, info = await db.ban_user(
        int(user["user_id"]), reason, banned_until, message.from_user.id
    )
    if success:
        try:
            text = (
                "К сожалению, вы заблокированы в этом боте.\n"
                f"Причина: {html.escape(reason)}.\n"
                f"Подробности: @{html.escape(BAN_SUPPORT_USERNAME.lstrip('@'))}"
            )
            if banned_until:
                text += f"\nСрок блокировки: до {format_datetime(banned_until)}."
            await send_user_message(int(user["user_id"]), text)
        except Exception:
            pass
    await answer_user_message(message, ("✅ " if success else "❌ ") + html.escape(info))


@router.message(Command("unban"))
async def command_unban_user(message: Message) -> None:
    if not message.from_user or not is_owner(message.from_user.id):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2:
        await answer_user_message(message, "Использование: <code>/unban @username</code>")
        return
    user = await db.find_user(parts[1])
    if not user:
        await answer_user_message(message, "Пользователь не найден.")
        return
    success, info = await db.unban_user(int(user["user_id"]))
    if success:
        try:
            await send_user_message(
                int(user["user_id"]),
                "✅ Блокировка снята. Вы снова можете пользоваться ботом.",
            )
        except Exception:
            pass
    await answer_user_message(message, ("✅ " if success else "❌ ") + html.escape(info))


async def render_bans(message: Message) -> None:
    banned = await db.list_banned_users()
    lines = ["<b>🚫 Заблокированные пользователи</b>", ""]
    if not banned:
        lines.append("Список пуст.")
    else:
        for index, row in enumerate(banned, start=1):
            lines.append(f"<b>{index}.</b> {ban_status_text(row)}\n")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin:bans")],
            [InlineKeyboardButton(text="⬅️ Админ-панель", callback_data="admin:menu")],
        ]
    )
    try:
        await safe_edit_text(message, "\n".join(lines), reply_markup=keyboard)
    except TelegramBadRequest:
        await answer_user_message(message, "\n".join(lines), reply_markup=keyboard)


@router.message(Command("bans"))
async def command_bans(message: Message) -> None:
    if not message.from_user or not is_owner(message.from_user.id):
        return
    await render_bans(message)


@router.callback_query(F.data == "admin:bans")
async def callback_admin_bans(callback: CallbackQuery) -> None:
    if not is_owner(callback.from_user.id):
        await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
        return
    await safe_callback_answer(callback)
    if callback.message:
        await render_bans(callback.message)


@router.message(Command("cripta"))
async def command_crypto_mode(message: Message) -> None:
    if not message.from_user or not is_owner(message.from_user.id):
        return
    parts = (message.text or "").split(maxsplit=1)
    argument = parts[1].strip().lower() if len(parts) == 2 else "toggle"
    if argument in {"toggle", "переключить"}:
        enabled = await db.toggle_crypto_mode()
    elif argument in {"on", "1", "вкл", "включить"}:
        enabled = True
        await db.set_setting("crypto_mode", "1")
    elif argument in {"off", "0", "выкл", "выключить"}:
        enabled = False
        await db.set_setting("crypto_mode", "0")
    elif argument in {"status", "статус"}:
        enabled = await db.crypto_mode_enabled()
    else:
        await answer_user_message(message, 
            "Использование: <code>/cripta on</code>, <code>/cripta off</code> "
            "или <code>/cripta</code>."
        )
        return
    await answer_user_message(message, 
        f"🪙 Режим «Крипта»: <b>{'ВКЛЮЧЁН' if enabled else 'ВЫКЛЮЧЕН'}</b>.\n"
        + (
            "Premium и Stars на аккаунт сейчас недоступны покупателям."
            if enabled
            else "Premium и Stars на аккаунт доступны при наличии товара."
        )
    )


@router.callback_query(F.data == "admin:crypto")
async def callback_crypto_mode(callback: CallbackQuery) -> None:
    if not is_owner(callback.from_user.id):
        await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
        return
    enabled = await db.toggle_crypto_mode()
    await safe_callback_answer(callback, 
        "Режим включён: Premium и Stars на аккаунт недоступны."
        if enabled
        else "Режим выключен: покупки снова доступны.",
        show_alert=True,
    )
    if callback.message:
        try:
            await render_stock(callback.message)
        except Exception:
            await safe_edit_text(
                callback.message,
                "<b>⚙️ Админ-панель</b>",
                reply_markup=admin_menu_keyboard(),
            )


# ==========================================================
# СТАТИСТИКА И ИСТОРИЯ
# ==========================================================


@router.callback_query(F.data == "admin:stats")
async def callback_admin_stats(callback: CallbackQuery) -> None:
    if not is_owner(callback.from_user.id):
        await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
        return
    await safe_callback_answer(callback)
    stats = await db.get_statistics()
    lines = [
        "<b>📊 Статистика</b>",
        "",
        f"👥 Пользователей всего: <b>{stats['users_count']}</b>",
        f"🧑‍💼 Покупателей с подтверждёнными покупками: <b>{stats['buyers_count']}</b>",
        f"⏳ Заявок на проверке: <b>{stats['pending_count']}</b>",
        f"🛒 Заказов сегодня: <b>{stats['today_count']}</b>",
        f"💰 Выручка сегодня: <b>{money(stats['today_revenue_rub'])}</b> / <b>{stars(stats['today_revenue_stars'])}</b> / <b>{usdt(stats['today_revenue_usdt'])}</b> / <b>{gram(stats['today_revenue_gram'])}</b>",
        f"📦 Заказов всего: <b>{stats['total_count']}</b>",
        f"💵 Выручка за всё время: <b>{money(stats['total_revenue_rub'])}</b> / <b>{stars(stats['total_revenue_stars'])}</b> / <b>{usdt(stats['total_revenue_usdt'])}</b> / <b>{gram(stats['total_revenue_gram'])}</b>",
        f"📈 Средний чек: <b>{money(stats['average_revenue_rub'])}</b> / <b>{stars(stats['average_revenue_stars'])}</b> / <b>{usdt(stats['average_revenue_usdt'])}</b> / <b>{gram(stats['average_revenue_gram'])}</b>",
        "",
        "<b>Самые продаваемые товары:</b>",
    ]
    if stats["top"]:
        for index, row in enumerate(stats["top"], start=1):
            lines.append(
                f"{index}. {html.escape(row['product_name'])} — {row['sold']} шт. "
                f"({money(row['revenue_rub'])} / {stars(row['revenue_stars'])} / "
                f"{usdt(row['revenue_usdt'])} / {gram(row['revenue_gram'])})"
            )
    else:
        lines.append("Пока нет подтверждённых заказов.")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin:stats")],
            [InlineKeyboardButton(text="⬅️ Админ-панель", callback_data="admin:menu")],
        ]
    )
    if callback.message:
        await safe_edit_text(callback.message, "\n".join(lines), reply_markup=keyboard)


@router.message(Command("history"))
async def command_history(message: Message) -> None:
    if not message.from_user or not is_owner(message.from_user.id):
        return
    orders, total = await db.get_order_history(0, 20)
    lines = [f"<b>📜 История заказов</b> · всего: <b>{total}</b>", ""]
    if not orders:
        lines.append("Заказов пока нет.")
    else:
        for order in orders:
            lines.append(
                f"<b>#{order['id']}</b> · {ORDER_STATUS_LABELS.get(order['status'], order['status'])}\n"
                f"👤 {safe_username(order['username'], order['user_id'])}\n"
                f"📦 {html.escape(order['product_name'])} · {order_amount(order)}\n"
                f"🕒 {format_datetime(order['created_at'])}\n"
            )
    await answer_user_message(message, "\n".join(lines))


@router.callback_query(F.data.startswith("admin:history:"))
async def callback_admin_history(callback: CallbackQuery) -> None:
    if not is_owner(callback.from_user.id):
        await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
        return
    await safe_callback_answer(callback)
    page = max(0, int(callback.data.rsplit(":", 1)[1]))
    page_size = 10
    orders, total = await db.get_order_history(page, page_size)
    total_pages = max(1, (total + page_size - 1) // page_size)
    if page >= total_pages:
        page = total_pages - 1
        orders, total = await db.get_order_history(page, page_size)

    lines = [f"<b>📜 История заказов — страница {page + 1}/{total_pages}</b>", ""]
    if not orders:
        lines.append("Заказов пока нет.")
    else:
        for order in orders:
            lines.append(
                f"<b>#{order['id']}</b> · {ORDER_STATUS_LABELS.get(order['status'], order['status'])}\n"
                f"👤 {safe_username(order['username'], order['user_id'])}\n"
                f"📦 {html.escape(order['product_name'])} · {order_amount(order)}\n"
                f"🕒 {format_datetime(order['created_at'])}\n"
            )

    builder = InlineKeyboardBuilder()
    if page > 0:
        builder.button(text="⬅️ Назад", callback_data=f"admin:history:{page - 1}")
    if page + 1 < total_pages:
        builder.button(text="Вперёд ➡️", callback_data=f"admin:history:{page + 1}")
    builder.button(text="🔄 Обновить", callback_data=f"admin:history:{page}")
    builder.button(text="⬅️ Админ-панель", callback_data="admin:menu")
    builder.adjust(2, 1, 1)

    if callback.message:
        await safe_edit_text(callback.message, "\n".join(lines), reply_markup=builder.as_markup())


# ==========================================================
# ПРОМОКОДЫ
# ==========================================================


async def render_promos(message: Message) -> None:
    promos = await db.get_promos()
    lines = ["<b>🎟 Промокоды</b>", ""]
    builder = InlineKeyboardBuilder()

    if not promos:
        lines.append("Промокодов пока нет.")
    else:
        for promo in promos:
            status = "✅" if promo["is_active"] else "❌"
            limit = promo["max_uses"] if promo["max_uses"] is not None else "∞"
            expires = promo["expires_on"] or "без срока"
            lines.append(
                f"{status} <code>{html.escape(promo['code'])}</code> — "
                f"{promo['discount_percent']}%\n"
                f"Использовано: {promo['uses']}/{limit} · До: {expires} · "
                f"Категория: {PROMO_CATEGORY_LABELS.get(promo['category'] or 'all', promo['category'])}\n"
            )
            builder.button(
                text=f"{'Отключить' if promo['is_active'] else 'Включить'} {promo['code']}",
                callback_data=f"promo_admin:toggle:{promo['id']}",
            )

    builder.button(text="➕ Создать промокод", callback_data="promo_admin:new")
    builder.button(text="⬅️ Админ-панель", callback_data="admin:menu")
    builder.adjust(1)
    try:
        await safe_edit_text(message, "\n".join(lines), reply_markup=builder.as_markup())
    except TelegramBadRequest:
        await answer_user_message(message, "\n".join(lines), reply_markup=builder.as_markup())


@router.callback_query(F.data == "admin:promos")
async def callback_admin_promos(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
        return
    await safe_callback_answer(callback)
    await state.clear()
    if callback.message:
        await render_promos(callback.message)


@router.callback_query(F.data == "promo_admin:new")
async def callback_new_promo(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
        return
    await safe_callback_answer(callback)
    await state.set_state(AdminStates.waiting_new_promo)
    if callback.message:
        await answer_user_message(callback.message, 
            "<b>Создание промокода</b>\n\n"
            "Отправьте одной строкой:\n"
            "<code>КОД | СКИДКА | ДАТА | ЛИМИТ | КАТЕГОРИЯ</code>\n\n"
            "Пример:\n"
            "<code>SUMMER5 | 5 | 2026-08-31 | 100 | Звезды</code>\n\n"
            "Без срока и без лимита:\n"
            "<code>WELCOME | 10 | - | - | Все</code>\n\n"
            "Категории вводятся текстом: Все, Звезды, Аккаунты, Premium.\n\n"
            "Для отмены: /cancel"
        )


@router.message(AdminStates.waiting_new_promo, F.text)
async def process_new_promo(message: Message, state: FSMContext) -> None:
    if not message.from_user or not is_owner(message.from_user.id):
        return
    parts = [part.strip() for part in message.text.split("|")]
    if len(parts) != 5:
        await answer_user_message(message, "Нужно 5 полей: код | скидка | дата | лимит | категория")
        return
    code, discount_raw, expires_raw, max_uses_raw, category_raw = parts
    try:
        discount = int(discount_raw)
    except ValueError:
        await answer_user_message(message, "Скидка должна быть целым числом.")
        return
    expires = None if expires_raw == "-" else expires_raw
    if max_uses_raw == "-":
        max_uses = None
    else:
        try:
            max_uses = int(max_uses_raw)
        except ValueError:
            await answer_user_message(message, "Лимит должен быть целым числом или символом -.")
            return

    category = normalize_promo_category(category_raw)
    if category is None:
        await answer_user_message(message, "Категория: Все, Звезды, Аккаунты или Premium.")
        return

    success, info = await db.create_promo(code, discount, expires, max_uses, category)
    if success:
        await state.clear()
    await answer_user_message(message, ("✅ " if success else "❌ ") + html.escape(info), reply_markup=admin_menu_keyboard())


@router.callback_query(F.data.startswith("promo_admin:toggle:"))
async def callback_toggle_promo(callback: CallbackQuery) -> None:
    if not is_owner(callback.from_user.id):
        await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
        return
    promo_id = int(callback.data.rsplit(":", 1)[1])
    success, info = await db.toggle_promo(promo_id)
    await safe_callback_answer(callback, info, show_alert=True)
    if success and callback.message:
        await render_promos(callback.message)


# ==========================================================
# РАССЫЛКА
# ==========================================================


@router.callback_query(F.data == "admin:broadcast")
async def callback_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
        return
    await safe_callback_answer(callback)
    await state.set_state(AdminStates.waiting_broadcast)
    if callback.message:
        await answer_user_message(callback.message, 
            "📣 Отправьте сообщение для рассылки.\n\n"
            "Можно отправить текст, фото, видео, документ или другое сообщение. "
            "Бот скопирует его всем пользователям.\n\nДля отмены: /cancel"
        )


@router.message(AdminStates.waiting_broadcast)
async def process_broadcast_message(message: Message, state: FSMContext) -> None:
    if not message.from_user or not is_owner(message.from_user.id):
        return
    await state.update_data(
        broadcast_chat_id=message.chat.id,
        broadcast_message_id=message.message_id,
    )
    await state.set_state(AdminStates.waiting_broadcast_confirmation)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Начать рассылку", callback_data="broadcast:confirm")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="broadcast:cancel")],
        ]
    )
    await answer_user_message(message, "Отправить это сообщение всем пользователям?", reply_markup=keyboard)


@router.callback_query(F.data == "broadcast:cancel")
async def callback_broadcast_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
        return
    await safe_callback_answer(callback, "Рассылка отменена.")
    await state.clear()
    if callback.message:
        await safe_edit_text(callback.message, "Рассылка отменена.", reply_markup=admin_menu_keyboard())


@router.callback_query(F.data == "broadcast:confirm")
async def callback_broadcast_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner(callback.from_user.id):
        await safe_callback_answer(callback, "Нет доступа.", show_alert=True)
        return
    current_state = await state.get_state()
    if current_state != AdminStates.waiting_broadcast_confirmation.state:
        await safe_callback_answer(callback, "Данные рассылки устарели.", show_alert=True)
        return

    await safe_callback_answer(callback)
    data = await state.get_data()
    source_chat_id = int(data["broadcast_chat_id"])
    source_message_id = int(data["broadcast_message_id"])
    await state.clear()

    if callback.message:
        await safe_edit_text(callback.message, "📣 Рассылка запущена…")

    users = await db.get_all_user_ids()
    sent = 0
    failed = 0

    for user_id in users:
        try:
            await bot.copy_message(
                chat_id=user_id,
                from_chat_id=source_chat_id,
                message_id=source_message_id,
            )
            sent += 1
            await asyncio.sleep(0.04)
        except TelegramRetryAfter as error:
            await asyncio.sleep(float(error.retry_after) + 0.5)
            try:
                await bot.copy_message(
                    chat_id=user_id,
                    from_chat_id=source_chat_id,
                    message_id=source_message_id,
                )
                sent += 1
            except Exception:
                failed += 1
        except TelegramForbiddenError:
            failed += 1
            await db.mark_user_blocked(user_id, True)
        except Exception:
            failed += 1
            logger.exception("Ошибка рассылки пользователю %s", user_id)

    result_text = (
        "<b>📣 Рассылка завершена</b>\n\n"
        f"✅ Отправлено: <b>{sent}</b>\n"
        f"❌ Не доставлено: <b>{failed}</b>\n"
        f"👥 Всего получателей: <b>{len(users)}</b>"
    )
    if callback.message:
        await answer_user_message(callback.message, result_text, reply_markup=admin_menu_keyboard())


# ==========================================================
# ПОЛУЧЕНИЕ FILE_ID ДЛЯ ИЗОБРАЖЕНИЙ
# ==========================================================


@router.message(Command("photoid"))
async def command_photo_id(message: Message) -> None:
    """Выдаёт настоящий Telegram file_id и готовую строку для вставки в код."""
    if not message.from_user or not is_owner(message.from_user.id):
        await answer_user_message(message, "❌ Эта команда доступна только владельцу.")
        return

    command_text = (message.caption or message.text or "").strip()
    parts = command_text.split(maxsplit=1)
    requested_slot = parts[1].strip().upper() if len(parts) == 2 else ""

    source = message
    if not message.photo and not message.document and message.reply_to_message:
        source = message.reply_to_message

    file_id = ""
    if source.photo:
        file_id = source.photo[-1].file_id
    elif source.document and (source.document.mime_type or "").startswith("image/"):
        file_id = source.document.file_id

    slots_text = "\n".join(f"• <code>{name}</code>" for name in PHOTO_SLOT_NAMES)
    if not file_id:
        await answer_user_message(
            message,
            "<b>Как получить file_id</b>\n\n"
            "1. Отправьте фотографию владельцу-боту с подписью, например:\n"
            "<code>/photoid MENU_IMAGE</code>\n\n"
            "2. Или ответьте этой командой на уже отправленную фотографию.\n\n"
            "Доступные места для фото:\n" + slots_text,
        )
        return

    if requested_slot and requested_slot not in PHOTO_SLOT_NAMES:
        await answer_user_message(
            message,
            "❌ Неизвестное место для фотографии.\n\n"
            "Доступные названия:\n" + slots_text,
        )
        return

    if requested_slot:
        result = f'{requested_slot} = "{file_id}"'
        await answer_user_message(
            message,
            "✅ Готовая строка для вставки в настройки кода:\n\n"
            f"<code>{html.escape(result)}</code>",
        )
        return

    await answer_user_message(
        message,
        "✅ Telegram file_id изображения:\n\n"
        f"<code>{html.escape(file_id)}</code>\n\n"
        "Чтобы сразу получить готовую строку, используйте, например, "
        "<code>/photoid MENU_IMAGE</code>.",
    )


# ==========================================================
# НЕИЗВЕСТНЫЕ СООБЩЕНИЯ
# ==========================================================


@router.message()
async def fallback_message(message: Message) -> None:
    await db.upsert_user(message)
    await answer_user_message(message, 
        "Используйте кнопки главного меню.",
        reply_markup=main_menu_keyboard(bool(message.from_user and is_owner(message.from_user.id))),
    )


# ==========================================================
# ЗАПУСК
# ==========================================================


async def automatic_unban_worker() -> None:
    while True:
        try:
            count = await db.unban_expired()
            if count:
                logger.info("Автоматически снято блокировок: %s", count)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Ошибка автоматического разбана")
        await asyncio.sleep(AUTO_UNBAN_CHECK_SECONDS)


async def set_commands() -> None:
    # Обычным пользователям не показываем административные команды.
    user_commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="cancel", description="Отменить текущее действие"),
    ]
    await bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())

    # Полный список команд виден только владельцу в его личном чате с ботом.
    owner_commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="admin", description="Админ-панель"),
        BotCommand(command="history", description="История заказов"),
        BotCommand(command="ban", description="Бан / список блокировок"),
        BotCommand(command="unban", description="Снять блокировку"),
        BotCommand(command="bans", description="Список блокировок"),
        BotCommand(command="cripta", description="Переключатель Crypto"),
        BotCommand(command="new", description="Добавить аккаунт"),
        BotCommand(command="newstars", description="Добавить Stars подарком"),
        BotCommand(command="add", description="Добавить остаток"),
        BotCommand(command="set", description="Установить остаток"),
        BotCommand(command="price", description="Изменить цену"),
        BotCommand(command="photoid", description="Получить file_id картинки"),
        BotCommand(command="cancel", description="Отменить текущее действие"),
    ]
    await bot.set_my_commands(owner_commands, scope=BotCommandScopeChat(chat_id=OWNER_ID))


async def main() -> None:
    global bot

    if BOT_TOKEN == "ВСТАВЬТЕ_ТОКЕН_БОТА":
        raise RuntimeError("Заполните BOT_TOKEN в блоке настроек.")
    if OWNER_ID == 123456789:
        logger.warning("OWNER_ID выглядит как пример. Укажите настоящий Telegram ID владельца.")

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    await db.initialize()
    await set_commands()
    await bot.delete_webhook(drop_pending_updates=False)
    logger.info("Бот запущен. База данных: %s", DB_PATH)
    unban_task = asyncio.create_task(automatic_unban_worker())
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        unban_task.cancel()
        try:
            await unban_task
        except asyncio.CancelledError:
            pass
        await bot.session.close()
        db.conn.close()


if __name__ == "__main__":
    asyncio.run(main())
