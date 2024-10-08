from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.config import settings
from app.database import get_db, Base

# إعداد URL للاتصال بقاعدة البيانات
SQLALCHEMY_DATABASE_URL = (
    f"postgresql://{settings.database_username}:"
    f"{settings.database_password}@"
    f"{settings.database_hostname}:"
    f"{settings.database_port}/"
    f"{settings.database_name}_test"
)

# إنشاء محرك الاتصال بقاعدة البيانات
engine = create_engine(SQLALCHEMY_DATABASE_URL)

# تكوين الجلسة المحلية
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(
    scope="function"
)  # تغيير النطاق إلى "function" لضمان تنظيف القاعدة بين الاختبارات
def session():
    # إعادة بناء قاعدة البيانات للاختبارات
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(
    scope="function"
)  # تغيير النطاق إلى "function" لضمان عدم تداخل الاختبارات
def client(session):
    # تجاوز دالة get_db لرجوع الجلسة الاختبارية
    def override_get_db():
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
