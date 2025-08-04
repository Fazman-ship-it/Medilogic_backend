from pydantic_settings import BaseSettings
# app/config.py
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
    
    #Email settings
    EMAIL_HOST: str
    EMAIL_PORT: int
    EMAIL_USERNAME: str
    EMAIL_PASSWORD: str
    EMAIL_FROM: str
    
    DELIVERY_CONFIRM_SECRET: str
    DELIVERY_CONFIRM_EXPIRY_MINUTES:int
    DELIVERY_CONFIRMATION_URL: str
    FRONTEND_CONFIRM_SUCCESS_URL: str


    class Config:
        env_file = ".env"

settings = Settings()