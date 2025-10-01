# Автоматическая миграция БД

## Как это работает

При запуске любого контейнера приложения (бот или webhook) автоматически:

1. ✅ Ждет готовности PostgreSQL
2. ✅ Выполняет миграции из `migrations/init.sql`
3. ✅ Запускает основное приложение

## Файлы автоматической миграции

### `entrypoint.sh`
- Shell-скрипт, который запускается первым при старте контейнера
- Проверяет доступность PostgreSQL
- Запускает `init_db.py` для применения миграций
- Запускает основное приложение

### `init_db.py`
- Python-скрипт для применения SQL миграций
- Читает файл `migrations/init.sql`
- Выполняет SQL-команды в базе данных
- Использует `CREATE TABLE IF NOT EXISTS`, поэтому безопасно запускать многократно

## Развертывание в Coolify

### Вариант 1: Docker Compose (рекомендуется)

```bash
# Просто запустите docker-compose
docker-compose up -d
```

Миграции применятся автоматически при первом запуске бота и webhook.

### Вариант 2: Отдельные сервисы в Coolify

Если разворачиваете бот и webhook как отдельные сервисы:

1. **Создайте PostgreSQL базу данных в Coolify**
   - Resources → New → Database → PostgreSQL
   - Назовите `cover-letter-bot-db`

2. **Создайте OAuth Webhook сервис**
   - Resources → New → Application
   - Git Repository: ваш репозиторий
   - Build Pack: Dockerfile
   - Command: `python oauth_webhook.py`
   - Environment Variables:
     ```
     DATABASE_URL=postgresql://user:pass@postgres:5432/cover_letter_bot
     HH_CLIENT_ID=...
     HH_CLIENT_SECRET=...
     HH_REDIRECT_URI=...
     ```
   - Port: 8080

3. **Создайте Telegram Bot сервис**
   - Resources → New → Application
   - Git Repository: ваш репозиторий
   - Build Pack: Dockerfile
   - Command: `python main_secure.py`
   - Environment Variables:
     ```
     BOT_TOKEN=...
     OPENAI_API_KEY=...
     DATABASE_URL=postgresql://user:pass@postgres:5432/cover_letter_bot
     HH_CLIENT_ID=...
     HH_CLIENT_SECRET=...
     HH_REDIRECT_URI=...
     ```

**Важно**: При первом запуске любого из сервисов (webhook или bot) миграции применятся автоматически.

## Проверка миграций

После запуска проверьте логи контейнера:

```bash
docker logs <container_name>
```

Вы должны увидеть:
```
🔄 Starting application initialization...
⏳ Waiting for PostgreSQL to be ready...
✅ PostgreSQL is ready!
📦 Running database migrations...
✅ Database initialized successfully!
🚀 Starting application: python main_secure.py
```

## Ручной запуск миграций

Если нужно применить миграции вручную:

```bash
# Через docker exec
docker exec -it <container_name> python init_db.py

# Или напрямую через psql
docker exec -i postgres-container psql -U bot_user -d cover_letter_bot < migrations/init.sql
```

## Добавление новых миграций

1. Создайте новый SQL файл в `migrations/`:
   ```
   migrations/002_add_new_table.sql
   ```

2. Обновите `init_db.py` для загрузки всех миграций:
   ```python
   import glob
   migration_files = sorted(glob.glob('migrations/*.sql'))
   for migration_file in migration_files:
       with open(migration_file, 'r') as f:
           await conn.execute(f.read())
   ```

3. Или просто добавьте SQL в `migrations/init.sql` (используя `CREATE TABLE IF NOT EXISTS`)

## Troubleshooting

### Ошибка "Migration file not found"
- Убедитесь, что `migrations/init.sql` существует в образе Docker
- Проверьте, что `COPY . .` в Dockerfile копирует папку migrations

### Ошибка "Database error"
- Проверьте DATABASE_URL
- Убедитесь, что PostgreSQL запущен и доступен
- Проверьте права доступа пользователя БД

### Миграции не применяются
- Проверьте логи: `docker logs <container>`
- Убедитесь, что entrypoint.sh исполняемый: `chmod +x entrypoint.sh`
- Проверьте, что в Dockerfile есть `RUN chmod +x entrypoint.sh`
