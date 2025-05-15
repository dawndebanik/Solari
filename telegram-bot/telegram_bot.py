#!/usr/bin/env python
import logging
import os
import traceback
from html import escape
from typing import Dict, List

from dotenv import load_dotenv
from firebase_admin import credentials
# Telegram Bot imports
from telegram import Update, InlineKeyboardMarkup, ForceReply
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackContext,
    CallbackQueryHandler,
    MessageHandler,
    filters, ContextTypes
)

from bot_utils import get_category_keyboard, get_sharing_type_keyboard, EXPENSE_CATEGORIES
from commons.google_sheets_manager import GoogleSheetsManager
from constants import CONTEXT_RELATED_MESSAGE_IDS
from conversation_context import ConversationContextManager, ConversationState
from env import FIREBASE_CREDENTIALS_PATH
from persistence.models import Transaction
from persistence.persistence_wrapper import PersistenceWrapper, FireBaseManager, PostgresManager

TELEGRAM_BOT_CONFIG_FILE_NAME = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bot_config.json')

# Constants and configs
from config_manager import ConfigManager
from commons.constants import ENV_TELEGRAM_TOKEN, ENV_SHEET_ID, ENV_SHEET_NAME, \
    CMD_START, CMD_CHECK, CALLBACK_CATEGORY_PREFIX, \
    CALLBACK_SHARE_PREFIX, CALLBACK_SHARE_YES, MSG_START, MSG_CHECKING, \
    MSG_NO_TRANSACTIONS, MSG_FOUND_TRANSACTIONS, MSG_TRANSACTION_NOTIFICATION, \
    MSG_TRANSACTION_NOT_FOUND, MSG_CATEGORY_SELECTED, MSG_CONTEXT_NOT_FOUND, MSG_SHARED_EXPENSE, \
    MSG_INVALID_SHARE_NEGATIVE, MSG_INVALID_SHARE_EXCEEDS_TOTAL, MSG_INVALID_AMOUNT_FORMAT, MSG_TRANSACTION_UPDATED, \
    MSG_TRANSACTION_UPDATE_FAILED, MSG_ERROR, CONFIG_USER_IDS, \
    CONTEXT_TRANSACTION, CHECK_INTERVAL_SECONDS, FIRST_CHECK_DELAY_SECONDS, HTML_PARSE_MODE, SHARED_TYPE, SOLO_TYPE, \
    ENV_SHEET_NAME_POST_REVIEW, ENV_POSTGRES_CONNECTION_STRING

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# load env file
load_dotenv()


class TelegramBot:
    """Main Telegram bot class"""

    def __init__(self, token: str, gsheets_manager: GoogleSheetsManager, config_manager: ConfigManager, persistence_wrapper: PersistenceWrapper):
        """
        Initialize the Telegram bot

        Args:
            token: Telegram Bot API token
            gsheets_manager: Sheet monitor instance
            config_manager: Config manager instance
            firebase_manager: Firebase database manager instance
            postgres_manager: Postgres database manager instance
        """
        self.application = Application.builder().token(token).build()
        self.sheet_monitor = gsheets_manager
        self.config_manager = config_manager
        self.conversation_context_manager = ConversationContextManager()
        self.persistence_wrapper = persistence_wrapper

        self._setup_handlers()

    def _setup_handlers(self) -> None:
        """Set up message and callback handlers"""

        # Command handlers
        self.application.add_handler(CommandHandler(CMD_START, self.start_cmd))
        self.application.add_handler(CommandHandler(CMD_CHECK, self.check_cmd))

        # Individual callback query handlers for each step
        self.application.add_handler(
            CallbackQueryHandler(self.category_selected, pattern=f"^{CALLBACK_CATEGORY_PREFIX}")
        )
        self.application.add_handler(
            CallbackQueryHandler(self.sharing_type_selected, pattern=f"^{CALLBACK_SHARE_PREFIX}")
        )

        # Message handler for plain text amount entry (share amount)
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.share_amount_entered)
        )

        # Global error handler
        self.application.add_error_handler(self.error_handler)

    async def start_cmd(self, update: Update, context: CallbackContext) -> None:
        """Handle /start command"""
        user_id = update.effective_user.id
        await update.message.reply_text(
            MSG_START.format(first_name=update.effective_user.first_name),
            parse_mode=HTML_PARSE_MODE
        )

    async def check_cmd(self, update: Update, context: CallbackContext) -> None:
        """Handle /check command to manually check for new transactions"""
        user_id = update.effective_user.id

        await update.message.reply_text(MSG_CHECKING)

        try:
            new_transactions = await self.check_for_updates()
            if not new_transactions:
                await update.message.reply_text(MSG_NO_TRANSACTIONS)
            else:
                await update.message.reply_text(
                    MSG_FOUND_TRANSACTIONS.format(count=len(new_transactions))
                )
        except Exception as e:
            logger.error(f"Error checking updates: {e}")
            await update.message.reply_text(MSG_ERROR.format(error=str(e)))

    async def check_for_updates(self) -> List[Dict[str, str]]:
        """
        Check for new transactions in the Google Sheet

        Returns:
            List of new transactions
        """
        last_processed_row = self.config_manager.get_last_processed_row()
        new_transactions, new_last_row = self.sheet_monitor.get_new_rows(last_processed_row)

        if new_transactions:
            self.config_manager.update_last_processed_row(new_last_row)

            # Process each new transaction
            for index, transaction in enumerate(new_transactions):
                transaction = Transaction.from_dict(transaction)
                await self.send_transaction_notification(transaction)

        return new_transactions

    async def send_transaction_notification(self, transaction: Transaction) -> None:
        """
        Send a notification about a new transaction and start the categorization flow

        Args:
            transaction: Transaction details
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

            # Send to all authorized users
            for user_id in self.config_manager.config.get(CONFIG_USER_IDS, []):
                try:
                    await self.application.bot.send_message(
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

                message = await context.bot.send_message(
                    chat_id=query.message.chat.id,
                    text="Enter your share amount for this transaction:",
                    reply_markup=ForceReply(selective=True),
                    parse_mode=HTML_PARSE_MODE,
                    reply_to_message_id=query.message.message_id
                )

                # Store the message_id to match replies later
                self.conversation_context_manager.add_message_id_to_conversation_context(user_id, transaction_id,
                                                                                         message.message_id)
                self.conversation_context_manager.update_state(user_id, transaction_id,
                                                               ConversationState.ENTERING_SHARE_AMOUNT)
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
                sent_message = await update.message.reply_text(MSG_INVALID_SHARE_NEGATIVE,
                                                               reply_markup=ForceReply(selective=True))
                self.conversation_context_manager.add_message_id_to_conversation_context(user_id,
                                                                                         matching_transaction_id,
                                                                                         sent_message.message_id)
                return

            if share_amount > total_amount:
                sent_message = await update.message.reply_text(
                    MSG_INVALID_SHARE_EXCEEDS_TOTAL.format(
                        share=share_amount,
                        total=total_amount
                    ),
                    reply_markup=ForceReply(selective=True)
                )
                self.conversation_context_manager.add_message_id_to_conversation_context(user_id,
                                                                                         matching_transaction_id,
                                                                                         sent_message.message_id)
                return

        except ValueError:
            sent_message = await update.message.reply_text(MSG_INVALID_AMOUNT_FORMAT,
                                                           reply_markup=ForceReply(selective=True))
            self.conversation_context_manager.add_message_id_to_conversation_context(user_id, matching_transaction_id,
                                                                                     sent_message.message_id)
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

    @staticmethod
    async def error_handler(update: object, context: CallbackContext) -> None:
        """Handle errors in the dispatcher"""
        logger.error(f"Exception while handling an update: {context.error}")
        tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
        tb_string = ''.join(tb_list)
        logger.error(f"Traceback: {tb_string}")

        # Notify user
        if update and hasattr(update, 'effective_chat'):
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="An error occurred. Please try again later."
            )

    def run_polling(self) -> None:
        """Start the bot in polling mode"""
        logger.info("Starting bot polling...")
        self.application.run_polling()

    async def periodic_check_task(self, context: CallbackContext) -> None:
        """Periodic task to check for new transactions"""
        logger.info("Running periodic check for new transactions...")
        try:
            await self.check_for_updates()
        except Exception as e:
            logger.error(f"Error in periodic check: {e}")


def main():
    """Main function to start the bot"""
    # Load environment variables or config
    token = os.environ.get(ENV_TELEGRAM_TOKEN)

    try:
        # Initialize components
        gsheets_manager = GoogleSheetsManager(
            os.environ.get(ENV_SHEET_ID),
            os.environ.get(ENV_SHEET_NAME),
            os.environ.get(ENV_SHEET_NAME_POST_REVIEW)
        )
        config_manager = ConfigManager(TELEGRAM_BOT_CONFIG_FILE_NAME)
        fire_base_manager = FireBaseManager(credentials.Certificate(FIREBASE_CREDENTIALS_PATH))
        postgres_manager = PostgresManager(os.environ.get(ENV_POSTGRES_CONNECTION_STRING))
        persistence_wrapper = PersistenceWrapper(fire_base_manager, postgres_manager, gsheets_manager)

        # Create and start the bot
        bot = TelegramBot(token, gsheets_manager, config_manager, persistence_wrapper)

        # Schedule periodic checks (every 5 minutes)
        job_queue = bot.application.job_queue
        job_queue.run_repeating(bot.periodic_check_task, interval=CHECK_INTERVAL_SECONDS,
                                first=FIRST_CHECK_DELAY_SECONDS)

        # Start the bot
        bot.run_polling()

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()
