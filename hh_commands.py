"""
Telegram commands for HH.ru integration
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import logging
from hh_oauth_client import get_oauth_client
from repositories.repositories import HHOAuthRepository, HHUserResumesRepository, SentVacanciesRepository
from datetime import datetime

logger = logging.getLogger(__name__)

# Global repositories (will be initialized in main)
hh_oauth_repo: HHOAuthRepository = None
hh_resumes_repo: HHUserResumesRepository = None
sent_vacancies_repo: SentVacanciesRepository = None


async def hh_auth_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /hh_auth - Start HH.ru OAuth authorization
    """
    telegram_id = update.message.from_user.id

    try:
        # Check if already authorized
        tokens = await hh_oauth_repo.get_tokens(telegram_id)
        if tokens and tokens.get('expires_at') and tokens['expires_at'] > datetime.utcnow():
            await update.message.reply_text(
                "✅ Вы уже авторизованы на HH.ru!\n\n"
                "Используйте:\n"
                "/hh_status - проверить статус\n"
                "/hh_resumes - посмотреть резюме\n"
                "/hh_logout - выйти"
            )
            return

        # Generate authorization URL
        oauth_client = get_oauth_client()
        auth_url = oauth_client.get_authorization_url(state=str(telegram_id))

        # Create inline keyboard with auth button
        keyboard = [[InlineKeyboardButton("🔐 Авторизоваться на HH.ru", url=auth_url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "🔑 **Авторизация на HH.ru**\n\n"
            "Для автоматических откликов на вакансии необходимо подключить ваш аккаунт HH.ru.\n\n"
            "**Что произойдет:**\n"
            "1. Вы перейдете на сайт HH.ru\n"
            "2. Авторизуетесь (если еще не авторизованы)\n"
            "3. Разрешите доступ к вашему профилю\n"
            "4. Вернетесь обратно в бота\n\n"
            "Нажмите кнопку ниже, чтобы начать:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"Error in hh_auth_command: {e}")
        await update.message.reply_text(
            "❌ Ошибка при запуске авторизации. Попробуйте позже."
        )


async def hh_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /hh_status - Check HH.ru authorization status
    """
    telegram_id = update.message.from_user.id

    try:
        tokens = await hh_oauth_repo.get_tokens(telegram_id)

        if not tokens:
            await update.message.reply_text(
                "❌ Вы не авторизованы на HH.ru\n\n"
                "Используйте /hh_auth для авторизации"
            )
            return

        # Check if token is expired
        expires_at = tokens.get('expires_at')
        is_expired = expires_at and expires_at < datetime.utcnow()

        # Get resumes count
        resumes = await hh_resumes_repo.get_resumes(telegram_id)
        resumes_count = len(resumes)

        # Get sent vacancies count
        sent_vacancies = await sent_vacancies_repo.get_sent_vacancies(telegram_id, limit=1000)
        sent_count = len(sent_vacancies)

        status_emoji = "✅" if not is_expired else "⚠️"
        status_text = "Активна" if not is_expired else "Истекла"

        message = f"{status_emoji} **Статус авторизации HH.ru**\n\n"
        message += f"Авторизация: {status_text}\n"
        if expires_at:
            message += f"Действительна до: {expires_at.strftime('%d.%m.%Y %H:%M')}\n"
        message += f"\n📄 Резюме на HH.ru: {resumes_count}\n"
        message += f"📨 Отправлено откликов: {sent_count}\n"

        if is_expired:
            message += "\n⚠️ Токен истек. Используйте /hh_auth для повторной авторизации"

        await update.message.reply_text(message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error in hh_status_command: {e}")
        await update.message.reply_text(
            "❌ Ошибка при проверке статуса"
        )


async def hh_resumes_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /hh_resumes - List user's HH.ru resumes
    """
    telegram_id = update.message.from_user.id

    try:
        # Check authorization
        tokens = await hh_oauth_repo.get_tokens(telegram_id)
        if not tokens:
            await update.message.reply_text(
                "❌ Вы не авторизованы на HH.ru\n\n"
                "Используйте /hh_auth для авторизации"
            )
            return

        # Get resumes
        resumes = await hh_resumes_repo.get_resumes(telegram_id)

        if not resumes:
            await update.message.reply_text(
                "❌ У вас нет резюме на HH.ru\n\n"
                "Создайте резюме на сайте hh.ru, затем используйте /hh_auth для обновления"
            )
            return

        message = "📄 **Ваши резюме на HH.ru:**\n\n"

        for i, resume in enumerate(resumes, 1):
            default_mark = " ⭐" if resume.get('is_default') else ""
            message += f"{i}. {resume.get('resume_title', 'Резюме')}{default_mark}\n"
            message += f"   ID: `{resume.get('resume_id')}`\n\n"

        message += "\n⭐ - резюме используется по умолчанию для откликов"

        await update.message.reply_text(message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error in hh_resumes_command: {e}")
        await update.message.reply_text(
            "❌ Ошибка при получении списка резюме"
        )


async def hh_logout_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /hh_logout - Logout from HH.ru (delete tokens)
    """
    telegram_id = update.message.from_user.id

    try:
        await hh_oauth_repo.delete_tokens(telegram_id)
        await update.message.reply_text(
            "✅ Вы вышли из аккаунта HH.ru\n\n"
            "Используйте /hh_auth для повторной авторизации"
        )

    except Exception as e:
        logger.error(f"Error in hh_logout_command: {e}")
        await update.message.reply_text(
            "❌ Ошибка при выходе из аккаунта"
        )


async def hh_apply_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /hh_apply - Manually apply to a vacancy
    Usage: /hh_apply <vacancy_id>
    """
    telegram_id = update.message.from_user.id

    try:
        # Check if vacancy ID is provided
        if not context.args or len(context.args) == 0:
            await update.message.reply_text(
                "❌ Укажите ID вакансии\n\n"
                "Использование: /hh_apply <vacancy_id>\n"
                "Например: /hh_apply 12345678"
            )
            return

        vacancy_id = context.args[0]

        # Check authorization
        tokens = await hh_oauth_repo.get_tokens(telegram_id)
        if not tokens or not tokens.get('access_token'):
            await update.message.reply_text(
                "❌ Вы не авторизованы на HH.ru\n\n"
                "Используйте /hh_auth для авторизации"
            )
            return

        # Check if token is expired
        expires_at = tokens.get('expires_at')
        if expires_at and expires_at < datetime.utcnow():
            await update.message.reply_text(
                "⚠️ Токен авторизации истек\n\n"
                "Используйте /hh_auth для повторной авторизации"
            )
            return

        # Get default resume
        default_resume = await hh_resumes_repo.get_default_resume(telegram_id)
        if not default_resume:
            await update.message.reply_text(
                "❌ У вас нет резюме на HH.ru\n\n"
                "Используйте /hh_resumes для просмотра резюме"
            )
            return

        # Check if already applied
        already_sent = await sent_vacancies_repo.is_already_sent(telegram_id, vacancy_id)
        if already_sent:
            await update.message.reply_text(
                "⚠️ Вы уже откликались на эту вакансию"
            )
            return

        await update.message.reply_text("📤 Отправляю отклик...")

        # Apply to vacancy
        oauth_client = get_oauth_client()
        # TODO: Generate cover letter from saved CV
        result = await oauth_client.apply_to_vacancy(
            access_token=tokens['access_token'],
            vacancy_id=vacancy_id,
            resume_id=default_resume['resume_id'],
            message="Здравствуйте! Заинтересован в данной позиции."
        )

        # Mark as sent
        await sent_vacancies_repo.mark_as_sent(
            telegram_id=telegram_id,
            vacancy_id=vacancy_id,
            vacancy_name="Manual application"
        )

        await update.message.reply_text(
            "✅ Отклик успешно отправлен!\n\n"
            f"Вакансия: {vacancy_id}\n"
            f"Резюме: {default_resume['resume_title']}"
        )

    except Exception as e:
        logger.error(f"Error in hh_apply_command: {e}")
        await update.message.reply_text(
            f"❌ Ошибка при отправке отклика: {str(e)}"
        )
