# app/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DB_HOST: str
    DB_PORT: str
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    OPENAI_API_KEY: str
    REFRESH_TOKEN_EXPIRE_MINUTES: int
    REFRESH_SECRET_KEY: str

    # Email settings
    EMAIL_HOST: str
    EMAIL_PORT: int
    EMAIL_USERNAME: str
    EMAIL_PASSWORD: str
    EMAIL_FROM: str

    DELIVERY_CONFIRM_SECRET: str
    DELIVERY_CONFIRM_EXPIRY_MINUTES: int
    DELIVERY_CONFIRMATION_URL: str
    FRONTEND_CONFIRM_SUCCESS_URL: str
    STRIPE_SECRET_KEY: str
    STRIPE_WEBHOOK_SECRET: str
    STRIPE_APPLICATION_FEE_PRICE_ID: str
    STRIPE_GREEN_PRICE_ID: str
    STRIPE_BLUE_PRICE_ID: str
    APPLICATION_FEE_AMOUNT: int
    FRONTEND_SUCCESS_URL: str
    FRONTEND_CANCEL_URL: str

    # AWS S3
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_REGION: str
    AWS_S3_BUCKET: str
    USE_S3: bool
    PRESIGNED_EXPIRY: int

    class Config:
        env_file = ".env"

settings = Settings()