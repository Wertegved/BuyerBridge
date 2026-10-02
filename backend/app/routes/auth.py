from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database.connection import get_db
from app.models.session import Session as SessionRecord
from app.models.user import User
from app.schemas.auth import LoginRequest, SignupRequest

router = APIRouter(prefix='/api/auth')
security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 200000)
    return f'pbkdf2_sha256${salt}${digest.hex()}'


def verify_password(password: str, stored_hash: str) -> bool:
    if not stored_hash or '$' not in stored_hash:
        return False
    algorithm, salt, digest = stored_hash.split('$', 2)
    if algorithm != 'pbkdf2_sha256':
        return False
    generated = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 200000)
    return hmac.compare_digest(generated.hex(), digest)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def transaction_expiration() -> datetime:
    return datetime.utcnow() + timedelta(minutes=settings.SESSION_EXPIRE_MINUTES)


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.SESSION_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite=settings.SESSION_COOKIE_SAME_SITE,
        path='/',
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=settings.SESSION_COOKIE_NAME, path='/')


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    database: Session = Depends(get_db),
) -> User:
    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    elif request.cookies.get(settings.SESSION_COOKIE_NAME):
        token = request.cookies.get(settings.SESSION_COOKIE_NAME)

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Authentication required.')

    hashed = hash_session_token(token)
    record = database.execute(select(SessionRecord).where(SessionRecord.session_token_hash == hashed)).scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid or expired session.')

    if record.expires_at <= datetime.utcnow():
        database.delete(record)
        database.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Session expired.')

    user = database.execute(select(User).where(User.id == record.user_id)).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='User account unavailable.')

    record.last_accessed_at = datetime.utcnow()
    record.expires_at = transaction_expiration()
    database.commit()
    return user


async def create_session_for_user(database: Session, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    session_hash = hash_session_token(token)
    expires_at = transaction_expiration()

    database.execute(select(SessionRecord).where(SessionRecord.user_id == user_id)).all()
    previous = database.execute(select(SessionRecord).where(SessionRecord.user_id == user_id)).scalars().all()
    for item in previous:
        database.delete(item)

    record = SessionRecord(
        user_id=user_id,
        session_token_hash=session_hash,
        created_at=datetime.utcnow(),
        expires_at=expires_at,
        last_accessed_at=datetime.utcnow(),
    )
    database.add(record)
    database.commit()
    return token


@router.post('/register')
@router.post('/signup')
async def signup(payload: SignupRequest, response: Response, database: Session = Depends(get_db)):
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Passwords do not match.')

    existing = database.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='An account with this email already exists.')

    user = User(
        name=payload.name.strip(),
        email=payload.email,
        password_hash=hash_password(payload.password),
        is_active=True,
        session_token=None,
    )
    database.add(user)
    database.commit()
    database.refresh(user)

    token = await create_session_for_user(database, user.id)
    set_session_cookie(response, token)
    return {
        'token': token,
        'user': {'id': user.id, 'name': user.name, 'email': user.email},
    }


@router.post('/login')
async def login(payload: LoginRequest, response: Response, database: Session = Depends(get_db)):
    user = database.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Email or password is incorrect.')

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='This account is no longer active.')

    token = await create_session_for_user(database, user.id)
    set_session_cookie(response, token)
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
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    database: Session = Depends(get_db),
):
    database.execute(select(SessionRecord).where(SessionRecord.user_id == current_user.id)).scalars().all()
    for record in database.execute(select(SessionRecord).where(SessionRecord.user_id == current_user.id)).scalars().all():
        database.delete(record)
    database.commit()
    clear_session_cookie(response)
    return {'status': 'ok'}


@router.post('/forgot-password')
async def request_password_reset():
    return {
        'status': 'not_configured',
        'message': 'Password reset is not configured yet. This flow will be connected to a secure email provider in a future release.',
    }
