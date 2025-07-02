from typing import Optional
from repositories.supabase_client import SupabaseClient

class UserRepository:
    def __init__(self, supabase_client: SupabaseClient):
        self.client = supabase_client
    
    async def get_or_create_user(self, telegram_id: int, username: str = None) -> dict:
        # Проверяем существование
        users = await self.client.select('users', {'telegram_id': telegram_id})
        if users:
            return users[0]
        # Создаем нового
        new_user = await self.client.insert('users', {
            'telegram_id': telegram_id,
            'username': username
        })
        return new_user[0] if isinstance(new_user, list) else new_user

class ResumeRepository:
    def __init__(self, supabase_client: SupabaseClient):
        self.client = supabase_client
    
    async def save_resume(self, telegram_id: int, cv_text: str) -> dict:
        # Используем upsert для автоматического обновления
        result = await self.client.upsert(
            'user_profiles',
            {
                'telegram_id': telegram_id,
                'cv_text': cv_text,
                'updated_at': 'now()'
            },
            on_conflict='telegram_id'
        )
        return result
    
    async def get_resume(self, telegram_id: int) -> Optional[str]:
        profiles = await self.client.select(
            'user_profiles', 
            {'telegram_id': telegram_id}
        )
        if profiles:
            return profiles[0].get('cv_text')
        return None 