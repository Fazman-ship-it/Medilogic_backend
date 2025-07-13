from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings
from sqlalchemy.ext.declarative import as_declarative
DATABASE_URL = (
    f"postgresql://{settings.DB_USER}:{settings.DB_PASSWORD}"
    f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

#Add this function here (this is what was missing)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

from app.models import Base  # Or wherever your Base is defined

def create_tables():
    Base.metadata.create_all(bind=engine)        