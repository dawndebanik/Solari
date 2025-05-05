import logging
from dataclasses import dataclass

import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from pyasn1.type.univ import Boolean

TRANSACTIONS_COLLECTION_NAME = 'transactions'

FIREBASE_CREDENTIALS_PATH = "firebase_credentials.json"

@dataclass
class Transaction:
    transaction_id: str
    date: str
    time: str
    recipient: str
    amount: float
    bank: str
    mode: str
    category: str
    is_shared: bool
    user_share: float

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
