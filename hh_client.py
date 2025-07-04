"""
HH.ru API клиент для работы с поиском вакансий
"""
import asyncio
import aiohttp
import json
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import os

logger = logging.getLogger(__name__)


class HHAPIClient:
    """Клиент для работы с API HH.ru"""
    
    BASE_URL = "https://api.hh.ru"
    
    def __init__(self, user_agent: str = "VacancyBot/1.0"):
        """
        Инициализация клиента
        
        Args:
            user_agent: User-Agent заголовок (обязателен для HH.ru)
        """
        self.user_agent = user_agent
        self.session: Optional[aiohttp.ClientSession] = None
        self.rate_limit_delay = 0.2  # 200ms между запросами
        self.last_request_time = 0
        
    async def __aenter__(self):
        """Async context manager entry"""
        await self._create_session()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self._close_session()
        
    async def _create_session(self):
        """Создает HTTP сессию"""
        if self.session is None:
            headers = {
                'User-Agent': self.user_agent,
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }
            
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(
                headers=headers,
                timeout=timeout
            )
            
    async def _close_session(self):
        """Закрывает HTTP сессию"""
        if self.session:
            await self.session.close()
            self.session = None
            
    async def _rate_limit(self):
        """Контроль частоты запросов"""
        current_time = asyncio.get_event_loop().time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - time_since_last)
            
        self.last_request_time = asyncio.get_event_loop().time()
        
    async def _make_request(self, method: str, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """
        Выполняет HTTP запрос к API
        
        Args:
            method: HTTP метод
            endpoint: Эндпоинт API
            params: Параметры запроса
            
        Returns:
            Ответ API в формате dict
        """
        if not self.session:
            await self._create_session()
            
        await self._rate_limit()
        
        url = f"{self.BASE_URL}{endpoint}"
        
        try:
            async with self.session.request(method, url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 429:
                    # Rate limit exceeded
                    logger.warning("Rate limit exceeded, waiting...")
                    await asyncio.sleep(1)
                    return await self._make_request(method, endpoint, params)
                else:
                    logger.error(f"API request failed: {response.status} - {await response.text()}")
                    response.raise_for_status()
                    
        except aiohttp.ClientError as e:
            logger.error(f"Request error: {e}")
            raise
            
    async def search_vacancies(self, search_params: Dict) -> Dict:
        """
        Поиск вакансий
        
        Args:
            search_params: Параметры поиска
            
        Returns:
            Результаты поиска
        """
        # Валидация и очистка параметров
        cleaned_params = self._clean_search_params(search_params)
        
        logger.info(f"Searching vacancies with params: {cleaned_params}")
        
        return await self._make_request("GET", "/vacancies", cleaned_params)
        
    async def get_vacancy_details(self, vacancy_id: str) -> Dict:
        """
        Получает детальную информацию о вакансии
        
        Args:
            vacancy_id: ID вакансии
            
        Returns:
            Детальная информация о вакансии
        """
        return await self._make_request("GET", f"/vacancies/{vacancy_id}")
        
    async def get_dictionaries(self) -> Dict:
        """
        Получает справочники HH.ru
        
        Returns:
            Словари с возможными значениями параметров
        """
        return await self._make_request("GET", "/dictionaries")
        
    def _clean_search_params(self, params: Dict) -> Dict:
        """
        Очищает и валидирует параметры поиска
        
        Args:
            params: Исходные параметры
            
        Returns:
            Очищенные параметры
        """
        cleaned = {}
        
        # Текстовый поиск
        if 'text' in params and params['text']:
            cleaned['text'] = str(params['text']).strip()
            
        # Регионы
        if 'area' in params:
            if isinstance(params['area'], list):
                cleaned['area'] = params['area']
            else:
                cleaned['area'] = [params['area']]
                
        # Опыт работы
        if 'experience' in params:
            experience_values = ['noExperience', 'between1And3', 'between3And6', 'moreThan6']
            if params['experience'] in experience_values:
                cleaned['experience'] = params['experience']
                
        # Тип занятости
        if 'employment' in params:
            employment_values = ['full', 'part', 'project', 'volunteer', 'probation']
            if isinstance(params['employment'], list):
                cleaned['employment'] = [e for e in params['employment'] if e in employment_values]
            elif params['employment'] in employment_values:
                cleaned['employment'] = params['employment']
                
        # Зарплата
        if 'salary' in params and params['salary']:
            cleaned['salary'] = int(params['salary'])
            
        # Только с зарплатой
        if 'only_with_salary' in params:
            cleaned['only_with_salary'] = 'true' if params['only_with_salary'] else 'false'
            
        # Период поиска (в днях)
        if 'period' in params:
            period = min(int(params['period']), 30)  # Максимум 30 дней
            cleaned['period'] = period
            
        # Количество на странице
        if 'per_page' in params:
            per_page = min(int(params['per_page']), 100)  # Максимум 100
            cleaned['per_page'] = per_page
        else:
            cleaned['per_page'] = 50  # По умолчанию
            
        # Сортировка
        if 'order_by' in params:
            order_values = ['relevance', 'publication_time', 'salary_desc', 'salary_asc']
            if params['order_by'] in order_values:
                cleaned['order_by'] = params['order_by']
        else:
            cleaned['order_by'] = 'publication_time'  # По умолчанию
            
        # Страница
        if 'page' in params:
            cleaned['page'] = int(params['page'])
        else:
            cleaned['page'] = 0
            
        return cleaned


class HHVacancySearcher:
    """Высокоуровневый интерфейс для поиска вакансий"""
    
    def __init__(self, client: HHAPIClient):
        self.client = client
        
    async def search_with_fallback(self, user_profile: Dict) -> List[Dict]:
        """
        Поиск вакансий с fallback стратегией
        
        Args:
            user_profile: Профиль пользователя
            
        Returns:
            Список найденных вакансий
        """
        all_vacancies = []
        
        # Последовательный поиск с расширением критериев
        search_modes = ['strict', 'relaxed', 'broad', 'any']
        
        for mode in search_modes:
            search_params = self._get_search_params(user_profile, mode)
            
            try:
                result = await self.client.search_vacancies(search_params)
                vacancies = result.get('items', [])
                
                # Добавляем новые вакансии (дедупликация)
                existing_ids = {v['id'] for v in all_vacancies}
                new_vacancies = [v for v in vacancies if v['id'] not in existing_ids]
                all_vacancies.extend(new_vacancies)
                
                logger.info(f"Mode {mode}: found {len(new_vacancies)} new vacancies (total: {len(all_vacancies)})")
                
                # ИСПРАВЛЕНИЕ: Более строгие критерии остановки
                if mode == 'strict' and len(all_vacancies) >= 20:
                    logger.info("Enough strict matches found, skipping broader search")
                    break
                elif mode == 'relaxed' and len(all_vacancies) >= 30:
                    logger.info("Enough relaxed matches found, skipping broader search")
                    break
                elif len(all_vacancies) >= 50:
                    break
                    
            except Exception as e:
                logger.error(f"Search failed for mode {mode}: {e}")
                continue
                
        return all_vacancies
        
    def _get_search_params(self, user_profile: Dict, mode: str) -> Dict:
        """
        Генерирует параметры поиска для разных режимов
        
        Args:
            user_profile: Профиль пользователя
            mode: Режим поиска
            
        Returns:
            Параметры для API
        """
        base_params = {
            'area': user_profile.get('areas', [1, 2]),  # Москва, СПб по умолчанию
            'period': 1,  # За сутки
            'per_page': 100,
            'order_by': 'publication_time'
        }
        
        if mode == 'strict':
            return {
                **base_params,
                'text': user_profile.get('exact_position', ''),
                'experience': user_profile.get('experience_level'),
                'employment': 'full',
                'salary': user_profile.get('salary_from'),
                'only_with_salary': True
            }
            
        elif mode == 'relaxed':
            # ИСПРАВЛЕНИЕ: Используем должность + основной навык вместо всех навыков
            position = user_profile.get('exact_position', '')
            main_skill = user_profile.get('top_skills', [''])[0] if user_profile.get('top_skills') else ''
            
            search_text = f"{position} {main_skill}".strip()
            return {
                **base_params,
                'text': search_text,
                'experience': user_profile.get('experience_level'),
                'employment': ['full', 'project']
            }
            
        elif mode == 'broad':
            # ИСПРАВЛЕНИЕ: Более точный поиск - альтернативные названия должности
            alternatives = user_profile.get('alternative_positions', [])
            if alternatives:
                search_text = alternatives[0]  # Берем первую альтернативу
            else:
                # Fallback: сокращенная версия должности
                position = user_profile.get('exact_position', '')
                # Убираем лишние слова для более широкого поиска
                position_words = position.split()
                search_text = ' '.join(position_words[:2])  # Берем первые 2 слова
                
            return {
                **base_params,
                'text': search_text,
                'area': [1, 2, 3, 4]  # Расширяем географию
            }
            
        elif mode == 'any':
            # ИСПРАВЛЕНИЕ: Более консервативный 'any' режим
            domain = user_profile.get('domain', '')
            field = user_profile.get('field', '')
            
            # Предпочитаем domain, если он более специфичен
            if len(domain) > len(field):
                search_text = domain
            else:
                search_text = field
                
            return {
                **base_params,
                'text': search_text,
                'area': [1, 2, 3, 4],  # Не расширяем до всей России
                'per_page': 50  # Меньше результатов для фильтрации
            }
            
        return base_params


# Тестовые функции
async def test_api_connection():
    """Тест базового подключения к API"""
    try:
        async with HHAPIClient() as client:
            # Проверяем справочники
            dictionaries = await client.get_dictionaries()
            logger.info("✅ API connection works")
            
            # Простейший поиск
            result = await client.search_vacancies({'text': 'python', 'per_page': 5})
            logger.info(f"✅ Found {result['found']} total vacancies")
            
            return True
    except Exception as e:
        logger.error(f"❌ API connection failed: {e}")
        return False


async def test_search_modes():
    """Тест различных режимов поиска"""
    test_profile = {
        'exact_position': 'Python разработчик',
        'top_skills': ['Python', 'Django', 'PostgreSQL'],
        'experience_level': 'between3And6',
        'salary_from': 200000,
        'areas': [1, 2],  # Москва, СПб
        'domain': 'backend python',
        'field': 'python'
    }
    
    try:
        async with HHAPIClient() as client:
            searcher = HHVacancySearcher(client)
            vacancies = await searcher.search_with_fallback(test_profile)
            
            logger.info(f"✅ Found {len(vacancies)} total vacancies")
            for i, vacancy in enumerate(vacancies[:3], 1):
                logger.info(f"{i}. {vacancy['name']} - {vacancy['employer']['name']}")
                
            return vacancies
    except Exception as e:
        logger.error(f"❌ Search test failed: {e}")
        return []


# Пример использования
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    async def main():
        # Тест подключения
        await test_api_connection()
        
        # Тест поиска
        await test_search_modes()
    
    asyncio.run(main())