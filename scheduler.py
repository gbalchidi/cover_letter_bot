"""
Модуль для ежедневного поиска и отправки вакансий пользователям
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict
import json

from hh_client import HHAPIClient, HHVacancySearcher
from resume_analyzer import ResumeAnalyzer
from vacancy_scorer import VacancyScorer
from repositories.supabase_client import SupabaseClient
from repositories.repositories import UserRepository, ResumeRepository

logger = logging.getLogger(__name__)


class VacancyScheduler:
    """Планировщик ежедневного поиска вакансий"""
    
    def __init__(self, bot, openai_client, supabase_client):
        self.bot = bot
        self.openai_client = openai_client
        self.supabase = supabase_client
        
        # Инициализация компонентов
        self.user_repo = UserRepository(supabase_client)
        self.resume_repo = ResumeRepository(supabase_client)
        self.resume_analyzer = ResumeAnalyzer(openai_client)
        self.vacancy_scorer = VacancyScorer()
        
        # Таблица для хранения отправленных вакансий
        self.sent_vacancies_table = "sent_vacancies"
        
    async def run_daily_search(self):
        """Основная функция ежедневного поиска"""
        logger.info("Starting daily vacancy search...")
        
        try:
            # Получаем всех активных пользователей
            active_users = await self._get_active_users()
            logger.info(f"Found {len(active_users)} active users")
            
            # Обрабатываем каждого пользователя
            for user in active_users:
                try:
                    await self._process_user(user)
                    # Небольшая пауза между пользователями
                    await asyncio.sleep(2)
                except Exception as e:
                    logger.error(f"Error processing user {user.get('telegram_id')}: {e}")
                    
        except Exception as e:
            logger.error(f"Daily search failed: {e}")
            
        logger.info("Daily vacancy search completed")
    
    async def _get_active_users(self) -> List[Dict]:
        """Получает список активных пользователей с резюме"""
        try:
            # Запрос пользователей, у которых есть резюме
            response = self.supabase.table("resumes").select("telegram_id").execute()
            
            if response.data:
                return [{"telegram_id": row["telegram_id"]} for row in response.data]
            return []
            
        except Exception as e:
            logger.error(f"Failed to get active users: {e}")
            return []
    
    async def _process_user(self, user: Dict):
        """Обрабатывает одного пользователя"""
        telegram_id = user["telegram_id"]
        logger.info(f"Processing user {telegram_id}")
        
        try:
            # Получаем резюме пользователя
            cv_text = await self.resume_repo.get_resume(telegram_id)
            if not cv_text:
                logger.warning(f"No resume found for user {telegram_id}")
                return
            
            # Анализируем резюме
            user_profile = await self.resume_analyzer.analyze_resume(cv_text)
            
            # Ищем вакансии
            daily_vacancies = await self._find_daily_vacancies(user_profile, telegram_id)
            
            if daily_vacancies:
                # Отправляем пользователю
                await self._send_vacancies_to_user(telegram_id, daily_vacancies)
                
                # Сохраняем информацию об отправленных вакансиях
                await self._save_sent_vacancies(telegram_id, daily_vacancies)
                
                logger.info(f"Sent {len(daily_vacancies)} vacancies to user {telegram_id}")
            else:
                logger.info(f"No new vacancies found for user {telegram_id}")
                
        except Exception as e:
            logger.error(f"Error processing user {telegram_id}: {e}")
    
    async def _find_daily_vacancies(self, user_profile: Dict, telegram_id: int) -> List[Dict]:
        """Ищет новые вакансии для пользователя"""
        
        try:
            # Получаем список уже отправленных вакансий за последние 7 дней
            sent_vacancy_ids = await self._get_sent_vacancy_ids(telegram_id, days=7)
            
            # Ищем вакансии через HH.ru API
            async with HHAPIClient() as hh_client:
                searcher = HHVacancySearcher(hh_client)
                all_vacancies = await searcher.search_with_fallback(user_profile)
            
            # Фильтруем уже отправленные
            new_vacancies = [
                v for v in all_vacancies 
                if v['id'] not in sent_vacancy_ids
            ]
            
            if not new_vacancies:
                logger.info(f"No new vacancies for user {telegram_id}")
                return []
            
            # Скорим и ранжируем
            scored_vacancies = self.vacancy_scorer.score_and_rank_vacancies(
                new_vacancies, user_profile
            )
            
            # Возвращаем топ-10
            return scored_vacancies[:10]
            
        except Exception as e:
            logger.error(f"Error finding vacancies for user {telegram_id}: {e}")
            return []
    
    async def _get_sent_vacancy_ids(self, telegram_id: int, days: int = 7) -> set:
        """Получает ID вакансий, отправленных пользователю за последние N дней"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            response = self.supabase.table(self.sent_vacancies_table).select("vacancy_id").eq(
                "telegram_id", telegram_id
            ).gte("sent_at", cutoff_date.isoformat()).execute()
            
            if response.data:
                return {row["vacancy_id"] for row in response.data}
            return set()
            
        except Exception as e:
            logger.error(f"Error getting sent vacancy IDs: {e}")
            return set()
    
    async def _send_vacancies_to_user(self, telegram_id: int, vacancies: List[Dict]):
        """Отправляет вакансии пользователю в Telegram"""
        try:
            # Формируем сообщение
            message = "🎯 **Ваши вакансии на сегодня:**\n\n"
            
            for i, vacancy in enumerate(vacancies, 1):
                score = vacancy.get('score', 0)
                
                # Информация о зарплате
                salary_info = ""
                if vacancy.get('salary'):
                    salary = vacancy['salary']
                    salary_from = salary.get('from', '')
                    salary_to = salary.get('to', '')
                    currency = salary.get('currency', 'RUR')
                    
                    if salary_from and salary_to:
                        salary_info = f"💰 {salary_from} - {salary_to} {currency}"
                    elif salary_from:
                        salary_info = f"💰 от {salary_from} {currency}"
                    elif salary_to:
                        salary_info = f"💰 до {salary_to} {currency}"
                
                message += f"{i}. **{vacancy['name']}**\n"
                message += f"🏢 {vacancy['employer']['name']}\n"
                
                if salary_info:
                    message += f"{salary_info}\n"
                
                message += f"📍 {vacancy.get('area', {}).get('name', 'Не указано')}\n"
                message += f"📊 Релевантность: {score:.1%}\n"
                message += f"🔗 [Подробнее]({vacancy.get('alternate_url', '')})\n\n"
            
            message += "Удачи в поиске работы! 🚀"
            
            # Отправляем сообщение
            await self.bot.send_message(
                chat_id=telegram_id,
                text=message,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            
        except Exception as e:
            logger.error(f"Error sending message to user {telegram_id}: {e}")
    
    async def _save_sent_vacancies(self, telegram_id: int, vacancies: List[Dict]):
        """Сохраняет информацию об отправленных вакансиях"""
        try:
            current_time = datetime.now().isoformat()
            
            records = []
            for vacancy in vacancies:
                records.append({
                    "telegram_id": telegram_id,
                    "vacancy_id": vacancy['id'],
                    "vacancy_name": vacancy['name'],
                    "employer_name": vacancy['employer']['name'],
                    "score": vacancy.get('score', 0),
                    "sent_at": current_time
                })
            
            # Вставляем записи в базу данных
            response = self.supabase.table(self.sent_vacancies_table).insert(records).execute()
            
            if not response.data:
                logger.warning(f"Failed to save sent vacancies for user {telegram_id}")
                
        except Exception as e:
            logger.error(f"Error saving sent vacancies for user {telegram_id}: {e}")


# Функция для создания таблицы sent_vacancies (если не существует)
async def create_sent_vacancies_table(supabase_client):
    """Создает таблицу для хранения отправленных вакансий"""
    try:
        # Примерная схема таблицы (нужно создать в Supabase UI или через SQL)
        sql_schema = """
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
        
        logger.info("Schema for sent_vacancies table:")
        logger.info(sql_schema)
        
        # В реальном проекте нужно выполнить этот SQL в Supabase
        
    except Exception as e:
        logger.error(f"Error creating table schema: {e}")


# Основная функция для запуска планировщика
async def run_scheduler(bot, openai_client, supabase_client):
    """Запускает планировщик с интервалом в 24 часа"""
    scheduler = VacancyScheduler(bot, openai_client, supabase_client)
    
    # Создаем таблицу если нужно
    await create_sent_vacancies_table(supabase_client)
    
    while True:
        try:
            # Запускаем ежедневный поиск
            await scheduler.run_daily_search()
            
            # Ждем 24 часа до следующего запуска
            logger.info("Waiting 24 hours until next search...")
            await asyncio.sleep(24 * 60 * 60)  # 24 часа
            
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
            # Ждем час и пробуем снова
            await asyncio.sleep(60 * 60)


# Тестовая функция
async def test_scheduler(bot, openai_client, supabase_client, test_user_id: int):
    """Тестирует планировщик для одного пользователя"""
    scheduler = VacancyScheduler(bot, openai_client, supabase_client)
    
    try:
        # Обрабатываем тестового пользователя
        await scheduler._process_user({"telegram_id": test_user_id})
        logger.info("Test completed successfully")
        
    except Exception as e:
        logger.error(f"Test failed: {e}")


if __name__ == "__main__":
    # Пример использования
    import os
    from openai import OpenAI
    from repositories.supabase_client import SupabaseClient
    
    logging.basicConfig(level=logging.INFO)
    
    # Примерная конфигурация
    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    supabase_client = SupabaseClient(
        os.getenv("SUPABASE_URL"), 
        os.getenv("SUPABASE_KEY")
    )
    
    # Для тестирования без бота
    class MockBot:
        async def send_message(self, chat_id, text, parse_mode=None, disable_web_page_preview=None):
            print(f"Message to {chat_id}: {text}")
    
    mock_bot = MockBot()
    
    # Запуск теста
    # asyncio.run(test_scheduler(mock_bot, openai_client, supabase_client, 123456789))