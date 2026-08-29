"""Pydantic schemas for auth request/response bodies."""

from typing import Optional

from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class GoogleAuth(BaseModel):
    credential: str  # Google ID token (JWT)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: str
    email: str
    name: Optional[str]
    avatar_url: Optional[str]

    model_config = {"from_attributes": True}


class TokenWithUser(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
