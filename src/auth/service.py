"""User CRUD operations and password helpers."""

from passlib.context import CryptContext
from sqlalchemy.orm import Session

from src.auth.models import User

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()


def get_user_by_id(db: Session, user_id: str) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_google_id(db: Session, google_id: str) -> User | None:
    return db.query(User).filter(User.google_id == google_id).first()


def create_user(db: Session, email: str, password: str, name: str | None = None) -> User:
    user = User(
        email=email,
        hashed_password=hash_password(password),
        name=name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_or_update_google_user(
    db: Session,
    google_id: str,
    email: str,
    name: str | None,
    avatar_url: str | None,
) -> User:
    user = get_user_by_google_id(db, google_id)
    if user is None:
        user = get_user_by_email(db, email)
    if user is None:
        user = User(
            email=email,
            google_id=google_id,
            name=name,
            avatar_url=avatar_url,
        )
        db.add(user)
    else:
        user.google_id = google_id
        user.name = name or user.name
        user.avatar_url = avatar_url or user.avatar_url
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = get_user_by_email(db, email)
    if user is None or user.hashed_password is None:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user
