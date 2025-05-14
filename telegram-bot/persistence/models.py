from dataclasses import dataclass
from typing import Dict, Optional

from constants import KEY_TRANSACTION_ID, KEY_DATE, KEY_TIME, KEY_RECIPIENT, KEY_AMOUNT, KEY_BANK, KEY_MODE, \
    KEY_CATEGORY, KEY_IS_SHARED, KEY_USER_SHARE


@dataclass
class Transaction:
    transaction_id: str
    date: Optional[str] = None
    time: Optional[str] = None
    recipient: Optional[str] = None
    amount: float = 0.0
    bank: Optional[str] = None
    mode: Optional[str] = None
    category: Optional[str] = None
    is_shared: bool = False
    user_share: float = 0.0

    @classmethod
    def from_dict(cls, transaction_dict: Dict[str, str]):
        if not transaction_dict.get(KEY_TRANSACTION_ID):
            raise ValueError("Transaction id must be present")

        return cls(
            transaction_id=transaction_dict[KEY_TRANSACTION_ID],
            date=transaction_dict.get(KEY_DATE),
            time=transaction_dict.get(KEY_TIME),
            recipient=transaction_dict.get(KEY_RECIPIENT),
            amount=float(transaction_dict.get(KEY_AMOUNT)) if transaction_dict.get(KEY_AMOUNT) else 0.0,
            bank=transaction_dict.get(KEY_BANK),
            mode=transaction_dict.get(KEY_MODE),
            category=transaction_dict.get(KEY_CATEGORY),
            is_shared=bool(transaction_dict.get(KEY_IS_SHARED)) if transaction_dict.get(KEY_IS_SHARED) else False,
            user_share=float(transaction_dict.get(KEY_USER_SHARE)) if transaction_dict.get(KEY_USER_SHARE) else 0.0
        )
