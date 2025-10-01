"""
Auto Apply Service
Handles batch vacancy applications with user confirmation
"""
import logging
from typing import List, Dict, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from hh_oauth_client import get_oauth_client
from repositories.repositories import HHOAuthRepository, HHUserResumesRepository, SentVacanciesRepository, ResumeRepository
from datetime import datetime

logger = logging.getLogger(__name__)

# Global repositories (initialized in main)
hh_oauth_repo: HHOAuthRepository = None
hh_resumes_repo: HHUserResumesRepository = None
sent_vacancies_repo: SentVacanciesRepository = None
resume_repo: ResumeRepository = None


class AutoApplyService:
    """Service for handling batch vacancy applications"""

    def __init__(self):
        self.pending_applications = {}  # {telegram_id: {vacancy_data}}

    async def prepare_batch_apply(self, telegram_id: int, vacancies: List[Dict]) -> Dict:
        """
        Prepare batch application for user confirmation

        Args:
            telegram_id: User's telegram ID
            vacancies: List of vacancy dicts from search

        Returns:
            Dict with prepared application data
        """
        # Check authorization
        tokens = await hh_oauth_repo.get_tokens(telegram_id)
        if not tokens or not tokens.get('access_token'):
            return {
                'success': False,
                'error': 'not_authorized',
                'message': 'Вы не авторизованы на HH.ru. Используйте /hh_auth'
            }

        # Check if token is expired
        expires_at = tokens.get('expires_at')
        if expires_at and expires_at < datetime.utcnow():
            return {
                'success': False,
                'error': 'token_expired',
                'message': 'Токен авторизации истек. Используйте /hh_auth'
            }

        # Get default resume
        default_resume = await hh_resumes_repo.get_default_resume(telegram_id)
        if not default_resume:
            return {
                'success': False,
                'error': 'no_resume',
                'message': 'У вас нет резюме на HH.ru. Используйте /hh_resumes'
            }

        # Filter out already sent vacancies
        filtered_vacancies = []
        for vacancy in vacancies:
            vacancy_id = vacancy.get('id')
            already_sent = await sent_vacancies_repo.is_already_sent(telegram_id, vacancy_id)
            if not already_sent:
                filtered_vacancies.append(vacancy)

        if not filtered_vacancies:
            return {
                'success': False,
                'error': 'all_sent',
                'message': 'Вы уже откликались на все найденные вакансии'
            }

        # Store pending applications
        self.pending_applications[telegram_id] = {
            'vacancies': filtered_vacancies,
            'resume_id': default_resume['resume_id'],
            'resume_title': default_resume['resume_title'],
            'access_token': tokens['access_token']
        }

        return {
            'success': True,
            'count': len(filtered_vacancies),
            'resume_title': default_resume['resume_title'],
            'vacancies': filtered_vacancies[:10]  # Show max 10 for preview
        }

    async def apply_to_vacancies(self, telegram_id: int, vacancy_indices: List[int],
                                generate_cover_letter_func) -> Dict:
        """
        Apply to selected vacancies

        Args:
            telegram_id: User's telegram ID
            vacancy_indices: List of vacancy indices to apply to
            generate_cover_letter_func: Function to generate cover letter

        Returns:
            Dict with application results
        """
        if telegram_id not in self.pending_applications:
            return {
                'success': False,
                'error': 'no_pending',
                'message': 'Нет ожидающих откликов. Сначала найдите вакансии.'
            }

        app_data = self.pending_applications[telegram_id]
        vacancies = app_data['vacancies']
        resume_id = app_data['resume_id']
        access_token = app_data['access_token']

        results = {
            'success': 0,
            'failed': 0,
            'errors': []
        }

        oauth_client = get_oauth_client()

        # Get user's CV for cover letter generation
        cv_text = await resume_repo.get_resume(telegram_id)

        for idx in vacancy_indices:
            if idx >= len(vacancies):
                continue

            vacancy = vacancies[idx]
            vacancy_id = vacancy.get('id')
            vacancy_name = vacancy.get('name', 'Unnamed')
            employer_name = vacancy.get('employer', {}).get('name', 'Unknown')

            try:
                # Generate cover letter
                cover_letter = None
                if cv_text and generate_cover_letter_func:
                    try:
                        # Get vacancy description (would need to fetch full vacancy details)
                        # For now, use vacancy snippet
                        vacancy_text = f"{vacancy_name}\n{vacancy.get('snippet', {}).get('requirement', '')}"
                        cover_letter = await generate_cover_letter_func(vacancy_text, cv_text)
                        logger.info(f"Generated cover letter for vacancy {vacancy_id}")
                    except Exception as e:
                        logger.warning(f"Failed to generate cover letter for {vacancy_id}: {e}")
                        cover_letter = None

                # Apply to vacancy
                await oauth_client.apply_to_vacancy(
                    access_token=access_token,
                    vacancy_id=vacancy_id,
                    resume_id=resume_id,
                    message=cover_letter
                )

                # Mark as sent
                await sent_vacancies_repo.mark_as_sent(
                    telegram_id=telegram_id,
                    vacancy_id=vacancy_id,
                    vacancy_name=vacancy_name,
                    employer_name=employer_name,
                    score=vacancy.get('score')
                )

                results['success'] += 1
                logger.info(f"✅ Applied to {vacancy_id}: {vacancy_name}")

            except Exception as e:
                results['failed'] += 1
                error_msg = str(e)
                results['errors'].append({
                    'vacancy_id': vacancy_id,
                    'vacancy_name': vacancy_name,
                    'error': error_msg
                })
                logger.error(f"❌ Failed to apply to {vacancy_id}: {error_msg}")

        # Clear pending applications
        del self.pending_applications[telegram_id]

        return results

    def cancel_pending(self, telegram_id: int):
        """Cancel pending applications"""
        if telegram_id in self.pending_applications:
            del self.pending_applications[telegram_id]


# Global service instance
auto_apply_service = AutoApplyService()


async def show_vacancies_for_apply(update: Update, context: ContextTypes.DEFAULT_TYPE,
                                  vacancies: List[Dict]) -> None:
    """
    Show vacancies with apply buttons

    Args:
        update: Telegram update
        context: Callback context
        vacancies: List of vacancy dicts
    """
    telegram_id = update.message.from_user.id

    # Prepare batch application
    result = await auto_apply_service.prepare_batch_apply(telegram_id, vacancies)

    if not result['success']:
        await update.message.reply_text(f"❌ {result['message']}")
        return

    preview_vacancies = result['vacancies']
    total_count = result['count']
    resume_title = result['resume_title']

    # Create message with vacancy list
    message = f"📋 **Найдено {total_count} новых вакансий**\n\n"
    message += f"Резюме для откликов: {resume_title}\n\n"
    message += "**Топ вакансии:**\n\n"

    for i, vacancy in enumerate(preview_vacancies, 1):
        score = vacancy.get('score', 0)
        name = vacancy.get('name', 'Unnamed')
        employer = vacancy.get('employer', {}).get('name', 'Unknown')
        salary_info = ""

        if vacancy.get('salary'):
            salary = vacancy['salary']
            salary_from = salary.get('from', '')
            salary_to = salary.get('to', '')
            currency = salary.get('currency', 'RUR')
            if salary_from or salary_to:
                salary_info = f"\n   💰 {salary_from or '?'} - {salary_to or '?'} {currency}"

        message += f"{i}. **{name}**\n"
        message += f"   🏢 {employer}\n"
        message += f"   📊 Релевантность: {score:.1%}{salary_info}\n\n"

    if total_count > 10:
        message += f"\n_И еще {total_count - 10} вакансий..._\n"

    # Create inline keyboard
    keyboard = [
        [
            InlineKeyboardButton("✅ Откликнуться на все", callback_data=f"apply_all_{telegram_id}"),
            InlineKeyboardButton("🔝 Только топ-5", callback_data=f"apply_top5_{telegram_id}")
        ],
        [
            InlineKeyboardButton("🔟 Только топ-10", callback_data=f"apply_top10_{telegram_id}"),
            InlineKeyboardButton("❌ Отменить", callback_data=f"apply_cancel_{telegram_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        message,
        reply_markup=reply_markup,
        parse_mode='Markdown',
        disable_web_page_preview=True
    )


async def handle_apply_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle apply button callbacks

    Callback data format: apply_{action}_{telegram_id}
    Actions: all, top5, top10, cancel
    """
    query = update.callback_query
    await query.answer()

    callback_data = query.data
    parts = callback_data.split('_')

    if len(parts) != 3 or parts[0] != 'apply':
        await query.edit_message_text("❌ Некорректная команда")
        return

    action = parts[1]
    telegram_id = int(parts[2])

    # Verify user
    if query.from_user.id != telegram_id:
        await query.answer("❌ Это не ваша операция", show_alert=True)
        return

    if action == 'cancel':
        auto_apply_service.cancel_pending(telegram_id)
        await query.edit_message_text("❌ Отклики отменены")
        return

    # Determine which vacancies to apply to
    if telegram_id not in auto_apply_service.pending_applications:
        await query.edit_message_text("❌ Сессия истекла. Попробуйте найти вакансии снова.")
        return

    app_data = auto_apply_service.pending_applications[telegram_id]
    total_vacancies = len(app_data['vacancies'])

    if action == 'all':
        indices = list(range(total_vacancies))
        count_text = f"все {total_vacancies}"
    elif action == 'top5':
        indices = list(range(min(5, total_vacancies)))
        count_text = "топ-5"
    elif action == 'top10':
        indices = list(range(min(10, total_vacancies)))
        count_text = "топ-10"
    else:
        await query.edit_message_text("❌ Неизвестная команда")
        return

    # Show progress message
    await query.edit_message_text(f"📤 Отправляю отклики на {count_text} вакансий...\nЭто может занять некоторое время.")

    # Import generate_cover_letter from main
    # This is a workaround - ideally should be passed as dependency
    try:
        from main_secure import generate_cover_letter
        generate_func = generate_cover_letter
    except:
        generate_func = None
        logger.warning("Could not import generate_cover_letter")

    # Apply to vacancies
    results = await auto_apply_service.apply_to_vacancies(
        telegram_id,
        indices,
        generate_func
    )

    # Format results message
    success_count = results['success']
    failed_count = results['failed']

    message = f"✅ **Отклики отправлены!**\n\n"
    message += f"✅ Успешно: {success_count}\n"
    if failed_count > 0:
        message += f"❌ Неудачно: {failed_count}\n\n"
        message += "**Ошибки:**\n"
        for error in results['errors'][:5]:  # Show max 5 errors
            message += f"• {error['vacancy_name']}: {error['error'][:50]}\n"

    await query.edit_message_text(message, parse_mode='Markdown')


def get_apply_callback_handler():
    """Get callback query handler for apply buttons"""
    return CallbackQueryHandler(handle_apply_callback, pattern=r'^apply_')
