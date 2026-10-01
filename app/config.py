from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    app_env: str = 'development'
    database_url: str = 'sqlite:///./crm.db'
    public_base_url: str = 'http://localhost:8000'
    crm_username: str = 'admin'
    crm_password: str = 'change-me-local'
    app_secret: str = 'change-me-local-secret'
    telegram_bot_token: str = ''
    telegram_webhook_secret: str = ''

    def validate_production(self):
        if self.app_env != 'production':
            return
        if not self.database_url.startswith('postgresql'):
            raise ValueError('Production requires PostgreSQL')
        if not self.public_base_url.startswith('https://'):
            raise ValueError('Production requires HTTPS PUBLIC_BASE_URL')
        if len(self.crm_password) < 20 or len(self.app_secret) < 32:
            raise ValueError('Configure strong CRM_PASSWORD and APP_SECRET')
        if not self.telegram_bot_token or len(self.telegram_webhook_secret) < 32:
            raise ValueError('Configure Telegram secrets before production startup')
