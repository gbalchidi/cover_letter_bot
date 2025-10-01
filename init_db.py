#!/usr/bin/env python3
"""
Database initialization script
Runs migrations automatically on startup
"""
import os
import sys
import asyncpg
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def init_database():
    """Initialize database with migrations"""
    # Get database URL from environment
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        # Fallback: construct from separate variables
        POSTGRES_USER = os.getenv("POSTGRES_USER", "bot_user")
        POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
        POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
        POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
        POSTGRES_DB = os.getenv("POSTGRES_DB", "cover_letter_bot")

        if not POSTGRES_PASSWORD:
            logger.error("DATABASE_URL or POSTGRES_PASSWORD must be set!")
            sys.exit(1)

        database_url = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

    try:
        # Connect to database
        logger.info("Connecting to database...")
        conn = await asyncpg.connect(database_url)

        # Read migration file
        logger.info("Reading migration file...")
        with open('migrations/init.sql', 'r') as f:
            migration_sql = f.read()

        # Execute migration
        logger.info("Executing migration...")
        await conn.execute(migration_sql)

        # Close connection
        await conn.close()

        logger.info("✅ Database initialized successfully!")
        return True

    except FileNotFoundError:
        logger.error("❌ Migration file not found: migrations/init.sql")
        return False
    except asyncpg.PostgresError as e:
        logger.error(f"❌ Database error: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(init_database())
    sys.exit(0 if success else 1)
