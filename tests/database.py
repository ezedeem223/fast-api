import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.core.database import Base

# إعداد URL للاتصال بقاعدة بيانات الاختبار
SQLALCHEMY_DATABASE_URL = (
    f"postgresql://{settings.database_username}:"
    f"{settings.database_password}@"
    f"{settings.database_hostname}:"
    f"{settings.database_port}/"
    f"{settings.database_name}_test"
)

# إنشاء محرك الاتصال بقاعدة بيانات الاختبار
engine = create_engine(SQLALCHEMY_DATABASE_URL, echo=False)

# تكوين الجلسة المحلية
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# نقوم بإنشاء جميع الجداول مرة واحدة عند بدء تشغيل الاختبارات
Base.metadata.create_all(bind=engine)


# Fixture لإنشاء جلسة اختبار جديدة لكل اختبار
@pytest.fixture(scope="function")
def session():
    # قبل كل اختبار: (يمكن استخدام TRUNCATE لتفريغ البيانات بين الاختبارات)
    with engine.connect() as connection:
        # تفريغ جميع الجداول مع إعادة تعيين الهوية
        table_names = ", ".join([tbl.name for tbl in Base.metadata.sorted_tables])
        connection.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))
        connection.commit()
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
