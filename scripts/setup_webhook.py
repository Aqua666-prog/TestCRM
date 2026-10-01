"""Run from repository root: python -m scripts.setup_webhook."""
import sys
import httpx
from app.config import Settings


def main():
    settings = Settings()
    settings.validate_production()
    if not settings.telegram_bot_token or not settings.telegram_webhook_secret:
        sys.exit('Configure TELEGRAM_BOT_TOKEN and TELEGRAM_WEBHOOK_SECRET')
    if not settings.public_base_url.startswith('https://'):
        sys.exit('PUBLIC_BASE_URL must be HTTPS')
    try:
        with httpx.Client(timeout=20) as client:
            base = 'https://api.telegram.org/bot' + settings.telegram_bot_token
            result = client.post(base + '/setWebhook', json={
                'url': settings.public_base_url.rstrip('/') + '/telegram/webhook',
                'secret_token': settings.telegram_webhook_secret,
                'max_connections': 1, 'allowed_updates': ['message'],
                'drop_pending_updates': False}).json()
            if not result.get('ok'):
                sys.exit('Telegram rejected webhook configuration; check secrets and HTTPS.')
            info = client.get(base + '/getWebhookInfo').json()
            if not info.get('ok') or info['result'].get('url') != settings.public_base_url.rstrip('/') + '/telegram/webhook':
                sys.exit('Webhook verification failed')
    except (httpx.HTTPError, ValueError):
        sys.exit('Telegram is unreachable; configuration not verified.')
    print('Webhook configured and endpoint verified. Now run the real Telegram acceptance test.')


if __name__ == '__main__':
    main()
