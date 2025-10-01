from typing import Optional
from repositories.postgres_client import PostgresClient
import logging

logger = logging.getLogger(__name__)


class UserRepository:
    def __init__(self, pg_client: PostgresClient):
        self.client = pg_client

    async def get_or_create_user(self, telegram_id: int, username: str = None) -> dict:
        """
        Получает или создает пользователя

        Args:
            telegram_id: Telegram ID пользователя
            username: Username в Telegram

        Returns:
            Словарь с данными пользователя
        """
        # Проверяем существование
        users = await self.client.select('users', {'telegram_id': telegram_id})
        if users:
            return users[0]

        # Создаем нового
        new_user = await self.client.insert('users', {
            'telegram_id': telegram_id,
            'username': username
        })
        logger.info(f"Created new user: telegram_id={telegram_id}")
        return new_user


class ResumeRepository:
    def __init__(self, pg_client: PostgresClient):
        self.client = pg_client

    async def save_resume(self, telegram_id: int, cv_text: str) -> dict:
        """
        Сохраняет или обновляет резюме пользователя

        Args:
            telegram_id: Telegram ID пользователя
            cv_text: Текст резюме

        Returns:
            Сохраненная запись
        """
        result = await self.client.upsert(
            'user_profiles',
            {
                'telegram_id': telegram_id,
                'cv_text': cv_text
            },
            conflict_columns=['telegram_id']
        )
        logger.info(f"Saved resume for telegram_id={telegram_id}")
        return result

    async def get_resume(self, telegram_id: int) -> Optional[str]:
        """
        Получает резюме пользователя

        Args:
            telegram_id: Telegram ID пользователя

        Returns:
            Текст резюме или None
        """
        profiles = await self.client.select(
            'user_profiles',
            {'telegram_id': telegram_id}
        )
        if profiles:
            return profiles[0].get('cv_text')
        return None

    async def delete_resume(self, telegram_id: int) -> None:
        """
        Удаляет резюме пользователя

        Args:
            telegram_id: Telegram ID пользователя
        """
        await self.client.delete('user_profiles', {'telegram_id': telegram_id})
        logger.info(f"Deleted resume for telegram_id={telegram_id}")


class HHOAuthRepository:
    """Репозиторий для работы с OAuth токенами HH.ru"""

    def __init__(self, pg_client: PostgresClient):
        self.client = pg_client

    async def save_tokens(self, telegram_id: int, access_token: str,
                         refresh_token: str = None, expires_at=None) -> dict:
        """
        Сохраняет OAuth токены пользователя

        Args:
            telegram_id: Telegram ID пользователя
            access_token: Access token от HH.ru
            refresh_token: Refresh token от HH.ru
            expires_at: Время истечения токена

        Returns:
            Сохраненная запись
        """
        data = {
            'telegram_id': telegram_id,
            'access_token': access_token,
            'refresh_token': refresh_token,
            'expires_at': expires_at
        }

        result = await self.client.upsert(
            'hh_oauth_tokens',
            data,
            conflict_columns=['telegram_id']
        )
        logger.info(f"Saved HH OAuth tokens for telegram_id={telegram_id}")
        return result

    async def get_tokens(self, telegram_id: int) -> Optional[dict]:
        """
        Получает OAuth токены пользователя

        Args:
            telegram_id: Telegram ID пользователя

        Returns:
            Словарь с токенами или None
        """
        tokens = await self.client.select(
            'hh_oauth_tokens',
            {'telegram_id': telegram_id}
        )
        if tokens:
            return tokens[0]
        return None

    async def delete_tokens(self, telegram_id: int) -> None:
        """
        Удаляет OAuth токены пользователя

        Args:
            telegram_id: Telegram ID пользователя
        """
        await self.client.delete('hh_oauth_tokens', {'telegram_id': telegram_id})
        logger.info(f"Deleted HH OAuth tokens for telegram_id={telegram_id}")


class HHUserResumesRepository:
    """Репозиторий для работы с резюме пользователя на HH.ru"""

    def __init__(self, pg_client: PostgresClient):
        self.client = pg_client

    async def save_resume(self, telegram_id: int, resume_id: str,
                         resume_title: str = None, is_default: bool = False) -> dict:
        """
        Сохраняет резюме пользователя с HH.ru

        Args:
            telegram_id: Telegram ID пользователя
            resume_id: ID резюме на HH.ru
            resume_title: Название резюме
            is_default: Использовать по умолчанию

        Returns:
            Сохраненная запись
        """
        # Если это дефолтное резюме, сбрасываем флаг у остальных
        if is_default:
            await self.client.execute(
                "UPDATE hh_user_resumes SET is_default = false WHERE telegram_id = $1",
                telegram_id
            )

        result = await self.client.upsert(
            'hh_user_resumes',
            {
                'telegram_id': telegram_id,
                'resume_id': resume_id,
                'resume_title': resume_title,
                'is_default': is_default,
                'is_active': True
            },
            conflict_columns=['telegram_id', 'resume_id']
        )
        logger.info(f"Saved HH resume {resume_id} for telegram_id={telegram_id}")
        return result

    async def get_resumes(self, telegram_id: int) -> list:
        """
        Получает все резюме пользователя с HH.ru

        Args:
            telegram_id: Telegram ID пользователя

        Returns:
            Список резюме
        """
        resumes = await self.client.select(
            'hh_user_resumes',
            {'telegram_id': telegram_id, 'is_active': True}
        )
        return resumes

    async def get_default_resume(self, telegram_id: int) -> Optional[dict]:
        """
        Получает дефолтное резюме пользователя

        Args:
            telegram_id: Telegram ID пользователя

        Returns:
            Дефолтное резюме или None
        """
        resumes = await self.client.select(
            'hh_user_resumes',
            {'telegram_id': telegram_id, 'is_default': True}
        )
        if resumes:
            return resumes[0]
        return None

    async def set_default_resume(self, telegram_id: int, resume_id: str) -> None:
        """
        Устанавливает дефолтное резюме

        Args:
            telegram_id: Telegram ID пользователя
            resume_id: ID резюме на HH.ru
        """
        # Сбрасываем флаг у всех
        await self.client.execute(
            "UPDATE hh_user_resumes SET is_default = false WHERE telegram_id = $1",
            telegram_id
        )

        # Устанавливаем флаг для выбранного
        await self.client.update(
            'hh_user_resumes',
            {'is_default': True},
            {'telegram_id': telegram_id, 'resume_id': resume_id}
        )
        logger.info(f"Set default resume {resume_id} for telegram_id={telegram_id}")


class SentVacanciesRepository:
    """Репозиторий для отслеживания отправленных откликов"""

    def __init__(self, pg_client: PostgresClient):
        self.client = pg_client

    async def mark_as_sent(self, telegram_id: int, vacancy_id: str,
                           vacancy_name: str = None, employer_name: str = None,
                           score: float = None) -> dict:
        """
        Отмечает вакансию как отправленную

        Args:
            telegram_id: Telegram ID пользователя
            vacancy_id: ID вакансии
            vacancy_name: Название вакансии
            employer_name: Название работодателя
            score: Скор релевантности

        Returns:
            Сохраненная запись
        """
        result = await self.client.insert(
            'sent_vacancies',
            {
                'telegram_id': telegram_id,
                'vacancy_id': vacancy_id,
                'vacancy_name': vacancy_name,
                'employer_name': employer_name,
                'score': score
            }
        )
        return result

    async def is_already_sent(self, telegram_id: int, vacancy_id: str) -> bool:
        """
        Проверяет, был ли уже отправлен отклик на вакансию

        Args:
            telegram_id: Telegram ID пользователя
            vacancy_id: ID вакансии

        Returns:
            True если отклик уже отправлен
        """
        sent = await self.client.select(
            'sent_vacancies',
            {'telegram_id': telegram_id, 'vacancy_id': vacancy_id}
        )
        return len(sent) > 0

    async def get_sent_vacancies(self, telegram_id: int, limit: int = 100) -> list:
        """
        Получает список отправленных вакансий

        Args:
            telegram_id: Telegram ID пользователя
            limit: Максимальное количество записей

        Returns:
            Список отправленных вакансий
        """
        query = """
            SELECT * FROM sent_vacancies
            WHERE telegram_id = $1
            ORDER BY sent_at DESC
            LIMIT $2
        """
        return await self.client.fetch_all(query, telegram_id, limit)
