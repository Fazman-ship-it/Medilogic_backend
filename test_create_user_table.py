from app.database import engine
from app import models
print("🔄 Creating tables in the database...")
# Create all tables
models.Base.metadata.create_all(bind=engine)
print("✅ All tables created successfully.")

