from __future__ import annotations

import hashlib
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.user import User
from app.schemas.auth import AuthResponse, LoginRequest, SignupRequest

router = APIRouter(prefix='/api/auth')
security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 200000)
    return f'{salt}${digest.hex()}'


def verify_password(password: str, stored_hash: str) -> bool:
    if not stored_hash or '$' not in stored_hash:
        return False
    salt, digest = stored_hash.split('$', 1)
    generated = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        200000,
    )
    return hashlib.compare_digest(generated.hex(), digest)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    database: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Authentication required.')

    token = credentials.credentials
    statement = select(User).where(User.session_token == token)
    user = database.execute(statement).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid or expired session.')
    return user


@router.post('/signup')
async def signup(payload: SignupRequest, database: Session = Depends(get_db)):
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Passwords do not match.')

    existing = database.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='An account with this email already exists.')

    user = User(
        name=payload.name.strip(),
        email=payload.email,
        password_hash=hash_password(payload.password),
        session_token=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    database.add(user)
    database.commit()
    database.refresh(user)

    token = secrets.token_urlsafe(32)
    user.session_token = token
    database.commit()
    database.refresh(user)

    return {
        'token': token,
        'user': {'id': user.id, 'name': user.name, 'email': user.email},
    }


@router.post('/login')
async def login(payload: LoginRequest, database: Session = Depends(get_db)):
    user = database.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Email or password is incorrect.')

    token = secrets.token_urlsafe(32)
    user.session_token = token
    database.commit()
    database.refresh(user)

    return {
        'token': token,
        'user': {'id': user.id, 'name': user.name, 'email': user.email},
    }


@router.get('/me')
async def get_current_user_profile(current_user: User = Depends(get_current_user)):
    return {
        'id': current_user.id,
        'name': current_user.name,
        'email': current_user.email,
    }


@router.post('/logout')
async def logout(current_user: User = Depends(get_current_user), database: Session = Depends(get_db)):
    current_user.session_token = None
    database.commit()
    return {'status': 'ok'}


@router.post('/forgot-password')
async def request_password_reset():
    return {
        'status': 'not_configured',
        'message': 'Password reset is not configured yet. This flow will be connected to a secure email provider in a future release.',
    }
