from typing import Optional, Dict, Any

from telegram.ext import ConversationHandler

from constants import CONTEXT_TRANSACTION, CONTEXT_CONVERSATION_STATE
from persistence.models import Transaction

from enum import Enum, auto


class ConversationState(Enum):
    SELECTING_CATEGORY = auto()
    SELECTING_SHARING_TYPE = auto()
    ENTERING_SHARE_AMOUNT = auto()
    COMPLETED = auto()


class ConversationContextManager:
    def __init__(self):
        self.conversations = {}

    def start_conversation(self, user_id: int, transaction: Transaction, conversation_state: ConversationState) -> None:
        if not self.conversations.get(user_id):
            self.conversations[user_id] = {}

        self.conversations[user_id][transaction.transaction_id] = {
            CONTEXT_TRANSACTION: transaction,
            CONTEXT_CONVERSATION_STATE: conversation_state
        }

    def update_state(self, user_id: int, transaction_id: str, conversation_state: ConversationState) -> None:
        if self.conversations.get(user_id) and self.conversations[user_id].get(transaction_id):
            self.conversations[user_id][transaction_id][CONTEXT_CONVERSATION_STATE] = conversation_state

    def update_category(self, user_id: int, transaction_id: str, category: str) -> None:
        if self.conversations.get(user_id) and self.conversations[user_id].get(transaction_id):
            if not self.conversations[user_id][transaction_id].get(CONTEXT_TRANSACTION):
                self.conversations[user_id][transaction_id][CONTEXT_TRANSACTION] = Transaction(transaction_id)

            self.conversations[user_id][transaction_id][CONTEXT_TRANSACTION].category = category

    def update_sharing_status(self, user_id: int, transaction_id: str, is_shared: bool) -> None:
        if self.conversations.get(user_id) and self.conversations[user_id].get(transaction_id):
            if not self.conversations[user_id][transaction_id].get(CONTEXT_TRANSACTION):
                self.conversations[user_id][transaction_id][CONTEXT_TRANSACTION] = Transaction(transaction_id)

            self.conversations[user_id][transaction_id][CONTEXT_TRANSACTION].is_shared = is_shared

    def update_user_share(self, user_id: int, transaction_id: str, share_amount: float) -> None:
        if self.conversations.get(user_id) and self.conversations[user_id].get(transaction_id):
            if not self.conversations[user_id][transaction_id].get(CONTEXT_TRANSACTION):
                self.conversations[user_id][transaction_id][CONTEXT_TRANSACTION] = Transaction(transaction_id)

            self.conversations[user_id][transaction_id][CONTEXT_TRANSACTION].user_share = share_amount

    def get_conversation(self, user_id: int, transaction_id: str) -> Optional[Dict[str, Any]]:
        user_conversations = self.conversations.get(user_id)
        if user_conversations:
            return user_conversations.get(transaction_id)
        return None

    def get_conversations_by_state(self, user_id: int, target_state: ConversationState) -> Optional[Dict[str, Any]]:
        user_conversations = self.conversations.get(user_id, {})
        filtered_conversations = {
            txn_id: data
            for txn_id, data in user_conversations.items()
            if data.get(CONTEXT_CONVERSATION_STATE) == target_state
        }
        return filtered_conversations

    def end_conversation(self, user_id: int, transaction_id: str) -> None:
        if self.conversations.get(user_id) and self.conversations.get(user_id).get(transaction_id):
            del self.conversations[user_id][transaction_id]
