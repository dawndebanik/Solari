import logging
from html import escape

from telegram import Update, InlineKeyboardMarkup, ForceReply
from telegram.error import TelegramError
from telegram.ext import CallbackContext, ContextTypes

from bot_utils import get_category_keyboard, get_sharing_type_keyboard, EXPENSE_CATEGORIES
from constants import (
    CONTEXT_TRANSACTION, CONTEXT_RELATED_MESSAGE_IDS,
    MSG_CATEGORY_SELECTED, MSG_TRANSACTION_NOT_FOUND, MSG_CONTEXT_NOT_FOUND,
    MSG_SHARED_EXPENSE, MSG_INVALID_SHARE_NEGATIVE, MSG_INVALID_SHARE_EXCEEDS_TOTAL,
    MSG_INVALID_AMOUNT_FORMAT, MSG_TRANSACTION_UPDATED, MSG_TRANSACTION_UPDATE_FAILED,
    MSG_ERROR, SHARED_TYPE, SOLO_TYPE, CALLBACK_SHARE_YES, HTML_PARSE_MODE,
    MSG_TRANSACTION_NOTIFICATION
)
from conversation_context import ConversationContextManager, ConversationState
from persistence.models import Transaction
from persistence.persistence_wrapper import PersistenceWrapper

logger = logging.getLogger(__name__)


class ConversationStateMachine:
    """Handles the conversation flow for transaction categorization and processing"""

    def __init__(self, bot, persistence_wrapper: PersistenceWrapper,
                 conversation_context_manager: ConversationContextManager):
        """
        Initialize the transaction handler

        Args:
            bot: The Telegram bot instance for sending messages
            persistence_wrapper: The persistence wrapper for storing transaction data
            conversation_context_manager: The conversation context manager for managing state
        """
        self.bot = bot
        self.persistence_wrapper = persistence_wrapper
        self.conversation_context_manager = conversation_context_manager
    async def send_transaction_notification(self, transaction: Transaction, user_id: int) -> None:
        """
        Send a notification about a new transaction and start the categorization flow

        Args:
            :param transaction: Transaction details
            :param user_id: The user to send the notification to
        """
        try:
            # Format the transaction message
            message = MSG_TRANSACTION_NOTIFICATION.format(
                date=escape(transaction.date),
                time=escape(transaction.time),
                recipient=escape(transaction.recipient),
                amount=escape(str(transaction.amount)),
                bank=escape(transaction.bank),
                mode=escape(transaction.mode)
            )

            keyboard = await get_category_keyboard(transaction.transaction_id)

            reply_markup = InlineKeyboardMarkup(keyboard)

            try:
                await self.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    reply_markup=reply_markup,
                    parse_mode=HTML_PARSE_MODE
                )
                self.conversation_context_manager.start_conversation(user_id, transaction,
                                                                     ConversationState.SELECTING_CATEGORY)
            except TelegramError as e:
                logger.error(f"Failed to send message to user {user_id}: {e}")

        except Exception as e:
            logger.error(f"Error sending transaction notification: {e}")

    async def category_selected(self, update: Update, context: CallbackContext) -> None:
        """Handle category selection and ask about sharing"""
        query = update.callback_query
        await query.answer()

        # Extract transaction id from callback data (cat_{transaction_id}_{category_index})
        parts = query.data.split("_")
        user_id = update.effective_user.id
        transaction_id = parts[1]

        try:
            # get conversation context
            conversation = self.conversation_context_manager.get_conversation(user_id, transaction_id)

            if not conversation:
                await query.edit_message_text(
                    text=MSG_TRANSACTION_NOT_FOUND,
                    reply_markup=None
                )
                return

            # Extract category index from callback data
            category = EXPENSE_CATEGORIES[int(parts[2])]

            # Update context with selected category
            self.conversation_context_manager.update_category(user_id, transaction_id, category)

            keyboard = await get_sharing_type_keyboard(transaction_id)
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                text=MSG_CATEGORY_SELECTED.format(category=category),
                parse_mode=HTML_PARSE_MODE,
                reply_markup=reply_markup
            )

            self.conversation_context_manager.update_state(user_id, transaction_id,
                                                           ConversationState.SELECTING_SHARING_TYPE)
            return
        except Exception as e:
            logger.error(f"Error in category selection: {e}")
            await query.edit_message_text(
                text=MSG_ERROR.format(error=str(e)),
                reply_markup=None
            )

        self.conversation_context_manager.end_conversation(user_id, transaction_id)

    async def sharing_type_selected(self, update: Update, context: CallbackContext) -> None:
        """Handle sharing type selection"""
        query = update.callback_query
        await query.answer()

        try:
            # Extract transaction id from callback data (share.yes_{transaction_id})
            parts = query.data.split("_")
            share_mode = parts[0]
            transaction_id = parts[1]
            user_id = update.effective_user.id
            conversation = self.conversation_context_manager.get_conversation(user_id, transaction_id)

            if not conversation:
                await query.edit_message_text(
                    text=MSG_CONTEXT_NOT_FOUND,
                    reply_markup=None
                )
                return

            # Get the sharing selection
            is_shared = share_mode == CALLBACK_SHARE_YES

            # Update context with sharing status
            self.conversation_context_manager.update_sharing_status(user_id, transaction_id, is_shared)

            if is_shared:
                # Ask for user's share
                transaction: Transaction = conversation[CONTEXT_TRANSACTION]
                total_amount = transaction.amount
                await query.edit_message_text(
                    text=MSG_SHARED_EXPENSE.format(amount=total_amount),
                    parse_mode=HTML_PARSE_MODE
                )

                message = await self.bot.send_message(
                    chat_id=query.message.chat.id,
                    text="Enter your share amount for this transaction:",
                    reply_markup=ForceReply(selective=True),
                    parse_mode=HTML_PARSE_MODE,
                    reply_to_message_id=query.message.message_id
                )

                # Store the message_id to match replies later
                self.conversation_context_manager.add_message_id_to_conversation_context(
                    user_id, transaction_id, message.message_id
                )
                self.conversation_context_manager.update_state(
                    user_id, transaction_id, ConversationState.ENTERING_SHARE_AMOUNT
                )
            else:
                # Complete the transaction as solo expense
                await self.complete_transaction(update, user_id, transaction_id)

        except Exception as e:
            logger.error(f"Error in sharing type selection: {e}")
            await query.edit_message_text(
                text=MSG_ERROR.format(error=str(e)),
                reply_markup=None
            )

    async def share_amount_entered(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle user entering their share amount"""
        message = update.message
        if not message or not message.reply_to_message:
            return

        user_id = message.from_user.id
        reply_to_message_id = message.reply_to_message.message_id

        # Find the conversation that is waiting for this reply
        conversations_waiting_for_share_amount = self.conversation_context_manager.get_conversations_by_state(
            user_id, ConversationState.ENTERING_SHARE_AMOUNT
        )

        if not conversations_waiting_for_share_amount:
            return

        # get the transaction id behind the message to which this is a reply
        matching_transaction_id = next(
            (transaction_id for transaction_id, data in conversations_waiting_for_share_amount.items()
             if reply_to_message_id in data.get(CONTEXT_RELATED_MESSAGE_IDS)),
            None
        )

        if not matching_transaction_id:
            return

        # Validate the share amount
        try:
            share_amount = float(message.text.strip())
            conversation = conversations_waiting_for_share_amount.get(matching_transaction_id)
            total_amount = float(conversation[CONTEXT_TRANSACTION].amount)

            if share_amount < 0:
                sent_message = await update.message.reply_text(
                    MSG_INVALID_SHARE_NEGATIVE,
                    reply_markup=ForceReply(selective=True)
                )
                self.conversation_context_manager.add_message_id_to_conversation_context(
                    user_id, matching_transaction_id, sent_message.message_id
                )
                return

            if share_amount > total_amount:
                sent_message = await update.message.reply_text(
                    MSG_INVALID_SHARE_EXCEEDS_TOTAL.format(
                        share=share_amount,
                        total=total_amount
                    ),
                    reply_markup=ForceReply(selective=True)
                )
                self.conversation_context_manager.add_message_id_to_conversation_context(
                    user_id, matching_transaction_id, sent_message.message_id
                )
                return

        except ValueError:
            sent_message = await update.message.reply_text(
                MSG_INVALID_AMOUNT_FORMAT,
                reply_markup=ForceReply(selective=True)
            )
            self.conversation_context_manager.add_message_id_to_conversation_context(
                user_id, matching_transaction_id, sent_message.message_id
            )
            return

        self.conversation_context_manager.update_user_share(user_id, matching_transaction_id, share_amount)
        await self.complete_transaction(update, user_id, matching_transaction_id)

    async def complete_transaction(self, update: Update, user_id: int, transaction_id: str) -> None:
        """Complete the transaction processing and update the sheet"""
        conversation = self.conversation_context_manager.get_conversation(user_id, transaction_id)

        if not conversation:
            if hasattr(update, 'message'):
                await update.message.reply_text(MSG_CONTEXT_NOT_FOUND)
            return

        try:
            transaction = conversation[CONTEXT_TRANSACTION]
            transaction.user_share = transaction.amount if not transaction.is_shared else transaction.user_share

            # Log to persistence store
            success = self.persistence_wrapper.write_transaction(transaction)

            if success:
                message = MSG_TRANSACTION_UPDATED.format(
                    date=transaction.date,
                    time=transaction.time,
                    recipient=transaction.recipient,
                    amount=transaction.amount,
                    category=transaction.category,
                    type=SHARED_TYPE if transaction.is_shared else SOLO_TYPE,
                    share_info=transaction.user_share
                )
            else:
                message = MSG_TRANSACTION_UPDATE_FAILED

            # Send confirmation message
            if hasattr(update, 'callback_query') and update.callback_query:
                await update.callback_query.edit_message_text(
                    text=message,
                    parse_mode=HTML_PARSE_MODE
                )
            else:
                await update.message.reply_text(
                    text=message,
                    parse_mode=HTML_PARSE_MODE
                )

        except Exception as e:
            logger.error(f"Error completing transaction: {e}")
            error_message = MSG_ERROR.format(error=str(e))

            if hasattr(update, 'callback_query') and update.callback_query:
                await update.callback_query.edit_message_text(text=error_message)
            else:
                await update.message.reply_text(text=error_message)

        # End the conversation
        self.conversation_context_manager.end_conversation(user_id, transaction_id)