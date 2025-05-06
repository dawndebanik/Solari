from dataclasses import dataclass


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
