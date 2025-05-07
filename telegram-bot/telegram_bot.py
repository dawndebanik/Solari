#!/usr/bin/env python
import logging
import os
import traceback
from html import escape
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv

from persistence.models import Transaction
from persistence.persistence_wrapper import PersistenceWrapper
from sheet_monitor import SheetMonitor

# Telegram Bot imports
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackContext,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters
)

# Constants and configs
from config_manager import ConfigManager
from constants import CREDENTIALS_FILE_NAME, CONFIG_FILE, ENV_TELEGRAM_TOKEN, ENV_SHEET_ID, ENV_SHEET_NAME, \
    CMD_START, CMD_CHECK, CMD_AUTHORIZE, CMD_CANCEL, CALLBACK_CATEGORY_PREFIX, \
    CALLBACK_SHARE_PREFIX, CALLBACK_SHARE_YES, CALLBACK_SHARE_NO, MSG_START, MSG_UNAUTHORIZED, MSG_CHECKING, \
    MSG_NO_TRANSACTIONS, MSG_FOUND_TRANSACTIONS, MSG_AUTHORIZED, MSG_TRANSACTION_NOTIFICATION, \
    MSG_TRANSACTION_NOT_FOUND, MSG_CATEGORY_SELECTED, MSG_CONTEXT_NOT_FOUND, MSG_SHARED_EXPENSE, \
    MSG_INVALID_SHARE_NEGATIVE, MSG_INVALID_SHARE_EXCEEDS_TOTAL, MSG_INVALID_AMOUNT_FORMAT, MSG_TRANSACTION_UPDATED, \
    MSG_TRANSACTION_UPDATE_FAILED, MSG_ERROR, KEY_TRANSACTION_ID, KEY_DATE, \
    KEY_TIME, KEY_RECIPIENT, KEY_AMOUNT, KEY_BANK, KEY_MODE, CONFIG_USER_IDS, \
    CONTEXT_TRANSACTION, CONTEXT_ROW_INDEX, CONTEXT_CATEGORY, CONTEXT_IS_SHARED, CONTEXT_USER_SHARE, BTN_SHARED_EXPENSE, \
    BTN_SOLO_EXPENSE, BUTTONS_PER_ROW, \
    CHECK_INTERVAL_SECONDS, FIRST_CHECK_DELAY_SECONDS, HTML_PARSE_MODE, SHARED_TYPE, SOLO_TYPE

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Define conversation states
(
    SELECTING_CATEGORY,
    SELECTING_SHARING_TYPE,
    ENTERING_SHARE_AMOUNT
) = range(3)

# Define constants for expense categories
EXPENSE_CATEGORIES = [
    "Food", "Commute", "Entertainment", "Home",
    "Utilities", "Shopping", "Health", "Education", "Other"
]

# load env file
load_dotenv()


class TransactionContext:
    """Class for storing transaction context during conversation flow"""

    def __init__(self):
        """Initialize transaction context storage"""
        self.conversations = {}

    def start_conversation(self, user_id: int, transaction: Dict[str, str],
                           row_index: int) -> None:
        """
        Start a new conversation for processing a transaction

        Args:
            user_id: The Telegram user ID
            transaction: Transaction details
            row_index: The row index in Google Sheets
        """
        self.conversations[user_id] = {
            CONTEXT_TRANSACTION: transaction,
            CONTEXT_ROW_INDEX: row_index,
            CONTEXT_CATEGORY: None,
            CONTEXT_IS_SHARED: None,
            CONTEXT_USER_SHARE: None
        }

    def update_category(self, user_id: int, category: str) -> None:
        """Update the category for a transaction"""
        if user_id in self.conversations:
            self.conversations[user_id][CONTEXT_CATEGORY] = category

    def update_sharing_status(self, user_id: int, is_shared: bool) -> None:
        """Update whether a transaction is shared"""
        if user_id in self.conversations:
            self.conversations[user_id][CONTEXT_IS_SHARED] = is_shared

    def update_user_share(self, user_id: int, share_amount: float) -> None:
        """Update the user's share amount for a shared transaction"""
        if user_id in self.conversations:
            self.conversations[user_id][CONTEXT_USER_SHARE] = share_amount

    def get_conversation(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get the current conversation context for a user"""
        return self.conversations.get(user_id)

    def end_conversation(self, user_id: int) -> None:
        """End and clean up a conversation"""
        if user_id in self.conversations:
            del self.conversations[user_id]


class TelegramBot:
    """Main Telegram bot class"""

    def __init__(self, token: str, sheet_monitor: SheetMonitor,
                 config_manager: ConfigManager):
        """
        Initialize the Telegram bot

        Args:
            token: Telegram Bot API token
            sheet_monitor: Sheet monitor instance
            config_manager: Config manager instance
        """
        self.application = Application.builder().token(token).build()
        self.sheet_monitor = sheet_monitor
        self.config_manager = config_manager
        self.transaction_context = TransactionContext()
        self.persistence_wrapper = PersistenceWrapper()
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        """Set up message and callback handlers"""
        # Command handlers
        self.application.add_handler(CommandHandler(CMD_START, self.start_cmd))
        self.application.add_handler(CommandHandler(CMD_CHECK, self.check_cmd))
        self.application.add_handler(CommandHandler(CMD_AUTHORIZE, self.authorize_cmd))

        # Conversation handler for transaction categorization flow
        conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.category_selected, pattern=f"^{CALLBACK_CATEGORY_PREFIX}")],
            states={
                SELECTING_SHARING_TYPE: [
                    CallbackQueryHandler(self.sharing_type_selected, pattern=f"^{CALLBACK_SHARE_PREFIX}")
                ],
                ENTERING_SHARE_AMOUNT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.share_amount_entered)
                ]
            },
            fallbacks=[CommandHandler(CMD_CANCEL, self.cancel_transaction)]
        )
        self.application.add_handler(conv_handler)

        # Error handler
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

        if not self.config_manager.is_authorized_user(user_id):
            await update.message.reply_text(MSG_UNAUTHORIZED)
            return

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

    async def authorize_cmd(self, update: Update, context: CallbackContext) -> None:
        """Handle /authorize command to authorize a user"""
        user_id = update.effective_user.id

        # You might want to add admin-only restrictions here
        self.config_manager.add_authorized_user(user_id)
        await update.message.reply_text(MSG_AUTHORIZED)

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
                row_index = last_processed_row + index + 1
                await self.send_transaction_notification(transaction, row_index)

        return new_transactions

    async def send_transaction_notification(self, transaction: Dict[str, str],
                                            row_index: int) -> None:
        """
        Send a notification about a new transaction and start the categorization flow

        Args:
            transaction: Transaction details
            row_index: Row index in the spreadsheet
        """
        try:
            # Format the transaction message
            message = MSG_TRANSACTION_NOTIFICATION.format(
                date=escape(transaction[KEY_DATE]),
                recipient=escape(transaction[KEY_RECIPIENT]),
                amount=escape(transaction[KEY_AMOUNT]),
                bank=escape(transaction[KEY_BANK]),
                mode=escape(transaction[KEY_MODE])
            )

            # Create inline keyboard for expense categories
            keyboard = []
            row = []
            for i, category in enumerate(EXPENSE_CATEGORIES):
                callback_data = f"{CALLBACK_CATEGORY_PREFIX}{row_index}_{i}"
                row.append(InlineKeyboardButton(category, callback_data=callback_data))

                # 3 buttons per row
                if (i + 1) % BUTTONS_PER_ROW == 0 or i == len(EXPENSE_CATEGORIES) - 1:
                    keyboard.append(row)
                    row = []

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
                except TelegramError as e:
                    logger.error(f"Failed to send message to user {user_id}: {e}")

        except Exception as e:
            logger.error(f"Error sending transaction notification: {e}")

    async def category_selected(self, update: Update,
                                context: CallbackContext) -> int:
        """Handle category selection and ask about sharing"""
        query = update.callback_query
        await query.answer()

        try:
            # Extract row_index from callback data (cat_{row_index}_{category_index})
            parts = query.data.split("_")
            if len(parts) >= 2:
                row_index = int(parts[1])

                # Get the transaction details from the sheet
                all_rows = self.sheet_monitor.get_rows()
                if row_index >= len(all_rows):
                    await query.edit_message_text(
                        text=MSG_TRANSACTION_NOT_FOUND,
                        reply_markup=None
                    )
                    return ConversationHandler.END

                transaction_row = all_rows[row_index]
                transaction = {
                    KEY_TRANSACTION_ID: transaction_row[0],
                    KEY_DATE: transaction_row[1],
                    KEY_TIME: transaction_row[2],
                    KEY_RECIPIENT: transaction_row[3],
                    KEY_AMOUNT: transaction_row[4],
                    KEY_BANK: transaction_row[5],
                    KEY_MODE: transaction_row[6]
                }

                # Store the context for this conversation
                user_id = update.effective_user.id
                self.transaction_context.start_conversation(user_id, transaction, row_index)

                # Extract category index from callback data
                category_index = int(query.data.split("_")[2])
                category = EXPENSE_CATEGORIES[category_index]

                # Update context with selected category
                self.transaction_context.update_category(user_id, category)

                # Create keyboard for sharing selection
                keyboard = [
                    [
                        InlineKeyboardButton(BTN_SHARED_EXPENSE, callback_data=CALLBACK_SHARE_YES),
                        InlineKeyboardButton(BTN_SOLO_EXPENSE, callback_data=CALLBACK_SHARE_NO)
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await query.edit_message_text(
                    text=MSG_CATEGORY_SELECTED.format(category=category),
                    parse_mode=HTML_PARSE_MODE,
                    reply_markup=reply_markup
                )

                return SELECTING_SHARING_TYPE

        except Exception as e:
            logger.error(f"Error in category selection: {e}")
            await query.edit_message_text(
                text=MSG_ERROR.format(error=str(e)),
                reply_markup=None
            )

        return ConversationHandler.END

    async def sharing_type_selected(self, update: Update,
                                    context: CallbackContext) -> int:
        """Handle sharing type selection"""
        query = update.callback_query
        await query.answer()

        try:
            user_id = update.effective_user.id
            conversation = self.transaction_context.get_conversation(user_id)

            if not conversation:
                await query.edit_message_text(
                    text=MSG_CONTEXT_NOT_FOUND,
                    reply_markup=None
                )
                return ConversationHandler.END

            # Get the sharing selection
            is_shared = query.data == CALLBACK_SHARE_YES

            # Update context with sharing status
            self.transaction_context.update_sharing_status(user_id, is_shared)

            if is_shared:
                # Ask for user's share
                total_amount = conversation[CONTEXT_TRANSACTION][KEY_AMOUNT]
                await query.edit_message_text(
                    text=MSG_SHARED_EXPENSE.format(amount=total_amount),
                    parse_mode=HTML_PARSE_MODE,
                    reply_markup=None
                )
                return ENTERING_SHARE_AMOUNT
            else:
                # Complete the transaction as solo expense
                await self.complete_transaction(update, context, user_id)
                return ConversationHandler.END

        except Exception as e:
            logger.error(f"Error in sharing type selection: {e}")
            await query.edit_message_text(
                text=MSG_ERROR.format(error=str(e)),
                reply_markup=None
            )

        return ConversationHandler.END

    async def share_amount_entered(self, update: Update,
                                   context: CallbackContext) -> int:
        """Handle user's share amount entry"""
        user_id = update.effective_user.id
        share_text = update.message.text.strip()

        try:
            conversation = self.transaction_context.get_conversation(user_id)

            if not conversation:
                await update.message.reply_text(MSG_CONTEXT_NOT_FOUND)
                return ConversationHandler.END

            # Validate the share amount
            try:
                share_amount = float(share_text)
                total_amount = float(conversation[CONTEXT_TRANSACTION][KEY_AMOUNT])

                if share_amount < 0:
                    await update.message.reply_text(MSG_INVALID_SHARE_NEGATIVE)
                    return ENTERING_SHARE_AMOUNT

                if share_amount > total_amount:
                    await update.message.reply_text(
                        MSG_INVALID_SHARE_EXCEEDS_TOTAL.format(
                            share=share_amount,
                            total=total_amount
                        )
                    )
                    return ENTERING_SHARE_AMOUNT

            except ValueError:
                await update.message.reply_text(MSG_INVALID_AMOUNT_FORMAT)
                return ENTERING_SHARE_AMOUNT

            # Update context with user's share
            self.transaction_context.update_user_share(user_id, share_amount)

            # Complete the transaction
            await self.complete_transaction(update, context, user_id)

        except Exception as e:
            logger.error(f"Error processing share amount: {e}")
            await update.message.reply_text(MSG_ERROR.format(error=str(e)))

        return ConversationHandler.END

    async def complete_transaction(self, update: Update, context: CallbackContext,
                                   user_id: int) -> None:
        """Complete the transaction processing and update the sheet"""
        conversation = self.transaction_context.get_conversation(user_id)

        if not conversation:
            if hasattr(update, 'message'):
                await update.message.reply_text(MSG_CONTEXT_NOT_FOUND)
            return

        try:
            category = conversation[CONTEXT_CATEGORY]
            is_shared = conversation[CONTEXT_IS_SHARED]
            user_share = conversation[CONTEXT_USER_SHARE] if is_shared else None

            # Log to persistence store
            success = self.persistence_wrapper.write_transaction(
                Transaction(
                    conversation[CONTEXT_TRANSACTION][KEY_TRANSACTION_ID],
                    conversation[CONTEXT_TRANSACTION][KEY_DATE],
                    conversation[CONTEXT_TRANSACTION][KEY_TIME],
                    conversation[CONTEXT_TRANSACTION][KEY_RECIPIENT],
                    conversation[CONTEXT_TRANSACTION][KEY_AMOUNT],
                    conversation[CONTEXT_TRANSACTION][KEY_BANK],
                    conversation[CONTEXT_TRANSACTION][KEY_MODE],
                    category,
                    is_shared,
                    user_share
                )
            )

            # Format a confirmation message
            transaction = conversation[CONTEXT_TRANSACTION]
            if success:
                share_info = f"*Your Share:* {user_share}\n" if is_shared else ""
                message = MSG_TRANSACTION_UPDATED.format(
                    recipient=transaction[KEY_RECIPIENT],
                    amount=transaction[KEY_AMOUNT],
                    category=category,
                    type=SHARED_TYPE if is_shared else SOLO_TYPE,
                    share_info=share_info
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
        self.transaction_context.end_conversation(user_id)

    async def cancel_transaction(self, update: Update,
                                 context: CallbackContext) -> int:
        """Cancel the current transaction categorization"""
        user_id = update.effective_user.id
        self.transaction_context.end_conversation(user_id)

        await update.message.reply_text(
            "Transaction categorization cancelled."
        )
        return ConversationHandler.END

    async def error_handler(self, update: object, context: CallbackContext) -> None:
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
        sheet_monitor = SheetMonitor(CREDENTIALS_FILE_NAME, os.environ.get(ENV_SHEET_ID),
                                     os.environ.get(ENV_SHEET_NAME))
        config_manager = ConfigManager(CONFIG_FILE)

        # Create and start the bot
        bot = TelegramBot(token, sheet_monitor, config_manager)

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
