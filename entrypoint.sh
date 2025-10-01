#!/bin/bash
set -e

echo "🔄 Starting application initialization..."

# Wait for PostgreSQL to be ready
echo "⏳ Waiting for PostgreSQL to be ready..."
until python3 -c "
import asyncpg
import asyncio
import os
import sys

async def check():
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        POSTGRES_USER = os.getenv('POSTGRES_USER', 'bot_user')
        POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD')
        POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
        POSTGRES_PORT = os.getenv('POSTGRES_PORT', '5432')
        POSTGRES_DB = os.getenv('POSTGRES_DB', 'cover_letter_bot')
        database_url = f'postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}'

    try:
        conn = await asyncpg.connect(database_url, timeout=2)
        await conn.close()
        return True
    except:
        return False

result = asyncio.run(check())
sys.exit(0 if result else 1)
" 2>/dev/null; do
  echo "PostgreSQL is unavailable - sleeping"
  sleep 2
done

echo "✅ PostgreSQL is ready!"

# Run database migrations
echo "📦 Running database migrations..."
python3 init_db.py

if [ $? -eq 0 ]; then
    echo "✅ Database migrations completed successfully!"
else
    echo "⚠️  Database migrations had issues, but continuing..."
fi

# Start the application
echo "🚀 Starting application: $@"
exec "$@"
