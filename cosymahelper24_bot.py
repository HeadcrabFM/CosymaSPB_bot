from telegram import Update
from telegram.ext import Application, MessageHandler, CallbackContext, filters
import re
from datetime import datetime
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

# Настройки
SERVICE_ACCOUNT_FILE = "..._keyring.json"
SPREADSHEET_ID = "* * *"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
BOT_TOKEN = "* * *"
ALLOWED_CHAT_ID = cosymachat_id

# Подключение к Google Sheets
credentials = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
service = build("sheets", "v4", credentials=credentials)
sheet = service.spreadsheets()

# Получение следующего уникального ID с префиксами
def get_next_id(sheet_name):
    # Определяем префикс в зависимости от вкладки
    prefix = "PCB_" if sheet_name == "PCB" else "S_"
    
    # Получаем текущие ID из выбранной вкладки
    result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=f"{sheet_name}!A:A").execute()
    values = result.get("values", [])

    # Если данные есть, ищем максимальный ID в текущей вкладке
    last_id = 0
    for row in values[1:]:  # Пропускаем заголовок
        if row and row[0].startswith(prefix):
            try:
                numeric_part = int(row[0].split("_")[1])
                last_id = max(last_id, numeric_part)
            except ValueError:
                continue

    # Генерируем следующий ID
    next_id = last_id + 1
    return f"{prefix}{str(next_id).zfill(4)}"

# Парсинг сообщения
def parse_message(message, sheet_name):
    date_time = datetime.now().strftime("%d.%m.%Y %H:%M")
    user = message.from_user.full_name
    text = message.caption or message.text or ''

    # Корректное извлечение хэштегов
    hashtags = ", ".join(re.findall(r"#\w+", text))
    comment = re.sub(r"#\w+", "", text).strip()

    # Проверяем наличие вложений и добавляем их типы
    attachments = []
    if message.photo:
        attachments.append("Фото")
    if message.video:
        attachments.append("Видео")
    if message.document:
        attachments.append("Документ")
    if message.audio:
        attachments.append("Аудио")
    if message.voice:
        attachments.append("Голосовое")
    
    has_attachments = "да: " + ", ".join(attachments) if attachments else "нет"

    # Получаем уникальный ID
    unique_id = get_next_id(sheet_name)
    return [unique_id, date_time, user, hashtags, comment, has_attachments]

# Обработка сообщений
async def handle_message(update: Update, context: CallbackContext):
    # Проверяем chat_id
    if update.message.chat_id != ALLOWED_CHAT_ID:
        return

    message = update.message
    command = message.text.split(' ')[0] if message.text else (message.caption.split(' ')[0] if message.caption else '')

    # Определяем вкладку для записи
    if command == '/bug_pcb':
        sheet_name = 'PCB'
    elif command == '/bug_po':
        sheet_name = 'ПО'
    else:
        await message.reply_text("Команда не распознана. Используйте /bug_pcb или /bug_po.")
        return

    try:
        # Парсим сообщение и сохраняем данные
        data = parse_message(message, sheet_name)
        sheet.values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{sheet_name}!A1",
            valueInputOption="RAW",
            body={"values": [data]},
        ).execute()
        await message.reply_text(f"Баг успешно зарегистрирован в реестре правок!\nid: {data[0]}")
    except Exception as e:
        await message.reply_text(f"Ошибка: {e}")

# Основная функция
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.ALL, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()

