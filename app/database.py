from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from .config import settings

# تكوين عنوان الاتصال بقاعدة البيانات
SQLALCHEMY_DATABASE_URL = f"postgresql://{settings.database_username}:{settings.database_password}@{settings.database_hostname}:{settings.database_port}/{settings.database_name}"

# إنشاء محرك الاتصال بقاعدة البيانات
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=100,  # عدد الاتصالات في المسبح
    max_overflow=200,  # عدد الاتصالات الإضافية التي يمكن إنشاؤها
)

# تكوين الجلسة المحلية
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# إنشاء قاعدة declarative base من SQLAlchemy
Base = declarative_base()


# دالة للحصول على جلسة قاعدة البيانات
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
