# Telegram Cover Letter Bot

AI бот для создания сопроводительных писем к вакансиям на основе анализа резюме и описания позиции.

## 🚀 Возможности

- **AI анализ резюме** - автоматическое извлечение ключевых навыков и опыта
- **Анализ вакансий** - парсинг требований и описания позиций
- **Создание писем** - генерация персонализированных сопроводительных писем
- **Скоринг вакансий** - оценка релевантности вакансий для кандидата
- **Автоматизация** - планировщик для регулярного поиска вакансий

## 🛠 Технологии

- **Python 3.8+** - основной язык программирования
- **Supabase** - база данных и аутентификация
- **HH.ru API** - интеграция с HeadHunter
- **AI/ML** - машинное обучение для анализа текста
- **Telegram Bot API** - интерфейс пользователя

## 📦 Установка

1. Клонируйте репозиторий:
```bash
git clone <repository-url>
cd telegram-cover-letter-bot
```

2. Установите зависимости:
```bash
pip install -r requirements.txt
```

3. Настройте конфигурацию:
```bash
cp config_template.py config.py
# Отредактируйте config.py с вашими настройками
```

4. Запустите бота:
```bash
python main_secure.py
```

## 🎯 Структура проекта

```
telegram-cover-letter-bot/
├── main_secure.py          # Основной файл бота
├── hh_client.py            # Клиент для HH.ru API
├── resume_analyzer.py      # Анализатор резюме
├── vacancy_scorer.py       # Система скоринга вакансий
├── scheduler.py            # Планировщик задач
├── auto_scheduler.py       # Автоматическое планирование
├── repositories/            # Репозитории для работы с данными
│   ├── supabase_client.py  # Клиент Supabase
│   ├── user_repository.py  # Работа с пользователями
│   └── resume_repository.py # Работа с резюме
├── requirements.txt         # Python зависимости
└── config_template.py      # Шаблон конфигурации
```

## 🔧 Конфигурация

Создайте файл `config.py` на основе `config_template.py`:

```python
# Telegram Bot
TELEGRAM_TOKEN = "your_telegram_bot_token"

# Supabase
SUPABASE_URL = "your_supabase_url"
SUPABASE_KEY = "your_supabase_anon_key"

# HH.ru API
HH_CLIENT_ID = "your_hh_client_id"
HH_CLIENT_SECRET = "your_hh_client_secret"

# Настройки
MAX_VACANCIES_PER_REQUEST = 100
RELEVANCE_THRESHOLD = 0.25
```

## 📊 Основные модули

### VacancyScorer
Система скоринга вакансий по релевантности:
- Анализ совпадения навыков
- Оценка соответствия опыта
- Учет зарплатных ожиданий
- Географическое соответствие

### ResumeAnalyzer
Анализ резюме и извлечение ключевой информации:
- Навыки и технологии
- Опыт работы
- Образование
- Ключевые достижения

### HhClient
Клиент для работы с HH.ru API:
- Поиск вакансий
- Получение деталей вакансий
- Аутентификация и авторизация

## 🚀 Использование

1. **Запуск бота**: `python main_secure.py`
2. **Настройка планировщика**: `python auto_scheduler.py`
3. **Тестирование скоринга**: `python vacancy_scorer.py`

## 📱 Telegram Bot

Бот поддерживает следующие команды:
- `/start` - начало работы
- `/help` - справка
- `/resume` - загрузка резюме
- `/search` - поиск вакансий
- `/settings` - настройки

## 🔒 Безопасность

- Все токены хранятся в переменных окружения
- Данные пользователей шифруются
- API ключи не попадают в код
- Безопасное хранение в Supabase

## 📄 Лицензия

MIT License

## 🌐 Веб-сайт

Лендинг страница проекта находится в отдельной папке: `telegram-cover-letter-landing/`
