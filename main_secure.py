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
from hh_client import HHAPIClient, HHVacancySearcher
from resume_analyzer import ResumeAnalyzer
from vacancy_scorer import VacancyScorer
from scheduler import VacancyScheduler

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

# Initialize HH.ru services
hh_client = HHAPIClient()
resume_analyzer = ResumeAnalyzer(client)
vacancy_scorer = VacancyScorer()

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
    await resume_repo.delete_resume(telegram_id)
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

# ===== ТЕСТОВЫЕ КОМАНДЫ (УДАЛИТЬ В ПРОДАКШЕНЕ) =====

async def test_hh_connection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Тестирует подключение к HH.ru API"""
    await update.message.reply_text("🔍 Тестирую подключение к HH.ru...")
    
    try:
        async with HHAPIClient() as client:
            # Простой поиск
            result = await client.search_vacancies({'text': 'python', 'per_page': 5})
            found_count = result.get('found', 0)
            items_count = len(result.get('items', []))
            
            await update.message.reply_text(
                f"✅ HH.ru API работает!\n"
                f"Найдено всего: {found_count} вакансий\n"
                f"Получено: {items_count} в выборке"
            )
    except Exception as e:
        logger.error(f"HH API test failed: {e}")
        await update.message.reply_text(f"❌ Ошибка подключения к HH.ru: {str(e)}")

async def test_resume_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Тестирует анализ резюме пользователя"""
    telegram_id = update.message.from_user.id
    cv_text = await resume_repo.get_resume(telegram_id)
    
    if not cv_text:
        await update.message.reply_text("❌ Сначала загрузите резюме командой /start")
        return
    
    await update.message.reply_text("🧠 Анализирую ваше резюме...")
    
    try:
        profile = await resume_analyzer.analyze_resume(cv_text)
        
        message = "✅ Анализ резюме завершен:\n\n"
        message += f"📋 Должность: {profile.get('exact_position', 'Не определена')}\n"
        message += f"🎯 Уровень: {profile.get('experience_level', 'Не определен')}\n"
        message += f"⚡ Навыки: {', '.join(profile.get('top_skills', [])[:3])}\n"
        message += f"🏢 Домен: {profile.get('domain', 'Не определен')}\n"
        message += f"💰 Зарплата: {profile.get('salary_from', 'Не указана')}\n"
        message += f"📍 Регионы: {profile.get('areas', [])}\n"
        message += f"🔧 Fallback: {'Да' if profile.get('fallback_used') else 'Нет'}"
        
        await update.message.reply_text(message)
        
        # Сохраняем профиль для дальнейших тестов
        context.user_data['test_profile'] = profile
        
    except Exception as e:
        logger.error(f"Resume analysis test failed: {e}")
        await update.message.reply_text(f"❌ Ошибка анализа резюме: {str(e)}")

async def test_vacancy_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Тестирует поиск вакансий"""
    telegram_id = update.message.from_user.id
    cv_text = await resume_repo.get_resume(telegram_id)
    
    if not cv_text:
        await update.message.reply_text("❌ Сначала загрузите резюме")
        return
    
    await update.message.reply_text("🔍 Ищу вакансии для вас...")
    
    try:
        # Анализируем резюме
        profile = await resume_analyzer.analyze_resume(cv_text)
        
        # Ищем вакансии
        async with HHAPIClient() as client:
            searcher = HHVacancySearcher(client)
            vacancies = await searcher.search_with_fallback(profile)
            
            # Скорим найденные вакансии
            scored_vacancies = vacancy_scorer.score_and_rank_vacancies(vacancies, profile)
            
            if not scored_vacancies:
                await update.message.reply_text("❌ Вакансии не найдены")
                return
            
            # Показываем топ-5
            message = f"✅ Найдено {len(scored_vacancies)} вакансий. Топ-5:\n\n"
            
            for i, vacancy in enumerate(scored_vacancies[:5], 1):
                score = vacancy.get('score', 0)
                salary_info = ""
                if vacancy.get('salary'):
                    salary = vacancy['salary']
                    salary_info = f" | 💰 {salary.get('from', 'от ?')} - {salary.get('to', 'до ?')} {salary.get('currency', 'RUR')}"
                
                message += f"{i}. **{vacancy['name']}**\n"
                message += f"   🏢 {vacancy['employer']['name']}\n"
                message += f"   📊 Score: {score:.3f}{salary_info}\n"
                message += f"   🔗 {vacancy.get('alternate_url', 'Ссылка недоступна')}\n\n"
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Vacancy search test failed: {e}")
        await update.message.reply_text(f"❌ Ошибка поиска вакансий: {str(e)}")

async def show_debug_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает детальный анализ профиля"""
    telegram_id = update.message.from_user.id
    cv_text = await resume_repo.get_resume(telegram_id)
    
    if not cv_text:
        await update.message.reply_text("❌ Сначала загрузите резюме")
        return
    
    try:
        profile = await resume_analyzer.analyze_resume(cv_text)
        
        # Форматируем JSON для читаемости
        import json
        profile_json = json.dumps(profile, ensure_ascii=False, indent=2)
        
        # Отправляем по частям если слишком длинно
        if len(profile_json) > 4000:
            await update.message.reply_text("📋 Полный профиль (часть 1):")
            await update.message.reply_text(f"```json\n{profile_json[:4000]}\n```", parse_mode='Markdown')
            await update.message.reply_text("📋 Полный профиль (часть 2):")
            await update.message.reply_text(f"```json\n{profile_json[4000:]}\n```", parse_mode='Markdown')
        else:
            await update.message.reply_text("📋 Полный анализ профиля:")
            await update.message.reply_text(f"```json\n{profile_json}\n```", parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Debug profile failed: {e}")
        await update.message.reply_text(f"❌ Ошибка отладки профиля: {str(e)}")

async def show_vacancy_scores(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает детальные скоры последних найденных вакансий"""
    telegram_id = update.message.from_user.id
    cv_text = await resume_repo.get_resume(telegram_id)
    
    if not cv_text:
        await update.message.reply_text("❌ Сначала загрузите резюме")
        return
        
    await update.message.reply_text("📊 Вычисляю детальные скоры...")
    
    try:
        profile = await resume_analyzer.analyze_resume(cv_text)
        
        async with HHAPIClient() as client:
            searcher = HHVacancySearcher(client)
            vacancies = await searcher.search_with_fallback(profile)
            
            if not vacancies:
                await update.message.reply_text("❌ Вакансии не найдены")
                return
            
            # Берем топ-3 для детального анализа
            top_vacancies = vacancies[:3]
            
            message = "📊 Детальный скоринг топ-3 вакансий:\n\n"
            
            for i, vacancy in enumerate(top_vacancies, 1):
                score = vacancy_scorer.score_vacancy(vacancy, profile)
                
                message += f"{i}. **{vacancy['name'][:50]}...**\n"
                message += f"   🏢 {vacancy['employer']['name']}\n"
                message += f"   📊 Общий скор: {score:.3f}\n"
                
                # Здесь можно добавить детализацию скоров по компонентам
                # Для простоты показываем только общий скор
                message += "\n"
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Vacancy scores test failed: {e}")
        await update.message.reply_text(f"❌ Ошибка анализа скоров: {str(e)}")

# ===== КОНЕЦ ТЕСТОВЫХ КОМАНД =====

def main() -> None:
    """Start the bot."""
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(CommandHandler("show_cv", show_cv))
    
    # ТЕСТОВЫЕ КОМАНДЫ (удалить в продакшене)
    application.add_handler(CommandHandler("test_hh", test_hh_connection))
    application.add_handler(CommandHandler("test_resume", test_resume_analysis))
    application.add_handler(CommandHandler("test_search", test_vacancy_search))
    application.add_handler(CommandHandler("debug_profile", show_debug_profile))
    application.add_handler(CommandHandler("show_scores", show_vacancy_scores))
    
    # Команда для полного тестирования цикла
    async def test_full_cycle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Тестирует полный цикл: анализ резюме -> поиск -> скоринг -> топ-10"""
        telegram_id = update.message.from_user.id
        cv_text = await resume_repo.get_resume(telegram_id)
        
        if not cv_text:
            await update.message.reply_text("❌ Сначала загрузите резюме")
            return
        
        await update.message.reply_text("🔄 Запускаю полный цикл тестирования...")
        
        try:
            # Шаг 1: Анализ резюме
            profile = await resume_analyzer.analyze_resume(cv_text)
            await update.message.reply_text(f"✅ Шаг 1: Резюме проанализировано\n📋 Должность: {profile.get('exact_position')}\n💰 Зарплата: {profile.get('salary_from', 'Не указана')} RUR/месяц")
            
            # Шаг 2: Поиск вакансий
            async with HHAPIClient() as client:
                searcher = HHVacancySearcher(client)
                all_vacancies = await searcher.search_with_fallback(profile)
            
            await update.message.reply_text(f"✅ Шаг 2: Найдено {len(all_vacancies)} вакансий")
            
            # Шаг 3: Скоринг и фильтрация
            scored_vacancies = vacancy_scorer.score_and_rank_vacancies(all_vacancies, profile)
            
            await update.message.reply_text(f"✅ Шаг 3: После фильтрации релевантности: {len(scored_vacancies)} вакансий")
            
            # Шаг 4: Топ-10 для отправки
            top_vacancies = scored_vacancies[:10]
            
            if top_vacancies:
                message = f"✅ Шаг 4: Топ-{len(top_vacancies)} вакансий для отправки:\n\n"
                
                for i, vacancy in enumerate(top_vacancies, 1):
                    score = vacancy.get('score', 0)
                    message += f"{i}. **{vacancy['name'][:40]}...**\n"
                    message += f"   🏢 {vacancy['employer']['name']}\n"
                    message += f"   📊 Релевантность: {score:.1%}\n\n"
                
                await update.message.reply_text(message, parse_mode='Markdown')
            else:
                await update.message.reply_text("❌ Релевантных вакансий не найдено")
            
        except Exception as e:
            logger.error(f"Full cycle test failed: {e}")
            await update.message.reply_text(f"❌ Ошибка полного цикла: {str(e)}")
    
    application.add_handler(CommandHandler("test_full", test_full_cycle))
    
    application.add_handler(MessageHandler(filters.Document.PDF | filters.Document.DOCX, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Запуск бота с интегрированным планировщиком
    logger.info("Bot started polling...")
    
    # ВРЕМЕННО: простая команда для ручного запуска планировщика
    async def start_daily_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Тестовая команда для запуска ежедневного поиска вручную"""
        # ВРЕМЕННО: команда доступна всем для тестирования
        # if update.message.from_user.id not in [your_telegram_id]:  # Замените на ваш ID
        #     await update.message.reply_text("❌ Команда доступна только администратору")
        #     return
            
        await update.message.reply_text("🔄 Запускаю ежедневный поиск вакансий...")
        
        try:
            scheduler = VacancyScheduler(application.bot, client, supabase)
            await scheduler.run_daily_search()
            await update.message.reply_text("✅ Ежедневный поиск завершен")
        except Exception as e:
            logger.error(f"Daily search failed: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    
    # Добавляем команду для тестирования
    application.add_handler(CommandHandler("daily_search", start_daily_search))
    
    # Тестовая команда для отображения SQL схемы
    async def show_sql_schema(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показывает SQL схему для создания таблицы sent_vacancies"""
        sql_schema = """
-- SQL схема для Supabase (выполните в SQL Editor)
CREATE TABLE IF NOT EXISTS sent_vacancies (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL,
    vacancy_id VARCHAR(50) NOT NULL,
    vacancy_name TEXT,
    employer_name TEXT,
    score DECIMAL(5,3),
    sent_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(telegram_id, vacancy_id)
);

CREATE INDEX IF NOT EXISTS idx_sent_vacancies_telegram_id ON sent_vacancies(telegram_id);
CREATE INDEX IF NOT EXISTS idx_sent_vacancies_sent_at ON sent_vacancies(sent_at);
        """
        
        await update.message.reply_text(f"📋 SQL схема для Supabase:\n\n```sql{sql_schema}\n```", parse_mode='Markdown')
    
    application.add_handler(CommandHandler("sql_schema", show_sql_schema))
    
    application.run_polling()

if __name__ == '__main__':
    main() 