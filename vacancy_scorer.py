"""
Модуль для скоринга и ранжирования вакансий
"""
import logging
import re
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import math

logger = logging.getLogger(__name__)


class VacancyScorer:
    """Система скоринга вакансий по релевантности"""
    
    def __init__(self):
        # Веса для различных критериев (сумма = 1.0)
        self.weights = {
            'title_match': 0.30,      # Совпадение в названии вакансии
            'skills_match': 0.35,     # Совпадение навыков
            'experience_match': 0.15, # Соответствие опыта
            'salary_match': 0.05,     # Зарплатное соответствие (низкий вес)
            'location_match': 0.10,   # География
            'freshness': 0.05         # Свежесть публикации
        }
        
        # Если есть точные зарплатные данные - увеличиваем вес
        self.weights_with_salary = {
            'title_match': 0.25,
            'skills_match': 0.30,
            'experience_match': 0.15,
            'salary_match': 0.15,     # Увеличиваем
            'location_match': 0.10,
            'freshness': 0.05
        }
    
    def score_vacancy(self, vacancy: Dict, user_profile: Dict) -> float:
        """
        Оценивает релевантность вакансии для пользователя
        
        Args:
            vacancy: Данные вакансии из HH.ru API
            user_profile: Профиль пользователя
            
        Returns:
            Скор от 0.0 до 1.0
        """
        try:
            # Определяем веса в зависимости от наличия зарплатных данных
            weights = self._get_weights(vacancy, user_profile)
            
            # Вычисляем компоненты скора
            title_score = self._calculate_title_match(vacancy, user_profile)
            skills_score = self._calculate_skills_match(vacancy, user_profile)
            experience_score = self._calculate_experience_match(vacancy, user_profile)
            salary_score = self._calculate_salary_match(vacancy, user_profile)
            location_score = self._calculate_location_match(vacancy, user_profile)
            freshness_score = self._calculate_freshness_score(vacancy)
            
            # Взвешенная сумма
            total_score = (
                title_score * weights['title_match'] +
                skills_score * weights['skills_match'] +
                experience_score * weights['experience_match'] +
                salary_score * weights['salary_match'] +
                location_score * weights['location_match'] +
                freshness_score * weights['freshness']
            )
            
            # Логирование для отладки
            logger.debug(f"Vacancy scoring: {vacancy['name'][:50]}...")
            logger.debug(f"  Title: {title_score:.2f}, Skills: {skills_score:.2f}, "
                        f"Experience: {experience_score:.2f}, Salary: {salary_score:.2f}, "
                        f"Location: {location_score:.2f}, Freshness: {freshness_score:.2f}")
            logger.debug(f"  Total score: {total_score:.3f}")
            
            return min(max(total_score, 0.0), 1.0)  # Ограничиваем 0-1
            
        except Exception as e:
            logger.error(f"Error scoring vacancy {vacancy.get('id', 'unknown')}: {e}")
            return 0.0
    
    def score_and_rank_vacancies(self, vacancies: List[Dict], user_profile: Dict) -> List[Dict]:
        """
        Оценивает и ранжирует список вакансий
        
        Args:
            vacancies: Список вакансий
            user_profile: Профиль пользователя
            
        Returns:
            Отсортированный список вакансий с добавленным полем 'score'
        """
        scored_vacancies = []
        
        for vacancy in vacancies:
            score = self.score_vacancy(vacancy, user_profile)
            vacancy_with_score = {**vacancy, 'score': score}
            scored_vacancies.append(vacancy_with_score)
        
        # ИСПРАВЛЕНИЕ: Фильтруем по минимальному порогу релевантности
        MIN_RELEVANCE_THRESHOLD = 0.25  # Минимум 25% релевантности
        relevant_vacancies = [v for v in scored_vacancies if v['score'] >= MIN_RELEVANCE_THRESHOLD]
        
        # Если релевантных мало - немного снижаем порог
        if len(relevant_vacancies) < 5:
            MIN_RELEVANCE_THRESHOLD = 0.15  # Снижаем до 15%
            relevant_vacancies = [v for v in scored_vacancies if v['score'] >= MIN_RELEVANCE_THRESHOLD]
            logger.warning(f"Lowered relevance threshold to {MIN_RELEVANCE_THRESHOLD}")
        
        # Сортируем по убыванию скора
        relevant_vacancies.sort(key=lambda x: x['score'], reverse=True)
        
        if relevant_vacancies:
            logger.info(f"Filtered to {len(relevant_vacancies)} relevant vacancies. "
                       f"Top score: {relevant_vacancies[0]['score']:.3f}, "
                       f"Bottom score: {relevant_vacancies[-1]['score']:.3f}")
        else:
            logger.warning("No relevant vacancies found after filtering")
            # Возвращаем топ-5 из всех, если совсем ничего нет
            relevant_vacancies = sorted(scored_vacancies, key=lambda x: x['score'], reverse=True)[:5]
        
        return relevant_vacancies
    
    def _get_weights(self, vacancy: Dict, user_profile: Dict) -> Dict:
        """Определяет веса в зависимости от наличия зарплатных данных"""
        has_vacancy_salary = bool(vacancy.get('salary'))
        has_user_salary = bool(user_profile.get('salary_from'))
        
        if has_vacancy_salary and has_user_salary:
            return self.weights_with_salary
        else:
            return self.weights
    
    def _calculate_title_match(self, vacancy: Dict, user_profile: Dict) -> float:
        """Оценка совпадения названия вакансии с желаемой позицией"""
        vacancy_title = vacancy.get('name', '').lower()
        user_position = user_profile.get('exact_position', '').lower()
        user_skills = [skill.lower() for skill in user_profile.get('top_skills', [])]
        
        score = 0.0
        
        # Прямое совпадение в названии
        if user_position and user_position in vacancy_title:
            score += 0.6
        
        # Совпадение ключевых навыков в названии
        skills_in_title = sum(1 for skill in user_skills if skill in vacancy_title)
        if user_skills:
            score += (skills_in_title / len(user_skills)) * 0.4
        
        return min(score, 1.0)
    
    def _calculate_skills_match(self, vacancy: Dict, user_profile: Dict) -> float:
        """Оценка совпадения навыков"""
        user_skills = [skill.lower() for skill in user_profile.get('top_skills', [])]
        if not user_skills:
            return 0.5  # Нейтральный скор если навыки не определены
        
        # Извлекаем навыки из описания вакансии
        vacancy_text = self._get_vacancy_text(vacancy).lower()
        
        matched_skills = 0
        for skill in user_skills:
            if self._skill_mentioned_in_text(skill, vacancy_text):
                matched_skills += 1
        
        # Процент совпадения навыков
        match_ratio = matched_skills / len(user_skills)
        
        # Бонус за количество совпавших навыков
        bonus = min(matched_skills * 0.1, 0.3)
        
        return min(match_ratio + bonus, 1.0)
    
    def _calculate_experience_match(self, vacancy: Dict, user_profile: Dict) -> float:
        """Оценка соответствия опыта"""
        user_years = user_profile.get('experience_years', 0)
        
        # Извлекаем требования к опыту из описания
        vacancy_text = self._get_vacancy_text(vacancy)
        required_years = self._extract_experience_requirements(vacancy_text)
        
        if required_years is None:
            return 0.7  # Нейтральный скор если требования неясны
        
        # Расчет соответствия
        if user_years >= required_years:
            # Пользователь соответствует или превышает требования
            if user_years <= required_years * 2:
                return 1.0  # Идеальное соответствие
            else:
                return 0.8  # Переквалификация
        else:
            # Пользователь не дотягивает
            gap = required_years - user_years
            return max(0.0, 1.0 - gap * 0.2)  # Штраф за недостаток опыта
    
    def _calculate_salary_match(self, vacancy: Dict, user_profile: Dict) -> float:
        """Оценка зарплатного соответствия"""
        vacancy_salary = vacancy.get('salary')
        user_expectation = user_profile.get('salary_from')
        
        # Если данных нет - нейтральный скор
        if not vacancy_salary or not user_expectation:
            return 0.5
        
        vacancy_from = vacancy_salary.get('from', 0)
        vacancy_to = vacancy_salary.get('to', vacancy_from)
        
        # Если зарплата в вакансии соответствует ожиданиям
        if vacancy_from >= user_expectation:
            return 1.0
        elif vacancy_to >= user_expectation:
            return 0.8
        else:
            # Зарплата ниже ожиданий
            gap = (user_expectation - vacancy_to) / user_expectation
            return max(0.0, 1.0 - gap)
    
    def _calculate_location_match(self, vacancy: Dict, user_profile: Dict) -> float:
        """Оценка географического соответствия"""
        vacancy_area_id = vacancy.get('area', {}).get('id')
        user_areas = user_profile.get('areas', [])
        
        # Проверка удаленной работы
        schedule = vacancy.get('schedule', {})
        if schedule and 'remote' in schedule.get('id', '').lower():
            return 1.0  # Удаленка всегда подходит
        
        # Проверка географического совпадения
        try:
            if vacancy_area_id and int(vacancy_area_id) in user_areas:
                return 1.0
        except (ValueError, TypeError):
            pass
        
        return 0.3  # Низкий скор если локация не совпадает
    
    def _calculate_freshness_score(self, vacancy: Dict) -> float:
        """Оценка свежести вакансии"""
        try:
            published_str = vacancy.get('published_at', '')
            if not published_str:
                return 0.5
            
            # Парсинг даты (формат: 2024-01-15T10:30:00+0300)
            published_dt = datetime.fromisoformat(published_str.replace('Z', '+00:00'))
            now = datetime.now(published_dt.tzinfo)
            
            hours_ago = (now - published_dt).total_seconds() / 3600
            
            # Скор уменьшается с возрастом
            if hours_ago <= 6:
                return 1.0
            elif hours_ago <= 24:
                return 0.8
            elif hours_ago <= 72:
                return 0.6
            else:
                return 0.3
                
        except Exception as e:
            logger.debug(f"Error calculating freshness: {e}")
            return 0.5
    
    def _get_vacancy_text(self, vacancy: Dict) -> str:
        """Собирает весь текст вакансии для анализа"""
        parts = [
            vacancy.get('name', ''),
            vacancy.get('description', ''),
            vacancy.get('key_skills', [])
        ]
        
        # Если key_skills это список словарей
        if isinstance(parts[2], list):
            if parts[2] and isinstance(parts[2][0], dict):
                parts[2] = ' '.join(skill.get('name', '') for skill in parts[2])
            else:
                parts[2] = ' '.join(str(skill) for skill in parts[2])
        
        return ' '.join(str(part) for part in parts if part)
    
    def _skill_mentioned_in_text(self, skill: str, text: str) -> bool:
        """Проверяет упоминание навыка в тексте"""
        # Очистка и нормализация
        skill_clean = re.sub(r'[^\w\s]', '', skill.lower())
        
        # Точное совпадение
        if skill_clean in text:
            return True
        
        # Проверка вариаций
        variations = {
            'javascript': ['js', 'javascript'],
            'postgresql': ['postgres', 'postgresql'],
            'kubernetes': ['k8s', 'kubernetes'],
        }
        
        for var in variations.get(skill_clean, [skill_clean]):
            if re.search(r'\b' + re.escape(var) + r'\b', text):
                return True
        
        return False
    
    def _extract_experience_requirements(self, text: str) -> Optional[int]:
        """Извлекает требования к опыту из текста вакансии"""
        text_lower = text.lower()
        
        # Паттерны для поиска опыта
        patterns = [
            r'опыт[а-я\s]*(\d+)[+\-\s]*(год|лет)',
            r'(\d+)[+\-\s]*(год|лет)[а-я\s]*опыт',
            r'от\s*(\d+)\s*(год|лет)',
            r'минимум\s*(\d+)\s*(год|лет)',
            r'не менее\s*(\d+)\s*(год|лет)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                try:
                    return int(match.group(1))
                except (ValueError, IndexError):
                    continue
        
        # Поиск уровней
        if 'junior' in text_lower or 'стажер' in text_lower:
            return 0
        elif 'middle' in text_lower or 'средний' in text_lower:
            return 2
        elif 'senior' in text_lower or 'старший' in text_lower:
            return 5
        elif 'lead' in text_lower or 'ведущий' in text_lower:
            return 7
        
        return None


def test_vacancy_scorer():
    """Тест системы скоринга"""
    
    # Тестовые данные
    user_profile = {
        'exact_position': 'Python разработчик',
        'top_skills': ['Python', 'Django', 'PostgreSQL'],
        'experience_years': 3,
        'salary_from': 200000,
        'areas': [1, 2]
    }
    
    test_vacancies = [
        {
            'id': '1',
            'name': 'Python разработчик (Django)',
            'description': 'Требуется Python разработчик с опытом Django, PostgreSQL. Опыт от 2 лет.',
            'salary': {'from': 180000, 'to': 250000, 'currency': 'RUR'},
            'area': {'id': '1', 'name': 'Москва'},
            'published_at': '2024-01-15T10:00:00+0300',
            'employer': {'name': 'Отличная компания'}
        },
        {
            'id': '2', 
            'name': 'Backend developer',
            'description': 'Java developer needed. Spring Boot experience required.',
            'salary': None,
            'area': {'id': '3', 'name': 'Екатеринбург'},
            'published_at': '2024-01-14T15:00:00+0300',
            'employer': {'name': 'Другая компания'}
        }
    ]
    
    # Тестирование
    scorer = VacancyScorer()
    scored_vacancies = scorer.score_and_rank_vacancies(test_vacancies, user_profile)
    
    print("=== РЕЗУЛЬТАТЫ СКОРИНГА ===")
    for vacancy in scored_vacancies:
        print(f"Вакансия: {vacancy['name']}")
        print(f"Скор: {vacancy['score']:.3f}")
        print(f"Компания: {vacancy['employer']['name']}")
        print("---")
    
    return scored_vacancies


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_vacancy_scorer()