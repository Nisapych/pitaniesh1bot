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
        with open(RESPONSIBLE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
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
        # ⭐ ДОБАВЛЕНЫ 'цена обеда' и 'цена' в список игнорируемых слов
        ignore_words = ['фио', 'список', 'фамилия', 'имя', 'фамилия имя', 'ученик', '№', 'цена обеда', 'цена']
        
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
                markup.add(types.InlineKeyboardButton(
                    str(date_str), 
                    callback_data=f"{action_prefix}_{date_str}"
                ))
    except: pass
    return markup

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
    students = get_students_with_status()
    
    if not students:
        bot.send_message(message.chat.id, "⚠️ Не удалось загрузить список учеников.")
        return
        
    for st in students:
        markup.add(types.InlineKeyboardButton(st['name'], callback_data=f"select_name_{st['row']}"))
    
    bot.send_message(message.chat.id, "Привет! Выбери своё ФИО из списка:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('select_name_'))
def handle_name_selection(call):
    user_id = call.from_user.id
    row = int(call.data.split('_')[2])
    students = get_students_with_status()
    name = next((st['name'] for st in students if st['row'] == row), 'Ученик')
    
    user_states[user_id]['name'] = name
    bot.answer_callback_query(call.id, f"Выбрано: {name}")
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add('📅 Записаться', '📋 Мои записи')
    markup.add('❌ Отменить запись', 'ℹ️ Помощь')
    bot.send_message(call.message.chat.id, f"Главное меню (ты: {name})", reply_markup=markup)

def show_admin_menu(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add('📝 Управление записями')
    markup.add('📋 Список записавшихся')
    markup.add('📊 Статистика дня')
    markup.add('⚙️ Управление ответственными')
    bot.send_message(message.chat.id, "👨‍🏫 Панель классного руководителя", reply_markup=markup)

def show_responsible_menu(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add('📝 Управление записями')
    markup.add('📋 Список записавшихся')
    markup.add('📊 Статистика дня')
    bot.send_message(message.chat.id, "👤 Меню ответственного", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == '📝 Управление записями')
def start_manage_records(message):
    user_id = message.from_user.id
    if user_states.get(user_id, {}).get('role') not in ['admin', 'responsible']:
        return
    
    user_states[user_id] = {'role': user_states[user_id]['role'], 'action': 'select_date_manage', 'selected': []}
    bot.send_message(message.chat.id, "Выберите дату:", reply_markup=get_available_dates_markup('manage_date'))

@bot.callback_query_handler(func=lambda call: call.data.startswith('manage_date_'))
def handle_manage_date_selection(call):
    user_id = call.from_user.id
    state = user_states.get(user_id, {})
    if state.get('action') != 'select_date_manage':
        return
    
    date_str = call.data.replace('manage_date_', '')
    state['action'] = 'select_students_manage'
    state['target_date'] = date_str
    state['selected'] = []
    state['students_cache'] = []
    state['manage_message_id'] = None
    
    bot.answer_callback_query(call.id, f"Дата: {date_str}")
    
    try:
        sheet = sh.worksheet(get_current_sheet_name())
        col = get_date_column_index(date_str)
        students = get_students_with_status()
        
        if not students:
            bot.send_message(call.message.chat.id, "⚠️ Список учеников пуст!")
            return
        
        for st in students:
            val = str(sheet.cell(st['row'], col).value).strip()
            if val == 'П':
                st['current_status'] = 'paid'
            elif val == 'Б':
                st['current_status'] = 'free'
            else:
                st['current_status'] = 'none'
        
        state['students_cache'] = students
        
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Ошибка: {e}")
        return
    
    # Отправляем новое сообщение со списком
    msg = render_manage_students_message(call.message.chat.id, state)
    state['manage_message_id'] = msg.message_id

def render_manage_students_message(chat_id, state):
    students = state.get('students_cache', [])
    selected_rows = state.get('selected', [])
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    for st in students:
        row_num = st['row']
        is_selected = row_num in selected_rows
        current_status = st.get('current_status', 'none')
        
        if current_status == 'paid':
            status_icon = "✅ (П)"
        elif current_status == 'free':
            status_icon = "🆓 (Б)"
        else:
            status_icon = "⬜"
        
        if is_selected:
            if current_status == 'none':
                new_status = "🆓" if st['is_free'] else "✅ (П)"
                button_text = f"👉 {st['name']} {status_icon} → {new_status}"
            else:
                button_text = f"👉 {st['name']} {status_icon} → ⬜"
        else:
            button_text = f"   {st['name']} {status_icon}"
        
        markup.add(types.InlineKeyboardButton(button_text, callback_data=f"toggle_manage_{row_num}"))
    
    markup.add(types.InlineKeyboardButton("💾 Сохранить изменения", callback_data="confirm_manage"))
    markup.add(types.InlineKeyboardButton("🔙 Отмена", callback_data="cancel_manage"))
    
    return bot.send_message(chat_id, "Отметьте учеников (нажмите для переключения):", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('toggle_manage_'))
def toggle_manage_student(call):
    user_id = call.from_user.id
    state = user_states.get(user_id, {})
    if state.get('action') != 'select_students_manage':
        return
    
    row = int(call.data.split('_')[2])
    
    if row in state['selected']:
        state['selected'].remove(row)
    else:
        state['selected'].append(row)
    
    bot.answer_callback_query(call.id)
    
    # Редактируем существующее сообщение
    students = state.get('students_cache', [])
    selected_rows = state.get('selected', [])
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    for st in students:
        row_num = st['row']
        is_selected = row_num in selected_rows
        current_status = st.get('current_status', 'none')
        
        if current_status == 'paid':
            status_icon = "✅ (П)"
        elif current_status == 'free':
            status_icon = "🆓 (Б)"
        else:
            status_icon = "⬜"
        
        if is_selected:
            if current_status == 'none':
                new_status = "🆓" if st['is_free'] else "✅ (П)"
                button_text = f"👉 {st['name']} {status_icon} → {new_status}"
            else:
                button_text = f"👉 {st['name']} {status_icon} → ⬜"
        else:
            button_text = f"   {st['name']} {status_icon}"
        
        markup.add(types.InlineKeyboardButton(button_text, callback_data=f"toggle_manage_{row_num}"))
    
    markup.add(types.InlineKeyboardButton("💾 Сохранить изменения", callback_data="confirm_manage"))
    markup.add(types.InlineKeyboardButton("🔙 Отмена", callback_data="cancel_manage"))
    
    try:
        bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)
    except:
        pass

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
        
        to_sign = []
        to_remove = []
        
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
        
        report = f"✅ Сохранено на {date_str}:\n\n"
        if to_sign:
            report += f"📝 Записаны ({len(to_sign)}):\n" + "\n".join([f"• {name}" for name in to_sign]) + "\n\n"
        if to_remove:
            report += f"❌ Сняты ({len(to_remove)}):\n" + "\n".join([f"• {name}" for name in to_remove])
        
        bot.send_message(call.message.chat.id, report)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Ошибка: {e}")
    
    state['action'] = None
    state['selected'] = []
    state['students_cache'] = []

@bot.callback_query_handler(func=lambda call: call.data == 'cancel_manage')
def cancel_manage(call):
    user_id = call.from_user.id
    if user_id in user_states:
        user_states[user_id]['action'] = None
        user_states[user_id]['selected'] = []
        user_states[user_id]['students_cache'] = []
    bot.answer_callback_query(call.id, "Отменено")
    bot.send_message(call.message.chat.id, "Действие отменено.")

@bot.message_handler(func=lambda message: message.text == '📋 Список записавшихся')
def show_all_signed(message):
    if user_states.get(message.from_user.id, {}).get('role') not in ['admin', 'responsible']:
        return
    bot.send_message(message.chat.id, "Выберите дату:", reply_markup=get_available_dates_markup('view_list'))
    user_states[message.from_user.id]['action'] = 'view_list'

@bot.callback_query_handler(func=lambda call: call.data.startswith('view_list_'))
def process_view_list(call):
    date_str = call.data.replace('view_list_', '')
    col = get_date_column_index(date_str)
    if not col:
        bot.send_message(call.message.chat.id, "Дата не найдена.")
        return
    
    try:
        sheet = sh.worksheet(get_current_sheet_name())
        students = get_students_with_status()
        signed = []
        free_count = 0
        
        for st in students:
            val = str(sheet.cell(st['row'], col).value).strip()
            if val in ['П', 'Б']:
                signed.append(f"{'🆓' if st['is_free'] else '✅'} {st['name']}")
                if st['is_free']: free_count += 1
        
        if signed:
            response = f"📋 Записались на {date_str} ({len(signed)} чел., из них 🆓 {free_count}):\n" + "\n".join(signed)
        else:
            response = f"📋 На {date_str} никто не записан."
        bot.send_message(call.message.chat.id, response)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Ошибка: {e}")

@bot.message_handler(func=lambda message: message.text == '📊 Статистика дня')
def show_daily_stats(message):
    if user_states.get(message.from_user.id, {}).get('role') not in ['admin', 'responsible']:
        return
    bot.send_message(message.chat.id, "Выберите дату:", reply_markup=get_available_dates_markup('view_stats'))
    user_states[message.from_user.id]['action'] = 'view_stats'

@bot.callback_query_handler(func=lambda call: call.data.startswith('view_stats_'))
def process_stats(call):
    date_str = call.data.replace('view_stats_', '')
    col = get_date_column_index(date_str)
    if not col:
        bot.send_message(call.message.chat.id, "Дата не найдена.")
        return
    
    try:
        sheet = sh.worksheet(get_current_sheet_name())
        students = get_students_with_status()
        total = len(students)
        paid_count = 0
        free_count = 0
        
        for st in students:
            val = str(sheet.cell(st['row'], col).value).strip()
            if val == 'П': paid_count += 1
            elif val == 'Б': free_count += 1
            
        total_signed = paid_count + free_count
        price = 1.50
        total_sum = paid_count * price
        
        response = f"📊 Статистика на {date_str}:\n"
        response += f"👥 Всего в классе: {total}\n"
        response += f"✅ Записались (платно): {paid_count}\n"
        response += f"🆓 Записались (бесплатно): {free_count}\n"
        response += f"❌ Не записались: {total - total_signed}\n"
        response += f"💵 Итого к оплате: {total_sum:.2f} BYN"
        
        bot.send_message(call.message.chat.id, response)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Ошибка: {e}")

@bot.message_handler(func=lambda message: message.text == '⚙️ Управление ответственными')
def admin_panel(message):
    if message.from_user.id != ADMIN_ID: return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add('👤 Добавить ответственного', '🗑 Убрать ответственного', '📋 Список ответственных', '🔙 В главное меню')
    bot.send_message(message.chat.id, "Выберите действие:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == '👤 Добавить ответственного')
def add_responsible(message):
    if message.from_user.id != ADMIN_ID: return
    bot.send_message(message.chat.id, "Перешлите сообщение от ученика ИЛИ напишите его ID числом.")
    user_states[message.from_user.id]['action'] = 'adding_resp'

@bot.message_handler(func=lambda message: user_states.get(message.from_user.id, {}).get('action') == 'adding_resp')
def process_add_resp(message):
    if message.forward_from:
        new_id = message.forward_from.id
        name = message.forward_from.first_name
    else:
        try:
            new_id = int(message.text.strip())
            name = str(new_id)
        except:
            bot.send_message(message.chat.id, "Не удалось определить ID.")
            return
    
    resp = load_responsible()
    if new_id in resp:
        bot.send_message(message.chat.id, "Уже является ответственным.")
    else:
        resp.append(new_id)
        save_responsible(resp)
        bot.send_message(message.chat.id, f"✅ {name} назначен ответственным!")
    user_states[message.from_user.id]['action'] = None

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
    bot.send_message(message.chat.id, "Выберите для удаления:", reply_markup=markup)

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
    response = "📋 Ответственные:\n" + "\n".join([f"{i}. ID: `{r}`" for i, r in enumerate(resp, 1)])
    bot.send_message(message.chat.id, response, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == '🔙 В главное меню')
def back_to_main(message):
    role = user_states.get(message.from_user.id, {}).get('role', 'student')
    if role == 'admin': show_admin_menu(message)
    elif role == 'responsible': show_responsible_menu(message)
    else:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add('📅 Записаться', '📋 Мои записи')
        markup.add('❌ Отменить запись', 'ℹ️ Помощь')
        bot.send_message(message.chat.id, "Главное меню", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == 'ℹ️ Помощь')
def help_cmd(message):
    bot.send_message(message.chat.id, "Используйте кнопки для управления записями.")

if __name__ == '__main__':
    print("🚀 Бот запущен...")
    bot.polling(none_stop=True)
