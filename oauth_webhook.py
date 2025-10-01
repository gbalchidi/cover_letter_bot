"""
OAuth Callback Webhook Server
Handles HH.ru OAuth callbacks
"""
from aiohttp import web
import logging
from hh_oauth_client import get_oauth_client
from repositories.postgres_client import PostgresClient
from repositories.repositories import HHOAuthRepository, HHUserResumesRepository
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Global repositories
oauth_repo = None
resumes_repo = None


async def init_repositories():
    """Initialize database repositories"""
    global oauth_repo, resumes_repo

    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        POSTGRES_USER = os.getenv("POSTGRES_USER", "bot_user")
        POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
        POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
        POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
        POSTGRES_DB = os.getenv("POSTGRES_DB", "cover_letter_bot")
        DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

    pg_client = PostgresClient(DATABASE_URL)
    await pg_client.connect()

    oauth_repo = HHOAuthRepository(pg_client)
    resumes_repo = HHUserResumesRepository(pg_client)

    return pg_client


async def oauth_callback(request):
    """
    Handle OAuth callback from HH.ru

    Query params:
        - code: Authorization code
        - state: User's telegram_id
    """
    try:
        code = request.query.get('code')
        state = request.query.get('state')  # telegram_id
        error = request.query.get('error')

        if error:
            logger.error(f"OAuth error: {error}")
            return web.Response(
                text=f"""
                <html>
                <head><meta charset="utf-8"></head>
                <body>
                    <h1>❌ Ошибка авторизации</h1>
                    <p>{error}</p>
                    <p>Вернитесь в Telegram и попробуйте снова.</p>
                </body>
                </html>
                """,
                content_type='text/html'
            )

        if not code or not state:
            return web.Response(
                text="Missing code or state parameter",
                status=400
            )

        telegram_id = int(state)

        # Exchange code for tokens
        oauth_client = get_oauth_client()
        token_data = await oauth_client.get_access_token(code)

        # Calculate expiry time
        expires_at = datetime.utcnow() + timedelta(seconds=token_data.get('expires_in', 3600))

        # Save tokens to database
        await oauth_repo.save_tokens(
            telegram_id=telegram_id,
            access_token=token_data['access_token'],
            refresh_token=token_data.get('refresh_token'),
            expires_at=expires_at
        )

        # Fetch user's resumes
        try:
            resumes = await oauth_client.get_user_resumes(token_data['access_token'])

            # Save resumes to database
            for i, resume in enumerate(resumes):
                await resumes_repo.save_resume(
                    telegram_id=telegram_id,
                    resume_id=resume['id'],
                    resume_title=resume.get('title', 'Резюме'),
                    is_default=(i == 0)  # First resume is default
                )

            logger.info(f"✅ OAuth successful for telegram_id={telegram_id}, saved {len(resumes)} resumes")

        except Exception as e:
            logger.error(f"Failed to fetch resumes: {e}")

        return web.Response(
            text=f"""
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        max-width: 600px;
                        margin: 50px auto;
                        text-align: center;
                        padding: 20px;
                    }}
                    h1 {{ color: #4CAF50; }}
                    p {{ font-size: 18px; }}
                </style>
            </head>
            <body>
                <h1>✅ Авторизация успешна!</h1>
                <p>Вы успешно подключили свой аккаунт HH.ru</p>
                <p>Вернитесь в Telegram, чтобы продолжить работу с ботом</p>
            </body>
            </html>
            """,
            content_type='text/html'
        )

    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        return web.Response(
            text=f"""
            <html>
            <head><meta charset="utf-8"></head>
            <body>
                <h1>❌ Ошибка</h1>
                <p>Произошла ошибка при авторизации: {str(e)}</p>
                <p>Попробуйте снова через бота в Telegram</p>
            </body>
            </html>
            """,
            content_type='text/html',
            status=500
        )


async def health_check(request):
    """Health check endpoint"""
    return web.Response(text="OK")


async def start_webhook_server(host='0.0.0.0', port=8080):
    """
    Start OAuth webhook server

    Args:
        host: Host to bind to
        port: Port to bind to
    """
    await init_repositories()

    app = web.Application()
    app.router.add_get('/hh/callback', oauth_callback)
    app.router.add_get('/health', health_check)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, host, port)
    await site.start()

    logger.info(f"✅ OAuth webhook server started on {host}:{port}")
    return runner


if __name__ == '__main__':
    import asyncio

    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )

    async def main():
        await start_webhook_server()
        # Keep server running
        await asyncio.Event().wait()

    asyncio.run(main())
