import json
import os
import re
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ==================== НАСТРОЙКИ ====================
TOKEN = "8935313158:AAGWvUM64akbazcHvJFfjwqQfZ10QAea-Rw"
ADMIN_ID = 8563327706

# Файлы для хранения данных
TICKETS_FILE = "tickets.json"
USERS_FILE = "users.json"
BLACKLIST_FILE = "blacklist.json"
SETTINGS_FILE = "settings.json"

# ==================== РАБОТА С JSON ====================
def load_json(file):
    if os.path.exists(file):
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_next_id():
    tickets = load_json(TICKETS_FILE)
    return max([int(k) for k in tickets.keys()] + [0]) + 1

# ==================== КЛАВИАТУРЫ ====================

# Главное меню пользователя
def get_user_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("📋 Мои тикеты", callback_data="user_my_tickets")],
        [InlineKeyboardButton("❓ FAQ", callback_data="user_faq")],
        [InlineKeyboardButton("⭐ Оценить поддержку", callback_data="user_rate")],
        [InlineKeyboardButton("📞 Связаться с админом", callback_data="user_contact_admin")],
    ]
    return InlineKeyboardMarkup(keyboard)

# Список тикетов пользователя
def get_user_tickets_keyboard(user_id):
    tickets = load_json(TICKETS_FILE)
    keyboard = []
    for tid, data in tickets.items():
        if data.get("user_id") == user_id and data.get("status") != "closed":
            emoji = "🟡" if data["status"] == "open" else "🟢"
            keyboard.append([InlineKeyboardButton(f"{emoji} Тикет #{tid}", callback_data=f"user_view_{tid}")])
    if not keyboard:
        keyboard.append([InlineKeyboardButton("📭 Нет активных тикетов", callback_data="noop")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="user_back")])
    return InlineKeyboardMarkup(keyboard)

# Действия с тикетом для пользователя
def get_user_ticket_actions(ticket_id):
    keyboard = [
        [InlineKeyboardButton("➕ Добавить сообщение", callback_data=f"user_add_msg_{ticket_id}")],
        [InlineKeyboardButton("🔴 Закрыть тикет", callback_data=f"user_close_{ticket_id}")],
        [InlineKeyboardButton("🔙 Назад", callback_data="user_my_tickets")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Главное меню администратора
def get_admin_main_keyboard():
    tickets = load_json(TICKETS_FILE)
    open_count = sum(1 for t in tickets.values() if t.get("status") == "open")
    progress_count = sum(1 for t in tickets.values() if t.get("status") == "in_progress")
    
    keyboard = [
        [InlineKeyboardButton(f"🟡 Открытые ({open_count})", callback_data="admin_list_open")],
        [InlineKeyboardButton(f"🟢 В работе ({progress_count})", callback_data="admin_list_progress")],
        [InlineKeyboardButton("📋 Все тикеты", callback_data="admin_list_all")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🚫 Черный список", callback_data="admin_blacklist")],
        [InlineKeyboardButton("⚙ Настройки", callback_data="admin_settings")],
        [InlineKeyboardButton("📁 Экспорт данных", callback_data="admin_export")],
    ]
    return InlineKeyboardMarkup(keyboard)

# Список тикетов для администратора
def get_admin_tickets_list(status=None):
    tickets = load_json(TICKETS_FILE)
    keyboard = []
    
    filtered = {}
    if status == "open":
        filtered = {k: v for k, v in tickets.items() if v.get("status") == "open"}
    elif status == "in_progress":
        filtered = {k: v for k, v in tickets.items() if v.get("status") == "in_progress"}
    else:
        filtered = tickets
    
    # Сортируем по дате (новые сверху)
    sorted_items = sorted(filtered.items(), key=lambda x: x[1].get("created_at", ""), reverse=True)
    
    for tid, data in sorted_items[:20]:
        emoji = "🟡" if data["status"] == "open" else "🟢" if data["status"] == "in_progress" else "🔴"
        name = data.get("user_name", "Unknown")[:20]
        keyboard.append([InlineKeyboardButton(f"{emoji} #{tid} — {name}", callback_data=f"admin_view_{tid}")])
    
    if not keyboard:
        keyboard.append([InlineKeyboardButton("📭 Нет тикетов", callback_data="noop")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_back")])
    return InlineKeyboardMarkup(keyboard)

# Действия с тикетом для администратора
def get_admin_ticket_actions(ticket_id):
    tickets = load_json(TICKETS_FILE)
    ticket = tickets.get(str(ticket_id), {})
    status = ticket.get("status", "open")
    keyboard = []
    
    if status == "open":
        keyboard.append([InlineKeyboardButton("🟢 Взять в работу", callback_data=f"admin_take_{ticket_id}")])
    elif status == "in_progress":
        keyboard.append([InlineKeyboardButton("💬 Ответить и закрыть", callback_data=f"admin_reply_{ticket_id}")])
        keyboard.append([InlineKeyboardButton("🔴 Закрыть без ответа", callback_data=f"admin_close_{ticket_id}")])
    
    keyboard.append([InlineKeyboardButton("👤 Инфо о пользователе", callback_data=f"admin_user_{ticket_id}")])
    keyboard.append([InlineKeyboardButton("🚫 Заблокировать", callback_data=f"admin_block_{ticket_id}")])
    keyboard.append([InlineKeyboardButton("🗑 Удалить тикет", callback_data=f"admin_delete_{ticket_id}")])
    keyboard.append([InlineKeyboardButton("📌 Закрепить", callback_data=f"admin_pin_{ticket_id}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_back")])
    
    return InlineKeyboardMarkup(keyboard)

# Клавиатура для оценки
def get_rating_keyboard(ticket_id):
    keyboard = [
        [InlineKeyboardButton("⭐ 1", callback_data=f"rate_1_{ticket_id}"),
         InlineKeyboardButton("⭐⭐ 2", callback_data=f"rate_2_{ticket_id}"),
         InlineKeyboardButton("⭐⭐⭐ 3", callback_data=f"rate_3_{ticket_id}")],
        [InlineKeyboardButton("⭐⭐⭐⭐ 4", callback_data=f"rate_4_{ticket_id}"),
         InlineKeyboardButton("⭐⭐⭐⭐⭐ 5", callback_data=f"rate_5_{ticket_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ==================== ОБРАБОТЧИКИ ПОЛЬЗОВАТЕЛЯ ====================

async def start(update, context):
    user = update.effective_user
    
    # Проверка в черном списке
    blacklist = load_json(BLACKLIST_FILE)
    if str(user.id) in blacklist:
        await update.message.reply_text("🚫 Вы заблокированы в системе поддержки.")
        return
    
    # Сохраняем пользователя
    users = load_json(USERS_FILE)
    if str(user.id) not in users:
        users[str(user.id)] = {
            "first_name": user.first_name,
            "username": user.username or "нет",
            "chat_id": update.message.chat_id,
            "created": datetime.now().isoformat(),
            "total_tickets": 0
        }
        save_json(USERS_FILE, users)
    
    if user.id == ADMIN_ID:
        await update.message.reply_text(
            "👋 **Панель администратора**\n\n"
            "Выбери действие:",
            reply_markup=get_admin_main_keyboard()
        )
    else:
        await update.message.reply_text(
            f"👋 Привет, {user.first_name}!\n\n"
            "🤖 **Техподдержка Energy Online**\n\n"
            "Напиши свой вопрос — я создам тикет.\n"
            "Используй кнопки для управления:",
            reply_markup=get_user_main_keyboard()
        )

# ==================== ПОЛЬЗОВАТЕЛЬСКИЕ CALLBACK'И ====================

async def user_callback(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    
    if data == "user_my_tickets":
        await query.edit_message_text(
            "📋 **Мои тикеты:**",
            reply_markup=get_user_tickets_keyboard(user_id)
        )
    
    elif data == "user_back":
        await query.edit_message_text(
            "🏠 **Главное меню:**",
            reply_markup=get_user_main_keyboard()
        )
    
    elif data.startswith("user_view_"):
        ticket_id = data.split("_")[2]
        tickets = load_json(TICKETS_FILE)
        ticket = tickets.get(ticket_id)
        if not ticket:
            await query.edit_message_text("❌ Тикет не найден.")
            return
        
        messages = "\n".join([
            f"{'👤' if m['from']=='user' else '👨‍💻'} {m['text']}"
            for m in ticket.get("messages", [])
        ])
        
        status_text = {
            "open": "🟡 Ожидает ответа",
            "in_progress": "🟢 В работе",
            "closed": "🔴 Закрыт"
        }.get(ticket.get("status"), "❓ Неизвестно")
        
        await query.edit_message_text(
            f"📋 **Тикет #{ticket_id}**\n\n"
            f"Статус: {status_text}\n"
            f"Создан: {ticket.get('created_at', '')[:16].replace('T', ' ')}\n\n"
            f"--- История ---\n\n{messages}",
            reply_markup=get_user_ticket_actions(ticket_id)
        )
    
    elif data.startswith("user_add_msg_"):
        ticket_id = data.split("_")[3]
        context.user_data["user_add_ticket"] = ticket_id
        await query.edit_message_text(
            f"✏️ **Введи сообщение для тикета #{ticket_id}**\n\n"
            f"Напиши текст — я добавлю его в тикет."
        )
    
    elif data.startswith("user_close_"):
        ticket_id = data.split("_")[2]
        tickets = load_json(TICKETS_FILE)
        ticket = tickets.get(ticket_id)
        if ticket:
            ticket["status"] = "closed"
            save_json(TICKETS_FILE, tickets)
            await query.edit_message_text(f"✅ Тикет #{ticket_id} закрыт.")
    
    elif data == "user_faq":
        await query.edit_message_text(
            "❓ **Часто задаваемые вопросы:**\n\n"
            "1️⃣ **Как создать тикет?**\n"
            "   Просто напиши свой вопрос.\n\n"
            "2️⃣ **Как узнать статус?**\n"
            "   Нажми 'Мои тикеты'.\n\n"
            "3️⃣ **Как закрыть тикет?**\n"
            "   Нажми 'Закрыть' в тикете.\n\n"
            "4️⃣ **Что делать, если не отвечают?**\n"
            "   Напиши администратору напрямую.\n\n"
            "📌 По всем вопросам: @dimmma3731",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="user_back")]])
        )
    
    elif data == "user_contact_admin":
        await query.edit_message_text(
            "📞 **Связаться с администратором**\n\n"
            "Напиши нам напрямую:\n"
            "👤 @dimmma3731\n\n"
            "Или создай тикет через /start",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="user_back")]])
        )
    
    elif data == "user_rate":
        tickets = load_json(TICKETS_FILE)
        closed = [t for t in tickets.items() if t[1].get("user_id") == user_id and t[1].get("status") == "closed" and "rating" not in t[1]]
        if not closed:
            await query.edit_message_text("📭 Нет закрытых тикетов для оценки.")
            return
        keyboard = []
        for tid, _ in closed[:5]:
            keyboard.append([InlineKeyboardButton(f"Тикет #{tid}", callback_data=f"rate_ticket_{tid}")])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="user_back")])
        await query.edit_message_text(
            "⭐ **Оцени поддержку:**\n\nВыбери тикет:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data.startswith("rate_ticket_"):
        ticket_id = data.split("_")[2]
        await query.edit_message_text(
            f"⭐ **Оцени тикет #{ticket_id}**\n\n"
            f"Как ты оценишь работу поддержки?",
            reply_markup=get_rating_keyboard(ticket_id)
        )
    
    elif data.startswith("rate_"):
        parts = data.split("_")
        rating = parts[1]
        ticket_id = parts[2]
        tickets = load_json(TICKETS_FILE)
        ticket = tickets.get(ticket_id)
        if ticket:
            ticket["rating"] = int(rating)
            save_json(TICKETS_FILE, tickets)
            await query.edit_message_text(f"✅ Спасибо за оценку! Ты поставил {rating}⭐.")

# ==================== АДМИНСКИЕ CALLBACK'И ====================

async def admin_callback(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "admin_back":
        await query.edit_message_text(
            "👋 **Панель администратора**",
            reply_markup=get_admin_main_keyboard()
        )
    
    elif data == "admin_list_open":
        await query.edit_message_text(
            "🟡 **Открытые тикеты:**",
            reply_markup=get_admin_tickets_list("open")
        )
    
    elif data == "admin_list_progress":
        await query.edit_message_text(
            "🟢 **Тикеты в работе:**",
            reply_markup=get_admin_tickets_list("in_progress")
        )
    
    elif data == "admin_list_all":
        await query.edit_message_text(
            "📋 **Все тикеты (последние 20):**",
            reply_markup=get_admin_tickets_list()
        )
    
    elif data.startswith("admin_view_"):
        ticket_id = data.split("_")[2]
        tickets = load_json(TICKETS_FILE)
        ticket = tickets.get(ticket_id)
        if not ticket:
            await query.edit_message_text("❌ Тикет не найден.")
            return
        
        messages = "\n".join([
            f"{'👤' if m['from']=='user' else '👨‍💻'} {m['text']}"
            for m in ticket.get("messages", [])
        ])
        
        status_text = {
            "open": "🟡 Ожидает ответа",
            "in_progress": "🟢 В работе",
            "closed": "🔴 Закрыт"
        }.get(ticket.get("status"), "❓ Неизвестно")
        
        await query.edit_message_text(
            f"📋 **Тикет #{ticket_id}**\n\n"
            f"👤 {ticket.get('user_name', 'Unknown')}\n"
            f"🆔 `{ticket.get('user_id', '')}`\n"
            f"📅 {ticket.get('created_at', '')[:16].replace('T', ' ')}\n"
            f"Статус: {status_text}\n"
            f"Рейтинг: {ticket.get('rating', 'Не оценён')}⭐\n\n"
            f"--- История ---\n\n{messages}",
            reply_markup=get_admin_ticket_actions(ticket_id),
            parse_mode="HTML"
        )
    
    elif data.startswith("admin_take_"):
        ticket_id = data.split("_")[2]
        tickets = load_json(TICKETS_FILE)
        ticket = tickets.get(ticket_id)
        if ticket:
            ticket["status"] = "in_progress"
            save_json(TICKETS_FILE, tickets)
            await context.bot.send_message(
                chat_id=ticket["chat_id"],
                text=f"🟢 **Тикет #{ticket_id} взят в работу!**\n\nАдминистратор начал обработку."
            )
            await query.edit_message_text(f"✅ Тикет #{ticket_id} взят в работу.")
    
    elif data.startswith("admin_reply_"):
        ticket_id = data.split("_")[2]
        context.user_data["pending_reply_ticket"] = ticket_id
        await query.edit_message_text(
            f"✏️ **Введи ответ для тикета #{ticket_id}**\n\n"
            f"Напиши сообщение пользователю.\n"
            f"Тикет закроется автоматически.\n\n"
            f"Чтобы отменить — нажми /cancel"
        )
    
    elif data.startswith("admin_close_"):
        ticket_id = data.split("_")[2]
        tickets = load_json(TICKETS_FILE)
        ticket = tickets.get(ticket_id)
        if ticket:
            ticket["status"] = "closed"
            save_json(TICKETS_FILE, tickets)
            await context.bot.send_message(
                chat_id=ticket["chat_id"],
                text=f"🔴 **Тикет #{ticket_id} закрыт.**\n\nОцени работу поддержки:",
                reply_markup=get_rating_keyboard(ticket_id)
            )
            await query.edit_message_text(f"✅ Тикет #{ticket_id} закрыт.")
    
    elif data.startswith("admin_user_"):
        ticket_id = data.split("_")[2]
        tickets = load_json(TICKETS_FILE)
        ticket = tickets.get(ticket_id)
        if not ticket:
            await query.edit_message_text("❌ Тикет не найден.")
            return
        
        user_id = ticket.get("user_id")
        users = load_json(USERS_FILE)
        user_data = users.get(str(user_id), {})
        
        # Считаем тикеты пользователя
        all_tickets = load_json(TICKETS_FILE)
        user_tickets = [t for t in all_tickets.values() if t.get("user_id") == user_id]
        
        await query.edit_message_text(
            f"👤 **Информация о пользователе**\n\n"
            f"Имя: {user_data.get('first_name', 'Неизвестно')}\n"
            f"Юзернейм: @{user_data.get('username', 'нет')}\n"
            f"🆔 `{user_id}`\n"
            f"Зарегистрирован: {user_data.get('created', '')[:16].replace('T', ' ')}\n"
            f"Всего тикетов: {len(user_tickets)}\n"
            f"Открытых: {sum(1 for t in user_tickets if t.get('status') in ['open', 'in_progress'])}",
            parse_mode="HTML"
        )
    
    elif data.startswith("admin_block_"):
        ticket_id = data.split("_")[2]
        tickets = load_json(TICKETS_FILE)
        ticket = tickets.get(ticket_id)
        if ticket:
            blacklist = load_json(BLACKLIST_FILE)
            blacklist[str(ticket["user_id"])] = {
                "blocked_at": datetime.now().isoformat(),
                "reason": "Заблокирован администратором"
            }
            save_json(BLACKLIST_FILE, blacklist)
            await query.edit_message_text(f"🚫 Пользователь заблокирован.")
    
    elif data.startswith("admin_delete_"):
        ticket_id = data.split("_")[2]
        tickets = load_json(TICKETS_FILE)
        if ticket_id in tickets:
            del tickets[ticket_id]
            save_json(TICKETS_FILE, tickets)
            await query.edit_message_text(f"🗑 Тикет #{ticket_id} удалён.")
    
    elif data.startswith("admin_pin_"):
        ticket_id = data.split("_")[2]
        tickets = load_json(TICKETS_FILE)
        ticket = tickets.get(ticket_id)
        if ticket:
            ticket["pinned"] = True
            save_json(TICKETS_FILE, tickets)
            await query.edit_message_text(f"📌 Тикет #{ticket_id} закреплён.")
    
    elif data == "admin_stats":
        tickets = load_json(TICKETS_FILE)
        total = len(tickets)
        open_tickets = sum(1 for t in tickets.values() if t.get("status") == "open")
        in_progress = sum(1 for t in tickets.values() if t.get("status") == "in_progress")
        closed = sum(1 for t in tickets.values() if t.get("status") == "closed")
        
        # Средний рейтинг
        ratings = [t.get("rating", 0) for t in tickets.values() if t.get("rating")]
        avg_rating = sum(ratings) / len(ratings) if ratings else 0
        
        users = load_json(USERS_FILE)
        blacklist = load_json(BLACKLIST_FILE)
        
        await query.edit_message_text(
            f"📊 **Статистика:**\n\n"
            f"📌 Всего тикетов: {total}\n"
            f"🟡 Открытых: {open_tickets}\n"
            f"🟢 В работе: {in_progress}\n"
            f"🔴 Закрытых: {closed}\n"
            f"⭐ Средний рейтинг: {avg_rating:.1f}/5\n\n"
            f"👤 Всего пользователей: {len(users)}\n"
            f"🚫 Заблокировано: {len(blacklist)}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]])
        )
    
    elif data == "admin_broadcast":
        context.user_data["broadcast_mode"] = True
        await query.edit_message_text(
            "📢 **Рассылка**\n\n"
            "Введи текст для рассылки всем пользователям.\n"
            "Чтобы отменить — нажми /cancel"
        )
    
    elif data == "admin_blacklist":
        blacklist = load_json(BLACKLIST_FILE)
        if not blacklist:
            await query.edit_message_text("🚫 Черный список пуст.")
            return
        text = "🚫 **Черный список:**\n\n"
        for uid, data in list(blacklist.items())[:20]:
            text += f"🆔 `{uid}` — {data.get('reason', 'Без причины')}\n"
        await query.edit_message_text(text, parse_mode="HTML")
    
    elif data == "admin_export":
        tickets = load_json(TICKETS_FILE)
        users = load_json(USERS_FILE)
        export = {
            "exported_at": datetime.now().isoformat(),
            "tickets": tickets,
            "users": users
        }
        # Сохраняем экспорт
        with open("export.json", "w", encoding="utf-8") as f:
            json.dump(export, f, ensure_ascii=False, indent=2)
        await query.edit_message_text("📁 Данные экспортированы в export.json")

# ==================== ОБРАБОТЧИКИ СООБЩЕНИЙ ====================

async def handle_message(update, context):
    user = update.effective_user
    msg = update.message
    
    # Проверка блокировки
    blacklist = load_json(BLACKLIST_FILE)
    if str(user.id) in blacklist:
        await msg.reply_text("🚫 Вы заблокированы.")
        return
    
    # === АДМИН ===
    if user.id == ADMIN_ID:
        # Рассылка
        if context.user_data.get("broadcast_mode"):
            users = load_json(USERS_FILE)
            sent = 0
            for uid, data in users.items():
                try:
                    await context.bot.send_message(
                        chat_id=data["chat_id"],
                        text=f"📢 **Объявление:**\n\n{msg.text}"
                    )
                    sent += 1
                except:
                    pass
            context.user_data.pop("broadcast_mode", None)
            await msg.reply_text(f"✅ Рассылка отправлена {sent} пользователям.")
            return
        
        # Ответ на тикет
        ticket_id = context.user_data.get("pending_reply_ticket")
        if ticket_id:
            tickets = load_json(TICKETS_FILE)
            ticket = tickets.get(ticket_id)
            if ticket:
                ticket["messages"].append({
                    "from": "admin",
                    "text": msg.text,
                    "time": datetime.now().isoformat()
                })
                ticket["status"] = "closed"
                save_json(TICKETS_FILE, tickets)
                
                await context.bot.send_message(
                    chat_id=ticket["chat_id"],
                    text=f"👨‍💻 **Ответ администратора** (тикет #{ticket_id}):\n\n{msg.text}"
                )
                await context.bot.send_message(
                    chat_id=ticket["chat_id"],
                    text=f"🔴 **Тикет #{ticket_id} закрыт.**\n\nОцени работу поддержки:",
                    reply_markup=get_rating_keyboard(ticket_id)
                )
                
                await msg.reply_text(f"✅ Ответ отправлен, тикет #{ticket_id} закрыт.")
                context.user_data.pop("pending_reply_ticket", None)
                return
        
        await msg.reply_text("❌ Используй кнопки для управления.")
        return
    
    # === ПОЛЬЗОВАТЕЛЬ ===
    
    # Добавление сообщения в тикет
    ticket_id = context.user_data.get("user_add_ticket")
    if ticket_id:
        tickets = load_json(TICKETS_FILE)
        ticket = tickets.get(ticket_id)
        if ticket and ticket["user_id"] == user.id:
            ticket["messages"].append({
                "from": "user",
                "text": msg.text,
                "time": datetime.now().isoformat()
            })
            save_json(TICKETS_FILE, tickets)
            context.user_data.pop("user_add_ticket", None)
            
            # Уведомляем админа
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"💬 **Новое сообщение в тикете #{ticket_id}**\n\n"
                     f"👤 {user.first_name}\n"
                     f"📝 {msg.text}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📋 Открыть", callback_data=f"admin_view_{ticket_id}")]
                ])
            )
            
            await msg.reply_text(f"✅ Сообщение добавлено в тикет #{ticket_id}.")
            return
    
    # Проверка на дубли тикетов
    tickets = load_json(TICKETS_FILE)
    for tid, data in tickets.items():
        if data.get("user_id") == user.id and data.get("status") in ["open", "in_progress"]:
            await msg.reply_text(f"⚠️ У тебя уже есть открытый тикет #{tid}.\n\nИспользуй /start для управления.")
            return
    
    # Создание нового тикета
    ticket_id = get_next_id()
    tickets[str(ticket_id)] = {
        "user_id": user.id,
        "user_name": user.first_name,
        "username": user.username or "нет",
        "chat_id": msg.chat_id,
        "status": "open",
        "created_at": datetime.now().isoformat(),
        "messages": [{"from": "user", "text": msg.text, "time": datetime.now().isoformat()}],
        "last_reply": "Ожидает ответа"
    }
    save_json(TICKETS_FILE, tickets)
    
    # Обновление пользователя
    users = load_json(USERS_FILE)
    if str(user.id) in users:
        users[str(user.id)]["total_tickets"] = users[str(user.id)].get("total_tickets", 0) + 1
        save_json(USERS_FILE, users)
    
    await msg.reply_text(
        f"✅ **Тикет #{ticket_id} создан!**\n\n"
        f"Администратор ответит в ближайшее время.\n"
        f"Используй /start для управления."
    )
    
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"🆕 **Новый тикет #{ticket_id}**\n\n"
             f"👤 {user.first_name} (@{user.username or 'нет'})\n"
             f"📝 {msg.text}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Открыть", callback_data=f"admin_view_{ticket_id}")]
        ])
    )

async def cancel(update, context):
    if update.effective_user.id == ADMIN_ID:
        context.user_data.pop("pending_reply_ticket", None)
        context.user_data.pop("broadcast_mode", None)
        await update.message.reply_text("❌ Отменено.")

# ==================== ЗАПУСК ====================

def main():
    app = Application.builder().token(TOKEN).build()
    
    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    
    # Callback'и
    app.add_handler(CallbackQueryHandler(user_callback, pattern="^user_"))
    app.add_handler(CallbackQueryHandler(user_callback, pattern="^rate_"))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^noop$"))
    
    # Сообщения
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🤖 Бот с тикетами запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()