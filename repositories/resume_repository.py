import uuid
from datetime import datetime

class ResumeRepository:
    def __init__(self, supabase):
        self.supabase = supabase

    async def save_resume(self, user_id, content_text, storage_path=None, file_name=None, file_type=None, file_size=None, parsed_data=None):
        resume_id = str(uuid.uuid4())
        data = {
            'id': resume_id,
            'user_id': user_id,
            'content_text': content_text,
            'storage_path': storage_path,
            'file_name': file_name,
            'file_type': file_type,
            'file_size': file_size,
            'parsed_data': parsed_data,
            'is_active': True,
            'created_at': datetime.utcnow().isoformat()
        }
        # Деактивируем старые резюме
        self.supabase.table('resumes').update({'is_active': False}).eq('user_id', user_id).execute()
        # Сохраняем новое
        response = self.supabase.table('resumes').insert(data).execute()
        return response.data[0]

    async def get_active_resume(self, user_id):
        response = self.supabase.table('resumes').select('*').eq('user_id', user_id).eq('is_active', True).limit(1).execute()
        if response.data:
            return response.data[0]['content_text']
        return None 