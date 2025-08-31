from pydantic_settings import BaseSettings
import os
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
    STRIPE_SECRET_KEY: str


    class Config:
        env_file = ".env"

settings = Settings()

# Automatically create upload directory if it doesn't exist
UPLOAD_DIR = os.path.join("app", "uploads", "pods")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Subfolders for raw and processed files
UPLOAD_DIR_RAW = os.path.join(UPLOAD_DIR, "raw")
UPLOAD_DIR_PDF = os.path.join(UPLOAD_DIR, "pdf")

os.makedirs(UPLOAD_DIR_RAW, exist_ok=True)
os.makedirs(UPLOAD_DIR_PDF, exist_ok=True)
