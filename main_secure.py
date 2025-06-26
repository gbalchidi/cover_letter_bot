import logging
import os
import re
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from openai import OpenAI
import nest_asyncio
import tempfile
from telegram.constants import DocumentMimeType
from PyPDF2 import PdfReader
import docx

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
    # Check if user already has a CV saved
    if context.user_data.get('cv'):
        await update.message.reply_text(
            'У меня уже есть ваше резюме! 📄\n\n'
            'Просто отправьте мне текст вакансии, и я сгенерирую сопроводительное письмо.\n\n'
            'Команды:\n'
            '/reset - обновить резюме\n'
            '/show_cv - показать сохраненное резюме'
        )
        context.user_data['state'] = READY_FOR_JOBS
    else:
        await update.message.reply_text(
            'Привет! Я помогу создавать сопроводительные письма. 👋\n\n'
            'Для начала отправьте мне ваше резюме, и я сохраню его. '
            'После этого вы сможете присылать любые вакансии, а я буду генерировать для них персонализированные сопроводительные письма.'
        )
        context.user_data['state'] = WAITING_FOR_CV

# Function to reset CV
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data['cv'] = None
    context.user_data['state'] = WAITING_FOR_CV
    await update.message.reply_text(
        'Резюме удалено. Отправьте мне новое резюме для сохранения.'
    )

# Function to show saved CV
async def show_cv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get('cv'):
        cv_preview = context.user_data['cv'][:500] + "..." if len(context.user_data['cv']) > 500 else context.user_data['cv']
        escaped_cv = escape_markdown_v2(cv_preview)
        await update.message.reply_text(
            f"Ваше сохраненное резюме (первые 500 символов):\n\n`{escaped_cv}`",
            parse_mode='MarkdownV2'
        )
    else:
        await update.message.reply_text(
            'У вас пока нет сохраненного резюме. Отправьте его мне!'
        )

# Part 1: About Me section
async def generate_about_me(job_text, cv_text):
    """Generate the 'About Me' section of the cover letter."""
    prompt = f"""Я хочу, чтобы ты помог мне составить часть сопроводительного письма "О себе" (заголовок добавлять не нужно). Когда я предоставляю резюме и текст вакансии, сделай следующее:

Начни письмо с приветствия: "Здравствуйте, меня зовут <Имя>, увидел, что вы в поиске <Название позиции>." Используй имя из резюме и название позиции из вакансии (если в вакансии явно не указано название позиции, выбери его по смыслу). Имя и позицию не переводить.
Найди в резюме блок "О себе" (summary, profile или аналогичный). Если такой блок есть — просто скопируй этот текст БЕЗ КАКИХ-ЛИБО изменений, дополнений или творческой обработки. Включить разрешается только прямой перевод этого блока на язык вакансии, если языки различаются.
Если блока "О себе" в резюме нет, саммари сгенерируй из всего резюме на 3 предложения, выделяя опыт и ключевые навыки.
Весь результат должен быть на языке, на котором написана вакансия: если вакансия на русском — всё на русском, если на английском — на английском.

Не добавляй никаких других секций, пояснений, подписей, выводов, ключевых навыков, дополнительного текста, перефразирований или аннотаций, кроме приветствия и блока "О себе". Если блок "О себе" есть, просто вставь его, либо переведи для единого языка, но не дописывай ничего от себя.

Текст вакансии:
{job_text}

Резюме:
{cv_text}"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=500
    )
    return response.choices[0].message.content.strip()

# Part 2: Why am I a good fit?
async def generate_good_fit(job_text, cv_text):
    """Generate the 'Why am I a good fit' section."""
    prompt = f"""Я хочу, чтобы ты выступил в роли эксперта карьерного консультирования и автора сопроводительных писем. 

ВАЖНО: Ты анализируешь ВАКАНСИЮ, а НЕ резюме. Название компании для которой пишется письмо нужно брать ТОЛЬКО из вакансии. В резюме указаны прошлые места работы - они НЕ являются целевой компанией!

Когда я предоставляю тебе текст вакансии и своё резюме:
1. Найди в ВАКАНСИИ название компании (обычно в начале текста вакансии, например "Мы Place.01...")
2. Проанализируй описание позиции из ВАКАНСИИ и выдели пять самых важных требований
3. Для каждого требования подбери релевантное достижение из резюме

Финальный вывод должен содержать только следующее:
Почему я хорошо подхожу для <company X>
Требование/задача → Моё достижение
Требование/задача → Моё достижение
Требование/задача → Моё достижение
Требование/задача → Моё достижение
Требование/задача → Моё достижение

Где <company X> — название компании ИЗ ВАКАНСИИ (НЕ из резюме!), без перевода и изменений.
В выводе не должно быть слова "Требование", нумерации, скобок или вспомогательных слов перед/после пар. Только заголовок и 5 пар строк в указанном формате, по одному на каждой строке.

Если вакансия на русском — пиши на русском, если на английском — на английском.

Текст вакансии:
{job_text}

Резюме:
{cv_text}"""

    response = client.chat.completions.create(
        model="gpt-4-turbo",  # or "gpt-4o" for better performance
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=700
    )
    return response.choices[0].message.content.strip()

# Part 3: Why do I want to work at this company?
async def generate_why_company(job_text, cv_text):
    """Generate the 'Why I want to work at this company' section."""
    prompt = f"""Я хочу, чтобы ты помог мне написать часть сопроводительного письма "Почему я хочу работать в этой компании?" (заголовок добавлять не нужно). 

ВАЖНО: Компания, для которой пишется письмо, указана в ВАКАНСИИ, а НЕ в резюме. В резюме указаны прошлые места работы кандидата.

Когда я даю тебе текст вакансии и своё резюме, действуй так:
1. Найди в ВАКАНСИИ название компании и её описание (обычно в начале, например "Мы Place.01...")
2. Посмотри на описание ЭТОЙ компании из ВАКАНСИИ: чем она занимается, какие ценности или миссию озвучивает
3. Взгляни на резюме, чтобы понять опыт кандидата
4. Составь короткий абзац (3-4 предложения) о том, почему кандидату интересна именно КОМПАНИЯ ИЗ ВАКАНСИИ

Используй простые искренние формулировки. Обязательно опирайся на конкретные факты о компании ИЗ ВАКАНСИИ.

Если вакансия на русском — весь текст на русском; если на английском — на английском.
Не добавляй никаких подписей, заголовков, пояснений, только сам "личный" абзац.

Текст вакансии:
{job_text}

Резюме:
{cv_text}"""

    response = client.chat.completions.create(
        model="gpt-4-turbo",  # or "gpt-4o"
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=400
    )
    return response.choices[0].message.content.strip()

# Part 4: Contacts
async def generate_contacts(job_text, cv_text):
    """Generate the contacts section."""
    prompt = f"""Я хочу, чтобы ты помог мне составить финальный блок сопроводительного письма — контакты. Когда я даю тебе своё резюме, выполни следующее:

Извлеки все контактные данные из резюме: имя, телефон, e-mail, город и (если есть) ссылку на LinkedIn или другой профессиональный профиль.
Размести эти контакты простым отдельным списком: Имя: Телефон: E-mail: Город: LinkedIn: (Указывай только те поля, которые действительно есть в резюме.)
В конце добавь одну ненавязчивую, дружелюбную строку-CTA ("Буду рад(а) ответить на ваши вопросы", "Если потребуется что-то уточнить — всегда на связи", "Готов(а) обсудить детали — пишите!" и т.п., неофициально и без формальностей).
Ответ пиши на языке вакансии: если вакансия на русском — всё на русском; если на английском — на английском.

Не добавляй никаких заголовков, вступлений, подписей, только список контактов и ненавязчивый CTA.

Текст вакансии:
{job_text}

Резюме:
{cv_text}"""

    response = client.chat.completions.create(
        model="gpt-4-turbo",  # or "gpt-4o"
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=300
    )
    return response.choices[0].message.content.strip()

# Main message handler
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_message = update.message.text
    chat_id = update.message.chat_id

    if not user_message:
        await update.message.reply_text("Пожалуйста, отправьте текстовое сообщение.")
        return

    # Get current state
    state = context.user_data.get('state', WAITING_FOR_CV)

    # Handle CV submission
    if state == WAITING_FOR_CV:
        # Save CV
        context.user_data['cv'] = user_message
        context.user_data['state'] = READY_FOR_JOBS
        
        await update.message.reply_text(
            'Отлично! Я сохранил ваше резюме. ✅\n\n'
            'Теперь просто отправляйте мне тексты вакансий, '
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
            # Get saved CV
            cv_text = context.user_data['cv']
            job_text = user_message
            
            # Detect primary language of the job posting
            input_language = detect_primary_language(job_text)
            
            # Generate all parts
            logger.info("Generating About Me section...")
            about_me = await generate_about_me(job_text, cv_text)
            
            logger.info("Generating Good Fit section...")
            good_fit = await generate_good_fit(job_text, cv_text)
            
            logger.info("Generating Why Company section...")
            why_company = await generate_why_company(job_text, cv_text)
            
            logger.info("Generating Contacts section...")
            contacts = await generate_contacts(job_text, cv_text)
            
            # Combine all parts
            cover_letter = f"""{about_me}

{good_fit}

{why_company}

{contacts}"""

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

    # Сохраняем текст резюме и переводим пользователя в режим подачи вакансий
    context.user_data['cv'] = text
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