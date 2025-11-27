"""Core database access helpers with optimized connection pooling."""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from app.core.config import settings

# ========================================================
# Task 6: Build Database URL & Optimize Connection
# ========================================================

# بناء رابط الاتصال يدوياً لأن settings.database_url قد يكون None
# إذا كانت القيم موجودة بشكل منفصل في .env
if hasattr(settings, "database_url") and settings.database_url:
    SQLALCHEMY_DATABASE_URL = str(settings.database_url)
else:
    # بناء الرابط لـ PostgreSQL
    SQLALCHEMY_DATABASE_URL = (
        f"postgresql://{settings.database_username}:{settings.database_password}"
        f"@{settings.database_hostname}:{settings.database_port}/{settings.database_name}"
    )

# تحديد Connect Args بناءً على نوع القاعدة لتفادي الأخطاء
connect_args = {}
if "postgresql" in SQLALCHEMY_DATABASE_URL:
    connect_args = {
        "options": "-c timezone=utc",
        "application_name": "fastapi_app",
    }
elif "sqlite" in SQLALCHEMY_DATABASE_URL:
    connect_args = {"check_same_thread": False}

# 1. إنشاء الـ Engine مع Pooling
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    poolclass=QueuePool,
    pool_size=20,
    max_overflow=30,
    pool_timeout=30,
    pool_recycle=3600,
    pool_pre_ping=True,
    echo=False,
    connect_args=connect_args,
)

# 2. إنشاء الـ SessionLocal
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 3. تعريف الـ Base
Base = declarative_base()


# 4. دالة الحصول على DB Session
def get_db():
    """Provide a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


try:
    from .query_helpers import (
        with_joined_loads,
        with_select_loads,
        paginate_query,
        optimize_post_query,
        optimize_comment_query,
        optimize_user_query,
    )

    __all__ = [
        "Base",
        "SessionLocal",
        "engine",
        "get_db",
        "with_joined_loads",
        "with_select_loads",
        "paginate_query",
        "optimize_post_query",
        "optimize_comment_query",
        "optimize_user_query",
    ]
except ImportError:
    # Fallback if query_helpers.py is missing
    __all__ = ["Base", "SessionLocal", "engine", "get_db"]
