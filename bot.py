import os
import json
import datetime
import telebot
from telebot import types
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
import time

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
DB_FILE = 'users_db.json'

def load_users_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return {}
    return {}

def save_users_db(db):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=4)

def load_responsible():
    if os.path.exists(RESPONSIBLE_FILE):
        try:
            with open(RESPONSIBLE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return []
    return []

def save_responsible(resp_list):
    with open(RESPONSIBLE_FILE, 'w', encoding='utf-8') as f:
        json.dump(resp_list, f)

def is_responsible(user_id):
    return user_id in load_responsible()

HOLIDAYS = [
    (datetime.date(2026, 11, 1), datetime.date(2026, 11, 8)),
    (datetime.date(2026, 12, 25), datetime.date(2027, 1, 10)),
    (datetime.date(2027, 3, 21), datetime.date(2027, 3, 28)),
    (datetime.date(2027, 6, 1), datetime.date(2027, 8, 31))
]

def is_school_day(date_obj):
    if date_obj.weekday() >= 5: return False
    for start, end in HOLIDAYS:
        if start <= date_obj <= end: return False
    return True

def get_current_sheet_name():
    months = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
    return f"{months[datetime.datetime.now().month - 1]} {datetime.datetime.now().year}"

def get_students_with_status():
    try:
        sheet = sh.worksheet("Список")
        rows = sheet.get_all_values()
        students = []
        ignore_words = ['фио', 'список', 'фамилия', 'имя', 'фамилия имя', 'ученик', '№', 'цена обеда', 'цена', 'статус', 'тип']
        for i, row in enumerate(rows):
            if len(row) >= 1:
                name = str(row[0]).strip()
                if name and name.lower() not in ignore_words:
                    status = str(row[1]).strip().upper() if len(row) >= 2 else ''
                    is_free = status in ['Б', 'БЕСПЛАТНО', 'FREE', 'ЛЬГОТНО', 'ЛЬГОТНОЕ']
                    students.append({'row': i + 1, 'name': name, 'is_free': is_free})
        return students
    except Exception as e:
        print(f"Ошибка чтения списка: {e}")
        return []

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

def get_available_dates_markup(action_prefix):
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
                markup.add(types.InlineKeyboardButton(str(date_str), callback_data=f"{action_prefix}_{date_str}"))
    except: pass
    return markup

def show_admin_menu(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add('📝 Управление записями', '📋 Список записавшихся', '📊 Статистика дня', '⚙️ Управление ответственными')
    bot.send_message(message.chat.id, "👨‍🏫 Панель классного руководителя", reply_markup=markup)

def show_responsible_menu(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add('📝 Управление записями', '📋 Список записавшихся', '📊 Статистика дня')
    bot.send_message(message.chat.id, "👤 Меню ответственного", reply_markup=markup)

def show_student_menu(chat_id, name):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add('📅 Записаться', '📋 Мои записи')
    markup.add('❌ Отменить запись', '🔄 Сменить ФИО')
    markup.add('ℹ️ Помощь')
    bot.send_message(chat_id, f"Главное меню (ты: {name})", reply_markup=markup)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    user_id_str = str(user_id) # ВСЕГДА ИСПОЛЬЗУЕМ СТРОКУ ДЛЯ JSON
    chat_id = message.chat.id
    
    if user_id == ADMIN_ID:
        user_states[user_id] = {'role': 'admin', 'chat_id': chat_id}
        show_admin_menu(message)
        return
    if is_responsible(user_id):
        user_states[user_id] = {'role': 'responsible', 'chat_id': chat_id}
        show_responsible_menu(message)
        return
    
    users_db = load_users_db()
    if user_id_str in users_db:
        name = users_db[user_id_str]
        user_states[user_id] = {'role': 'student', 'name': name, 'chat_id': chat_id}
        show_student_menu(chat_id, name)
        return
    
    user_states[user_id] = {'role': 'student', 'name': None, 'chat_id': chat_id}
    markup = types.InlineKeyboardMarkup(row_width=1)
    students = get_students_with_status()
    if not students:
        bot.send_message(chat_id, "⚠️ Не удалось загрузить список учеников.")
        return
    for st in students:
        markup.add(types.InlineKeyboardButton(st['name'], callback_data=f"select_name_{st['row']}"))
    bot.send_message(chat_id, "Привет! Выбери своё ФИО из списка:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('select_name_'))
def handle_name_selection(call):
    user_id = call.from_user.id
    user_id_str = str(user_id) # ВСЕГДА СТРОКА
    chat_id = call.message.chat.id if call.message else user_states.get(user_id, {}).get('chat_id')
    if not chat_id: return
    
    row = int(call.data.split('_')[2])
    students = get_students_with_status()
    name = next((st['name'] for st in students if st['row'] == row), 'Ученик')
    
    users_db = load_users_db()
    users_db[user_id_str] = name # СОХРАНЯЕМ КАК СТРОКУ
    save_users_db(users_db)
    
    user_states[user_id] = {'role': 'student', 'name': name, 'chat_id': chat_id}
    bot.answer_callback_query(call.id, f"Выбрано: {name}")
    show_student_menu(chat_id, name)

@bot.message_handler(func=lambda message: message.text == '🔄 Сменить ФИО')
def change_name(message):
    user_id = message.from_user.id
    user_id_str = str(user_id)
    chat_id = message.chat.id
    users_db = load_users_db()
    if user_id_str in users_db:
        del users_db[user_id_str]
        save_users_db(users_db)
    user_states[user_id] = {'role': 'student', 'name': None, 'chat_id': chat_id}
    markup = types.InlineKeyboardMarkup(row_width=1)
    students = get_students_with_status()
    for st in students:
        markup.add(types.InlineKeyboardButton(st['name'], callback_data=f"select_name_{st['row']}"))
    bot.send_message(chat_id, "Выбери своё новое ФИО из списка:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == 'ℹ️ Помощь')
def help_cmd(message):
    bot.send_message(message.chat.id, "📖 Помощь:\n📅 Записаться\n📋 Мои записи\n❌ Отменить запись\n🔄 Сменить ФИО")

@bot.message_handler(func=lambda message: message.text == '📝 Управление записями')
def start_manage_records(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    current_role = user_states.get(user_id, {}).get('role')
    if current_role not in ['admin', 'responsible']:
        if is_responsible(user_id): current_role = 'responsible'
        elif user_id == ADMIN_ID: current_role = 'admin'
        else:
            bot.send_message(chat_id, "⛔ У вас нет прав.")
            return
    user_states[user_id] = {'role': current_role, 'action': 'select_date_manage', 'selected': [], 'chat_id': chat_id}
    bot.send_message(chat_id, "Выберите дату:", reply_markup=get_available_dates_markup('manage_date'))

@bot.callback_query_handler(func=lambda call: call.data.startswith('manage_date_'))
def handle_manage_date_selection(call):
    user_id = call.from_user.id
    state = user_states.get(user_id, {})
    if state.get('action') != 'select_date_manage': return
    chat_id = call.message.chat.id if call.message else state.get('chat_id')
    date_str = call.data.replace('manage_date_', '')
    state['action'] = 'select_students_manage'
    state['target_date'] = date_str
    state['selected'] = []
    state['students_cache'] = []
    state['chat_id'] = chat_id
    bot.answer_callback_query(call.id, f"Дата: {date_str}")
    try:
        sheet = sh.worksheet(get_current_sheet_name())
        col = get_date_column_index(date_str)
        students = get_students_with_status()
        col_values = sheet.col_values(col)
        for st in students:
            row_index = st['row'] - 1
            val = str(col_values[row_index]).strip() if row_index < len(col_values) else ''
            if val == 'П': st['current_status'] = 'paid'
            elif val == 'Б': st['current_status'] = 'free'
            else: st['current_status'] = 'none'
        state['students_cache'] = students
        msg = bot.send_message(chat_id, "Отметьте учеников:", reply_markup=build_manage_markup(state))
        state['manage_message_id'] = msg.message_id
    except Exception as e:
        bot.send_message(chat_id, f"Ошибка: {e}")

def build_manage_markup(state):
    students = state.get('students_cache', [])
    selected_rows = state.get('selected', [])
    markup = types.InlineKeyboardMarkup(row_width=1)
    for st in students:
        row_num = st['row']
        is_selected = row_num in selected_rows
        current_status = st.get('current_status', 'none')
        status_icon = "✅ (П)" if current_status == 'paid' else "🆓 (Б)" if current_status == 'free' else "⬜"
        if is_selected:
            new_status = "🆓" if st['is_free'] else "✅ (П)" if current_status == 'none' else "⬜"
            button_text = f"👉 {st['name']} {status_icon} → {new_status}"
        else:
            button_text = f"   {st['name']} {status_icon}"
        markup.add(types.InlineKeyboardButton(button_text, callback_data=f"toggle_manage_{row_num}"))
    markup.add(types.InlineKeyboardButton("💾 Сохранить", callback_data="confirm_manage"))
    markup.add(types.InlineKeyboardButton("🔙 Отмена", callback_data="cancel_manage"))
    return markup

@bot.callback_query_handler(func=lambda call: call.data.startswith('toggle_manage_'))
def toggle_manage_student(call):
    user_id = call.from_user.id
    state = user_states.get(user_id, {})
    if state.get('action') != 'select_students_manage': return
    row = int(call.data.split('_')[2])
    if row in state['selected']: state['selected'].remove(row)
    else: state['selected'].append(row)
    bot.answer_callback_query(call.id)
    chat_id = state.get('chat_id')
    message_id = state.get('manage_message_id')
    if chat_id and message_id:
        try:
            bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=build_manage_markup(state))
        except:
            msg = bot.send_message(chat_id, "Отметьте учеников:", reply_markup=build_manage_markup(state))
            state['manage_message_id'] = msg.message_id

@bot.callback_query_handler(func=lambda call: call.data == 'confirm_manage')
def confirm_manage(call):
    user_id = call.from_user.id
    state = user_states.get(user_id, {})
    date_str = state.get('target_date')
    selected_rows = state.get('selected', [])
    if not selected_rows:
        bot.answer_callback_query(call.id, "Никто не выбран!", show_alert=True)
        return
    try:
        sheet = sh.worksheet(get_current_sheet_name())
        col = get_date_column_index(date_str)
        students = state.get('students_cache', [])
        to_sign, to_remove = [], []
        for st in students:
            if st['row'] in selected_rows:
                current = st.get('current_status', 'none')
                if current == 'none':
                    mark = 'Б' if st['is_free'] else 'П'
                    sheet.update_cell(st['row'], col, mark)
                    to_sign.append(f"{st['name']} ({'Б' if st['is_free'] else 'П'})")
                else:
                    sheet.update_cell(st['row'], col, '')
                    to_remove.append(st['name'])
        chat_id = state.get('chat_id')
        if chat_id:
            report = f"✅ Сохранено на {date_str}:\n"
            if to_sign: report += f"📝 Записаны: " + ", ".join(to_sign) + "\n"
            if to_remove: report += f"❌ Сняты: " + ", ".join(to_remove)
            bot.send_message(chat_id, report)
    except Exception as e:
        bot.send_message(state.get('chat_id'), f"Ошибка: {e}")
    state['action'] = None

@bot.callback_query_handler(func=lambda call: call.data == 'cancel_manage')
def cancel_manage(call):
    user_id = call.from_user.id
    if user_id in user_states:
        user_states[user_id]['action'] = None
    bot.answer_callback_query(call.id, "Отменено")
    bot.send_message(call.message.chat.id, "Действие отменено.")

@bot.message_handler(func=lambda message: message.text == '📅 Записаться')
def student_signup(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    state = user_states.get(user_id, {})
    if state.get('role') != 'student' or not state.get('name'):
        bot.send_message(chat_id, "Сначала выберите свое имя командой /start")
        return
    state['action'] = 'student_signup_date'
    state['chat_id'] = chat_id
    bot.send_message(chat_id, "Выберите дату для записи:", reply_markup=get_available_dates_markup('student_signup'))

@bot.callback_query_handler(func=lambda call: call.data.startswith('student_signup_'))
def handle_student_signup_date(call):
    user_id = call.from_user.id
    state = user_states.get(user_id, {})
    if state.get('action') != 'student_signup_date': return
    chat_id = state.get('chat_id', call.message.chat.id if call.message else None)
    date_str = call.data.replace('student_signup_', '')
    bot.answer_callback_query(call.id, f"Дата: {date_str}")
    try:
        sheet = sh.worksheet(get_current_sheet_name())
        col = get_date_column_index(date_str)
        students = get_students_with_status()
        current_student = next((st for st in students if st['name'] == state['name']), None)
        if not current_student: return
        col_values = sheet.col_values(col)
        row_index = current_student['row'] - 1
        current_val = str(col_values[row_index]).strip() if row_index < len(col_values) else ''
        if current_val in ['П', 'Б']:
            bot.send_message(chat_id, f"⚠️ Вы уже записаны на {date_str} ({current_val}).")
        else:
            mark = 'Б' if current_student['is_free'] else 'П'
            sheet.update_cell(current_student['row'], col, mark)
            bot.send_message(chat_id, f"✅ Вы успешно записаны на {date_str}.")
    except Exception as e:
        bot.send_message(chat_id, f"Ошибка: {e}")
    state['action'] = None

@bot.message_handler(func=lambda message: message.text == '📋 Мои записи')
def student_my_records(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    state = user_states.get(user_id, {})
    if state.get('role') != 'student' or not state.get('name'):
        bot.send_message(chat_id, "Сначала выберите свое имя командой /start")
        return
    try:
        sheet = sh.worksheet(get_current_sheet_name())
        students = get_students_with_status()
        current_student = next((st for st in students if st['name'] == state['name']), None)
        if not current_student: return
        headers = sheet.row_values(1)
        date_cols = [(i, str(h).strip()) for i, h in enumerate(headers, start=1) if i >= 3 and '.' in str(h)]
        row_values = sheet.row_values(current_student['row'])
        my_records = []
        for col_idx, date_str in date_cols:
            val = str(row_values[col_idx - 1]).strip()
            if val in ['П', 'Б']:
                status = "бесплатно 🆓" if val == 'Б' else "платно ✅"
                my_records.append(f"📅 {date_str} — {status}")
        response = f"📋 Ваши записи:\n\n" + "\n".join(my_records) if my_records else f"📋 Вы пока не записаны."
        bot.send_message(chat_id, response)
    except Exception as e:
        bot.send_message(chat_id, f"Ошибка: {e}")

@bot.message_handler(func=lambda message: message.text == '❌ Отменить запись')
def student_cancel(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    state = user_states.get(user_id, {})
    if state.get('role') != 'student' or not state.get('name'):
        bot.send_message(chat_id, "Сначала выберите свое имя командой /start")
        return
    state['action'] = 'student_cancel_date'
    state['chat_id'] = chat_id
    bot.send_message(chat_id, "Выберите дату для отмены:", reply_markup=get_available_dates_markup('student_cancel'))

@bot.callback_query_handler(func=lambda call: call.data.startswith('student_cancel_'))
def handle_student_cancel_date(call):
    user_id = call.from_user.id
    state = user_states.get(user_id, {})
    if state.get('action') != 'student_cancel_date': return
    chat_id = state.get('chat_id', call.message.chat.id if call.message else None)
    date_str = call.data.replace('student_cancel_', '')
    bot.answer_callback_query(call.id, f"Дата: {date_str}")
    try:
        sheet = sh.worksheet(get_current_sheet_name())
        col = get_date_column_index(date_str)
        students = get_students_with_status()
        current_student = next((st for st in students if st['name'] == state['name']), None)
        if not current_student: return
        col_values = sheet.col_values(col)
        row_index = current_student['row'] - 1
        current_val = str(col_values[row_index]).strip() if row_index < len(col_values) else ''
        if current_val in ['П', 'Б']:
            sheet.update_cell(current_student['row'], col, '')
            bot.send_message(chat_id, f"✅ Запись на {date_str} отменена.")
        else:
            bot.send_message(chat_id, f"⚠️ Вы и так не записаны.")
    except Exception as e:
        bot.send_message(chat_id, f"Ошибка: {e}")
    state['action'] = None

@bot.message_handler(func=lambda message: message.text in ['📋 Список записавшихся', '📊 Статистика дня'])
def admin_stats(message):
    bot.send_message(message.chat.id, "Выберите дату:", reply_markup=get_available_dates_markup('view_list' if message.text == '📋 Список записавшихся' else 'view_stats'))
    user_states[message.from_user.id]['action'] = 'view_list' if message.text == '📋 Список записавшихся' else 'view_stats'

@bot.callback_query_handler(func=lambda call: call.data.startswith('view_list_') or call.data.startswith('view_stats_'))
def process_view(call):
    if call.data.startswith('view_list_'):
        date_str = call.data.replace('view_list_', '')
    else:
        date_str = call.data.replace('view_stats_', '')
    col = get_date_column_index(date_str)
    if not col:
        bot.send_message(call.message.chat.id, "Дата не найдена.")
        return
    try:
        sheet = sh.worksheet(get_current_sheet_name())
        students = get_students_with_status()
        col_values = sheet.col_values(col)
        signed, free_count, paid_count = [], 0, 0
        for st in students:
            row_index = st['row'] - 1
            val = str(col_values[row_index]).strip() if row_index < len(col_values) else ''
            if val == 'П': 
                signed.append(f"✅ {st['name']}")
                paid_count += 1
            elif val == 'Б': 
                signed.append(f"🆓 {st['name']}")
                free_count += 1
        if call.data.startswith('view_list_'):
            response = f"📋 На {date_str} ({len(signed)} чел.):\n" + "\n".join(signed) if signed else f"📋 На {date_str} никто не записан."
        else:
            total = len(students)
            response = f"📊 Статистика на {date_str}:\n👥 Всего: {total}\n✅ Платно: {paid_count}\n🆓 Бесплатно: {free_count}\n❌ Не записались: {total - (paid_count + free_count)}\n💵 Итого: {paid_count * 1.50:.2f} BYN"
        bot.send_message(call.message.chat.id, response)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Ошибка: {e}")

@bot.message_handler(func=lambda message: message.text == '⚙️ Управление ответственными')
def admin_panel(message):
    if message.from_user.id != ADMIN_ID: return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add('👤 Добавить', '🗑 Убрать', '📋 Список', '🔙 В главное меню')
    bot.send_message(message.chat.id, "Выберите действие:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == '👤 Добавить')
def add_responsible(message):
    if message.from_user.id != ADMIN_ID: return
    bot.send_message(message.chat.id, "Перешлите сообщение от ученика ИЛИ напишите его ID числом.")
    user_states[message.from_user.id]['action'] = 'adding_resp'

@bot.message_handler(func=lambda message: user_states.get(message.from_user.id, {}).get('action') == 'adding_resp')
def process_add_resp(message):
    if message.from_user.id != ADMIN_ID: return
    new_id = message.forward_from.id if message.forward_from else int(message.text.strip())
    resp = load_responsible()
    if new_id not in resp:
        resp.append(new_id)
        save_responsible(resp)
        bot.send_message(message.chat.id, f"✅ Добавлен!")
    user_states[message.from_user.id]['action'] = None

@bot.message_handler(func=lambda message: message.text == '🗑 Убрать')
def remove_responsible(message):
    if message.from_user.id != ADMIN_ID: return
    resp = load_responsible()
    markup = types.InlineKeyboardMarkup(row_width=1)
    for r_id in resp:
        markup.add(types.InlineKeyboardButton(f"ID: {r_id}", callback_data=f"remove_resp_{r_id}"))
    bot.send_message(message.chat.id, "Выберите для удаления:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('remove_resp_'))
def process_remove_resp(call):
    if call.from_user.id != ADMIN_ID: return
    r_id = int(call.data.replace('remove_resp_', ''))
    resp = load_responsible()
    if r_id in resp:
        resp.remove(r_id)
        save_responsible(resp)
        bot.send_message(call.message.chat.id, f"✅ Удалён.")

@bot.message_handler(func=lambda message: message.text == '📋 Список')
def list_resp(message):
    if message.from_user.id != ADMIN_ID: return
    resp = load_responsible()
    response = "📋 Ответственные:\n" + "\n".join([f"{i}. ID: `{r}`" for i, r in enumerate(resp, 1)]) if resp else "Пусто."
    bot.send_message(message.chat.id, response, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == '🔙 В главное меню')
def back_to_main(message):
    role = user_states.get(message.from_user.id, {}).get('role', 'student')
    if role == 'admin': show_admin_menu(message)
    elif role == 'responsible': show_responsible_menu(message)
    else:
        name = user_states.get(message.from_user.id, {}).get('name', 'Ученик')
        show_student_menu(message.chat.id, name)

@bot.message_handler(commands=['export_db'])
def export_db(message):
    if message.from_user.id != ADMIN_ID: return
    with open(DB_FILE, 'rb') as f:
        bot.send_document(message.chat.id, f, caption="📦 users_db.json")

@bot.message_handler(content_types=['document'])
def import_db(message):
    if message.from_user.id != ADMIN_ID: return
    if message.document.file_name.endswith('.json'):
        file_info = bot.get_file(message.document.file_id)
        with open(DB_FILE, 'wb') as f:
            f.write(bot.download_file(file_info.file_path))
        bot.send_message(message.chat.id, "✅ База импортирована!")

if __name__ == '__main__':
    print("🚀 Бот запущен. Токен и ID загружены из .env")
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            print(f"Ошибка: {e}. Перезапуск...")
            time.sleep(5)
