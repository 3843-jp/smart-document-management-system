import os
from dotenv import load_dotenv
load_dotenv()


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'unsafe-development-key-change-me')
    MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/triad_dms')
    MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', 25 * 1024 * 1024))
    TOKEN_TTL_HOURS = int(os.getenv('TOKEN_TTL_HOURS', '12'))
    BOOTSTRAP_ADMIN_EMAIL = os.getenv('BOOTSTRAP_ADMIN_EMAIL', '').strip().lower()
