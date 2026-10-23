from contextlib import contextmanager
from pathlib import Path
import hashlib
import secrets
import sqlite3
import time

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field


router = APIRouter(prefix="/auth", tags=["Authentication"])

# Creates users.db beside the backend folder containing this routers folder.
DB_PATH = Path(__file__).resolve().parents[1] / "users.db"


@contextmanager
def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def create_tables():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS auth_sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return f"{salt.hex()}:{hashed.hex()}"


def password_matches(password: str, saved_hash: str) -> bool:
    salt_hex, hash_hex = saved_hash.split(":")
    salt = bytes.fromhex(salt_hex)
    new_hash = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return secrets.compare_digest(new_hash.hex(), hash_hex)


create_tables()


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=100)
    email: str
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/register", status_code=201)
def register(data: RegisterRequest):
    email = data.email.strip().lower()

    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Enter a valid email address")

    try:
        with get_db() as db:
            cursor = db.execute(
                "INSERT INTO users (full_name, email, password_hash) VALUES (?, ?, ?)",
                (data.full_name.strip(), email, hash_password(data.password)),
            )
            user_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    return {"message": "Account created", "user": {
        "id": user_id,
        "full_name": data.full_name.strip(),
        "email": email,
    }}


@router.post("/login")
def login(data: LoginRequest):
    email = data.email.strip().lower()

    with get_db() as db:
        user = db.execute(
            "SELECT id, full_name, email, password_hash FROM users WHERE email = ?",
            (email,),
        ).fetchone()

        if not user or not password_matches(data.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Email or password is incorrect")

        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        expires_at = int(time.time()) + (60 * 60 * 24)

        db.execute(
            "INSERT INTO auth_sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (token_hash, user["id"], expires_at),
        )

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "full_name": user["full_name"],
            "email": user["email"],
        },
    }


@router.get("/me")
def get_current_user(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Please log in")

    token = authorization.removeprefix("Bearer ").strip()
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    with get_db() as db:
        user = db.execute(
            """
            SELECT users.id, users.full_name, users.email
            FROM users
            JOIN auth_sessions ON auth_sessions.user_id = users.id
            WHERE auth_sessions.token_hash = ? AND auth_sessions.expires_at > ?
            """,
            (token_hash, int(time.time())),
        ).fetchone()

    if not user:
        raise HTTPException(status_code=401, detail="Session expired; please log in again")

    return {"id": user["id"], "full_name": user["full_name"], "email": user["email"]}