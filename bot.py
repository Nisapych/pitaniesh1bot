import os
import json
import datetime
import telebot
from telebot import types
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')
ADMIN_ID = int(os.getenv('ADMIN_ID', 0))

bot = telebot.TeleBot(BOT_TOKEN)

SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_file('credentials.json', scopes=SCOPE)
gc = gspread.authorize(creds)
sh = gc.open_by_key(SPREADSHEET_ID)

user_states = {}
RESPONSIBLE_FILE = 'responsible.json'

def load_responsible():
    if os.path.exists(RESPONSIBLE_FILE):
        with open(RESPONSIBLE_FILE, 'r') as f:
            return json.load(f)
    return []

def save_responsible(responsible_list):
    with open(RESPONSIBLE_FILE, 'w') as f:
        json.dump(responsible_list, f)

def is_responsible(user_id):
    return user_id in load_responsible()

HOLIDAYS = [
    (datetime.date(2026, 11, 1), datetime.date(2026, 11, 8)),
    (datetime.date(2026, 12, 25), datetime.date(2027, 1, 10)),
    (datetime.date(2027, 3, 21), datetime.date(2027, 3, 28)),
    (datetime.date(2027, 6, 1), datetime.date(2027, 8, 31))
]

def is_school_day(date_obj):
    if date_obj.weekday() >= 5:
        return False
    for start, end in HOLIDAYS:
        if start <= date_obj <= end:
            return False
    return True

def get_current_sheet_name():
    months_ru = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
    now = datetime.datetime.now()
    return f"{months_ru[now.month - 1]} {now.year}"

def get_student_row(student_name):
    try:
        sheet = sh.worksheet("Список")
        names = sheet.col_values(1)
        for i, name in enumerate(names, start=1):
            if name.strip().lower() == student_name.strip().lower():
                return i
        return None
    except:
        return None

def get_date_column_index(date_str):
    try:
        sheet = sh.worksheet(get_current_sheet_name())
        headers = sheet.row_values(1)
        for i, header in enumerate(headers, start=1):
            if str(header).strip() == str(date_str).strip():
                return i
        return None
    except:
        return None

# ================= СТАРТ И МЕНЮ =================

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    
    if user_id == ADMIN_ID:
        user_states[user_id] = {'role': 'admin'}
        show_admin_menu(message)
        return
    
    if is_responsible(user_id):
        user_states[user_id] = {'role': 'responsible'}
        show_responsible_menu(message)
        return
    
    user_states[user_id] = {'role': 'student', 'name': None}
    markup = types.InlineKeyboardMarkup(row_width=1)
    try:
        sheet = sh.worksheet("Список")
        for name in sheet.col_values(1)[1:]:
            if name.strip():
                markup.add(types.InlineKeyboardButton(name.strip(), callback_data=f"select_name_{name.strip()}"))
        bot.send_message(message.chat.id, "Привет! Выбери своё ФИО из списка:", reply_markup=markup)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('select_name_'))
def handle_name_selection(call):
    user_id = call.from_user.id
    name = call.data.replace('select_name_', '')
    user_states[user_id]['name'] = name
    bot.answer_callback_query(call.id, f"Выбрано: {name}")
    show_student_menu(call.message, user_id)

def show_student_menu(message, user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add('📅 Записаться', '📋 Мои записи')
    markup.add('❌ Отменить запись', 'ℹ️ Помощь')
    bot.send_message(message.chat.id, f"Главное меню (ты: {user_states[user_id]['name']})", reply_markup=markup)

def show_responsible_menu(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add('➕ Записать учащегося', '➖ Снять с питания')
    markup.add('📋 Список записавшихся', '📊 Статистика дня')
    bot.send_message(message.chat.id, "Меню ответственного за питание", reply_markup=markup)

def show_admin_menu(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add('➕ Записать учащегося')
    markup.add('➖ Снять с питания')
    markup.add('📋 Список записавшихся')
    markup.add('📊 Статистика дня')
    markup.add('⚙️ Управление ответственными')
    bot.send_message(message.chat.id, "👨‍🏫 Панель классного руководителя", reply_markup=markup)

# ================= ФУНКЦИИ АДМИНА / ОТВЕТСТВЕННОГО =================

def get_date_markup():
    markup = types.InlineKeyboardMarkup(row_width=3)
    try:
        sheet = sh.worksheet(get_current_sheet_name())
        headers = sheet.row_values(1)[2:]
        today = datetime.date.today()
        for date_str in headers:
            if not date_str: continue
            try:
                d, m = map(int, str(date_str).split('.'))
                date_obj = datetime.date(today.year, m, d)
            except: continue
            if is_school_day(date_obj) and date_obj >= today:
                markup.add(types.InlineKeyboardButton(str(date_str), callback_data=f"admin_date_{date_str}"))
    except: pass
    return markup

@bot.message_handler(func=lambda message: message.text in ['➕ Записать учащегося', '➖ Снять с питания'])
def admin_action_start(message):
    user_id = message.from_user.id
    state = user_states.get(user_id, {})
    if state.get('role') not in ['admin', 'responsible']:
        return
    
    action = 'signup' if message.text == '➕ Записать учащегося' else 'cancel'
    user_states[user_id]['admin_action'] = action
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    try:
        sheet = sh.worksheet("Список")
        for name in sheet.col_values(1)[1:]:
            if name.strip():
                markup.add(types.InlineKeyboardButton(name.strip(), callback_data=f"admin_student_{name.strip()}"))
        bot.send_message(message.chat.id, "Выбери ученика:", reply_markup=markup)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_student_'))
def admin_select_student(call):
    user_id = call.from_user.id
    student_name = call.data.replace('admin_student_', '')
    user_states[user_id]['selected_student'] = student_name
    bot.answer_callback_query(call.id, f"Выбран: {student_name}")
    
    action = user_states[user_id].get('admin_action')
    text = "Выбери дату для ЗАПИСИ:" if action == 'signup' else "Выбери дату для ОТМЕНЫ:"
    bot.send_message(call.message.chat.id, text, reply_markup=get_date_markup())

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_date_'))
def admin_process_date(call):
    user_id = call.from_user.id
    date_str = call.data.replace('admin_date_', '')
    state = user_states.get(user_id, {})
    student_name = state.get('selected_student')
    action = state.get('admin_action')
    
    row = get_student_row(student_name)
    col = get_date_column_index(date_str)
    
    if row and col:
        try:
            sheet = sh.worksheet(get_current_sheet_name())
            if action == 'signup':
                sheet.update_cell(row, col, '✓')
                bot.answer_callback_query(call.id, "Записан!")
                bot.send_message(call.message.chat.id, f"✅ {student_name} записан на {date_str}")
            else:
                sheet.update_cell(row, col, '')
                bot.answer_callback_query(call.id, "Отменён!")
                bot.send_message(call.message.chat.id, f"❌ Запись {student_name} на {date_str} отменена")
        except Exception as e:
            bot.send_message(call.message.chat.id, f"Ошибка: {e}")
    else:
        bot.send_message(call.message.chat.id, "Ошибка: не удалось найти имя или дату.")

@bot.message_handler(func=lambda message: message.text == '📋 Список записавшихся')
def show_all_signed(message):
    if user_states.get(message.from_user.id, {}).get('role') not in ['admin', 'responsible']:
        return
    bot.send_message(message.chat.id, "Выбери дату для просмотра списка:", reply_markup=get_date_markup())
    user_states[message.from_user.id]['admin_action'] = 'view_list'

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_date_') and user_states.get(call.from_user.id, {}).get('admin_action') == 'view_list')
def process_view_list(call):
    date_str = call.data.replace('admin_date_', '')
    col = get_date_column_index(date_str)
    
    if col:
        try:
            sheet = sh.worksheet(get_current_sheet_name())
            names = sheet.col_values(1)[1:]
            signed = [name for i, name in enumerate(names, start=2) if sheet.cell(i, col).value == '✓']
            
            if signed:
                response = f"📋 Записались на {date_str} ({len(signed)} чел.):\n" + "\n".join([f"✅ {name}" for name in signed])
            else:
                response = f"📋 На {date_str} никто не записан."
            bot.send_message(call.message.chat.id, response)
        except Exception as e:
            bot.send_message(call.message.chat.id, f"Ошибка: {e}")

@bot.message_handler(func=lambda message: message.text == '📊 Статистика дня')
def show_daily_stats(message):
    if user_states.get(message.from_user.id, {}).get('role') not in ['admin', 'responsible']:
        return
    bot.send_message(message.chat.id, "Выбери дату для статистики:", reply_markup=get_date_markup())
    user_states[message.from_user.id]['admin_action'] = 'view_stats'

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_date_') and user_states.get(call.from_user.id, {}).get('admin_action') == 'view_stats')
def process_stats(call):
    date_str = call.data.replace('admin_date_', '')
    col = get_date_column_index(date_str)
    
    if col:
        try:
            sheet = sh.worksheet(get_current_sheet_name())
            names = sheet.col_values(1)[1:]
            total = len(names)
            signed_count = sum(1 for i in range(2, total + 2) if sheet.cell(i, col).value == '✓')
            
            response = f"📊 Статистика на {date_str}:\n"
            response += f"👥 Всего: {total}\n✅ Записались: {signed_count}\n❌ Не записались: {total - signed_count}"
            bot.send_message(call.message.chat.id, response)
        except Exception as e:
            bot.send_message(call.message.chat.id, f"Ошибка: {e}")

# ================= УПРАВЛЕНИЕ ОТВЕТСТВЕННЫМИ =================

@bot.message_handler(func=lambda message: message.text == '⚙️ Управление ответственными')
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add('👤 Добавить ответственного', '🗑 Убрать ответственного', '📋 Список ответственных', '🔙 В главное меню')
    bot.send_message(message.chat.id, "Выбери действие:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == '👤 Добавить ответственного')
def add_responsible(message):
    if message.from_user.id != ADMIN_ID: return
    bot.send_message(message.chat.id, "Перешли мне сообщение от ученика ИЛИ напиши его Telegram ID числом.")
    user_states[message.from_user.id]['admin_action'] = 'adding_resp'

@bot.message_handler(func=lambda message: user_states.get(message.from_user.id, {}).get('admin_action') == 'adding_resp')
def process_add_resp(message):
    if message.forward_from:
        new_id = message.forward_from.id
        name = message.forward_from.first_name
    else:
        try:
            new_id = int(message.text.strip())
            name = str(new_id)
        except:
            bot.send_message(message.chat.id, "Не удалось определить ID. Перешли сообщение или напиши ID числом.")
            return
    
    resp = load_responsible()
    if new_id in resp:
        bot.send_message(message.chat.id, "Уже является ответственным.")
    else:
        resp.append(new_id)
        save_responsible(resp)
        bot.send_message(message.chat.id, f"✅ {name} назначен ответственным!")
    user_states[message.from_user.id]['admin_action'] = None

@bot.message_handler(func=lambda message: message.text == '🗑 Убрать ответственного')
def remove_responsible(message):
    if message.from_user.id != ADMIN_ID: return
    resp = load_responsible()
    if not resp:
        bot.send_message(message.chat.id, "Список пуст.")
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for r_id in resp:
        markup.add(types.InlineKeyboardButton(f"ID: {r_id}", callback_data=f"remove_resp_{r_id}"))
    bot.send_message(message.chat.id, "Выбери для удаления:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('remove_resp_'))
def process_remove_resp(call):
    if call.from_user.id != ADMIN_ID: return
    r_id = int(call.data.replace('remove_resp_', ''))
    resp = load_responsible()
    if r_id in resp:
        resp.remove(r_id)
        save_responsible(resp)
        bot.send_message(call.message.chat.id, f"✅ Ответственный {r_id} удалён.")

@bot.message_handler(func=lambda message: message.text == '📋 Список ответственных')
def list_resp(message):
    if message.from_user.id != ADMIN_ID: return
    resp = load_responsible()
    if not resp:
        bot.send_message(message.chat.id, "Список пуст.")
        return
    bot.send_message(message.chat.id, "📋 Ответственные:\n" + "\n".join([f"{i}. ID: {r}" for i, r in enumerate(resp, 1)]))

@bot.message_handler(func=lambda message: message.text == '🔙 В главное меню')
def back_to_main(message):
    role = user_states.get(message.from_user.id, {}).get('role', 'student')
    if role == 'admin': show_admin_menu(message)
    elif role == 'responsible': show_responsible_menu(message)
    else: show_student_menu(message, message.from_user.id)

@bot.message_handler(func=lambda message: message.text == 'ℹ️ Помощь')
def help_cmd(message):
    bot.send_message(message.chat.id, "Используй кнопки внизу экрана для управления.")

if __name__ == '__main__':
    print("Бот запущен...")
    bot.polling(none_stop=True)
