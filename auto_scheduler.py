"""
Автоматический планировщик для ежедневной отправки вакансий
"""
import asyncio
import logging
from datetime import datetime, time
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from scheduler import VacancyScheduler

logger = logging.getLogger(__name__)


class AutoScheduler:
    """Автоматический планировщик с настраиваемым временем"""
    
    def __init__(self, bot, openai_client, supabase_client):
        self.bot = bot
        self.openai_client = openai_client
        self.supabase_client = supabase_client
        self.scheduler = AsyncIOScheduler()
        self.vacancy_scheduler = VacancyScheduler(bot, openai_client, supabase_client)
        
        # Настройки по умолчанию
        self.default_time = time(9, 0)  # 9:00 утра
        self.timezone = pytz.timezone('Europe/Moscow')  # Московское время
        
    async def start_scheduler(self, send_time: time = None):
        """
        Запускает автоматический планировщик
        
        Args:
            send_time: Время отправки (по умолчанию 9:00)
        """
        if send_time is None:
            send_time = self.default_time
            
        logger.info(f"Starting auto scheduler at {send_time} Moscow time")
        
        # Добавляем задачу в планировщик
        self.scheduler.add_job(
            func=self._run_daily_search,
            trigger=CronTrigger(
                hour=send_time.hour,
                minute=send_time.minute,
                timezone=self.timezone
            ),
            id='daily_vacancy_search',
            replace_existing=True,
            max_instances=1
        )
        
        # Запускаем планировщик
        self.scheduler.start()
        logger.info("Auto scheduler started successfully")
        
    async def stop_scheduler(self):
        """Останавливает планировщик"""
        self.scheduler.shutdown()
        logger.info("Auto scheduler stopped")
        
    async def _run_daily_search(self):
        """Выполняет ежедневный поиск (вызывается планировщиком)"""
        try:
            logger.info("Starting automated daily vacancy search...")
            await self.vacancy_scheduler.run_daily_search()
            logger.info("Automated daily vacancy search completed")
        except Exception as e:
            logger.error(f"Automated daily search failed: {e}")
            
    def get_next_run_time(self) -> str:
        """Возвращает время следующего запуска"""
        job = self.scheduler.get_job('daily_vacancy_search')
        if job:
            next_run = job.next_run_time
            if next_run:
                return next_run.strftime('%Y-%m-%d %H:%M:%S %Z')
        return "Не запланировано"
        
    def is_running(self) -> bool:
        """Проверяет, запущен ли планировщик"""
        return self.scheduler.running








# Пример использования
async def setup_auto_scheduler(bot, openai_client, supabase_client):
    """
    Настраивает автоматический планировщик
    Всем пользователям отправляет вакансии в 9:00 утра по Москве
    """
    auto_scheduler = AutoScheduler(bot, openai_client, supabase_client)
    await auto_scheduler.start_scheduler(time(9, 0))  # 9:00 утра
    return auto_scheduler


if __name__ == "__main__":
    # Тест
    import os
    from openai import OpenAI
    from repositories.supabase_client import SupabaseClient
    
    logging.basicConfig(level=logging.INFO)
    
    async def test_scheduler():
        # Настройка клиентов
        openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        supabase_client = SupabaseClient(
            os.getenv("SUPABASE_URL"), 
            os.getenv("SUPABASE_KEY")
        )
        
        # Мок бота для тестирования
        class MockBot:
            async def send_message(self, chat_id, text, parse_mode=None, disable_web_page_preview=None):
                print(f"[MOCK] Message to {chat_id}: {text[:100]}...")
        
        mock_bot = MockBot()
        
        # Тест планировщика
        scheduler = await setup_auto_scheduler(
            mock_bot, openai_client, supabase_client
        )
        
        print(f"Scheduler running: {scheduler.is_running()}")
        print(f"Next run: {scheduler.get_next_run_time()}")
        
        # Ждем 10 секунд для демонстрации
        await asyncio.sleep(10)
        await scheduler.stop_scheduler()
    
    # asyncio.run(test_scheduler())