# Руководство по миграции с Supabase на PostgreSQL

## 📋 Что изменилось

- **Удалено**: Зависимость от Supabase SDK
- **Добавлено**: Прямое подключение к PostgreSQL через `asyncpg`
- **Новые таблицы**:
  - `hh_oauth_tokens` - для хранения OAuth токенов HH.ru
  - `hh_user_resumes` - для хранения резюме пользователей с HH.ru
  - `sent_vacancies` - для отслеживания отправленных откликов

## 🚀 Шаги миграции

### 1. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 2. Настройка переменных окружения

Скопируйте `.env.example` в `.env` и заполните переменные:

```bash
cp .env.example .env
```

Отредактируйте `.env`:

```env
BOT_TOKEN=your_telegram_bot_token
OPENAI_API_KEY=your_openai_api_key
DATABASE_URL=postgresql://bot_user:password@localhost:5432/cover_letter_bot
```

### 3. Запуск PostgreSQL через Docker

```bash
docker-compose up -d postgres
```

Это создаст:
- PostgreSQL контейнер
- Автоматически применит миграции из `migrations/init.sql`
- Создаст volume для сохранения данных

### 4. Проверка подключения к базе данных

```bash
docker exec -it cover_letter_bot_db psql -U bot_user -d cover_letter_bot
```

Проверьте таблицы:

```sql
\dt
```

Вы должны увидеть:
- users
- user_profiles
- sent_vacancies
- hh_oauth_tokens
- hh_user_resumes

### 5. Миграция данных из Supabase (опционально)

Если у вас есть данные в Supabase, экспортируйте их:

1. В Supabase зайдите в SQL Editor
2. Экспортируйте данные из таблиц `users` и `user_profiles`
3. Импортируйте в PostgreSQL:

```bash
psql -U bot_user -d cover_letter_bot < your_export.sql
```

### 6. Запуск бота

```bash
python main_secure.py
```

Или через Docker:

```bash
docker-compose up -d
```

## 📦 Деплой в Coolify

### 1. Создайте приложение в Coolify

1. В Coolify создайте новое приложение (Docker Compose)
2. Укажите репозиторий Git

### 2. Добавьте переменные окружения

В настройках приложения добавьте:

```env
BOT_TOKEN=your_telegram_bot_token
OPENAI_API_KEY=your_openai_api_key
POSTGRES_PASSWORD=secure_password_here
HH_CLIENT_ID=your_hh_client_id
HH_CLIENT_SECRET=your_hh_client_secret
```

### 3. Подключение к PostgreSQL в Coolify

Coolify автоматически создаст PostgreSQL контейнер.
DATABASE_URL будет сформирован автоматически.

### 4. Деплой

Нажмите "Deploy" в Coolify. Приложение автоматически:
1. Соберет Docker образ
2. Запустит PostgreSQL
3. Применит миграции
4. Запустит бота

## 🔧 Troubleshooting

### Ошибка подключения к PostgreSQL

```
asyncpg.exceptions.InvalidCatalogNameError: database "cover_letter_bot" does not exist
```

**Решение**: Создайте базу данных вручную:

```bash
docker exec -it cover_letter_bot_db createdb -U bot_user cover_letter_bot
```

### Ошибка миграции

```
relation "users" already exists
```

**Решение**: Миграции уже применены. Пропустите этот шаг.

### Бот не запускается

Проверьте логи:

```bash
docker logs cover_letter_bot
docker logs cover_letter_bot_db
```

## 📝 Полезные команды

### Подключение к базе данных

```bash
docker exec -it cover_letter_bot_db psql -U bot_user -d cover_letter_bot
```

### Просмотр таблиц

```sql
SELECT * FROM users;
SELECT * FROM user_profiles;
SELECT * FROM hh_oauth_tokens;
```

### Очистка базы данных

```bash
docker-compose down -v  # Удалит volumes с данными
docker-compose up -d    # Пересоздаст базу
```

### Бэкап базы данных

```bash
docker exec cover_letter_bot_db pg_dump -U bot_user cover_letter_bot > backup.sql
```

### Восстановление из бэкапа

```bash
cat backup.sql | docker exec -i cover_letter_bot_db psql -U bot_user -d cover_letter_bot
```

## ✅ Проверка работоспособности

1. Запустите бота
2. Отправьте `/start` в Telegram
3. Загрузите резюме
4. Проверьте, что данные сохранились:

```sql
SELECT * FROM users;
SELECT * FROM user_profiles;
```

Готово! 🎉
