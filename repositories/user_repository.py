from typing import Optional
from repositories.supabase_client import SupabaseClient

class UserRepository:
    def __init__(self, supabase_client: SupabaseClient):
        self.client = supabase_client
    
    async def get_or_create_user(self, telegram_id: int, username: Optional[str] = None) -> dict:
        users = await self.client.select('users', {'telegram_id': telegram_id})
        if users:
            return users[0]
        new_user = await self.client.insert('users', {
            'telegram_id': telegram_id,
            'username': username
        })
        return new_user[0] if isinstance(new_user, list) else new_user 