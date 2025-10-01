"""
PostgreSQL клиент для работы с базой данных
Заменяет SupabaseClient
"""
import asyncpg
from typing import Optional, Dict, List
import logging

logger = logging.getLogger(__name__)


class PostgresClient:
    """Асинхронный клиент для работы с PostgreSQL"""

    def __init__(self, database_url: str):
        """
        Инициализация клиента

        Args:
            database_url: URL подключения к PostgreSQL
                         формат: postgresql://user:password@host:port/database
        """
        self.database_url = database_url
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Создает пул подключений к базе данных"""
        if not self.pool:
            try:
                self.pool = await asyncpg.create_pool(
                    self.database_url,
                    min_size=2,
                    max_size=10,
                    command_timeout=60
                )
                logger.info("✅ PostgreSQL connection pool created successfully")
            except Exception as e:
                logger.error(f"❌ Failed to create PostgreSQL pool: {e}")
                raise

    async def disconnect(self):
        """Закрывает пул подключений"""
        if self.pool:
            await self.pool.close()
            self.pool = None
            logger.info("PostgreSQL connection pool closed")

    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.disconnect()

    async def fetch_one(self, query: str, *args) -> Optional[Dict]:
        """
        Выполняет запрос и возвращает одну запись

        Args:
            query: SQL запрос
            *args: Параметры запроса

        Returns:
            Словарь с данными или None
        """
        if not self.pool:
            await self.connect()

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(query, *args)
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error in fetch_one: {e}")
            raise

    async def fetch_all(self, query: str, *args) -> List[Dict]:
        """
        Выполняет запрос и возвращает все записи

        Args:
            query: SQL запрос
            *args: Параметры запроса

        Returns:
            Список словарей с данными
        """
        if not self.pool:
            await self.connect()

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, *args)
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error in fetch_all: {e}")
            raise

    async def execute(self, query: str, *args) -> str:
        """
        Выполняет запрос без возврата данных (INSERT, UPDATE, DELETE)

        Args:
            query: SQL запрос
            *args: Параметры запроса

        Returns:
            Статус выполнения
        """
        if not self.pool:
            await self.connect()

        try:
            async with self.pool.acquire() as conn:
                status = await conn.execute(query, *args)
                return status
        except Exception as e:
            logger.error(f"Error in execute: {e}")
            raise

    async def execute_many(self, query: str, args_list: List[tuple]) -> None:
        """
        Выполняет множественные запросы (batch операции)

        Args:
            query: SQL запрос
            args_list: Список кортежей с параметрами
        """
        if not self.pool:
            await self.connect()

        try:
            async with self.pool.acquire() as conn:
                await conn.executemany(query, args_list)
        except Exception as e:
            logger.error(f"Error in execute_many: {e}")
            raise

    # Удобные методы для работы с таблицами

    async def insert(self, table: str, data: dict, returning: str = "*") -> Optional[Dict]:
        """
        Вставляет запись в таблицу

        Args:
            table: Название таблицы
            data: Данные для вставки
            returning: Что вернуть после вставки

        Returns:
            Вставленная запись
        """
        columns = ', '.join(data.keys())
        placeholders = ', '.join(f'${i+1}' for i in range(len(data)))
        values = list(data.values())

        query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) RETURNING {returning}"

        return await self.fetch_one(query, *values)

    async def select(self, table: str, filters: dict = None, columns: str = "*") -> List[Dict]:
        """
        Выбирает записи из таблицы

        Args:
            table: Название таблицы
            filters: Фильтры для WHERE
            columns: Колонки для выборки

        Returns:
            Список записей
        """
        query = f"SELECT {columns} FROM {table}"
        values = []

        if filters:
            where_conditions = []
            for i, (key, value) in enumerate(filters.items(), 1):
                where_conditions.append(f"{key} = ${i}")
                values.append(value)
            query += f" WHERE {' AND '.join(where_conditions)}"

        return await self.fetch_all(query, *values)

    async def update(self, table: str, data: dict, filters: dict) -> str:
        """
        Обновляет записи в таблице

        Args:
            table: Название таблицы
            data: Данные для обновления
            filters: Фильтры для WHERE

        Returns:
            Статус выполнения
        """
        set_clauses = []
        values = []
        param_idx = 1

        for key, value in data.items():
            set_clauses.append(f"{key} = ${param_idx}")
            values.append(value)
            param_idx += 1

        where_conditions = []
        for key, value in filters.items():
            where_conditions.append(f"{key} = ${param_idx}")
            values.append(value)
            param_idx += 1

        query = f"UPDATE {table} SET {', '.join(set_clauses)} WHERE {' AND '.join(where_conditions)}"

        return await self.execute(query, *values)

    async def upsert(self, table: str, data: dict, conflict_columns: List[str],
                     returning: str = "*") -> Optional[Dict]:
        """
        Вставляет или обновляет запись (INSERT ... ON CONFLICT)

        Args:
            table: Название таблицы
            data: Данные для вставки/обновления
            conflict_columns: Колонки для определения конфликта
            returning: Что вернуть после операции

        Returns:
            Результирующая запись
        """
        columns = ', '.join(data.keys())
        placeholders = ', '.join(f'${i+1}' for i in range(len(data)))
        values = list(data.values())

        # Колонки для UPDATE (исключая conflict_columns)
        update_columns = [k for k in data.keys() if k not in conflict_columns]
        update_set = ', '.join(f"{col} = EXCLUDED.{col}" for col in update_columns)

        conflict_clause = ', '.join(conflict_columns)

        query = f"""
            INSERT INTO {table} ({columns})
            VALUES ({placeholders})
            ON CONFLICT ({conflict_clause})
            DO UPDATE SET {update_set}
            RETURNING {returning}
        """

        return await self.fetch_one(query, *values)

    async def delete(self, table: str, filters: dict) -> str:
        """
        Удаляет записи из таблицы

        Args:
            table: Название таблицы
            filters: Фильтры для WHERE

        Returns:
            Статус выполнения
        """
        where_conditions = []
        values = []

        for i, (key, value) in enumerate(filters.items(), 1):
            where_conditions.append(f"{key} = ${i}")
            values.append(value)

        query = f"DELETE FROM {table} WHERE {' AND '.join(where_conditions)}"

        return await self.execute(query, *values)
