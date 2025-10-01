"""
HH.ru OAuth 2.0 Client
Handles OAuth authentication flow for HH.ru API
"""
import aiohttp
import logging
from typing import Optional, Dict
from datetime import datetime, timedelta
from urllib.parse import urlencode
import os

logger = logging.getLogger(__name__)


class HHOAuthClient:
    """OAuth 2.0 client for HH.ru API"""

    # HH.ru OAuth endpoints
    AUTHORIZE_URL = "https://hh.ru/oauth/authorize"
    TOKEN_URL = "https://hh.ru/oauth/token"

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        """
        Initialize OAuth client

        Args:
            client_id: Application ID from dev.hh.ru
            client_secret: Application secret from dev.hh.ru
            redirect_uri: Callback URL for OAuth
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    def get_authorization_url(self, state: str = None) -> str:
        """
        Generate authorization URL for user to visit

        Args:
            state: Random state string for CSRF protection (telegram_id recommended)

        Returns:
            Full authorization URL
        """
        params = {
            'response_type': 'code',
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
        }

        if state:
            params['state'] = state

        url = f"{self.AUTHORIZE_URL}?{urlencode(params)}"
        logger.info(f"Generated authorization URL for state={state}")
        return url

    async def get_access_token(self, authorization_code: str) -> Dict:
        """
        Exchange authorization code for access token

        Args:
            authorization_code: Code received from OAuth callback

        Returns:
            Dict with access_token, refresh_token, expires_in, token_type
        """
        data = {
            'grant_type': 'authorization_code',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': authorization_code,
            'redirect_uri': self.redirect_uri
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(self.TOKEN_URL, data=data) as response:
                if response.status == 200:
                    token_data = await response.json()
                    logger.info("Successfully obtained access token")
                    return token_data
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to get access token: {response.status} - {error_text}")
                    raise Exception(f"Failed to get access token: {error_text}")

    async def refresh_access_token(self, refresh_token: str) -> Dict:
        """
        Refresh access token using refresh token

        Args:
            refresh_token: Refresh token from previous authorization

        Returns:
            Dict with new access_token, refresh_token, expires_in, token_type
        """
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'client_id': self.client_id,
            'client_secret': self.client_secret
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(self.TOKEN_URL, data=data) as response:
                if response.status == 200:
                    token_data = await response.json()
                    logger.info("Successfully refreshed access token")
                    return token_data
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to refresh token: {response.status} - {error_text}")
                    raise Exception(f"Failed to refresh token: {error_text}")

    def calculate_expiry_time(self, expires_in: int) -> datetime:
        """
        Calculate token expiry timestamp

        Args:
            expires_in: Seconds until token expires

        Returns:
            Datetime when token expires
        """
        return datetime.utcnow() + timedelta(seconds=expires_in)

    async def get_user_info(self, access_token: str) -> Dict:
        """
        Get authenticated user information from HH.ru

        Args:
            access_token: Valid access token

        Returns:
            User info dict
        """
        headers = {
            'Authorization': f'Bearer {access_token}',
            'User-Agent': 'CoverLetterBot/1.0'
        }

        async with aiohttp.ClientSession() as session:
            async with session.get('https://api.hh.ru/me', headers=headers) as response:
                if response.status == 200:
                    user_data = await response.json()
                    logger.info(f"Successfully fetched user info: {user_data.get('email', 'N/A')}")
                    return user_data
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to get user info: {response.status} - {error_text}")
                    raise Exception(f"Failed to get user info: {error_text}")

    async def get_user_resumes(self, access_token: str) -> list:
        """
        Get list of user's resumes from HH.ru

        Args:
            access_token: Valid access token

        Returns:
            List of resume dicts
        """
        headers = {
            'Authorization': f'Bearer {access_token}',
            'User-Agent': 'CoverLetterBot/1.0'
        }

        async with aiohttp.ClientSession() as session:
            async with session.get('https://api.hh.ru/resumes/mine', headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    resumes = data.get('items', [])
                    logger.info(f"Successfully fetched {len(resumes)} resumes")
                    return resumes
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to get resumes: {response.status} - {error_text}")
                    raise Exception(f"Failed to get resumes: {error_text}")

    async def apply_to_vacancy(self, access_token: str, vacancy_id: str,
                              resume_id: str, message: str = None) -> Dict:
        """
        Send application to vacancy

        Args:
            access_token: Valid access token
            vacancy_id: HH.ru vacancy ID
            resume_id: User's resume ID to use
            message: Cover letter message (optional)

        Returns:
            Response from HH.ru API
        """
        headers = {
            'Authorization': f'Bearer {access_token}',
            'User-Agent': 'CoverLetterBot/1.0',
            'Content-Type': 'application/json'
        }

        data = {
            'resume_id': resume_id,
            'vacancy_id': vacancy_id
        }

        if message:
            data['message'] = message

        async with aiohttp.ClientSession() as session:
            async with session.post(
                'https://api.hh.ru/negotiations',
                headers=headers,
                json=data
            ) as response:
                response_text = await response.text()

                if response.status in [200, 201]:
                    logger.info(f"✅ Successfully applied to vacancy {vacancy_id}")
                    try:
                        return await response.json() if response_text else {}
                    except:
                        return {'status': 'success'}
                elif response.status == 400:
                    logger.warning(f"⚠️ Bad request when applying to {vacancy_id}: {response_text}")
                    raise Exception(f"Ошибка при отклике: {response_text}")
                elif response.status == 403:
                    error_data = await response.json() if response_text else {}
                    error_type = error_data.get('errors', [{}])[0].get('type', 'unknown')

                    error_messages = {
                        'invalid_vacancy': 'Вакансия архивирована или скрыта',
                        'resume_not_found': 'Резюме не найдено или удалено',
                        'limit_exceeded': 'Превышен лимит откликов',
                        'disabled_by_employer': 'Работодатель отключил отклики',
                        'resume_deleted': 'Резюме удалено',
                        'archived': 'Вакансия архивирована'
                    }

                    error_msg = error_messages.get(error_type, f'Отклик запрещен: {response_text}')
                    logger.error(f"❌ Forbidden when applying to {vacancy_id}: {error_msg}")
                    raise Exception(error_msg)
                else:
                    logger.error(f"❌ Failed to apply to vacancy {vacancy_id}: {response.status} - {response_text}")
                    raise Exception(f"Ошибка отклика: {response_text}")


# Global OAuth client instance
_oauth_client = None


def get_oauth_client() -> HHOAuthClient:
    """
    Get or create global OAuth client instance

    Returns:
        HHOAuthClient instance
    """
    global _oauth_client

    if _oauth_client is None:
        client_id = os.getenv("HH_CLIENT_ID")
        client_secret = os.getenv("HH_CLIENT_SECRET")
        redirect_uri = os.getenv("HH_REDIRECT_URI")

        if not all([client_id, client_secret, redirect_uri]):
            raise RuntimeError(
                "HH OAuth credentials not configured. "
                "Set HH_CLIENT_ID, HH_CLIENT_SECRET, and HH_REDIRECT_URI environment variables."
            )

        _oauth_client = HHOAuthClient(client_id, client_secret, redirect_uri)
        logger.info("✅ HH OAuth client initialized")

    return _oauth_client
