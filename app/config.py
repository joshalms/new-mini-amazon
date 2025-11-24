import os
from urllib.parse import quote_plus


class Config(object):
    SECRET_KEY = os.environ.get('SECRET_KEY')
    DB_USER = os.environ.get('DB_USER') or ''
    DB_PASSWORD = os.environ.get('DB_PASSWORD') or ''
    DB_HOST = os.environ.get('DB_HOST') or 'localhost'
    DB_PORT = os.environ.get('DB_PORT') or '5432'
    DB_NAME = os.environ.get('DB_NAME') or ''
    SQLALCHEMY_DATABASE_URI = 'postgresql://{}:{}@{}:{}/{}'\
        .format(DB_USER,
                quote_plus(DB_PASSWORD),
                DB_HOST,
                DB_PORT,
                DB_NAME)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
