import uuid

class UserRepository:
    def __init__(self, supabase):
        self.supabase = supabase

    async def get_or_create_user(self, telegram_id):
        # Проверяем, есть ли пользователь
        response = self.supabase.table('users').select('*').eq('telegram_id', telegram_id).execute()
        if response.data:
            return response.data[0]
        # Если нет — создаём
        user_id = str(uuid.uuid4())
        response = self.supabase.table('users').insert({
            'id': user_id,
            'telegram_id': telegram_id
        }).execute()
        return response.data[0] 