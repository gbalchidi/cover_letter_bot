import logging
import os
import re
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from openai import OpenAI
import nest_asyncio
import tempfile
from PyPDF2 import PdfReader
import docx
from repositories.supabase_client import SupabaseClient
from repositories.repositories import UserRepository, ResumeRepository

# Try to load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, will use system environment variables

nest_asyncio.apply()

# Get tokens from environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Validate that required environment variables are set
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is not set. Please set it in your .env file or environment.")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is not set. Please set it in your .env file or environment.")

# Set up logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

# States for conversation
WAITING_FOR_CV = "waiting_for_cv"
READY_FOR_JOBS = "ready_for_jobs"

# Supabase client initialization
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL и SUPABASE_KEY должны быть заданы в переменных окружения!")
supabase = SupabaseClient(SUPABASE_URL, SUPABASE_KEY)
user_repo = UserRepository(supabase)
resume_repo = ResumeRepository(supabase)

# Function to detect language
def detect_primary_language(text):
    """Simple language detection based on character count."""
    russian_chars = len(re.findall(r'[а-яА-ЯёЁ]', text))
    english_chars = len(re.findall(r'[a-zA-Z]', text))
    
    if russian_chars > english_chars:
        return 'russian'
    else:
        return 'english'

# Function to check language consistency
def check_language_consistency(text):
    """Check if text has mixed languages."""
    lines = text.split('\n')
    russian_lines = 0
    english_lines = 0
    
    for line in lines:
        if len(line.strip()) > 10:  # Only check meaningful lines
            if detect_primary_language(line) == 'russian':
                russian_lines += 1
            else:
                english_lines += 1
    
    # If more than 20% of lines are in a different language, it's mixed
    total_lines = russian_lines + english_lines
    if total_lines > 0:
        if russian_lines > english_lines:
            return 'russian' if english_lines / total_lines < 0.2 else 'mixed'
        else:
            return 'english' if russian_lines / total_lines < 0.2 else 'mixed'
    
    return detect_primary_language(text)

# Function to unify language
async def unify_language(text, target_language):
    """Unify the language of the cover letter."""
    prompt = f"""Переведи следующее сопроводительное письмо полностью на {'русский' if target_language == 'russian' else 'английский'} язык. 
Сохрани всю структуру и форматирование. Не добавляй никаких пояснений или комментариев.
Просто верни переведенный текст:

{text}"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=1500
    )
    return response.choices[0].message.content.strip()

# Function to escape markdown characters for Telegram
def escape_markdown_v2(text):
    """Escape special characters for Telegram MarkdownV2."""
    # List of characters to escape
    escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    
    # Escape each character
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')
    
    return text

# Function to handle the /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = update.message.from_user.id
    username = update.message.from_user.username
    user = await user_repo.get_or_create_user(telegram_id, username)
    resume = await resume_repo.get_resume(telegram_id)
    if resume:
        context.user_data['state'] = READY_FOR_JOBS
        await update.message.reply_text(
            'С возвращением! У меня есть ваше резюме. '
            'Отправьте текст вакансии для генерации письма.'
        )
    else:
        context.user_data['state'] = WAITING_FOR_CV
        await update.message.reply_text(
            'Привет! Отправьте мне ваше резюме для начала работы.'
        )

# Function to reset CV
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = update.message.from_user.id
    # Просто сохраняем пустое резюме (или можно реализовать отдельный метод удаления)
    await resume_repo.save_resume(telegram_id, "")
    context.user_data['state'] = WAITING_FOR_CV
    await update.message.reply_text(
        'Резюме удалено. Отправьте мне новое резюме для сохранения.'
    )

# Function to show saved CV
async def show_cv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = update.message.from_user.id
    cv_text = await resume_repo.get_resume(telegram_id)
    if cv_text:
        cv_preview = cv_text[:500] + "..." if len(cv_text) > 500 else cv_text
        escaped_cv = escape_markdown_v2(cv_preview)
        await update.message.reply_text(
            f"Ваше сохраненное резюме (первые 500 символов):\n\n`{escaped_cv}`",
            parse_mode='MarkdownV2'
        )
    else:
        await update.message.reply_text(
            'У вас пока нет сохраненного резюме. Отправьте его мне!'
        )

# Generate complete cover letter
async def generate_cover_letter(job_text, cv_text):
    """Generate a complete cover letter using a single API call."""
    system_message = """Я хочу, чтобы ты выступил в роли эксперта карьерного консультирования и составил полное сопроводительное письмо на основе моего резюме и текста вакансии. Внимательно проанализируй описание позиции и действуй по следующему плану:

1. **Приветствие и "О себе"**
    
    — Начни с фразы: "Здравствуйте, меня зовут <Имя>, увидел, что вы в поиске <Название позиции>."
    
    — Имя возьми из резюме, название позиции — из вакансии (если не указано явно, выбери по смыслу).
    
    — Найди в резюме раздел "О себе" (или "Summary", "Profile" и т.п.):
    
    • Если он есть — просто вставь его текст без изменений.
    
    • Если раздела нет — составь саммари на 3 предложения, выделяя ключевой опыт и навыки.
    
    — Убедись, что весь результат на том же языке, что и вакансия: русский — всё по-русски, английский — всё по-английски.
    
2. **Соответствие требованиям**
    
    — Определи 5 ключевых требований или задач из вакансии.
    
    — Для каждого подбери краткое и конкретное достижение из резюме, включая метрики, если есть.
    
    — Если прямого соответствия нет — подбери смежный опыт и честно обозначь это как зону роста.
    
    — Вывод напиши в формате:
    
    Почему я хорошо подхожу для <Company X>
    
    <Ключевая задача или требование> → <Соответствующее достижение>
    
    … (5 строк)
    
3. **Мотивация: Почему хочу работать здесь**
    
    — Посмотри, что сказано о компании: миссия, подход, ценности, продукты, культура.
    
    — Напиши искренний абзац (3–4 предложения), как если бы объяснял другу, почему тебе правда интересна эта команда или проект.
    
    — Ссылайся на конкретные ценности, детали или проекты, которые тебя "зажигают".
    
    — Если миссия не указана, опиши, почему задачи или сфера тебя привлекают.
    
4. **Контактный блок**
    
    — Извлеки из резюме: имя, телефон, e-mail, город и (если есть) ссылку на LinkedIn или профиль.
    
    — Выведи отдельным списком в следующем формате (только те поля, которые есть):
    
    Имя:
    
    Телефон:
    
    E-mail:
    
    Город:
    
    LinkedIn:
    
    — В конце добавь одну неформальную строку-CTA, например: "Если потребуется что-то уточнить — всегда на связи!"
    

Общие правила:

— Не добавляй заголовков, подписей или пояснений к частям письма.

— Всё письмо — на языке вакансии.

— Не повторяй одни и те же фразы по частям.

— Сохраняй естественный, уважительный, но живой тон.

— Соблюдай общую длину письма в пределах 220–300 слов."""

    user_message = f"""Текст вакансии:
{job_text}

Резюме:
{cv_text}"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ],
        temperature=0.7,
        max_tokens=1500
    )
    return response.choices[0].message.content.strip()

# Main message handler
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Get text from regular message or forwarded message
    user_message = None
    telegram_id = update.message.from_user.id
    username = update.message.from_user.username
    user = await user_repo.get_or_create_user(telegram_id, username)
    
    # Check if it's a regular text message
    if update.message.text:
        user_message = update.message.text
    # Check if it's a forwarded message with text
    elif update.message.forward_from and update.message.text:
        user_message = update.message.text
    elif update.message.forward_from_chat and update.message.text:
        user_message = update.message.text
    # Check if it's a forwarded message with caption
    elif update.message.caption:
        user_message = update.message.caption
    
    if not user_message:
        await update.message.reply_text("Пожалуйста, отправьте текстовое сообщение или перешлите сообщение с описанием вакансии.")
        return

    chat_id = update.message.chat_id

    # Get current state
    state = context.user_data.get('state', WAITING_FOR_CV)

    # Handle CV submission
    if state == WAITING_FOR_CV:
        # Сохраняем резюме в БД
        await resume_repo.save_resume(telegram_id, user_message)
        context.user_data['state'] = READY_FOR_JOBS
        await update.message.reply_text(
            'Резюме сохранено в базе данных! ✅\n\n'
            'Теперь просто отправляйте мне тексты вакансий или пересылайте сообщения с вакансиями, '
            'и я буду генерировать персонализированные сопроводительные письма.\n\n'
            'Команды:\n'
            '/reset - обновить резюме\n'
            '/show_cv - показать сохраненное резюме'
        )
        return

    # Handle job posting submission
    if state == READY_FOR_JOBS:
        # Check if we're already processing
        if context.user_data.get('processing', False):
            await update.message.reply_text("Уже обрабатываю ваше предыдущее сообщение, пожалуйста подождите.")
            return
        
        # Set processing flag
        context.user_data['processing'] = True

        await update.message.reply_text("Генерирую сопроводительное письмо... Это займет несколько секунд.")

        try:
            # Get saved CV from DB
            cv_text = await resume_repo.get_resume(telegram_id)
            job_text = user_message
            
            if not cv_text:
                await update.message.reply_text('Резюме не найдено. Пожалуйста, загрузите его снова.')
                context.user_data['state'] = WAITING_FOR_CV
                return
            
            # Detect primary language of the job posting
            input_language = detect_primary_language(job_text)
            
            # Generate complete cover letter
            logger.info("Generating complete cover letter...")
            cover_letter = await generate_cover_letter(job_text, cv_text)
            
            # Check language consistency
            letter_language = check_language_consistency(cover_letter)
            
            if letter_language == 'mixed':
                logger.info("Mixed languages detected, unifying...")
                cover_letter = await unify_language(cover_letter, input_language)
            
            # Escape special characters for MarkdownV2
            escaped_letter = escape_markdown_v2(cover_letter)
            
            # Send the complete cover letter in Monospace format
            formatted_message = f"`{escaped_letter}`"
            
            await update.message.reply_text(
                formatted_message,
                parse_mode='MarkdownV2'
            )
            
            await update.message.reply_text(
                "Готово! Отправьте следующую вакансию для нового письма. 🚀"
            )

        except Exception as e:
            logger.error(f"Error generating cover letter: {e}")
            await update.message.reply_text(
                "Произошла ошибка при генерации письма. Пожалуйста, попробуйте еще раз."
            )
        finally:
            # Reset processing flag
            context.user_data['processing'] = False

# Handler for document uploads (PDF/DOCX)
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    document = update.message.document
    if not document:
        await update.message.reply_text("Не удалось получить файл. Пожалуйста, попробуйте еще раз.")
        return

    file_name = document.file_name.lower()
    mime_type = document.mime_type
    file = await context.bot.get_file(document.file_id)
    telegram_id = update.message.from_user.id
    username = update.message.from_user.username
    user = await user_repo.get_or_create_user(telegram_id, username)

    # Download file to a temporary location
    with tempfile.NamedTemporaryFile(delete=True) as tmp:
        await file.download_to_drive(tmp.name)
        try:
            if file_name.endswith('.pdf') or (mime_type and 'pdf' in mime_type):
                # Parse PDF
                reader = PdfReader(tmp.name)
                text = "\n".join(page.extract_text() or '' for page in reader.pages)
            elif file_name.endswith('.docx') or (mime_type and 'word' in mime_type):
                # Parse DOCX
                doc = docx.Document(tmp.name)
                text = "\n".join([para.text for para in doc.paragraphs])
            else:
                await update.message.reply_text("Формат файла не поддерживается. Пожалуйста, отправьте PDF или DOCX.")
                return
        except Exception as e:
            logger.error(f"Ошибка при обработке файла: {e}")
            await update.message.reply_text("Не удалось прочитать файл. Пожалуйста, убедитесь, что файл не поврежден и повторите попытку.")
            return

    # Сохраняем текст резюме в БД и переводим пользователя в режим подачи вакансий
    await resume_repo.save_resume(telegram_id, text)
    context.user_data['state'] = READY_FOR_JOBS
    await update.message.reply_text(
        'Отлично! Я сохранил ваше резюме из файла. ✅\n\n'
        'Теперь просто отправляйте мне тексты вакансий, и я буду генерировать персонализированные сопроводительные письма.\n\n'
        'Команды:\n'
        '/reset - обновить резюме\n'
        '/show_cv - показать сохраненное резюме'
    )

def main() -> None:
    """Start the bot."""
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(CommandHandler("show_cv", show_cv))
    application.add_handler(MessageHandler(filters.Document.PDF | filters.Document.DOCX, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Run the bot
    logger.info("Bot started polling...")
    application.run_polling()

if __name__ == '__main__':
    main() 