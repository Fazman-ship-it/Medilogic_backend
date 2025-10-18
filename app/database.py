from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings
from sqlalchemy.exc import OperationalError
import time

# ✅ Construct full connection URL (with SSL required for Neon)
DATABASE_URL = (
    f"postgresql+psycopg2://{settings.DB_USER}:{settings.DB_PASSWORD}"
    f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}?sslmode=require"
)

# ✅ Create a stable engine with automatic reconnection and pool health checks
def create_stable_engine():
    for attempt in range(5):
        try:
            engine = create_engine(
                DATABASE_URL,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,        # checks connection before using it
                pool_recycle=1800,         # recycle stale connections every 30 mins
                connect_args={"connect_timeout": 10},
            )
            # ✅ Test connection safely (SQLAlchemy 2.x requires `text()`)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("✅ Database connection established successfully.")
            return engine
        except OperationalError as e:
            print(f"⚠️ Database connection failed (attempt {attempt + 1}/5): {e}")
            time.sleep(2)
    raise RuntimeError("❌ Could not connect to the database after 5 attempts.")

# ✅ Initialize engine
engine = create_stable_engine()

# ✅ Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ✅ Dependency for FastAPI routes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()