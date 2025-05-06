import logging
import os

import firebase_admin
from dotenv import load_dotenv
from firebase_admin import credentials
from firebase_admin import firestore
import psycopg2
from psycopg2 import sql
from contextlib import closing

from constants import ENV_POSTGRES_CONNECTION_STRING
from persistence.models import Transaction

TRANSACTIONS_COLLECTION_NAME = 'transactions'

FIREBASE_CREDENTIALS_PATH = "persistence/firebase_credentials.json"

load_dotenv()

logger = logging.getLogger(__name__)

class FireBaseManager:
    def __init__(self):
        # Initialize Firebase app
        cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
        firebase_admin.initialize_app(cred)
        self.db = firestore.client()

    def write_transaction(self, transaction: Transaction) -> bool:
        try:
            self.db.collection(TRANSACTIONS_COLLECTION_NAME).document(transaction.transaction_id).set({
                'date': transaction.date,
                'time': transaction.time,
                'recipient': transaction.recipient,
                'amount': transaction.amount,
                'bank': transaction.bank,
                'mode': transaction.mode,
                'category': transaction.category,
                'is_shared': transaction.is_shared,
                'user_share': transaction.user_share
            })

            return True
        except Exception as e:
            return False


class PostgresManager:
    def __init__(self, db_config):
        """
        db_config should be a dictionary with keys:
        - dbname
        - user
        - password
        - host
        - port
        """
        self.db_config = db_config

    def write_transaction(self, transaction) -> bool:
        insert_query = sql.SQL("""
            INSERT INTO transactions (
                transaction_id,
                date,
                time,
                recipient,
                amount,
                bank,
                mode,
                category,
                is_shared,
                user_share
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (transaction_id) DO UPDATE SET
                date = EXCLUDED.date,
                time = EXCLUDED.time,
                recipient = EXCLUDED.recipient,
                amount = EXCLUDED.amount,
                bank = EXCLUDED.bank,
                mode = EXCLUDED.mode,
                category = EXCLUDED.category,
                is_shared = EXCLUDED.is_shared,
                user_share = EXCLUDED.user_share;
        """)

        values = (
            transaction.transaction_id,
            transaction.date,
            transaction.time,
            transaction.recipient,
            transaction.amount,
            transaction.bank,
            transaction.mode,
            transaction.category,
            transaction.is_shared,
            transaction.user_share
        )

        try:
            with closing(psycopg2.connect(self.db_config)) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(insert_query, values)
                    conn.commit()
            return True
        except Exception as e:
            # Optionally log e here
            return False


class PersistenceWrapper:
    def __init__(self):
        self.firebase_manager = FireBaseManager()
        self.postgres_manager = PostgresManager(os.environ.get(ENV_POSTGRES_CONNECTION_STRING))

    def write_transaction(self, transaction) -> bool:
        success = True
        try:
            self.firebase_manager.write_transaction(transaction)
        except Exception as e:
            logger.error(f"Error writing to firebase: {e}")
            success = False

        try:
            self.postgres_manager.write_transaction(transaction)
        except Exception as e:
            logger.error(f"Error writing to postgres: {e}")
            success = False

        return success