# scripts/generate_invite_codes.py
import os
import sys
from sqlalchemy.orm import Session
from app.models import Organization
from app.database import SessionLocal
from app.utilites.generator import generate_invite_code

def generate_codes():
    db: Session = SessionLocal()

    try:
        orgs = db.query(Organization).filter(Organization.invite_code == None).all()
        if not orgs:
            print("No organizations found that need invite codes.")
            return

        for org in orgs:
            org.invite_code = generate_invite_code()
            print(f"Set invite_code for {org.name}: {org.invite_code}")

        db.commit()
        print("✅ Invite codes generated and saved.")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    generate_codes()