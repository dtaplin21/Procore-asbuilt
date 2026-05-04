from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from models.models import Base
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

