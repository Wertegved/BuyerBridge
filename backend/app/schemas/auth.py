from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class SignupRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=8, max_length=200)
    confirm_password: str = Field(..., min_length=8, max_length=200)

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator('name', 'email')
    @classmethod
    def validate_required_fields(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError('This field is required.')
        return value

    @field_validator('password')
    @classmethod
    def validate_password(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError('Password must be at least 8 characters long.')
        return value


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=8, max_length=200)

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class AuthUserResponse(BaseModel):
    id: int
    name: str
    email: str


class AuthResponse(BaseModel):
    token: str
    user: AuthUserResponse
