"""Authentication endpoints: register, login, Google OAuth, and me."""

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.auth.database import get_db
from src.auth.dependencies import get_current_user
from src.auth.jwt_utils import create_access_token
from src.auth.models import User
from src.auth.schemas import GoogleAuth, TokenWithUser, UserCreate, UserLogin, UserOut
from src.auth.service import (
    authenticate_user,
    create_or_update_google_user,
    create_user,
    get_user_by_email,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


def _make_token_response(user: User) -> TokenWithUser:
    token = create_access_token(user.id)
    return TokenWithUser(
        access_token=token,
        user=UserOut.model_validate(user),
    )


@router.post("/register", response_model=TokenWithUser, status_code=status.HTTP_201_CREATED)
def register(body: UserCreate, db: Session = Depends(get_db)) -> TokenWithUser:
    if get_user_by_email(db, body.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )
    if len(body.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters.",
        )
    user = create_user(db, email=body.email, password=body.password, name=body.name)
    logger.info("New user registered: %s", user.email)
    return _make_token_response(user)


@router.post("/login", response_model=TokenWithUser)
def login(body: UserLogin, db: Session = Depends(get_db)) -> TokenWithUser:
    user = authenticate_user(db, body.email, body.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )
    return _make_token_response(user)


@router.post("/google", response_model=TokenWithUser)
def google_auth(body: GoogleAuth, db: Session = Depends(get_db)) -> TokenWithUser:
    """Verify a Google ID token and return a local JWT."""
    try:
        resp = httpx.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": body.credential},
            timeout=10,
        )
        resp.raise_for_status()
        info = resp.json()
    except Exception as exc:
        logger.warning("Google token verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google credential.",
        )

    google_id: str = info.get("sub", "")
    email: str = info.get("email", "")
    if not google_id or not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google token missing required fields.",
        )

    user = create_or_update_google_user(
        db,
        google_id=google_id,
        email=email,
        name=info.get("name"),
        avatar_url=info.get("picture"),
    )
    logger.info("Google login: %s", user.email)
    return _make_token_response(user)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)
