"""
Анализатор резюме для извлечения структурированных данных
"""
import json
import logging
import re
from typing import Dict, List, Optional
from openai import OpenAI

logger = logging.getLogger(__name__)


class ResumeAnalyzer:
    """Анализатор резюме с использованием OpenAI"""
    
    def __init__(self, openai_client: OpenAI):
        self.client = openai_client
        
    async def analyze_resume(self, cv_text: str) -> Dict:
        """
        Глубокий анализ резюме с извлечением структурированной информации
        
        Args:
            cv_text: Текст резюме
            
        Returns:
            Структурированные данные профиля
        """
        try:
            # Основной анализ через GPT
            profile_data = await self._extract_profile_data(cv_text)
            
            # Дополнительная обработка
            profile_data = self._post_process_profile(profile_data)
            
            # Добавляем метаданные
            profile_data['analysis_timestamp'] = self._get_current_timestamp()
            profile_data['original_text_length'] = len(cv_text)
            
            logger.info(f"Resume analyzed: {profile_data.get('exact_position', 'Unknown')} with {len(profile_data.get('top_skills', []))} skills")
            
            return profile_data
            
        except Exception as e:
            logger.error(f"Resume analysis failed: {e}")
            return self._create_fallback_profile(cv_text)
    
    async def _extract_profile_data(self, cv_text: str) -> Dict:
        """Извлечение данных через OpenAI"""
        
        prompt = """Проанализируй резюме и извлеки структурированную информацию в JSON формате.

ВАЖНО: Верни ТОЛЬКО валидный JSON без дополнительных комментариев.

Структура ответа:
{
  "exact_position": "точная должность из резюме",
  "alternative_positions": ["альтернативные названия должности"],
  "experience_level": "junior/middle/senior/lead", 
  "experience_years": число_лет_опыта,
  "top_skills": ["топ-5 ключевых навыков"],
  "domain": "область (backend/frontend/fullstack/data/devops/etc)",
  "field": "основная технология (python/javascript/java/etc)",
  "industries": ["отрасли в которых работал"],
  "salary_expectation": {
    "has_explicit": true/false,
    "estimated_min": число_или_null,
    "estimated_max": число_или_null,
    "currency": "RUR/USD/EUR"
  },
  "location_preferences": {
    "current_location": "город",
    "areas": [1, 2],
    "remote_ok": true/false,
    "relocation_ok": true/false
  },
  "employment_preferences": {
    "employment_types": ["full", "part", "project"],
    "company_size": "startup/medium/large/any"
  },
  "unique_features": ["особые достижения/сертификаты"]
}

Правила анализа:
1. experience_level определяй по годам: 0-1=junior, 1-3=middle, 3-6=senior, 6+=lead
2. areas: 1=Москва, 2=СПб, 3=Екатеринбург, 4=Новосибирск  
3. Если зарплата не указана явно - оцени по рынку для данного уровня
4. top_skills - только технические навыки, без soft skills
5. Если что-то неясно - используй разумные значения по умолчанию

Резюме для анализа:
""" + cv_text

        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1500
        )
        
        result_text = response.choices[0].message.content.strip()
        
        # Пытаемся извлечь JSON из ответа
        try:
            # Ищем JSON в ответе
            json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            else:
                return json.loads(result_text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from GPT response: {e}")
            logger.error(f"Raw response: {result_text}")
            raise
    
    def _post_process_profile(self, profile_data: Dict) -> Dict:
        """Дополнительная обработка и валидация данных"""
        
        # Валидация experience_level
        if profile_data.get('experience_level') not in ['junior', 'middle', 'senior', 'lead']:
            years = profile_data.get('experience_years', 0)
            if years <= 1:
                profile_data['experience_level'] = 'junior'
            elif years <= 3:
                profile_data['experience_level'] = 'middle'  
            elif years <= 6:
                profile_data['experience_level'] = 'senior'
            else:
                profile_data['experience_level'] = 'lead'
        
        # Маппинг experience_level в коды HH.ru
        experience_mapping = {
            'junior': 'between1And3',
            'middle': 'between3And6', 
            'senior': 'between3And6',
            'lead': 'moreThan6'
        }
        profile_data['experience_code'] = experience_mapping.get(
            profile_data.get('experience_level'), 'between1And3'
        )
        
        # Обработка зарплатных ожиданий
        salary_data = profile_data.get('salary_expectation', {})
        if salary_data.get('estimated_min'):
            profile_data['salary_from'] = salary_data['estimated_min']
        
        # Обработка локации
        location_data = profile_data.get('location_preferences', {})
        if not location_data.get('areas'):
            # По умолчанию Москва и СПб
            profile_data['areas'] = [1, 2]
        else:
            profile_data['areas'] = location_data['areas']
            
        # Очистка навыков
        skills = profile_data.get('top_skills', [])
        profile_data['top_skills'] = [skill.strip() for skill in skills if skill.strip()][:5]
        
        return profile_data
    
    def _create_fallback_profile(self, cv_text: str) -> Dict:
        """Создает базовый профиль в случае ошибки анализа"""
        
        # Простое извлечение навыков по ключевым словам
        skills = []
        skill_patterns = {
            'Python': r'\bpython\b',
            'JavaScript': r'\bjavascript\b|\bjs\b',
            'Java': r'\bjava\b',
            'React': r'\breact\b',
            'Django': r'\bdjango\b',
            'PostgreSQL': r'\bpostgresql\b|\bpostgres\b',
            'Docker': r'\bdocker\b',
            'Git': r'\bgit\b'
        }
        
        for skill, pattern in skill_patterns.items():
            if re.search(pattern, cv_text, re.IGNORECASE):
                skills.append(skill)
        
        return {
            'exact_position': 'Разработчик',
            'alternative_positions': [],
            'experience_level': 'middle',
            'experience_code': 'between1And3',
            'experience_years': 2,
            'top_skills': skills[:5] or ['Python'],
            'domain': 'backend',
            'field': skills[0].lower() if skills else 'python',
            'industries': [],
            'salary_expectation': {
                'has_explicit': False,
                'estimated_min': None,
                'estimated_max': None,
                'currency': 'RUR'
            },
            'areas': [1, 2],
            'salary_from': None,
            'location_preferences': {
                'current_location': 'Москва',
                'areas': [1, 2],
                'remote_ok': True,
                'relocation_ok': False
            },
            'employment_preferences': {
                'employment_types': ['full'],
                'company_size': 'any'
            },
            'unique_features': [],
            'analysis_timestamp': self._get_current_timestamp(),
            'original_text_length': len(cv_text),
            'fallback_used': True
        }
    
    def _get_current_timestamp(self) -> str:
        """Возвращает текущую временную метку"""
        from datetime import datetime
        return datetime.now().isoformat()


# Тестовые функции
def test_resume_analyzer():
    """Тест анализатора резюме"""
    import os
    import asyncio
    
    # Тестовое резюме
    test_resume = """
    Иван Петров
    Python разработчик
    
    Опыт работы: 3 года
    
    Навыки:
    - Python, Django, FastAPI
    - PostgreSQL, Redis
    - Docker, Git
    - REST API разработка
    
    Опыт работы:
    2021-2024 - Backend разработчик в IT компании
    Разработка веб-приложений на Django, работа с базами данных
    
    Желаемая зарплата: от 180 000 руб
    Готов к удаленной работе
    Местоположение: Москва
    """
    
    async def run_test():
        try:
            # Инициализация клиента OpenAI
            openai_api_key = os.getenv("OPENAI_API_KEY")
            if not openai_api_key:
                logger.error("OPENAI_API_KEY not found in environment")
                return
                
            client = OpenAI(api_key=openai_api_key)
            analyzer = ResumeAnalyzer(client)
            
            # Анализ резюме
            profile = await analyzer.analyze_resume(test_resume)
            
            # Вывод результатов
            logger.info("=== РЕЗУЛЬТАТЫ АНАЛИЗА РЕЗЮМЕ ===")
            logger.info(f"Должность: {profile.get('exact_position')}")
            logger.info(f"Уровень: {profile.get('experience_level')}")
            logger.info(f"Навыки: {profile.get('top_skills')}")
            logger.info(f"Домен: {profile.get('domain')}")
            logger.info(f"Зарплата: {profile.get('salary_from')}")
            logger.info(f"Регионы: {profile.get('areas')}")
            logger.info(f"Fallback использован: {profile.get('fallback_used', False)}")
            
            return profile
            
        except Exception as e:
            logger.error(f"Test failed: {e}")
            return None
    
    return asyncio.run(run_test())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_resume_analyzer()