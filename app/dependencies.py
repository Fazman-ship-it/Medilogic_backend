from fastapi import Depends, HTTPException, status,Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from typing import Optional
from app import models, database
from app.config import settings
from app.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/access/login")

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()
        
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User
from app.auth import verify_token


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    payload = verify_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.query(User).filter(User.id == payload.get("sub")).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user

def require_role(*allowed_roles: list[str]):
    def role_checker(current_user: models.User = Depends(get_current_user)):
        print("Debug >> User role:", str(current_user.role))
        print("Debug >> Allowed roles:", allowed_roles)
        if str(current_user.role) not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this resource",
            )
        return current_user
    return role_checker


async def get_current_user_optional(
    request: Request
) -> Optional[User]:
    try:
        return await get_current_user(request)
    except Exception:
        return None
    
from fastapi import WebSocket
from jose import JWTError

async def get_current_user_ws(websocket: WebSocket, db: Session = Depends(get_db)) -> User:
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008)  # Policy Violation
        return

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_email = payload.get("sub")
        if user_email is None:
            await websocket.close(code=1008)
            return
    except JWTError:
        await websocket.close(code=1008)
        return

    user = db.query(User).filter(User.email == user_email).first()
    if user is None:
        await websocket.close(code=1008)
        return

    return user

# app/dependencies/applicants.py
from fastapi import HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import get_current_user
from app.models import InternationalApplication

def get_current_intl_application(db: Session, user_id):
    app = db.query(InternationalApplication).filter(
        InternationalApplication.user_id == user_id
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="International application not found for user")
    return app

def require_application_fee_paid(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    app = get_current_intl_application(db, current_user.id)
    if not app.has_paid_application_fee:
        raise HTTPException(status_code=402, detail="Payment required to upload gated documents")
    return app    


