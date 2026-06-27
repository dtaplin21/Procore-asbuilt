from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from models.base import Base
import models.drawing_region  # noqa: F401 — register drawing_regions before overlay FK
import models.drawing_overlay  # noqa: F401
import models.models  # noqa: F401 — register remaining ORM tables on Base.metadata
from config import settings, sqlalchemy_connect_args

DATABASE_URL = settings.database_url

engine = create_engine(DATABASE_URL, connect_args=sqlalchemy_connect_args())
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    Base.metadata.create_all(bind=engine)

