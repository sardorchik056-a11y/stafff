import telebot
from telebot import types
import json
import os
import threading
import requests
import time

# ==================== CONFIG ====================
BOT_TOKEN = "8183211325:AAGmSXuqkxHuXz4iWLbBNhrcImFy_Em3kGE"          # Токен бота от @BotFather
ADMIN_ID = 8118184388                   # Твой Telegram ID
SUPPORT_LINK = "https://t.me/support_username"  # Ссылка на поддержку
CRYPTO_PAY_TOKEN = "582363:AALEf7JOugnrQyrkMHzH5UrO7pdOjjYnTQy"      # Токен от @CryptoBot → Apps → Create App

# CryptoPay API
CRYPTO_API_URL = "https://pay.crypt.bot/api"   # Mainnet
# CRYPTO_API_URL = "https://testnet-pay.crypt.bot/api"  # Testnet для тестов

bot = telebot.TeleBot(BOT_TOKEN)

# ==================== DATABASE ====================
DB_FILE = "db.json"

def load_db():
    if not os.path.exists(DB_FILE):
        return {"users": {}, "settings": {"fine_amount": 0.5}, "invoices": {}}
    with open(DB_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if "invoices" not in data:
        data["invoices"] = {}
    return data

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user(user_id):
    db = load_db()
    uid = str(user_id)
    if uid not in db["users"]:
        db["users"][uid] = {"balance": 0.0, "username": ""}
        save_db(db)
    return db["users"][uid]

def update_user(user_id, data):
    db = load_db()
    uid = str(user_id)
    db["users"][uid].update(data)
    save_db(db)

def get_setting(key):
    db = load_db()
    return db["settings"].get(key, 0.5)

def set_setting(key, value):
    db = load_db()
    db["settings"][key] = value
    save_db(db)

def save_invoice(invoice_id, user_id, amount):
    db = load_db()
    db["invoices"][str(invoice_id)] = {"user_id": user_id, "amount": amount, "paid": False}
    save_db(db)

def get_invoice(invoice_id):
    db = load_db()
    return db["invoices"].get(str(invoice_id))

def mark_invoice_paid(invoice_id):
    db = load_db()
    if str(invoice_id) in db["invoices"]:
        db["invoices"][str(invoice_id)]["paid"] = True
        save_db(db)

# ==================== CRYPTOPAY API ====================

def crypto_request(method, params=None):
    """Выполнить запрос к CryptoPay API"""
    headers = {"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN}
    url = f"{CRYPTO_API_URL}/{method}"
    try:
        resp = requests.get(url, headers=headers, params=params or {}, timeout=10)
        data = resp.json()
        if data.get("ok"):
            return data["result"]
        else:
            print(f"CryptoPay error: {data}")
            return None
    except Exception as e:
        print(f"CryptoPay request error: {e}")
        return None

def create_invoice(amount_usd, user_id):
    """Создать инвойс на пополнение в USDT"""
    result = crypto_request("createInvoice", {
        "currency_type": "fiat",
        "fiat": "USD",
        "accepted_assets": "USDT,TON,BTC,ETH,LTC,BNB,TRX,USDC",
        "amount": str(amount_usd),
        "description": f"Пополнение баланса Kretros SMS Shop | ID: {user_id}",
        "expires_in": 3600,  # 1 час
        "payload": str(user_id),
    })
    return result

def check_invoice(invoice_id):
    """Проверить статус инвойса"""
    result = crypto_request("getInvoices", {"invoice_ids": str(invoice_id)})
    if result and result.get("items"):
        return result["items"][0]
    return None

# ==================== STATE ====================
pending_requests = {}   # {user_id: {"search_msg_id": ..., "timer": ...}}
active_numbers = {}     # {user_id: {"number": ..., "timer": ...}}
admin_state = {}        # {ADMIN_ID: {"action": ..., ...}}
user_state = {}         # {user_id: {"action": ..., ...}}
invoice_checkers = {}   # {invoice_id: Timer}

# ==================== KEYBOARDS ====================

def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📲 Взять номер")
    kb.row("💰 Баланс")
    kb.row("📋 Правила", "🎧 Поддержка")
    return kb

def cancel_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("❌ Отмена", callback_data="user_cancel"))
    return kb

def sent_cancel_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✅ Отправил", callback_data="user_sent"))
    kb.add(types.InlineKeyboardButton("❌ Отмена", callback_data="user_cancel_number"))
    return kb

def admin_request_kb(user_id):
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("✅ Выдать номер", callback_data=f"admin_issue_{user_id}"),
        types.InlineKeyboardButton("❌ Отклонить", callback_data=f"admin_reject_{user_id}")
    )
    return kb

def admin_code_kb(user_id):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📨 Ввести код", callback_data=f"admin_enter_code_{user_id}"))
    return kb

def admin_fine_kb(user_id):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💸 Штраф", callback_data=f"admin_fine_{user_id}"))
    return kb

def balance_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("➕ Пополнить", callback_data="topup"))
    kb.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_menu"))
    return kb

def topup_amount_kb():
    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.add(
        types.InlineKeyboardButton("1$", callback_data="topup_amount_1"),
        types.InlineKeyboardButton("2$", callback_data="topup_amount_2"),
        types.InlineKeyboardButton("5$", callback_data="topup_amount_5"),
        types.InlineKeyboardButton("10$", callback_data="topup_amount_10"),
        types.InlineKeyboardButton("20$", callback_data="topup_amount_20"),
        types.InlineKeyboardButton("50$", callback_data="topup_amount_50"),
    )
    kb.add(types.InlineKeyboardButton("✏️ Своя сумма", callback_data="topup_custom"))
    kb.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_balance"))
    return kb

def pay_kb(pay_url, invoice_id):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💳 Оплатить через CryptoBot", url=pay_url))
    kb.add(types.InlineKeyboardButton("✅ Я оплатил", callback_data=f"check_payment_{invoice_id}"))
    kb.add(types.InlineKeyboardButton("❌ Отмена", callback_data="back_balance"))
    return kb

def admin_panel_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💸 Изменить штраф", callback_data="admin_set_fine"))
    kb.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_menu"))
    return kb

# ==================== HELPERS ====================

def send_main_menu(message, text="🏠 Главное меню"):
    bot.send_message(message.chat.id, text, reply_markup=main_menu())

def cancel_timer(user_id):
    if user_id in pending_requests and pending_requests[user_id].get("timer"):
        pending_requests[user_id]["timer"].cancel()
    if user_id in active_numbers and active_numbers[user_id].get("timer"):
        active_numbers[user_id]["timer"].cancel()

# ==================== /start ====================

@bot.message_handler(commands=["start"])
def cmd_start(message):
    user = message.from_user
    uid = str(user.id)
    db = load_db()
    if uid not in db["users"]:
        db["users"][uid] = {"balance": 0.0, "username": user.username or ""}
        save_db(db)
    else:
        db["users"][uid]["username"] = user.username or ""
        save_db(db)

    text = (
        f"👋 Добро пожаловать в <b>Kretros SMS Shop</b>!\n\n"
        f"👤 User: @{user.username or user.first_name}\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"💰 Баланс: <b>{db['users'][uid]['balance']}$</b>\n\n"
        f"Выберите действие в меню ниже 👇"
    )
    bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=main_menu())

# ==================== /admin ====================

@bot.message_handler(commands=["admin"])
def cmd_admin(message):
    if message.from_user.id != ADMIN_ID:
        return
    fine = get_setting("fine_amount")
    text = (
        f"⚙️ <b>Админ-панель</b>\n\n"
        f"💸 Текущий штраф: <b>{fine}$</b>"
    )
    bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=admin_panel_kb())

# ==================== BALANCE ====================

@bot.message_handler(func=lambda m: m.text == "💰 Баланс")
def btn_balance(message):
    user = message.from_user
    u = get_user(user.id)
    text = (
        f"💰 <b>Ваш баланс</b>\n\n"
        f"👤 User: @{user.username or user.first_name}\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"💵 Баланс: <b>{u['balance']}$</b>"
    )
    bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=balance_kb())

# ==================== RULES ====================

@bot.message_handler(func=lambda m: m.text == "📋 Правила")
def btn_rules(message):
    text = (
        "📋 <b>Правила сервиса</b>\n\n"
        "1️⃣ После получения номера у вас есть <b>3 минуты</b> для отправки SMS.\n"
        "2️⃣ Если SMS не пришло — номер возвращается в сток.\n"
        f"3️⃣ Штраф за истёкшее время: <b>{get_setting('fine_amount')}$</b>.\n"
        "4️⃣ Средства за неудачную попытку возвращаются на баланс.\n"
        "5️⃣ Запрещено злоупотреблять сервисом."
    )
    bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=main_menu())

# ==================== SUPPORT ====================

@bot.message_handler(func=lambda m: m.text == "🎧 Поддержка")
def btn_support(message):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💬 Написать в поддержку", url=SUPPORT_LINK))
    bot.send_message(
        message.chat.id,
        "🎧 <b>Поддержка</b>\n\nНажмите кнопку ниже, чтобы связаться с поддержкой:",
        parse_mode="HTML",
        reply_markup=kb
    )

# ==================== TAKE NUMBER ====================

@bot.message_handler(func=lambda m: m.text == "📲 Взять номер")
def btn_take_number(message):
    user = message.from_user
    uid = user.id
    msg = bot.send_message(
        message.chat.id,
        "🔍 <b>Идёт поиск номера...</b>\n\nПожалуйста, ожидайте.",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    pending_requests[uid] = {"search_msg_id": msg.message_id, "timer": None}
    username = f"@{user.username}" if user.username else user.first_name
    admin_text = (
        f"🆕 <b>Новая заявка!</b>\n\n"
        f"👤 От: {username}\n"
        f"🆔 ID: <code>{uid}</code>"
    )
    bot.send_message(ADMIN_ID, admin_text, parse_mode="HTML", reply_markup=admin_request_kb(uid))

# ==================== USER CANCEL (searching) ====================

@bot.callback_query_handler(func=lambda c: c.data == "user_cancel")
def cb_user_cancel(call):
    uid = call.from_user.id
    if uid in pending_requests:
        del pending_requests[uid]
    bot.edit_message_text("❌ Поиск отменён.", call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id)
    send_main_menu(call.message)

# ==================== ADMIN ISSUE NUMBER ====================

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_issue_"))
def cb_admin_issue(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "⛔ Нет доступа")
        return
    user_id = int(call.data.split("_")[2])
    admin_state[ADMIN_ID] = {"action": "issue_number", "user_id": user_id}
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.send_message(ADMIN_ID, "📝 Введите номер телефона для выдачи:")
    bot.answer_callback_query(call.id)

# ==================== ADMIN REJECT ====================

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_reject_"))
def cb_admin_reject(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "⛔ Нет доступа")
        return
    user_id = int(call.data.split("_")[2])
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.edit_message_text(
        f"❌ Заявка от ID <code>{user_id}</code> отклонена.",
        call.message.chat.id, call.message.message_id, parse_mode="HTML"
    )
    if user_id in pending_requests:
        try:
            bot.edit_message_text(
                "❌ <b>В стоке нет номеров.</b>\n\nСредства возвращены на ваш баланс.",
                user_id, pending_requests[user_id]["search_msg_id"], parse_mode="HTML"
            )
        except:
            bot.send_message(user_id, "❌ <b>В стоке нет номеров.</b>\n\nСредства возвращены на ваш баланс.", parse_mode="HTML")
        del pending_requests[user_id]
    bot.answer_callback_query(call.id)

# ==================== ADMIN TEXT HANDLER ====================

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and ADMIN_ID in admin_state)
def admin_text_input(message):
    state = admin_state.get(ADMIN_ID, {})
    action = state.get("action")

    # ---- ISSUE NUMBER ----
    if action == "issue_number":
        number = message.text.strip()
        user_id = state["user_id"]
        del admin_state[ADMIN_ID]
        active_numbers[user_id] = {"number": number, "timer": None}

        user_text = (
            f"✅ <b>Номер получен!</b>\n\n"
            f"├ Номер: <code>{number}</code>\n"
            f"├ Формат: СМС\n"
            f"└ 💲 Остаток: {get_user(user_id)['balance']:.4f}$\n\n"
            f"⏳ Ожидаю СМС, отправьте код в течение 3 минут"
        )
        try:
            if user_id in pending_requests:
                bot.edit_message_text(
                    user_text, user_id, pending_requests[user_id]["search_msg_id"],
                    parse_mode="HTML", reply_markup=sent_cancel_kb()
                )
            else:
                bot.send_message(user_id, user_text, parse_mode="HTML", reply_markup=sent_cancel_kb())
        except:
            bot.send_message(user_id, user_text, parse_mode="HTML", reply_markup=sent_cancel_kb())

        if user_id in pending_requests:
            del pending_requests[user_id]

        bot.send_message(ADMIN_ID, f"✅ Номер <code>{number}</code> выдан пользователю <code>{user_id}</code>.", parse_mode="HTML")

        def sms_timeout():
            if user_id in active_numbers:
                bot.send_message(
                    ADMIN_ID,
                    f"‼️ <b>СМС не пришло</b> ‼️\n\n"
                    f"📱 Номер: <code>{number}</code>\n"
                    f"👤 ID: <code>{user_id}</code>",
                    parse_mode="HTML", reply_markup=admin_fine_kb(user_id)
                )
                bot.send_message(
                    user_id,
                    "‼️ <b>СМС не пришло</b> ‼️\n\n🟢 Номер был возвращён в сток",
                    parse_mode="HTML"
                )
                del active_numbers[user_id]

        timer = threading.Timer(180, sms_timeout)
        timer.daemon = True
        timer.start()
        active_numbers[user_id]["timer"] = timer

    # ---- ENTER CODE ----
    elif action == "enter_code":
        code = message.text.strip()
        user_id = state["user_id"]
        number = state.get("number", "")
        del admin_state[ADMIN_ID]

        user_text = (
            f"‼️ <b>СМС получен</b> ‼️\n\n"
            f"├ 📱 Номер: <code>{number}</code>\n"
            f"└ 🔑 СМС: <b>{code}</b>"
        )
        bot.send_message(user_id, user_text, parse_mode="HTML")
        bot.send_message(ADMIN_ID, "✅ Код отправлен пользователю.")

        if user_id in active_numbers:
            cancel_timer(user_id)
            del active_numbers[user_id]

    # ---- SET FINE ----
    elif action == "set_fine":
        del admin_state[ADMIN_ID]
        try:
            amount = float(message.text.strip().replace(",", "."))
            set_setting("fine_amount", amount)
            bot.send_message(ADMIN_ID, f"✅ Штраф обновлён: <b>{amount}$</b>", parse_mode="HTML")
        except:
            bot.send_message(ADMIN_ID, "❌ Неверный формат. Введите число, например: 0.5")

# ==================== USER TEXT HANDLER (custom topup amount) ====================

@bot.message_handler(func=lambda m: m.from_user.id in user_state and user_state[m.from_user.id].get("action") == "custom_topup")
def user_custom_topup(message):
    uid = message.from_user.id
    del user_state[uid]
    try:
        amount = float(message.text.strip().replace(",", "."))
        if amount < 0.5:
            bot.send_message(uid, "❌ Минимальная сумма пополнения: <b>0.5$</b>", parse_mode="HTML")
            return
        process_topup(uid, amount, message.chat.id)
    except:
        bot.send_message(uid, "❌ Неверный формат. Введите число, например: 5.0")

# ==================== TOPUP FLOW ====================

@bot.callback_query_handler(func=lambda c: c.data == "topup")
def cb_topup(call):
    bot.edit_message_text(
        "💳 <b>Пополнение баланса</b>\n\n"
        "Выберите сумму или введите свою.\n"
        "Оплата принимается в USDT, TON, BTC, ETH и других монетах через @CryptoBot.",
        call.message.chat.id, call.message.message_id,
        parse_mode="HTML", reply_markup=topup_amount_kb()
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("topup_amount_"))
def cb_topup_amount(call):
    uid = call.from_user.id
    amount = float(call.data.split("_")[2])
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.answer_callback_query(call.id)
    process_topup(uid, amount, call.message.chat.id)

@bot.callback_query_handler(func=lambda c: c.data == "topup_custom")
def cb_topup_custom(call):
    uid = call.from_user.id
    user_state[uid] = {"action": "custom_topup"}
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.send_message(uid, "✏️ Введите сумму пополнения в долларах (минимум 0.5$):")
    bot.answer_callback_query(call.id)

def process_topup(user_id, amount, chat_id):
    """Создать инвойс и отправить пользователю"""
    msg = bot.send_message(chat_id, "⏳ Создаю счёт на оплату...")
    invoice = create_invoice(amount, user_id)
    if not invoice:
        bot.edit_message_text(
            "❌ Ошибка при создании счёта. Попробуйте позже или обратитесь в поддержку.",
            chat_id, msg.message_id
        )
        return

    invoice_id = invoice["invoice_id"]
    pay_url = invoice["bot_invoice_url"]

    save_invoice(invoice_id, user_id, amount)

    text = (
        f"💳 <b>Счёт на оплату создан</b>\n\n"
        f"💵 Сумма: <b>{amount}$</b>\n"
        f"🔖 Номер счёта: <code>{invoice_id}</code>\n"
        f"⏱ Действует: <b>1 час</b>\n\n"
        f"Нажмите кнопку ниже для оплаты через @CryptoBot.\n"
        f"Принимаем: USDT, TON, BTC, ETH, LTC, BNB и другие.\n\n"
        f"После оплаты нажмите <b>«✅ Я оплатил»</b>"
    )
    bot.edit_message_text(
        text, chat_id, msg.message_id,
        parse_mode="HTML", reply_markup=pay_kb(pay_url, invoice_id)
    )

    # Auto-check every 30 seconds for 1 hour
    def auto_check(check_count=0):
        if check_count >= 120:  # 120 * 30s = 1 час
            return
        inv = check_invoice(invoice_id)
        if inv and inv.get("status") == "paid":
            db_inv = get_invoice(invoice_id)
            if db_inv and not db_inv["paid"]:
                mark_invoice_paid(invoice_id)
                u = get_user(user_id)
                new_balance = round(u["balance"] + amount, 4)
                update_user(user_id, {"balance": new_balance})
                try:
                    bot.send_message(
                        user_id,
                        f"✅ <b>Баланс пополнен!</b>\n\n"
                        f"💵 Зачислено: <b>+{amount}$</b>\n"
                        f"💰 Новый баланс: <b>{new_balance}$</b>",
                        parse_mode="HTML"
                    )
                except:
                    pass
                return
        t = threading.Timer(30, auto_check, args=[check_count + 1])
        t.daemon = True
        t.start()
        invoice_checkers[invoice_id] = t

    t = threading.Timer(30, auto_check, args=[0])
    t.daemon = True
    t.start()
    invoice_checkers[invoice_id] = t

@bot.callback_query_handler(func=lambda c: c.data.startswith("check_payment_"))
def cb_check_payment(call):
    invoice_id = int(call.data.split("_")[2])
    uid = call.from_user.id
    bot.answer_callback_query(call.id, "🔍 Проверяю оплату...", show_alert=False)

    db_inv = get_invoice(invoice_id)
    if not db_inv:
        bot.send_message(uid, "❌ Счёт не найден.")
        return

    if db_inv["paid"]:
        bot.send_message(uid, "✅ Этот счёт уже был оплачен ранее.")
        return

    inv = check_invoice(invoice_id)
    if inv and inv.get("status") == "paid":
        amount = db_inv["amount"]
        mark_invoice_paid(invoice_id)
        u = get_user(uid)
        new_balance = round(u["balance"] + amount, 4)
        update_user(uid, {"balance": new_balance})
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except:
            pass
        bot.send_message(
            uid,
            f"✅ <b>Оплата подтверждена!</b>\n\n"
            f"💵 Зачислено: <b>+{amount}$</b>\n"
            f"💰 Новый баланс: <b>{new_balance}$</b>",
            parse_mode="HTML", reply_markup=main_menu()
        )
    else:
        status = inv.get("status", "неизвестен") if inv else "ошибка"
        bot.send_message(
            uid,
            f"⏳ Оплата ещё не поступила.\n\n"
            f"Статус: <b>{status}</b>\n\n"
            f"Попробуйте проверить через несколько секунд после оплаты.",
            parse_mode="HTML"
        )

# ==================== USER SENT ====================

@bot.callback_query_handler(func=lambda c: c.data == "user_sent")
def cb_user_sent(call):
    uid = call.from_user.id
    number = active_numbers.get(uid, {}).get("number", "неизвестен")
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.answer_callback_query(call.id, "✅ Ожидаем код от администратора")
    username = f"@{call.from_user.username}" if call.from_user.username else str(uid)
    bot.send_message(
        ADMIN_ID,
        f"📨 <b>Пользователь отправил SMS</b>\n\n"
        f"👤 {username}\n"
        f"📱 Номер: <code>{number}</code>\n\n"
        f"Введите полученный код:",
        parse_mode="HTML", reply_markup=admin_code_kb(uid)
    )

# ==================== USER CANCEL NUMBER ====================

@bot.callback_query_handler(func=lambda c: c.data == "user_cancel_number")
def cb_user_cancel_number(call):
    uid = call.from_user.id
    cancel_timer(uid)
    if uid in active_numbers:
        del active_numbers[uid]
    bot.edit_message_text(
        "❌ Операция отменена. Номер возвращён в сток.",
        call.message.chat.id, call.message.message_id
    )
    bot.answer_callback_query(call.id)
    send_main_menu(call.message)

# ==================== ADMIN ENTER CODE BUTTON ====================

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_enter_code_"))
def cb_admin_enter_code(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "⛔ Нет доступа")
        return
    user_id = int(call.data.split("_")[3])
    number = active_numbers.get(user_id, {}).get("number", "")
    admin_state[ADMIN_ID] = {"action": "enter_code", "user_id": user_id, "number": number}
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.send_message(ADMIN_ID, "🔑 Введите код из СМС:")
    bot.answer_callback_query(call.id)

# ==================== ADMIN FINE BUTTON ====================

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_fine_"))
def cb_admin_fine(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "⛔ Нет доступа")
        return
    user_id = int(call.data.split("_")[2])
    fine = get_setting("fine_amount")
    u = get_user(user_id)
    new_balance = round(u["balance"] - fine, 4)
    update_user(user_id, {"balance": new_balance})
    bot.send_message(
        user_id,
        f"‼️ <b>СМС не пришло</b> ‼️\n\n"
        f"🟢 Номер был возвращён в сток\n\n"
        f"🌐 Штраф: <b>{fine}$</b>",
        parse_mode="HTML"
    )
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.send_message(ADMIN_ID, f"✅ Штраф {fine}$ применён к пользователю <code>{user_id}</code>.", parse_mode="HTML")
    bot.answer_callback_query(call.id)

# ==================== BACK CALLBACKS ====================

@bot.callback_query_handler(func=lambda c: c.data == "back_balance")
def cb_back_balance(call):
    user = call.from_user
    u = get_user(user.id)
    text = (
        f"💰 <b>Ваш баланс</b>\n\n"
        f"👤 User: @{user.username or user.first_name}\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"💵 Баланс: <b>{u['balance']}$</b>"
    )
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=balance_kb())
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "back_menu")
def cb_back_menu(call):
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.send_message(call.message.chat.id, "🏠 Главное меню", reply_markup=main_menu())
    bot.answer_callback_query(call.id)

# ==================== ADMIN SET FINE ====================

@bot.callback_query_handler(func=lambda c: c.data == "admin_set_fine")
def cb_admin_set_fine(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "⛔ Нет доступа")
        return
    admin_state[ADMIN_ID] = {"action": "set_fine"}
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.send_message(ADMIN_ID, f"💸 Введите новую сумму штрафа (текущая: {get_setting('fine_amount')}$):")
    bot.answer_callback_query(call.id)

# ==================== RUN ====================

if __name__ == "__main__":
    print("🤖 Bot started...")
    bot.infinity_polling()
