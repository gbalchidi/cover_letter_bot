import aiohttp
import json
from typing import Optional, Dict, List

class SupabaseClient:
    """Легковесный клиент для работы с Supabase без SDK"""
    
    def __init__(self, url: str, key: str):
        self.url = url
        self.headers = {
            'apikey': key,
            'Authorization': f'Bearer {key}',
            'Content-Type': 'application/json',
            'Prefer': 'return=representation'
        }
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def insert(self, table: str, data: dict) -> dict:
        """Вставка записи в таблицу"""
        if not self.session:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.url}/rest/v1/{table}",
                    headers=self.headers,
                    json=data
                ) as response:
                    return await response.json()
        else:
            async with self.session.post(
                f"{self.url}/rest/v1/{table}",
                headers=self.headers,
                json=data
            ) as response:
                return await response.json()
    
    async def select(self, table: str, filters: dict = None) -> List[dict]:
        """Выборка из таблицы"""
        url = f"{self.url}/rest/v1/{table}"
        if filters:
            query_params = '&'.join([f"{k}=eq.{v}" for k, v in filters.items()])
            url += f"?{query_params}"
        
        if not self.session:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers) as response:
                    return await response.json()
        else:
            async with self.session.get(url, headers=self.headers) as response:
                return await response.json()
    
    async def update(self, table: str, data: dict, filters: dict) -> dict:
        """Обновление записи"""
        query_params = '&'.join([f"{k}=eq.{v}" for k, v in filters.items()])
        url = f"{self.url}/rest/v1/{table}?{query_params}"
        
        if not self.session:
            async with aiohttp.ClientSession() as session:
                async with session.patch(
                    url,
                    headers=self.headers,
                    json=data
                ) as response:
                    return await response.json()
        else:
            async with self.session.patch(
                url,
                headers=self.headers,
                json=data
            ) as response:
                return await response.json()
    
    async def upsert(self, table: str, data: dict, on_conflict: str = None) -> dict:
        """Вставка или обновление"""
        headers = self.headers.copy()
        if on_conflict:
            headers['Prefer'] = f'resolution=merge-duplicates,return=representation'
        
        if not self.session:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.url}/rest/v1/{table}",
                    headers=headers,
                    json=data
                ) as response:
                    return await response.json()
        else:
            async with self.session.post(
                f"{self.url}/rest/v1/{table}",
                headers=headers,
                json=data
            ) as response:
                return await response.json() 