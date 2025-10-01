# Настройка HH.ru OAuth

## 📝 Шаг 1: Регистрация приложения на HH.ru

1. Перейдите на https://dev.hh.ru/
2. Войдите в свой аккаунт HH.ru
3. Нажмите "Создать приложение"
4. Заполните форму:
   - **Название приложения**: Cover Letter Bot
   - **Описание**: Telegram бот для автоматической генерации cover letter
   - **Redirect URI**: `https://your-domain.com/hh/callback`
     - Для локальной разработки: `http://localhost:8080/hh/callback`
     - Для прод: ваш домен в Coolify
   - **Тип приложения**: Веб-приложение

5. После создания вы получите:
   - **Client ID** - идентификатор приложения
   - **Client Secret** - секретный ключ

## ⚙️ Шаг 2: Настройка переменных окружения

Добавьте в `.env` файл:

```env
# HH.ru OAuth Configuration
HH_CLIENT_ID=your_client_id_here
HH_CLIENT_SECRET=your_client_secret_here
HH_REDIRECT_URI=https://your-domain.com/hh/callback
```

## 🚀 Шаг 3: Запуск OAuth Webhook сервера

### Локально

```bash
# В одном терминале запустите webhook сервер
python oauth_webhook.py

# В другом терминале запустите бота
python main_secure.py
```

### Docker

```bash
docker-compose up -d
```

Это запустит:
- PostgreSQL на порту 5432
- OAuth Webhook на порту 8080
- Telegram Bot

## 📱 Шаг 4: Авторизация пользователя

1. Пользователь отправляет `/hh_auth` в Telegram боте
2. Бот отправляет кнопку с OAuth URL
3. Пользователь переходит по ссылке и авторизуется на HH.ru
4. HH.ru перенаправляет на `https://your-domain.com/hh/callback?code=xxx&state=telegram_id`
5. Webhook сервер:
   - Обменивает `code` на `access_token`
   - Сохраняет токены в базу данных
   - Получает список резюме пользователя
   - Сохраняет резюме в базу
6. Пользователь видит сообщение об успешной авторизации

## 🔧 Доступные команды

### OAuth команды

- `/hh_auth` - Начать авторизацию на HH.ru
- `/hh_status` - Проверить статус авторизации
- `/hh_resumes` - Посмотреть список резюме на HH.ru
- `/hh_logout` - Выйти из аккаунта HH.ru
- `/hh_apply <vacancy_id>` - Откликнуться на вакансию вручную

### Основные команды

- `/start` - Начать работу с ботом
- `/reset` - Обновить резюме
- `/show_cv` - Показать сохраненное резюме

## 🌐 Настройка для Coolify

### 1. Добавьте переменные окружения в Coolify

В интерфейсе Coolify добавьте:

```
BOT_TOKEN=your_telegram_bot_token
OPENAI_API_KEY=your_openai_api_key
POSTGRES_PASSWORD=your_secure_password
HH_CLIENT_ID=your_hh_client_id
HH_CLIENT_SECRET=your_hh_client_secret
HH_REDIRECT_URI=https://your-coolify-domain.com/hh/callback
```

### 2. Настройте порты

OAuth Webhook использует порт **8080**.
В Coolify убедитесь, что порт 8080 проброшен наружу.

### 3. Настройте domain для OAuth callback

В настройках Coolify:
1. Добавьте домен для сервиса `oauth_webhook`
2. Убедитесь, что SSL сертификат настроен
3. Обновите `HH_REDIRECT_URI` на правильный домен

### 4. Обновите Redirect URI в приложении HH.ru

На https://dev.hh.ru/ обновите Redirect URI на:
```
https://your-coolify-domain.com/hh/callback
```

## 🔐 Безопасность

### OAuth State Parameter

Используется `telegram_id` как `state` parameter для защиты от CSRF атак.

### Token Storage

Токены хранятся в PostgreSQL с шифрованием на уровне базы данных.

### Token Refresh

Access tokens HH.ru действительны 2 недели.
Refresh tokens могут использоваться для получения новых access tokens.

## 🐛 Troubleshooting

### Ошибка "OAuth credentials not configured"

**Решение**: Убедитесь, что переменные окружения `HH_CLIENT_ID`, `HH_CLIENT_SECRET`, `HH_REDIRECT_URI` установлены.

### Ошибка "Invalid redirect_uri"

**Решение**:
1. Проверьте, что `HH_REDIRECT_URI` в `.env` совпадает с redirect URI в приложении на dev.hh.ru
2. Убедитесь, что URL использует HTTPS (для продакшена)

### Webhook не получает callback

**Решение**:
1. Проверьте, что webhook сервер запущен (`docker logs cover_letter_bot_webhook`)
2. Проверьте, что порт 8080 доступен извне
3. Проверьте логи: `docker logs cover_letter_bot_webhook -f`

### Ошибка "Failed to get access token"

**Проверьте**:
1. Client ID и Client Secret правильные
2. Authorization code не истек (используется один раз)
3. Redirect URI совпадает

## 📊 Архитектура

```
┌─────────────┐
│   Telegram  │
│     User    │
└──────┬──────┘
       │ /hh_auth
       ▼
┌─────────────────┐
│ Telegram Bot    │
│ (main_secure.py)│
└────────┬────────┘
         │ Sends OAuth URL
         ▼
┌─────────────────┐
│    HH.ru OAuth  │
│   Authorization │
└────────┬────────┘
         │ Redirects with code
         ▼
┌─────────────────┐
│ OAuth Webhook   │
│(oauth_webhook.py│
└────────┬────────┘
         │ Exchange code for token
         │ Save to database
         ▼
┌─────────────────┐
│   PostgreSQL    │
│ hh_oauth_tokens │
│ hh_user_resumes │
└─────────────────┘
```

## ✅ Проверка работы

1. Запустите бота и webhook
2. Отправьте `/hh_auth`
3. Перейдите по ссылке и авторизуйтесь
4. Проверьте, что видите сообщение "Авторизация успешна"
5. В Telegram отправьте `/hh_status` - должен показать активную авторизацию
6. Отправьте `/hh_resumes` - должен показать ваши резюме с HH.ru

Готово! 🎉
