import os
from dotenv import load_dotenv
load_dotenv()
class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///anpr.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_TIME_LIMIT = None
    TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata")
