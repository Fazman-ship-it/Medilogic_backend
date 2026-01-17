from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from passlib.context import CryptContext

from app import models

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ✅ HARD-CODED DATABASE URL (paste your Neon connection string here)
DATABASE_URL = 'postgresql://neondb_owner:npg_7hr2HZEwdNpa@ep-purple-hat-abx30txl-pooler.eu-west-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require'
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def main():
    email = "ademoladurojaiye15@gmail.com"
    password = "Ademola@15"
    name = "Durojaiye Ademola"

    db = SessionLocal()

    existing = db.query(models.User).filter(models.User.email == email).first()
    if existing:
        print("User already exists:", existing.email)
        return

    user = models.User(
        name=name,
        email=email,
        hashed_password=pwd_context.hash(password),
        role="super_admin",
        is_active=True,
        is_verified=True,
        is_superuser=True,
        organization_id=None,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    print("✅ Super admin created")
    print("Email:", email)
    print("Temp Password:", password)
    print("User ID:", user.id)

if __name__ == "__main__":
    main()