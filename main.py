import telebot
from telebot import types
import json
import os
import threading
import requests
from datetime import datetime

# ==================== CONFIG ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8183211325:AAGmSXuqkxHuXz4iWLbBNhrcImFy_Em3kGE")
ADMIN_IDS = [8118184388]  # Список ID админов
SUPPORT_LINK = "https://t.me/support_username"
CRYPTO_PAY_TOKEN = os.environ.get("CRYPTOBOT_TOKEN", "582363:AALEf7JOugnrQyrkMHzH5UrO7pdOjjYnTQy")
CRYPTO_API_URL = "https://pay.crypt.bot/api"

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

# ==================== CUSTOM EMOJI ====================
E = {
    "shop":    "5307843983102204243",
    "buy":     "5307843983102204243",
    "balance": "6078158956188930337",
    "rules":   "5341715473882955310",
    "support": "5848400681416793625",
    "token":   "5449407131675558756",
    "back":    "6039539366177541657",
    "confirm": "5206607081334906820",
    "cancel":  "5210952531676504517",
    "refill":  "6078158956188930337",
    "channel": "5271604874419647061",
    "check":   "5206607081334906820",
    "pay":     "6078158956188930337",
    "price":   "5197434882321567830",
    "user":    "5906581476639513176",
    "id":      "5445353829304387411",
    "phone":   "5449407131675558756",
}

def em(key):
    return f'<tg-emoji emoji-id="{E[key]}">⭐</tg-emoji>'

def eib(label, **kwargs):
    """Inline button"""
    return types.InlineKeyboardButton(text=label, **kwargs)

# ==================== DATABASE ====================
DB_FILE      = "users_db.json"
ADMIN_DB     = "admin_db.json"
INVOICE_DB   = "invoices_db.json"

def load_users():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def load_admin_db():
    if os.path.exists(ADMIN_DB):
        with open(ADMIN_DB, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "fine_amount": 0.5,
        "number_price": 5.0,
        "menu_sticker": None,
        "banned_users": [],
    }

def save_admin_db(data):
    with open(ADMIN_DB, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_invoices():
    if os.path.exists(INVOICE_DB):
        with open(INVOICE_DB, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_invoices(data):
    with open(INVOICE_DB, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user(user_id):
    users = load_users()
    uid = str(user_id)
    if uid not in users:
        users[uid] = {"balance": 0.0, "username": ""}
        save_users(users)
    return users[uid]

def update_user(user_id, data):
    users = load_users()
    uid = str(user_id)
    if uid not in users:
        users[uid] = {"balance": 0.0, "username": ""}
    users[uid].update(data)
    save_users(users)

def get_setting(key, default=None):
    db = load_admin_db()
    return db.get(key, default)

def set_setting(key, value):
    db = load_admin_db()
    db[key] = value
    save_admin_db(db)

# ==================== CRYPTOPAY ====================

def create_invoice_crypto(amount_usd, user_id):
    headers = {
        "Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN,
        "Content-Type": "application/json"
    }
    payload = {
        "asset": "USDT",
        "amount": str(amount_usd),
        "currency_code": "USD",
        "description": f"Пополнение баланса Kretros SMS Shop | ID: {user_id}",
        "expires_in": 3600
    }
    try:
        resp = requests.post(f"{CRYPTO_API_URL}/createInvoice", headers=headers, json=payload, timeout=10)
        result = resp.json()
        if result.get("ok"):
            inv = result["result"]
            return {
                "invoice_id": inv["invoice_id"],
                "pay_url": inv.get("pay_url") or inv.get("bot_invoice_url"),
                "amount": amount_usd,
                "user_id": user_id,
                "paid": False
            }
        print(f"CryptoBot error: {result}")
        return None
    except Exception as ex:
        print(f"CryptoBot exception: {ex}")
        return None

def check_invoice_status(invoice_id):
    headers = {"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN}
    try:
        resp = requests.get(
            f"{CRYPTO_API_URL}/getInvoices?invoice_ids={invoice_id}",
            headers=headers, timeout=10
        )
        result = resp.json()
        if result.get("ok"):
            items = result["result"].get("items", [])
            if items:
                return items[0]
        return None
    except Exception as ex:
        print(f"Check invoice error: {ex}")
        return None

def monitor_invoice(invoice_id, user_id, chat_id, message_id, amount_usd):
    import time
    for _ in range(1800):  # 1 час, проверка каждые 2 сек
        time.sleep(2)
        inv = check_invoice_status(invoice_id)
        if not inv:
            continue
        status = inv.get("status")
        if status == "paid":
            invoices = load_invoices()
            if str(invoice_id) in invoices and not invoices[str(invoice_id)].get("paid"):
                invoices[str(invoice_id)]["paid"] = True
                save_invoices(invoices)
                users = load_users()
                uid = str(user_id)
                if uid in users:
                    users[uid]["balance"] = round(users[uid]["balance"] + amount_usd, 2)
                    save_users(users)
                new_balance = get_user(user_id)["balance"]
                try:
                    bot.edit_message_text(
                        f"✅ <b>Оплата получена!</b>\n\n"
                        f"💵 Зачислено: <b>+{amount_usd}$</b>\n"
                        f"💰 Новый баланс: <b>{new_balance}$</b>",
                        chat_id, message_id, parse_mode="HTML"
                    )
                except:
                    pass
                try:
                    time.sleep(2)
                    bot.delete_message(chat_id, message_id)
                    show_balance_inline(chat_id, user_id)
                except:
                    pass
            break
        elif status == "expired":
            try:
                markup = types.InlineKeyboardMarkup()
                markup.add(eib(f"{em('back')} Назад", callback_data="back_balance"))
                bot.edit_message_text(
                    "❌ Время оплаты истекло. Создайте новый счёт.",
                    chat_id, message_id, reply_markup=markup, parse_mode="HTML"
                )
            except:
                pass
            break

# ==================== STATE ====================
pending_requests = {}   # {user_id: {"search_msg_id": ...}}
active_numbers   = {}   # {user_id: {"number": ..., "timer": ...}}
admin_state      = {}   # {admin_id: {"action": ..., ...}}
user_state       = {}   # {user_id: {"action": ..., ...}}

# ==================== HELPERS ====================

def is_admin(user_id):
    return user_id in ADMIN_IDS

def is_banned(user_id):
    db = load_admin_db()
    return str(user_id) in db.get("banned_users", [])

def register_user(user):
    users = load_users()
    uid = str(user.id)
    if uid not in users:
        users[uid] = {
            "username": user.username or "Unknown",
            "id": user.id,
            "balance": 0.0,
            "joined": datetime.now().isoformat()
        }
        save_users(users)
    else:
        users[uid]["username"] = user.username or users[uid].get("username", "Unknown")
        save_users(users)

def cancel_timer(user_id):
    if user_id in active_numbers and active_numbers[user_id].get("timer"):
        active_numbers[user_id]["timer"].cancel()

# ==================== KEYBOARDS ====================

def main_menu_kb():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(eib(f"{em('phone')} Взять номер", callback_data="take_number"))
    kb.add(
        eib(f"{em('balance')} Баланс", callback_data="check_balance"),
        eib(f"{em('rules')} Правила",  callback_data="rules")
    )
    kb.add(eib(f"{em('support')} Поддержка", url=SUPPORT_LINK))
    return kb

def balance_kb():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("Пополнить баланс", callback_data="refill_balance"))
    kb.add(types.InlineKeyboardButton("Назад", callback_data="back_to_menu"))
    return kb

def topup_amount_kb():
    kb = types.InlineKeyboardMarkup(row_width=3)
    for amt in [1, 2, 5, 10, 20, 50]:
        kb.add(eib(f"{amt}$", callback_data=f"topup_amount_{amt}"))
    kb.add(eib("✏️ Своя сумма", callback_data="topup_custom"))
    kb.add(eib(f"{em('back')} Назад", callback_data="back_balance"))
    return kb

def pay_kb(pay_url, invoice_id):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(eib(f"{em('pay')} Оплатить через CryptoBot", url=pay_url))
    kb.add(eib(f"{em('check')} Я оплатил", callback_data=f"check_payment_{invoice_id}"))
    kb.add(eib(f"{em('cancel')} Отмена", callback_data="back_balance"))
    return kb

def cancel_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(eib(f"{em('cancel')} Отмена", callback_data="user_cancel"))
    return kb

def sent_cancel_kb():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(eib(f"{em('confirm')} Отправил", callback_data="user_sent"))
    kb.add(eib(f"{em('cancel')} Отмена", callback_data="user_cancel_number"))
    return kb

def admin_request_kb(user_id):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        eib("✅ Выдать номер", callback_data=f"admin_issue_{user_id}"),
        eib("❌ Отклонить",    callback_data=f"admin_reject_{user_id}")
    )
    return kb

def admin_code_kb(user_id):
    kb = types.InlineKeyboardMarkup()
    kb.add(eib("📨 Ввести код", callback_data=f"admin_enter_code_{user_id}"))
    return kb

def admin_fine_kb(user_id):
    kb = types.InlineKeyboardMarkup()
    kb.add(eib("💸 Применить штраф", callback_data=f"admin_fine_{user_id}"))
    return kb

def admin_panel_kb():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        eib("💸 Изменить штраф",       callback_data="admin_set_fine"),
        eib("💲 Изменить цену номера", callback_data="admin_set_price"),
        eib("🎁 Выдать баланс юзеру",  callback_data="admin_give_balance"),
        eib("🚫 Бан / Разбан",         callback_data="admin_ban"),
        eib("🖼 Стикер меню",          callback_data="admin_set_sticker"),
    )
    return kb

# ==================== SHOW MENU ====================

def show_main_menu(chat_id, user_id, message_id=None):
    u = get_user(user_id)
    balance  = u.get("balance", 0)
    username = u.get("username", "Unknown")

    text = (
        f"<b>Kretros Shop</b>\n"
        f"——————————————\n"
        f"|{em('user')} User: @{username}!\n"
        f"|{em('id')} ID: {user_id}\n"
        f"|{em('balance')} Баланс: {balance}$\n"
        f"——————————————"
    )

    if message_id:
        try:
            bot.edit_message_text(
                text, chat_id, message_id,
                reply_markup=main_menu_kb(), parse_mode="HTML"
            )
            return
        except:
            pass

    # Отправляем стикер перед меню
    db = load_admin_db()
    sticker_id = db.get("menu_sticker")
    if sticker_id:
        try:
            bot.send_sticker(chat_id, sticker_id)
        except:
            pass

    bot.send_message(chat_id, text, reply_markup=main_menu_kb(), parse_mode="HTML")

def show_balance_inline(chat_id, user_id, message_id=None):
    u = get_user(user_id)
    balance  = u.get("balance", 0)
    username = u.get("username", "Unknown")

    text = (
        f"——————————————\n"
        f'|<tg-emoji emoji-id="5906581476639513176">⭐</tg-emoji>User: @{username}!\n'
        f'|<tg-emoji emoji-id="5445353829304387411">⭐</tg-emoji>ID: {user_id}\n'
        f'|<tg-emoji emoji-id="6078158956188930337">⭐</tg-emoji>Баланс: {balance}$\n'
        f"——————————————"
    )

    if message_id:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=balance_kb(), parse_mode="HTML")
    else:
        bot.send_message(chat_id, text, reply_markup=balance_kb(), parse_mode="HTML")

# ==================== /start ====================

@bot.message_handler(commands=["start"])
def cmd_start(message):
    user = message.from_user
    if is_banned(user.id):
        return
    register_user(user)
    show_main_menu(message.chat.id, user.id)

# ==================== /admin ====================

@bot.message_handler(commands=["admin"])
def cmd_admin(message):
    if not is_admin(message.from_user.id):
        return
    fine  = get_setting("fine_amount", 0.5)
    price = get_setting("number_price", 5.0)
    bot.send_message(
        message.chat.id,
        f"⚙️ <b>Админ-панель</b>\n\n"
        f"💸 Штраф: <b>{fine}$</b>\n"
        f"💲 Цена номера: <b>{price}$</b>",
        parse_mode="HTML", reply_markup=admin_panel_kb()
    )

# ==================== /getfileid ====================

@bot.message_handler(commands=["getfileid"])
def cmd_getfileid(message):
    if not is_admin(message.from_user.id):
        return
    msg = bot.send_message(message.chat.id, "Отправь стикер, который будет показываться перед меню:")
    bot.register_next_step_handler(msg, save_sticker)

def save_sticker(message):
    if not is_admin(message.from_user.id):
        return
    if not message.sticker:
        bot.send_message(message.chat.id, "Это не стикер! Попробуй /getfileid ещё раз.")
        return
    set_setting("menu_sticker", message.sticker.file_id)
    bot.send_message(message.chat.id, f"✅ Стикер сохранён!\n<code>{message.sticker.file_id}</code>", parse_mode="HTML")

# ==================== MAIN MENU CALLBACKS ====================

@bot.callback_query_handler(func=lambda c: c.data == "back_to_menu")
def cb_back_to_menu(call):
    if is_banned(call.from_user.id):
        return
    bot.clear_step_handler_by_chat_id(call.message.chat.id)
    show_main_menu(call.message.chat.id, call.from_user.id, call.message.message_id)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "rules")
def cb_rules(call):
    fine = get_setting("fine_amount", 0.5)
    markup = types.InlineKeyboardMarkup()
    markup.add(eib(f"{em('back')} Назад", callback_data="back_to_menu"))
    bot.edit_message_text(
        f"📋 <b>Правила сервиса</b>\n\n"
        f"1️⃣ После получения номера у вас есть <b>3 минуты</b> для отправки SMS.\n"
        f"2️⃣ Если SMS не пришло — номер возвращается в сток.\n"
        f"3️⃣ Штраф за истёкшее время: <b>{fine}$</b>.\n"
        f"4️⃣ Средства за неудачную попытку возвращаются на баланс.\n"
        f"5️⃣ Запрещено злоупотреблять сервисом.",
        call.message.chat.id, call.message.message_id,
        reply_markup=markup, parse_mode="HTML"
    )
    bot.answer_callback_query(call.id)

# ==================== BALANCE ====================

@bot.callback_query_handler(func=lambda c: c.data == "check_balance")
def cb_check_balance(call):
    if is_banned(call.from_user.id):
        return
    bot.clear_step_handler_by_chat_id(call.message.chat.id)
    show_balance_inline(call.message.chat.id, call.from_user.id, call.message.message_id)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "back_balance")
def cb_back_balance(call):
    bot.clear_step_handler_by_chat_id(call.message.chat.id)
    show_balance_inline(call.message.chat.id, call.from_user.id, call.message.message_id)
    bot.answer_callback_query(call.id)

# ==================== TOPUP ====================

@bot.callback_query_handler(func=lambda c: c.data == "refill_balance")
def cb_refill_balance(call):
    if is_banned(call.from_user.id):
        return
    bot.clear_step_handler_by_chat_id(call.message.chat.id)
    bot.edit_message_text(
        f"{em('refill')} <b>Пополнение баланса</b>\n\n"
        f"{em('buy')} Выберите сумму или введите свою.\n"
        f"Принимаем: USDT, TON, BTC, ETH, LTC, BNB и другие через @CryptoBot.",
        call.message.chat.id, call.message.message_id,
        reply_markup=topup_amount_kb(), parse_mode="HTML"
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("topup_amount_"))
def cb_topup_amount(call):
    amount = float(call.data.split("_")[2])
    bot.answer_callback_query(call.id)
    process_topup(call.from_user.id, amount, call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda c: c.data == "topup_custom")
def cb_topup_custom(call):
    uid = call.from_user.id
    user_state[uid] = {"action": "custom_topup", "msg_id": call.message.message_id}
    markup = types.InlineKeyboardMarkup()
    markup.add(eib(f"{em('back')} Назад", callback_data="refill_balance"))
    msg = bot.edit_message_text(
        f"{em('refill')} <b>Пополнение баланса</b>\n\n"
        f"Введите сумму в $ (минимум 1$):",
        call.message.chat.id, call.message.message_id,
        reply_markup=markup, parse_mode="HTML"
    )
    bot.register_next_step_handler(msg, handle_custom_topup_input, call.message.message_id)
    bot.answer_callback_query(call.id)

def handle_custom_topup_input(message, msg_id):
    uid = message.from_user.id
    user_state.pop(uid, None)
    try:
        bot.delete_message(message.chat.id, message.message_id)
    except:
        pass
    try:
        amount = float(message.text.strip().replace(",", "."))
        if amount < 1:
            markup = types.InlineKeyboardMarkup()
            markup.add(eib(f"{em('back')} Назад", callback_data="refill_balance"))
            m = bot.edit_message_text(
                f"{em('cancel')} Минимальная сумма 1$!\n\nВведите сумму заново:",
                message.chat.id, msg_id, reply_markup=markup, parse_mode="HTML"
            )
            bot.register_next_step_handler(m, handle_custom_topup_input, msg_id)
            return
        process_topup(uid, amount, message.chat.id, msg_id)
    except:
        markup = types.InlineKeyboardMarkup()
        markup.add(eib(f"{em('back')} Назад", callback_data="refill_balance"))
        m = bot.edit_message_text(
            f"{em('cancel')} Введите число! Например: 5.0",
            message.chat.id, msg_id, reply_markup=markup, parse_mode="HTML"
        )
        bot.register_next_step_handler(m, handle_custom_topup_input, msg_id)

def process_topup(user_id, amount, chat_id, message_id):
    markup = types.InlineKeyboardMarkup()
    markup.add(eib(f"{em('back')} Назад", callback_data="refill_balance"))
    bot.edit_message_text(
        f"⏳ Создаю счёт на <b>{amount}$</b>...",
        chat_id, message_id, reply_markup=markup, parse_mode="HTML"
    )
    invoice = create_invoice_crypto(amount, user_id)
    if not invoice:
        bot.edit_message_text(
            f"{em('cancel')} <b>Ошибка создания счёта.</b>\n\nПопробуйте позже или обратитесь в поддержку.",
            chat_id, message_id, reply_markup=markup, parse_mode="HTML"
        )
        return

    invoice_id = invoice["invoice_id"]
    pay_url    = invoice["pay_url"]

    invoices = load_invoices()
    invoices[str(invoice_id)] = invoice
    save_invoices(invoices)

    bot.edit_message_text(
        f"{em('pay')} <b>Счёт на оплату создан</b>\n\n"
        f"{em('price')} Сумма: <b>{amount}$</b>\n"
        f"🔖 Номер счёта: <code>{invoice_id}</code>\n"
        f"⏱ Действует: <b>1 час</b>\n\n"
        f"Оплата через @CryptoBot: USDT, TON, BTC, ETH, LTC, BNB и другие.\n\n"
        f"После оплаты нажмите <b>«{em('check')} Я оплатил»</b>",
        chat_id, message_id,
        reply_markup=pay_kb(pay_url, invoice_id), parse_mode="HTML"
    )

    thread = threading.Thread(
        target=monitor_invoice,
        args=(invoice_id, user_id, chat_id, message_id, amount)
    )
    thread.daemon = True
    thread.start()

@bot.callback_query_handler(func=lambda c: c.data.startswith("check_payment_"))
def cb_check_payment(call):
    invoice_id = int(call.data.split("_")[2])
    uid = call.from_user.id
    bot.answer_callback_query(call.id, "🔍 Проверяю оплату...", show_alert=False)

    invoices = load_invoices()
    inv_data = invoices.get(str(invoice_id))
    if not inv_data:
        bot.send_message(uid, "❌ Счёт не найден.")
        return
    if inv_data.get("paid"):
        bot.send_message(uid, "✅ Этот счёт уже был оплачен ранее.")
        return

    inv = check_invoice_status(invoice_id)
    if inv and inv.get("status") == "paid":
        amount = inv_data["amount"]
        invoices[str(invoice_id)]["paid"] = True
        save_invoices(invoices)
        users = load_users()
        uid_s = str(uid)
        if uid_s in users:
            users[uid_s]["balance"] = round(users[uid_s]["balance"] + amount, 2)
            save_users(users)
        new_balance = get_user(uid)["balance"]
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except:
            pass
        bot.send_message(
            uid,
            f"{em('confirm')} <b>Оплата подтверждена!</b>\n\n"
            f"💵 Зачислено: <b>+{amount}$</b>\n"
            f"{em('balance')} Новый баланс: <b>{new_balance}$</b>",
            parse_mode="HTML"
        )
        show_balance_inline(call.message.chat.id, uid)
    else:
        status = inv.get("status", "неизвестен") if inv else "ошибка"
        bot.answer_callback_query(
            call.id,
            f"⏳ Оплата ещё не поступила.\nСтатус: {status}",
            show_alert=True
        )

# ==================== TAKE NUMBER ====================

@bot.callback_query_handler(func=lambda c: c.data == "take_number")
def cb_take_number(call):
    user = call.from_user
    uid  = user.id
    if is_banned(uid):
        return

    price = get_setting("number_price", 5.0)
    u = get_user(uid)
    if u["balance"] < price:
        markup = types.InlineKeyboardMarkup()
        markup.add(eib(f"{em('refill')} Пополнить баланс", callback_data="refill_balance"))
        markup.add(eib(f"{em('back')} Назад", callback_data="back_to_menu"))
        bot.edit_message_text(
            f"{em('cancel')} <b>Недостаточно средств!</b>\n\n"
            f"💲 Стоимость номера: <b>{price}$</b>\n"
            f"{em('balance')} Ваш баланс: <b>{u['balance']}$</b>",
            call.message.chat.id, call.message.message_id,
            reply_markup=markup, parse_mode="HTML"
        )
        bot.answer_callback_query(call.id)
        return

    bot.edit_message_text(
        f"🔍 <b>Идёт поиск номера...</b>\n\nПожалуйста, ожидайте.",
        call.message.chat.id, call.message.message_id,
        reply_markup=cancel_kb(), parse_mode="HTML"
    )
    bot.answer_callback_query(call.id)

    pending_requests[uid] = {"search_msg_id": call.message.message_id, "chat_id": call.message.chat.id}

    username = f"@{user.username}" if user.username else user.first_name
    for admin_id in ADMIN_IDS:
        bot.send_message(
            admin_id,
            f"🆕 <b>Новая заявка!</b>\n\n"
            f"{em('user')} От: {username}\n"
            f"{em('id')} ID: <code>{uid}</code>\n"
            f"💲 Стоимость: <b>{price}$</b>",
            parse_mode="HTML", reply_markup=admin_request_kb(uid)
        )

@bot.callback_query_handler(func=lambda c: c.data == "user_cancel")
def cb_user_cancel(call):
    uid = call.from_user.id
    pending_requests.pop(uid, None)
    show_main_menu(call.message.chat.id, uid, call.message.message_id)
    bot.answer_callback_query(call.id)

# ==================== ADMIN ISSUE ====================

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_issue_"))
def cb_admin_issue(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ Нет доступа")
        return
    user_id = int(call.data.split("_")[2])
    admin_state[call.from_user.id] = {"action": "issue_number", "user_id": user_id}
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.send_message(call.message.chat.id, "📝 Введите номер телефона для выдачи:")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_reject_"))
def cb_admin_reject(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ Нет доступа")
        return
    user_id = int(call.data.split("_")[2])
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.edit_message_text(
        f"❌ Заявка от <code>{user_id}</code> отклонена.",
        call.message.chat.id, call.message.message_id, parse_mode="HTML"
    )
    req = pending_requests.pop(user_id, None)
    if req:
        try:
            bot.edit_message_text(
                f"{em('cancel')} <b>В стоке нет номеров.</b>\n\nСредства возвращены на ваш баланс.",
                req["chat_id"], req["search_msg_id"],
                reply_markup=types.InlineKeyboardMarkup().add(
                    eib(f"{em('back')} В меню", callback_data="back_to_menu")
                ),
                parse_mode="HTML"
            )
        except:
            bot.send_message(
                user_id,
                f"{em('cancel')} <b>В стоке нет номеров.</b>\n\nСредства возвращены на ваш баланс.",
                parse_mode="HTML"
            )
    bot.answer_callback_query(call.id)

# ==================== ADMIN TEXT HANDLER ====================

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.from_user.id in admin_state)
def admin_text_input(message):
    aid   = message.from_user.id
    state = admin_state.get(aid, {})
    action = state.get("action")

    # ---------- ISSUE NUMBER ----------
    if action == "issue_number":
        number  = message.text.strip()
        user_id = state["user_id"]
        price   = get_setting("number_price", 5.0)
        del admin_state[aid]

        # Списываем с баланса
        u = get_user(user_id)
        new_balance = round(u["balance"] - price, 2)
        update_user(user_id, {"balance": new_balance})

        active_numbers[user_id] = {"number": number, "timer": None}

        user_text = (
            f"✅ <b>Номер получен!</b>\n\n"
            f"├ {em('phone')} Номер: <code>{number}</code>\n"
            f"├ Формат: СМС\n"
            f"└ {em('balance')} Остаток: {new_balance:.4f}$\n\n"
            f"⏳ Ожидаю СМС, отправьте код в течение 3 минут"
        )
        req = pending_requests.pop(user_id, None)
        try:
            if req:
                bot.edit_message_text(
                    user_text, req["chat_id"], req["search_msg_id"],
                    parse_mode="HTML", reply_markup=sent_cancel_kb()
                )
            else:
                bot.send_message(user_id, user_text, parse_mode="HTML", reply_markup=sent_cancel_kb())
        except:
            bot.send_message(user_id, user_text, parse_mode="HTML", reply_markup=sent_cancel_kb())

        bot.send_message(aid, f"✅ Номер <code>{number}</code> выдан пользователю <code>{user_id}</code>.", parse_mode="HTML")

        def sms_timeout():
            if user_id in active_numbers:
                for a in ADMIN_IDS:
                    bot.send_message(
                        a,
                        f"‼️ <b>СМС не пришло</b> ‼️\n\n"
                        f"{em('phone')} Номер: <code>{number}</code>\n"
                        f"{em('id')} ID: <code>{user_id}</code>",
                        parse_mode="HTML", reply_markup=admin_fine_kb(user_id)
                    )
                bot.send_message(
                    user_id,
                    f"‼️ <b>СМС не пришло</b> ‼️\n\n🟢 Номер был возвращён в сток",
                    parse_mode="HTML"
                )
                del active_numbers[user_id]

        timer = threading.Timer(180, sms_timeout)
        timer.daemon = True
        timer.start()
        active_numbers[user_id]["timer"] = timer

    # ---------- ENTER CODE ----------
    elif action == "enter_code":
        code    = message.text.strip()
        user_id = state["user_id"]
        number  = state.get("number", "")
        del admin_state[aid]

        bot.send_message(
            user_id,
            f"‼️ <b>СМС получен</b> ‼️\n\n"
            f"├ {em('phone')} Номер: <code>{number}</code>\n"
            f"└ 🔑 СМС: <b>{code}</b>",
            parse_mode="HTML"
        )
        bot.send_message(aid, "✅ Код отправлен пользователю.")

        if user_id in active_numbers:
            cancel_timer(user_id)
            del active_numbers[user_id]

    # ---------- SET FINE ----------
    elif action == "set_fine":
        del admin_state[aid]
        try:
            amount = float(message.text.strip().replace(",", "."))
            set_setting("fine_amount", amount)
            bot.send_message(aid, f"✅ Штраф обновлён: <b>{amount}$</b>", parse_mode="HTML")
        except:
            bot.send_message(aid, "❌ Неверный формат. Пример: 0.5")

    # ---------- SET PRICE ----------
    elif action == "set_price":
        del admin_state[aid]
        try:
            price = float(message.text.strip().replace(",", "."))
            set_setting("number_price", price)
            bot.send_message(aid, f"✅ Цена номера обновлена: <b>{price}$</b>", parse_mode="HTML")
        except:
            bot.send_message(aid, "❌ Неверный формат. Пример: 5.0")

    # ---------- GIVE BALANCE ----------
    elif action == "give_balance_id":
        try:
            target_id = int(message.text.strip())
            admin_state[aid] = {"action": "give_balance_amount", "target_id": target_id}
            bot.send_message(aid, f"Введи сумму для выдачи пользователю <code>{target_id}</code>:", parse_mode="HTML")
        except:
            del admin_state[aid]
            bot.send_message(aid, "❌ Неверный ID. Введи числовой ID.")

    elif action == "give_balance_amount":
        target_id = state["target_id"]
        del admin_state[aid]
        try:
            amount = float(message.text.strip().replace(",", "."))
            users = load_users()
            uid_s = str(target_id)
            if uid_s not in users:
                users[uid_s] = {"balance": 0.0, "username": "Unknown", "id": target_id}
            users[uid_s]["balance"] = round(users[uid_s]["balance"] + amount, 2)
            save_users(users)
            bot.send_message(aid, f"✅ Выдано <b>{amount}$</b> пользователю <code>{target_id}</code>.", parse_mode="HTML")
            try:
                bot.send_message(
                    target_id,
                    f"{em('refill')} <b>Вам начислено {amount}$</b>\n\n"
                    f"{em('balance')} Текущий баланс: <b>{users[uid_s]['balance']}$</b>",
                    parse_mode="HTML"
                )
            except:
                pass
        except:
            bot.send_message(aid, "❌ Неверный формат суммы.")

    # ---------- BAN ----------
    elif action == "ban_user":
        del admin_state[aid]
        try:
            target_id = str(int(message.text.strip()))
            db = load_admin_db()
            banned = db.get("banned_users", [])
            if target_id in banned:
                banned.remove(target_id)
                db["banned_users"] = banned
                save_admin_db(db)
                bot.send_message(aid, f"✅ Пользователь <code>{target_id}</code> разбанен.", parse_mode="HTML")
            else:
                banned.append(target_id)
                db["banned_users"] = banned
                save_admin_db(db)
                bot.send_message(aid, f"🚫 Пользователь <code>{target_id}</code> забанен.", parse_mode="HTML")
        except:
            bot.send_message(aid, "❌ Неверный ID.")

# ==================== USER SENT ====================

@bot.callback_query_handler(func=lambda c: c.data == "user_sent")
def cb_user_sent(call):
    uid    = call.from_user.id
    number = active_numbers.get(uid, {}).get("number", "неизвестен")
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.answer_callback_query(call.id, "✅ Ожидаем код от администратора")
    username = f"@{call.from_user.username}" if call.from_user.username else str(uid)
    for aid in ADMIN_IDS:
        bot.send_message(
            aid,
            f"📨 <b>Пользователь отправил SMS</b>\n\n"
            f"{em('user')} {username}\n"
            f"{em('phone')} Номер: <code>{number}</code>\n\n"
            f"Введите полученный код:",
            parse_mode="HTML", reply_markup=admin_code_kb(uid)
        )

@bot.callback_query_handler(func=lambda c: c.data == "user_cancel_number")
def cb_user_cancel_number(call):
    uid = call.from_user.id
    cancel_timer(uid)
    active_numbers.pop(uid, None)
    show_main_menu(call.message.chat.id, uid, call.message.message_id)
    bot.answer_callback_query(call.id)

# ==================== ADMIN ENTER CODE ====================

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_enter_code_"))
def cb_admin_enter_code(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ Нет доступа")
        return
    user_id = int(call.data.split("_")[3])
    number  = active_numbers.get(user_id, {}).get("number", "")
    admin_state[call.from_user.id] = {"action": "enter_code", "user_id": user_id, "number": number}
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.send_message(call.message.chat.id, "🔑 Введите код из СМС:")
    bot.answer_callback_query(call.id)

# ==================== ADMIN FINE ====================

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_fine_"))
def cb_admin_fine(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ Нет доступа")
        return
    user_id = int(call.data.split("_")[2])
    fine    = get_setting("fine_amount", 0.5)
    u       = get_user(user_id)
    new_bal = round(u["balance"] - fine, 4)
    update_user(user_id, {"balance": new_bal})

    # Редактируем сообщение пользователю (не отправляем новое)
    try:
        bot.send_message(
            user_id,
            f"‼️ <b>СМС не пришло</b> ‼️\n\n"
            f"🟢 Номер был возвращён в сток\n\n"
            f"🌐 Штраф: <b>{fine}$</b>",
            parse_mode="HTML"
        )
    except:
        pass

    # Редактируем сообщение у админа — убираем кнопку штрафа
    bot.edit_message_text(
        f"✅ Штраф <b>{fine}$</b> применён к пользователю <code>{user_id}</code>.\n"
        f"💰 Новый баланс юзера: <b>{new_bal}$</b>",
        call.message.chat.id, call.message.message_id,
        parse_mode="HTML"
    )
    bot.answer_callback_query(call.id)

# ==================== ADMIN PANEL CALLBACKS ====================

@bot.callback_query_handler(func=lambda c: c.data == "admin_set_fine")
def cb_admin_set_fine(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ Нет доступа")
        return
    admin_state[call.from_user.id] = {"action": "set_fine"}
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.send_message(call.message.chat.id, f"💸 Текущий штраф: {get_setting('fine_amount', 0.5)}$\n\nВведите новую сумму штрафа:")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "admin_set_price")
def cb_admin_set_price(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ Нет доступа")
        return
    admin_state[call.from_user.id] = {"action": "set_price"}
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.send_message(call.message.chat.id, f"💲 Текущая цена номера: {get_setting('number_price', 5.0)}$\n\nВведите новую цену:")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "admin_give_balance")
def cb_admin_give_balance(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ Нет доступа")
        return
    admin_state[call.from_user.id] = {"action": "give_balance_id"}
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.send_message(call.message.chat.id, "👤 Введите Telegram ID пользователя:")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "admin_ban")
def cb_admin_ban(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ Нет доступа")
        return
    admin_state[call.from_user.id] = {"action": "ban_user"}
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.send_message(call.message.chat.id, "🚫 Введите ID пользователя для бана/разбана:")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "admin_set_sticker")
def cb_admin_set_sticker(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ Нет доступа")
        return
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    msg = bot.send_message(call.message.chat.id, "🖼 Отправь стикер для главного меню:")
    bot.register_next_step_handler(msg, save_sticker)
    bot.answer_callback_query(call.id)

# ==================== RUN ====================

if __name__ == "__main__":
    print("🤖 Bot started...")
    bot.infinity_polling()
