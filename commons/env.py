import os

from dotenv import load_dotenv

from constants import ENV_SHEET_ID, ENV_SHEET_NAME, ENV_SHEET_NAME_POST_REVIEW, ENV_TELEGRAM_TOKEN, \
    ENV_POSTGRES_CONNECTION_STRING


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDS_DIR = os.path.join(BASE_DIR, 'credentials')

load_dotenv(os.path.join(CREDS_DIR, '.env'))

SHEET_ID = os.environ.get(ENV_SHEET_ID)
SHEET_NAME = os.environ.get(ENV_SHEET_NAME)
SHEET_NAME_POST_REVIEW = os.environ.get(ENV_SHEET_NAME_POST_REVIEW)
TELEGRAM_TOKEN = os.environ.get(ENV_TELEGRAM_TOKEN)
POSTGRES_CONNECTION_STRING = os.environ.get(ENV_POSTGRES_CONNECTION_STRING)
FIREBASE_CREDENTIALS_PATH = os.path.join(CREDS_DIR, 'firebase_credentials.json')
GMAIL_OAUTH_CREDENTIALS_PATH = os.path.join(CREDS_DIR, 'gmail_oauth_credentials.json')
SERVICE_ACCOUNT_CREDENTIALS_PATH = os.path.join(CREDS_DIR, 'service_account_credentials.json')
TOKEN_PATH = os.path.join(CREDS_DIR, 'token.json')