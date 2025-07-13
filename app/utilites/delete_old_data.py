from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import User, Trip

def delete_expired_data():
    db: Session = SessionLocal()
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=3 * 365)  # 3 years

        # Delete users older than 3 years with no activity
        old_users = db.query(User).filter(User.created_at < cutoff_date).all()
        for user in old_users:
            db.delete(user)

        # Delete trips older than 3 years
        old_trips = db.query(Trip).filter(Trip.created_at < cutoff_date).all()
        for trip in old_trips:
            db.delete(trip)

        db.commit()
        print(f"[✅] Cleanup complete: deleted {len(old_users)} users, {len(old_trips)} trips.")
    except Exception as e:
        db.rollback()
        print(f"[❌] Error during cleanup: {e}")
    finally:
        db.close()