import aiohttp
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
    async def insert(self, table: str, data: dict) -> dict:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.url}/rest/v1/{table}",
                headers=self.headers,
                json=data
            ) as response:
                return await response.json()
    async def select(self, table: str, filters: dict = None) -> List[dict]:
        url = f"{self.url}/rest/v1/{table}"
        if filters:
            query_params = '&'.join([f"{k}=eq.{v}" for k, v in filters.items()])
            url += f"?{query_params}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers) as response:
                return await response.json()
    async def update(self, table: str, data: dict, filters: dict) -> dict:
        query_params = '&'.join([f"{k}=eq.{v}" for k, v in filters.items()])
        url = f"{self.url}/rest/v1/{table}?{query_params}"
        async with aiohttp.ClientSession() as session:
            async with session.patch(
                url,
                headers=self.headers,
                json=data
            ) as response:
                return await response.json()
    async def upsert(self, table: str, data: dict, on_conflict: str = None) -> dict:
        headers = self.headers.copy()
        if on_conflict:
            headers['Prefer'] = f'resolution=merge-duplicates,return=representation'
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.url}/rest/v1/{table}",
                headers=headers,
                json=data
            ) as response:
                return await response.json() 