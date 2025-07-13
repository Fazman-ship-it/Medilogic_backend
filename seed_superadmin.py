from app.models import User
from app.database import SessionLocal
from app.auth import get_password_hash

db = SessionLocal()

hashed_pw = get_password_hash("Ademola@15")

super_admin = User(
    name="Durojaiye Ademola",
    email="ademoladurojaiye15@gmail.com",
    hashed_password=hashed_pw,
    role="super_admin",
    is_verified=True
)

db.add(super_admin)
db.commit()
db.refresh(super_admin)

print("✅ Super admin recreated with ID:", super_admin.id)
