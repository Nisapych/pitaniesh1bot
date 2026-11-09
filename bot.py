import os
import datetime
import telebot
from telebot import types
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')
ADMIN_ID = int(os.getenv('ADMIN_ID', 0))

# Инициализация бота
bot = telebot.TeleBot(BOT_TOKEN)

# Настройка Google Sheets
SCOPE = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]
creds = Credentials.from_service_account_file('credentials.json', scopes=SCOPE)
gc = gspread.authorize(creds)
sh = gc.open_by_key(SPREADSHEET_ID)

# Хранилище состояний пользователей
user_states = {}

# Каникулы Беларуси 2026-2027
HOLIDAYS = [
    (datetime.date(2026, 11, 1), datetime.date(2026, 11, 8)),
    (datetime.date(2026, 12, 25), datetime.date(2027, 1, 10)),
    (datetime.date(2027, 3, 21), datetime.date(2027, 3, 28)),
    (datetime.date(2027, 6, 1), datetime.date(2027, 8, 31))
]

def is_school_day(date_obj):
    """Проверяет, является ли день учебным"""
    if date_obj.weekday() >= 5:  # Суббота, Воскресенье
        return False
    for start, end in HOLIDAYS:
        if start <= date_obj <= end:
            return False
    return True

def get_current_sheet_name():
    """Возвращает название листа текущего месяца"""
    months_ru = [
        'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
        'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
    ]
    now = datetime.datetime.now()
    return f"{months_ru[now.month - 1]} {now.year}"

def get_student_row(student_name):
    """Находит номер строки ученика на листе 'Список'"""
    try:
        sheet = sh.worksheet("Список")
        names = sheet.col_values(1)
        for i, name in enumerate(names, start=1):
            if name.strip().lower() == student_name.strip().lower():
                return i
        return None
    except gspread.WorksheetNotFound:
        return None

def get_date_column_index(date_str):
    """Находит номер столбца по дате"""
    sheet_name = get_current_sheet_name()
    try:
        sheet = sh.worksheet(sheet_name)
        headers = sheet.row_values(1)
        for i, header in enumerate(headers, start=1):
            if str(header).strip() == str(date_str).strip():
                return i
        return None
    except gspread.WorksheetNotFound:
        return None

# ================= ОБРАБОТЧИКИ КОМАНД =================

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    user_states[user_id] = {'name': None, 'role': 'student'}
    
    if user_id == ADMIN_ID:
        user_states[user_id]['role'] = 'admin'
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    try:
        sheet = sh.worksheet("Список")
        names = sheet.col_values(1)[1:]
        for name in names:
            if name.strip():
                markup.add(types.InlineKeyboardButton(
                    name.strip(), 
                    callback_data=f"select_name_{name.strip()}"
                ))
        bot.send_message(
            message.chat.id, 
            "Привет! Выбери своё ФИО из списка:", 
            reply_markup=markup
        )
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка чтения списка: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('select_name_'))
def handle_name_selection(call):
    user_id = call.from_user.id
    name = call.data.replace('select_name_', '')
    user_states[user_id]['name'] = name
    
    bot.answer_callback_query(call.id, f"Выбрано: {name}")
    show_main_menu(call.message, user_id)

def show_main_menu(message, user_id):
    state = user_states.get(user_id, {})
    name = state.get('name', 'Ученик')
    role = state.get('role', 'student')
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add('📅 Записаться', '📋 Мои записи')
    markup.add('❌ Отменить запись', 'ℹ️ Помощь')
    
    if role in ['admin', 'responsible']:
        markup.add('👥 Список всех', '📊 Статистика дня')
    if role == 'admin':
        markup.add('⚙️ АДМИН-ПАНЕЛЬ')
        
    bot.send_message(
        message.chat.id, 
        f"Главное меню (ты записан как: {name})", 
        reply_markup=markup
    )

@bot.message_handler(func=lambda message: message.text == '📅 Записаться')
def handle_signup(message):
    user_id = message.from_user.id
    state = user_states.get(user_id)
    if not state or not state.get('name'):
        bot.send_message(message.chat.id, "Сначала нажми /start и выбери своё имя.")
        return

    markup = types.InlineKeyboardMarkup(row_width=3)
    sheet_name = get_current_sheet_name()
    try:
        sheet = sh.worksheet(sheet_name)
        headers = sheet.row_values(1)[2:]
        
        today = datetime.date.today()
        for date_str in headers:
            if not date_str:
                continue
            try:
                d, m = map(int, str(date_str).split('.'))
                date_obj = datetime.date(today.year, m, d)
            except:
                continue
                
            if is_school_day(date_obj) and date_obj >= today:
                markup.add(types.InlineKeyboardButton(
                    str(date_str), 
                    callback_data=f"sign_up_{date_str}"
                ))
        
        if len(markup.keyboard) == 0:
            bot.send_message(message.chat.id, "На текущий месяц нет доступных дат.")
        else:
            bot.send_message(
                message.chat.id, 
                f"Выберите дату для записи на обед ({sheet_name}):", 
                reply_markup=markup
            )
    except Exception as e:
        bot.send_message(
            message.chat.id, 
            f"Ошибка: лист '{sheet_name}' не найден. Создайте его в таблице."
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith('sign_up_'))
def process_signup(call):
    user_id = call.from_user.id
    date_str = call.data.replace('sign_up_', '')
    state = user_states.get(user_id)
    name = state.get('name')
    
    row = get_student_row(name)
    col = get_date_column_index(date_str)
    
    if row and col:
        try:
            sheet = sh.worksheet(get_current_sheet_name())
            sheet.update_cell(row, col, '✓')
            bot.answer_callback_query(call.id, "Успешно записан!")
            bot.send_message(call.message.chat.id, f"✅ Ты записан на обед на {date_str}")
        except Exception as e:
            bot.send_message(call.message.chat.id, f"Ошибка записи: {e}")
    else:
        bot.send_message(call.message.chat.id, "Ошибка: не удалось найти имя или дату.")

@bot.message_handler(func=lambda message: message.text == '📋 Мои записи')
def show_my_records(message):
    user_id = message.from_user.id
    state = user_states.get(user_id)
    if not state or not state.get('name'):
        bot.send_message(message.chat.id, "Сначала нажми /start")
        return
        
    name = state.get('name')
    row = get_student_row(name)
    
    if row:
        try:
            sheet = sh.worksheet(get_current_sheet_name())
            row_data = sheet.row_values(row)
            headers = sheet.row_values(1)
            
            records = []
            for i, val in enumerate(row_data):
                if val == '✓' and i >= 2:
                    records.append(headers[i])
            
            if records:
                bot.send_message(
                    message.chat.id, 
                    f"📋 Твои записи на {get_current_sheet_name()}:\n" + "\n".join(records)
                )
            else:
                bot.send_message(message.chat.id, "У тебя пока нет записей на этот месяц.")
        except Exception as e:
            bot.send_message(message.chat.id, f"Ошибка: {e}")

@bot.message_handler(func=lambda message: message.text == '❌ Отменить запись')
def handle_cancel(message):
    bot.send_message(
        message.chat.id, 
        "Напиши дату, которую хочешь отменить (в формате ДД.ММ, например 15.11):"
    )
    user_states[message.from_user.id]['action'] = 'waiting_for_cancel_date'

@bot.message_handler(func=lambda message: user_states.get(message.from_user.id, {}).get('action') == 'waiting_for_cancel_date')
def process_cancel(message):
    user_id = message.from_user.id
    date_str = message.text.strip()
    state = user_states.get(user_id)
    name = state.get('name')
    
    row = get_student_row(name)
    col = get_date_column_index(date_str)
    
    if row and col:
        try:
            sheet = sh.worksheet(get_current_sheet_name())
            sheet.update_cell(row, col, '')
            bot.send_message(message.chat.id, f"❌ Запись на {date_str} отменена.")
        except Exception as e:
            bot.send_message(message.chat.id, f"Ошибка отмены: {e}")
    else:
        bot.send_message(message.chat.id, "Дата не найдена или ты не был на неё записан.")
    
    if user_id in user_states:
        user_states[user_id]['action'] = None

@bot.message_handler(func=lambda message: message.text == '⚙️ АДМИН-ПАНЕЛЬ')
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "Доступ запрещён.")
        return
    bot.send_message(
        message.chat.id, 
        "Админ-панель в разработке. Используйте прямое редактирование таблицы."
    )

@bot.message_handler(func=lambda message: message.text == 'ℹ️ Помощь')
def help_command(message):
    bot.send_message(
        message.chat.id, 
        "Этот бот помогает записываться на школьные обеды.\n"
        "Используй кнопки внизу экрана для управления записями.\n"
        "Если возникли проблемы, обратись к классному руководителю."
    )

# Запуск бота
if __name__ == '__main__':
    print("Бот запущен...")
    bot.polling(none_stop=True)