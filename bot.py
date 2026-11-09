import os
import json
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

# Файл для хранения ответственных
RESPONSIBLE_FILE = 'responsible.json'

def load_responsible():
    """Загружает список ответственных из файла"""
    if os.path.exists(RESPONSIBLE_FILE):
        with open(RESPONSIBLE_FILE, 'r') as f:
            return json.load(f)
    return []

def save_responsible(responsible_list):
    """Сохраняет список ответственных в файл"""
    with open(RESPONSIBLE_FILE, 'w') as f:
        json.dump(responsible_list, f)

def is_responsible(user_id):
    """Проверяет, является ли пользователь ответственным"""
    responsible = load_responsible()
    return user_id in responsible

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
    
    # Если админ - сразу показываем админ-меню
    if user_id == ADMIN_ID:
        user_states[user_id] = {'role': 'admin', 'name': 'Администратор'}
        show_admin_menu(message)
        return
    
    # Если ответственный - показываем меню ответственного
    if is_responsible(user_id):
        user_states[user_id] = {'role': 'responsible', 'name': 'Ответственный'}
        show_responsible_menu(message)
        return
    
    # Обычный ученик - выбирает ФИО
    user_states[user_id] = {'role': 'student', 'name': None}
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    try:
        sheet = sh.worksheet("Список")
        names = sheet.col_values(1)[1:]  # Пропускаем заголовок
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
    show_student_menu(call.message, user_id)

def show_student_menu(message, user_id):
    """Меню для обычного ученика"""
    state = user_states.get(user_id, {})
    name = state.get('name', 'Ученик')
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add('📅 Записаться', '📋 Мои записи')
    markup.add('❌ Отменить запись', 'ℹ️ Помощь')
        
    bot.send_message(
        message.chat.id, 
        f"Главное меню (ты записан как: {name})", 
        reply_markup=markup
    )

def show_responsible_menu(message):
    """Меню для ответственного"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add('📅 Записаться', '📋 Мои записи')
    markup.add('❌ Отменить запись', 'ℹ️ Помощь')
    markup.add('👥 Список всех', '📊 Статистика дня')
        
    bot.send_message(
        message.chat.id, 
        "Меню ответственного за питание", 
        reply_markup=markup
    )

def show_admin_menu(message):
    """Меню для администратора (классного руководителя)"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add('📅 Записаться', '📋 Мои записи')
    markup.add('❌ Отменить запись', 'ℹ️ Помощь')
    markup.add('👥 Список всех', '📊 Статистика дня')
    markup.add('⚙️ АДМИН-ПАНЕЛЬ')
        
    bot.send_message(
        message.chat.id, 
        "Админ-панель (Классный руководитель)", 
        reply_markup=markup
    )

# ================= ФУНКЦИИ УЧЕНИКА =================

@bot.message_handler(func=lambda message: message.text == '📅 Записаться')
def handle_signup(message):
    user_id = message.from_user.id
    state = user_states.get(user_id)
    
    # Админ и ответственные могут записывать других учеников
    if state and state.get('role') in ['admin', 'responsible']:
        bot.send_message(message.chat.id, "Выбери ученика для записи:")
        markup = types.InlineKeyboardMarkup(row_width=1)
        try:
            sheet = sh.worksheet("Список")
            names = sheet.col_values(1)[1:]
            for name in names:
                if name.strip():
                    markup.add(types.InlineKeyboardButton(
                        name.strip(), 
                        callback_data=f"admin_select_{name.strip()}"
                    ))
            user_states[user_id]['action'] = 'select_student_for_signup'
            bot.send_message(message.chat.id, "Выбери ученика:", reply_markup=markup)
        except Exception as e:
            bot.send_message(message.chat.id, f"Ошибка: {e}")
        return
    
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

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_select_'))
def handle_admin_student_selection(call):
    user_id = call.from_user.id
    student_name = call.data.replace('admin_select_', '')
    user_states[user_id]['selected_student'] = student_name
    
    bot.answer_callback_query(call.id, f"Выбран: {student_name}")
    
    # Теперь показываем даты для записи
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
                    callback_data=f"admin_sign_up_{date_str}"
                ))
        
        bot.send_message(
            call.message.chat.id, 
            f"Выберите дату для записи {student_name}:", 
            reply_markup=markup
        )
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Ошибка: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_sign_up_'))
def process_admin_signup(call):
    user_id = call.from_user.id
    date_str = call.data.replace('admin_sign_up_', '')
    state = user_states.get(user_id)
    student_name = state.get('selected_student')
    
    row = get_student_row(student_name)
    col = get_date_column_index(date_str)
    
    if row and col:
        try:
            sheet = sh.worksheet(get_current_sheet_name())
            sheet.update_cell(row, col, '✓')
            bot.answer_callback_query(call.id, "Успешно записан!")
            bot.send_message(call.message.chat.id, f"✅ {student_name} записан на обед на {date_str}")
        except Exception as e:
            bot.send_message(call.message.chat.id, f"Ошибка записи: {e}")
    else:
        bot.send_message(call.message.chat.id, "Ошибка: не удалось найти имя или дату.")

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
    
    # Админ и ответственные могут смотреть записи любого ученика
    if state and state.get('role') in ['admin', 'responsible']:
        bot.send_message(message.chat.id, "Выбери ученика для просмотра записей:")
        markup = types.InlineKeyboardMarkup(row_width=1)
        try:
            sheet = sh.worksheet("Список")
            names = sheet.col_values(1)[1:]
            for name in names:
                if name.strip():
                    markup.add(types.InlineKeyboardButton(
                        name.strip(), 
                        callback_data=f"view_records_{name.strip()}"
                    ))
            bot.send_message(message.chat.id, "Выбери ученика:", reply_markup=markup)
        except Exception as e:
            bot.send_message(message.chat.id, f"Ошибка: {e}")
        return
    
    if not state or not state.get('name'):
        bot.send_message(message.chat.id, "Сначала нажми /start")
        return
        
    name = state.get('name')
    show_records_for_student(message, name)

@bot.callback_query_handler(func=lambda call: call.data.startswith('view_records_'))
def handle_view_records(call):
    user_id = call.from_user.id
    student_name = call.data.replace('view_records_', '')
    bot.answer_callback_query(call.id, f"Записи: {student_name}")
    show_records_for_student(call.message, student_name)

def show_records_for_student(message, name):
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
                    f"📋 Записи {name} на {get_current_sheet_name()}:\n" + "\n".join(records)
                )
            else:
                bot.send_message(message.chat.id, f"У {name} пока нет записей на этот месяц.")
        except Exception as e:
            bot.send_message(message.chat.id, f"Ошибка: {e}")

@bot.message_handler(func=lambda message: message.text == '❌ Отменить запись')
def handle_cancel(message):
    user_id = message.from_user.id
    state = user_states.get(user_id)
    
    # Админ и ответственные могут отменять записи других
    if state and state.get('role') in ['admin', 'responsible']:
        bot.send_message(message.chat.id, "Выбери ученика:")
        markup = types.InlineKeyboardMarkup(row_width=1)
        try:
            sheet = sh.worksheet("Список")
            names = sheet.col_values(1)[1:]
            for name in names:
                if name.strip():
                    markup.add(types.InlineKeyboardButton(
                        name.strip(), 
                        callback_data=f"cancel_select_{name.strip()}"
                    ))
            user_states[user_id]['action'] = 'select_student_for_cancel'
            bot.send_message(message.chat.id, "Выбери ученика:", reply_markup=markup)
        except Exception as e:
            bot.send_message(message.chat.id, f"Ошибка: {e}")
        return
    
    bot.send_message(
        message.chat.id, 
        "Напиши дату, которую хочешь отменить (в формате ДД.ММ, например 15.11):"
    )
    user_states[user_id]['action'] = 'waiting_for_cancel_date'

@bot.callback_query_handler(func=lambda call: call.data.startswith('cancel_select_'))
def handle_cancel_student_selection(call):
    user_id = call.from_user.id
    student_name = call.data.replace('cancel_select_', '')
    user_states[user_id]['selected_student'] = student_name
    
    bot.answer_callback_query(call.id, f"Выбран: {student_name}")
    bot.send_message(
        call.message.chat.id, 
        f"Напиши дату для отмены записи {student_name} (в формате ДД.ММ):"
    )
    user_states[user_id]['action'] = 'waiting_for_cancel_date_admin'

@bot.message_handler(func=lambda message: user_states.get(message.from_user.id, {}).get('action') in ['waiting_for_cancel_date', 'waiting_for_cancel_date_admin'])
def process_cancel(message):
    user_id = message.from_user.id
    date_str = message.text.strip()
    state = user_states.get(user_id)
    
    # Определяем, для кого отменяем
    if state.get('action') == 'waiting_for_cancel_date_admin':
        name = state.get('selected_student')
    else:
        name = state.get('name')
    
    row = get_student_row(name)
    col = get_date_column_index(date_str)
    
    if row and col:
        try:
            sheet = sh.worksheet(get_current_sheet_name())
            sheet.update_cell(row, col, '')
            bot.send_message(message.chat.id, f"❌ Запись {name} на {date_str} отменена.")
        except Exception as e:
            bot.send_message(message.chat.id, f"Ошибка отмены: {e}")
    else:
        bot.send_message(message.chat.id, "Дата не найдена или запись не существовала.")
    
    if user_id in user_states:
        user_states[user_id]['action'] = None

# ================= ФУНКЦИИ ОТВЕТСТВЕННОГО И АДМИНА =================

@bot.message_handler(func=lambda message: message.text == '👥 Список всех')
def show_all_signed(message):
    user_id = message.from_user.id
    state = user_states.get(user_id)
    
    if not state or state.get('role') not in ['admin', 'responsible']:
        bot.send_message(message.chat.id, "Доступ запрещён.")
        return
    
    bot.send_message(message.chat.id, "Выбери дату для просмотра списка:")
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
                    callback_data=f"view_all_{date_str}"
                ))
        
        bot.send_message(message.chat.id, "Выбери дату:", reply_markup=markup)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('view_all_'))
def process_view_all(call):
    user_id = call.from_user.id
    date_str = call.data.replace('view_all_', '')
    
    col = get_date_column_index(date_str)
    
    if col:
        try:
            sheet = sh.worksheet(get_current_sheet_name())
            names = sheet.col_values(1)[1:]  # Все ученики
            signed = []
            not_signed = []
            
            for i, name in enumerate(names, start=2):  # Начинаем со 2-й строки
                cell_value = sheet.cell(i, col).value
                if cell_value == '✓':
                    signed.append(name)
                else:
                    not_signed.append(name)
            
            response = f"📊 Записанные на {date_str}:\n"
            if signed:
                response += "\n".join([f"✅ {name}" for name in signed])
            else:
                response += "Никто не записан\n"
            
            response += f"\n❌ Не записались ({len(not_signed)}):\n"
            if not_signed:
                response += "\n".join(not_signed[:10])  # Показываем первые 10
                if len(not_signed) > 10:
                    response += f"\n... и ещё {len(not_signed) - 10}"
            
            bot.send_message(call.message.chat.id, response)
        except Exception as e:
            bot.send_message(call.message.chat.id, f"Ошибка: {e}")
    else:
        bot.send_message(call.message.chat.id, "Дата не найдена.")

@bot.message_handler(func=lambda message: message.text == '📊 Статистика дня')
def show_daily_stats(message):
    user_id = message.from_user.id
    state = user_states.get(user_id)
    
    if not state or state.get('role') not in ['admin', 'responsible']:
        bot.send_message(message.chat.id, "Доступ запрещён.")
        return
    
    bot.send_message(message.chat.id, "Выбери дату для статистики:")
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
                    callback_data=f"stats_{date_str}"
                ))
        
        bot.send_message(message.chat.id, "Выбери дату:", reply_markup=markup)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('stats_'))
def process_stats(call):
    user_id = call.from_user.id
    date_str = call.data.replace('stats_', '')
    
    col = get_date_column_index(date_str)
    
    if col:
        try:
            sheet = sh.worksheet(get_current_sheet_name())
            names = sheet.col_values(1)[1:]
            total_students = len(names)
            signed_count = 0
            
            for i in range(2, len(names) + 2):
                cell_value = sheet.cell(i, col).value
                if cell_value == '✓':
                    signed_count += 1
            
            not_signed_count = total_students - signed_count
            price_per_meal = 1.5  # Цена обеда (можно брать из таблицы)
            total_sum = signed_count * price_per_meal
            
            response = f"📊 Статистика на {date_str}:\n\n"
            response += f"👥 Всего учеников: {total_students}\n"
            response += f"✅ Записались: {signed_count}\n"
            response += f"❌ Не записались: {not_signed_count}\n"
            response += f"💰 Сумма: {total_sum} BYN\n"
            response += f"📈 Процент записавшихся: {(signed_count/total_students*100):.1f}%"
            
            bot.send_message(call.message.chat.id, response)
        except Exception as e:
            bot.send_message(call.message.chat.id, f"Ошибка: {e}")
    else:
        bot.send_message(call.message.chat.id, "Дата не найдена.")

# ================= АДМИН-ПАНЕЛЬ =================

@bot.message_handler(func=lambda message: message.text == '⚙️ АДМИН-ПАНЕЛЬ')
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "Доступ запрещён.")
        return
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add('👤 Добавить ответственного')
    markup.add('🗑 Убрать ответственного')
    markup.add('📋 Список ответственных')
    markup.add('🔙 Назад в главное меню')
    
    bot.send_message(
        message.chat.id, 
        "Админ-панель:\n\nВыбери действие:", 
        reply_markup=markup
    )

@bot.message_handler(func=lambda message: message.text == '👤 Добавить ответственного')
def add_responsible(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    bot.send_message(
        message.chat.id, 
        "Перешли мне сообщение от ученика, которого хочешь назначить ответственным.\n\n"
        "Или напиши его Telegram ID числом."
    )
    user_states[message.from_user.id]['action'] = 'adding_responsible'

@bot.message_handler(func=lambda message: user_states.get(message.from_user.id, {}).get('action') == 'adding_responsible')
def process_add_responsible(message):
    user_id = message.from_user.id
    
    # Пытаемся получить ID из пересланного сообщения
    if message.forward_from:
        new_responsible_id = message.forward_from.id
        new_responsible_name = message.forward_from.first_name
    else:
        # Пытаемся парсить ID из текста
        try:
            new_responsible_id = int(message.text.strip())
            new_responsible_name = str(new_responsible_id)
        except:
            bot.send_message(message.chat.id, "Не удалось определить ID. Перешли сообщение от ученика или напиши его ID числом.")
            return
    
    responsible = load_responsible()
    
    if new_responsible_id in responsible:
        bot.send_message(message.chat.id, "Этот пользователь уже является ответственным.")
    else:
        responsible.append(new_responsible_id)
        save_responsible(responsible)
        bot.send_message(message.chat.id, f"✅ {new_responsible_name} назначен ответственным за питание!")
    
    user_states[user_id]['action'] = None

@bot.message_handler(func=lambda message: message.text == '🗑 Убрать ответственного')
def remove_responsible(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    responsible = load_responsible()
    
    if not responsible:
        bot.send_message(message.chat.id, "Список ответственных пуст.")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for resp_id in responsible:
        markup.add(types.InlineKeyboardButton(
            f"ID: {resp_id}", 
            callback_data=f"remove_resp_{resp_id}"
        ))
    
    bot.send_message(message.chat.id, "Выбери ответственного для удаления:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('remove_resp_'))
def process_remove_responsible(call):
    user_id = call.from_user.id
    
    if user_id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Доступ запрещён")
        return
    
    resp_id = int(call.data.replace('remove_resp_', ''))
    responsible = load_responsible()
    
    if resp_id in responsible:
        responsible.remove(resp_id)
        save_responsible(responsible)
        bot.answer_callback_query(call.id, "Удалён")
        bot.send_message(call.message.chat.id, f"✅ Ответственный с ID {resp_id} удалён.")
    else:
        bot.send_message(call.message.chat.id, "Ответственный не найден.")

@bot.message_handler(func=lambda message: message.text == '📋 Список ответственных')
def list_responsible(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    responsible = load_responsible()
    
    if not responsible:
        bot.send_message(message.chat.id, "Список ответственных пуст.")
        return
    
    response = "📋 Ответственные за питание:\n\n"
    for i, resp_id in enumerate(responsible, 1):
        response += f"{i}. ID: {resp_id}\n"
    
    bot.send_message(message.chat.id, response)

@bot.message_handler(func=lambda message: message.text == '🔙 Назад в главное меню')
def back_to_main(message):
    user_id = message.from_user.id
    state = user_states.get(user_id, {})
    
    if state.get('role') == 'admin':
        show_admin_menu(message)
    elif state.get('role') == 'responsible':
        show_responsible_menu(message)
    else:
        show_student_menu(message, user_id)

@bot.message_handler(func=lambda message: message.text == 'ℹ️ Помощь')
def help_command(message):
    bot.send_message(
        message.chat.id, 
        "Этот бот помогает записываться на школьные обеды.\n\n"
        "📅 Записаться - выбрать дату для обеда\n"
        "📋 Мои записи - посмотреть свои записи\n"
        "❌ Отменить запись - отменить запись на дату\n\n"
        "Если возникли проблемы, обратись к классному руководителю."
    )

# Запуск бота
if __name__ == '__main__':
    print("Бот запущен...")
    bot.polling(none_stop=True)
