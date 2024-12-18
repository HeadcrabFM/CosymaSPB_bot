import os
from imapclient import IMAPClient
from email import message_from_bytes
from email.header import decode_header
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from html import unescape
import re

# Настройки
TELEGRAM_TOKEN = '* * *'
YANDEX_EMAIL = 'gs@cosyma.pro'
YANDEX_PASSWORD = '* * *'
IMAP_SERVER = 'imap.yandex.ru'
SAVE_PATH = '* * *'

# Глобальный список UID прочитанных писем
seen_emails = set()
CHAT_ID = None
autocheck_initialized = False  # Флаг для автоматической проверки

# Функция для декодирования MIME-заголовков
def decode_mime_header(header_value):
    decoded_parts = decode_header(header_value)
    decoded_string = ""
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            decoded_string += part.decode(encoding or "utf-8", errors="ignore")
        else:
            decoded_string += part
    return decoded_string

# Функция преобразования HTML в текст
def html_to_text(html_content):
    text = re.sub(r"<br\s*/?>", "\n", html_content)
    text = re.sub(r"</?div.*?>", "\n", text)
    text = re.sub(r"<.*?>", "", text)
    return unescape(text.strip())

# Функция обработки команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global CHAT_ID
    CHAT_ID = update.effective_chat.id
    print("Команда /start получена.")
    await update.message.reply_text("Салам! >:] Я Косима-бот для Яндекс.Почты!")

# Функция включения автоматической проверки почты
async def reboot_autocheck(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global autocheck_initialized

    print("Команда /autocheck получена.")
    if not autocheck_initialized:
        context.job_queue.run_repeating(
            check_email_periodically,
            interval=60,  # Интервал проверки почты раз в минуту
            first=0,  # Выполнить сразу после запуска
            name="check_email",
            data={"chat_id": update.effective_chat.id},
            job_kwargs={"misfire_grace_time": 60, "max_instances": 1}
        )
        autocheck_initialized = True
        await update.message.reply_text("Работа автопроверки писем возобновлена.")
        print("Автопроверка писем запущена.")
    else:
        await update.message.reply_text("Автопроверка писем уже включена.")
        print("Автопроверка уже была запущена.")

# Функция периодической проверки почты
async def check_email_periodically(context):
    global seen_emails
    chat_id = context.job.data["chat_id"]

    try:
        print("Периодическая проверка запущена.")
        with IMAPClient(IMAP_SERVER) as client:
            client.login(YANDEX_EMAIL, YANDEX_PASSWORD)
            client.select_folder('INBOX')

            # Получаем все письма
            messages = client.search('UNSEEN')
            print(f"Всего писем в ящике: {len(messages)}")

            # Отфильтровываем только те, которые ещё не обработаны
            new_emails = set(messages) - seen_emails
            print(f"Новых писем для обработки: {len(new_emails)}")

            if not new_emails:
                return  # Если новых писем нет, ничего не делаем

            # Обрабатываем новые письма
            for uid, message_data in client.fetch(new_emails, ['BODY.PEEK[]']).items():
                email_message = message_from_bytes(message_data[b'BODY[]'])

                # Декодируем заголовки
                subject = decode_mime_header(email_message['Subject'])
                from_ = decode_mime_header(email_message['From'])
                to = decode_mime_header(email_message['To'])

                # Проверяем наличие вложений
                has_attachments = any(
                    part.get('Content-Disposition') for part in email_message.walk()
                    if email_message.is_multipart()
                )

                # Декодируем тело письма
                body = ""
                if email_message.is_multipart():
                    for part in email_message.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode(
                                part.get_content_charset() or "utf-8", errors="ignore"
                            )
                            break
                        elif part.get_content_type() == "text/html":
                            html_body = part.get_payload(decode=True).decode(
                                part.get_content_charset() or "utf-8", errors="ignore"
                            )
                            body = html_to_text(html_body)
                            break
                else:
                    if email_message.get_content_type() == "text/plain":
                        body = email_message.get_payload(decode=True).decode(
                            email_message.get_content_charset() or "utf-8", errors="ignore"
                        )
                    elif email_message.get_content_type() == "text/html":
                        html_body = email_message.get_payload(decode=True).decode(
                            email_message.get_content_charset() or "utf-8", errors="ignore"
                        )
                        body = html_to_text(html_body)

                # Отправляем уведомление
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"Новое письмо!\n"
                        f"Тема: {subject}\n"
                        f"Отправитель: {from_}\n"
                        f"Кому: {to}\n"
                        f"Сообщение: {body}\n"
                        f"Вложения: {'да' if has_attachments else 'нет'}"
                    )
                )

                # Добавляем UID в список обработанных писем
                seen_emails.add(uid)
                print(f"Письмо UID {uid} обработано.")

    except Exception as e:
        print(f"Ошибка при проверке почты: {e}")

# Функция проверки почты по запросу
async def notify_new_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global seen_emails

    try:
        print("Проверка почты по запросу.")
        with IMAPClient(IMAP_SERVER) as client:
            client.login(YANDEX_EMAIL, YANDEX_PASSWORD)
            client.select_folder('INBOX')

            # Получаем все письма
            messages = client.search('UNSEEN')
            print(f"Всего писем в ящике: {len(messages)}")

            # Отфильтровываем уже обработанные письма
            new_emails = set(messages) - seen_emails
            print(f"Новых писем для обработки: {len(new_emails)}")

            if not new_emails:
                await update.message.reply_text("Новых писем на данный момент нет.")
                print("Нет новых писем.")
                return

            # Обрабатываем новые письма
            for uid, message_data in client.fetch(new_emails, ['BODY.PEEK[]']).items():
                email_message = message_from_bytes(message_data[b'BODY[]'])

                # Декодируем заголовки
                subject = decode_mime_header(email_message['Subject'])
                from_ = decode_mime_header(email_message['From'])
                to = decode_mime_header(email_message['To'])

                # Проверяем наличие вложений
                has_attachments = any(
                    part.get('Content-Disposition') for part in email_message.walk()
                    if email_message.is_multipart()
                )

                # Декодируем тело письма
                body = ""
                if email_message.is_multipart():
                    for part in email_message.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode(
                                part.get_content_charset() or "utf-8", errors="ignore"
                            )
                            break
                        elif part.get_content_type() == "text/html":
                            html_body = part.get_payload(decode=True).decode(
                                part.get_content_charset() or "utf-8", errors="ignore"
                            )
                            body = html_to_text(html_body)
                            break
                else:
                    if email_message.get_content_type() == "text/plain":
                        body = email_message.get_payload(decode=True).decode(
                            email_message.get_content_charset() or "utf-8", errors="ignore"
                        )
                    elif email_message.get_content_type() == "text/html":
                        html_body = email_message.get_payload(decode=True).decode(
                            email_message.get_content_charset() or "utf-8", errors="ignore"
                        )
                        body = html_to_text(html_body)

                # Отправляем уведомление
                await update.message.reply_text(
                    f"Новое письмо!\n"
                    f"Тема: {subject}\n"
                    f"Отправитель: {from_}\n"
                    f"Кому: {to}\n"
                    f"Сообщение: {body}\n"
                    f"Вложения: {'да' if has_attachments else 'нет'}"
                )

                # Добавляем UID в список обработанных писем
                seen_emails.add(uid)
                print(f"Письмо UID {uid} обработано.")

    except Exception as e:
        await update.message.reply_text(f"Ошибка при проверке почты: {e}")
        print(f"Ошибка при проверке почты по запросу: {e}")

# Статическое значение CHAT_ID
CHAT_ID = 237709531  # Ваш известный ID чата

if __name__ == "__main__":
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Добавление обработчиков команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("check_email", notify_new_email))
    application.add_handler(CommandHandler("autocheck", reboot_autocheck))

    # Отправляем сообщение о перезапуске перед запуском polling
    async def send_restart_message():
        if CHAT_ID:
            await application.bot.send_message(
                chat_id=CHAT_ID,
                text="СЕРВЕР ПЕРЕЗАПУЩЕН! ИСПОЛЬЗУЙТЕ /autocheck"
            )
            print("Сообщение о перезапуске отправлено в чат.")
        else:
            print("CHAT_ID не установлен. Сообщение не отправлено.")

    print("Запуск бота...")
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(send_restart_message())  # Выполняем перед запуском polling
    application.run_polling()

