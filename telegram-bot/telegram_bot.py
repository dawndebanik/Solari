#!/usr/bin/env python
import os
from html import escape

import dotenv
import logging
from typing import Dict, List, Optional, Tuple, Union, Any
import json
import traceback

# Google Sheets API imports
import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from google.auth.exceptions import GoogleAuthError

# Telegram Bot imports
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackContext,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters
)
from telegram.error import TelegramError
from firebase_wrapper import FireBaseManager, Transaction

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

# Define expense categories
EXPENSE_CATEGORIES = [
    "Food", "Commute", "Entertainment", "Home",
    "Utilities", "Shopping", "Health", "Education", "Other"
]

# Google Sheets configuration
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]
CREDENTIALS_FILE = 'credentials.json'  # Your Google API credentials file

# Configuration for the last processed row tracking
CONFIG_FILE = 'bot_config.json'

# load env file
load_dotenv()

class SheetMonitor:
    """Class for monitoring and interacting with Google Sheets"""

    def __init__(self, credentials_file: str, sheet_id: str, sheet_name: str):
        """Initialize the Sheet Monitor with credentials and sheet information"""
        self.credentials_file = credentials_file
        self.sheet_id = sheet_id
        self.sheet_name = sheet_name
        self.client = None
        self.sheet = None
        self.connect()

    def connect(self) -> None:
        """Establish connection to Google Sheets API"""
        try:
            credentials = Credentials.from_service_account_file(
                self.credentials_file, scopes=SCOPES
            )
            self.client = gspread.authorize(credentials)
            self.sheet = self.client.open_by_key(self.sheet_id).worksheet(self.sheet_name)
            logger.info("Successfully connected to Google Sheets")
        except GoogleAuthError as e:
            logger.error(f"Authentication error: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to connect to Google Sheets: {e}")
            raise

    def get_rows(self) -> List[List[str]]:
        """Get all rows from the sheet"""
        try:
            return self.sheet.get_all_values()
        except Exception as e:
            logger.error(f"Failed to get rows from sheet: {e}")
            self.connect()  # Try reconnecting
            return self.sheet.get_all_values()

    def get_new_rows(self, last_processed_row: int) -> Tuple[List[Dict[str, str]], int]:
        """
        Get new rows added since the last check

        Args:
            last_processed_row: The index of the last processed row

        Returns:
            Tuple containing list of new rows as dictionaries and the new last processed row index
        """
        try:
            rows = self.get_rows()
            if not rows:
                return [], last_processed_row

            headers = rows[0]
            if len(headers) < 5:
                logger.error(f"Sheet doesn't have expected columns. Found: {headers}")
                return [], last_processed_row

            new_rows = []
            # Start from the row after the last processed one, skipping header
            for i in range(max(1, last_processed_row + 1), len(rows)):
                row = rows[i]
                if len(row) >= 5:  # Ensure the row has all required fields
                    row_dict = {
                        "transaction_id": row[0],
                        "date": row[1],
                        "time": row[2],
                        "recipient": row[3],
                        "amount": row[4],
                        "bank": row[5],
                        "mode": row[6]
                    }
                    new_rows.append(row_dict)

            if new_rows:
                new_last_processed_row = len(rows) - 1
            else:
                new_last_processed_row = last_processed_row

            return new_rows, new_last_processed_row
        except Exception as e:
            logger.error(f"Error getting new rows: {e}")
            return [], last_processed_row

    def update_transaction_details(self, row_index: int, category: str,
                                   is_shared: bool, user_share: float = None) -> bool:
        """
        Update the transaction with category and sharing information

        Args:
            row_index: The index of the row to update
            category: The expense category
            is_shared: Whether the expense is shared
            user_share: User's share amount if shared

        Returns:
            True if update successful, False otherwise
        """
        try:
            # Adjust row_index to account for 1-based indexing in Google Sheets
            actual_row = row_index + 1

            # Add columns for category, sharing status, and share amount if they don't exist
            headers = self.sheet.row_values(1)
            if "Category" not in headers:
                self.sheet.update_cell(1, len(headers) + 1, "Category")
            category_col = headers.index("Category") + 1 if "Category" in headers else len(headers) + 1

            if "Is Shared" not in headers:
                self.sheet.update_cell(1, len(headers) + 2, "Is Shared")
            shared_col = headers.index("Is Shared") + 1 if "Is Shared" in headers else len(headers) + 2

            if "User Share" not in headers:
                self.sheet.update_cell(1, len(headers) + 3, "User Share")
            user_share_col = headers.index("User Share") + 1 if "User Share" in headers else len(headers) + 3

            # Update cells
            self.sheet.update_cell(actual_row, category_col, category)
            self.sheet.update_cell(actual_row, shared_col, "Yes" if is_shared else "No")
            if is_shared and user_share is not None:
                self.sheet.update_cell(actual_row, user_share_col, str(user_share))
            else:
                self.sheet.update_cell(actual_row, user_share_col, "N/A")

            return True
        except Exception as e:
            logger.error(f"Failed to update transaction details: {e}")
            return False


class ConfigManager:
    """Class for managing bot configuration"""

    def __init__(self, config_file: str):
        """Initialize config manager with config file path"""
        self.config_file = config_file
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file or create default"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            else:
                default_config = {
                    "last_processed_row": 0,
                    "user_ids": []  # List of authorized Telegram user IDs
                }
                self._save_config(default_config)
                return default_config
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return {"last_processed_row": 0, "user_ids": []}

    def _save_config(self, config: Dict[str, Any]) -> bool:
        """Save configuration to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error saving config: {e}")
            return False

    def get_last_processed_row(self) -> int:
        """Get the index of the last processed row"""
        return self.config.get("last_processed_row", 0)

    def update_last_processed_row(self, row_index: int) -> bool:
        """Update the last processed row index"""
        self.config["last_processed_row"] = row_index
        return self._save_config(self.config)

    def is_authorized_user(self, user_id: int) -> bool:
        """Check if a user is authorized"""
        if not self.config.get("user_ids"):
            # If no users configured, allow all (you may want to change this)
            return True
        return user_id in self.config.get("user_ids", [])

    def add_authorized_user(self, user_id: int) -> bool:
        """Add a user to the authorized users list"""
        if user_id not in self.config.get("user_ids", []):
            if "user_ids" not in self.config:
                self.config["user_ids"] = []
            self.config["user_ids"].append(user_id)
            return self._save_config(self.config)
        return True


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
            "transaction": transaction,
            "row_index": row_index,
            "category": None,
            "is_shared": None,
            "user_share": None
        }

    def update_category(self, user_id: int, category: str) -> None:
        """Update the category for a transaction"""
        if user_id in self.conversations:
            self.conversations[user_id]["category"] = category

    def update_sharing_status(self, user_id: int, is_shared: bool) -> None:
        """Update whether a transaction is shared"""
        if user_id in self.conversations:
            self.conversations[user_id]["is_shared"] = is_shared

    def update_user_share(self, user_id: int, share_amount: float) -> None:
        """Update the user's share amount for a shared transaction"""
        if user_id in self.conversations:
            self.conversations[user_id]["user_share"] = share_amount

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
        self.firebase_manager = FireBaseManager()
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        """Set up message and callback handlers"""
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.start_cmd))
        self.application.add_handler(CommandHandler("check", self.check_cmd))
        self.application.add_handler(CommandHandler("authorize", self.authorize_cmd))

        # Conversation handler for transaction categorization flow
        conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.category_selected, pattern=r'^cat_')],
            states={
                SELECTING_SHARING_TYPE: [
                    CallbackQueryHandler(self.sharing_type_selected, pattern=r'^share_')
                ],
                ENTERING_SHARE_AMOUNT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.share_amount_entered)
                ]
            },
            fallbacks=[CommandHandler("cancel", self.cancel_transaction)]
        )
        self.application.add_handler(conv_handler)

        # Error handler
        self.application.add_error_handler(self.error_handler)

    async def start_cmd(self, update: Update, context: CallbackContext) -> None:
        """Handle /start command"""
        user_id = update.effective_user.id
        await update.message.reply_text(
            f"Hi {update.effective_user.first_name}! I'm your expense tracking bot. "
            "I'll notify you when new expenses are added to your Google Sheet.\n\n"
            "Commands:\n"
            "/check - Manually check for new transactions\n"
            "/authorize - Authorize yourself (admin only)"
        )

    async def check_cmd(self, update: Update, context: CallbackContext) -> None:
        """Handle /check command to manually check for new transactions"""
        user_id = update.effective_user.id

        if not self.config_manager.is_authorized_user(user_id):
            await update.message.reply_text("You are not authorized to use this bot.")
            return

        await update.message.reply_text("Checking for new transactions...")

        try:
            new_transactions = await self.check_for_updates()
            if not new_transactions:
                await update.message.reply_text("No new transactions found.")
            else:
                await update.message.reply_text(f"Found {len(new_transactions)} new transactions.")
        except Exception as e:
            logger.error(f"Error checking updates: {e}")
            await update.message.reply_text(f"Error checking for updates: {str(e)}")

    async def authorize_cmd(self, update: Update, context: CallbackContext) -> None:
        """Handle /authorize command to authorize a user"""
        user_id = update.effective_user.id

        # You might want to add admin-only restrictions here
        self.config_manager.add_authorized_user(user_id)
        await update.message.reply_text("You have been authorized to use this bot.")

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
            message = (
                f"📝 <b>New Transaction</b>\n\n"
                f"<b>Date:</b> {escape(transaction['date'])}\n"
                f"<b>Description:</b> {escape(transaction['recipient'])}\n"
                f"<b>Amount:</b> {escape(transaction['amount'])}\n"
                f"<b>Bank:</b> {escape(transaction['bank'])}\n"
                f"<b>Mode:</b> {escape(transaction['mode'])}\n\n"
                f"Please categorize this transaction:"
            )

            # Create inline keyboard for expense categories
            keyboard = []
            row = []
            for i, category in enumerate(EXPENSE_CATEGORIES):
                callback_data = f"cat_{row_index}_{i}"
                row.append(InlineKeyboardButton(category, callback_data=callback_data))

                # 3 buttons per row
                if (i + 1) % 3 == 0 or i == len(EXPENSE_CATEGORIES) - 1:
                    keyboard.append(row)
                    row = []

            reply_markup = InlineKeyboardMarkup(keyboard)

            # Send to all authorized users
            for user_id in self.config_manager.config.get("user_ids", []):
                try:
                    await self.application.bot.send_message(
                        chat_id=user_id,
                        text=message,
                        reply_markup=reply_markup,
                        parse_mode='HTML'
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
            # Extract row_index from callback data (tx_{row_index}_{category_index})
            parts = query.data.split("_")
            if len(parts) >= 2:
                row_index = int(parts[1])

                # Get the transaction details from the sheet
                all_rows = self.sheet_monitor.get_rows()
                if row_index >= len(all_rows):
                    await query.edit_message_text(
                        text="Error: Transaction not found.",
                        reply_markup=None
                    )
                    return ConversationHandler.END

                transaction_row = all_rows[row_index]
                transaction = {
                    "transaction_id": transaction_row[0],
                    "date": transaction_row[1],
                    "time": transaction_row[2],
                    "recipient": transaction_row[3],
                    "amount": transaction_row[4],
                    "bank": transaction_row[5],
                    "mode": transaction_row[6]
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
                        InlineKeyboardButton("Shared Expense", callback_data="share_yes"),
                        InlineKeyboardButton("Solo Expense", callback_data="share_no")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await query.edit_message_text(
                    text=f"Category selected: *{category}*\n\n"
                         f"Is this a shared expense or solo expense?",
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )

                return SELECTING_SHARING_TYPE

        except Exception as e:
            logger.error(f"Error in category selection: {e}")
            await query.edit_message_text(
                text=f"An error occurred: {str(e)}",
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
                    text="Error: Conversation context not found. Please try again.",
                    reply_markup=None
                )
                return ConversationHandler.END

            # Get the sharing selection
            is_shared = query.data == "share_yes"

            # Update context with sharing status
            self.transaction_context.update_sharing_status(user_id, is_shared)

            if is_shared:
                # Ask for user's share
                total_amount = conversation["transaction"]["Amount"]
                await query.edit_message_text(
                    text=f"This is a shared expense.\n\n"
                         f"Total amount: *{total_amount}*\n\n"
                         f"Please enter your share amount:",
                    parse_mode='Markdown',
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
                text=f"An error occurred: {str(e)}",
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
                await update.message.reply_text(
                    "Error: Conversation context not found. Please try again."
                )
                return ConversationHandler.END

            # Validate the share amount
            try:
                share_amount = float(share_text)
                total_amount = float(conversation["transaction"]["Amount"])

                if share_amount < 0:
                    await update.message.reply_text(
                        "Share amount cannot be negative. Please enter a valid amount:"
                    )
                    return ENTERING_SHARE_AMOUNT

                if share_amount > total_amount:
                    await update.message.reply_text(
                        f"Share amount ({share_amount}) cannot be greater than "
                        f"total amount ({total_amount}). Please enter a valid amount:"
                    )
                    return ENTERING_SHARE_AMOUNT

            except ValueError:
                await update.message.reply_text(
                    "Invalid amount format. Please enter a numeric value:"
                )
                return ENTERING_SHARE_AMOUNT

            # Update context with user's share
            self.transaction_context.update_user_share(user_id, share_amount)

            # Complete the transaction
            await self.complete_transaction(update, context, user_id)

        except Exception as e:
            logger.error(f"Error processing share amount: {e}")
            await update.message.reply_text(
                f"An error occurred: {str(e)}\n\nPlease try again later."
            )

        return ConversationHandler.END

    async def complete_transaction(self, update: Update, context: CallbackContext,
                                   user_id: int) -> None:
        """Complete the transaction processing and update the sheet"""
        conversation = self.transaction_context.get_conversation(user_id)

        if not conversation:
            if hasattr(update, 'message'):
                await update.message.reply_text("Error: Transaction context not found.")
            return

        try:
            category = conversation["category"]
            is_shared = conversation["is_shared"]
            user_share = conversation["user_share"] if is_shared else None
            row_index = conversation["row_index"]

            # Log to Firebase
            success = self.firebase_manager.write_transaction(
                Transaction(
                    conversation['transaction']['transaction_id'],
                    conversation['transaction']['date'],
                    conversation['transaction']['time'],
                    conversation['transaction']['recipient'],
                    conversation['transaction']['amount'],
                    conversation['transaction']['bank'],
                    conversation['transaction']['mode'],
                    category,
                    is_shared,
                    user_share
                )
            )

            # Format a confirmation message
            transaction = conversation["transaction"]
            if success:
                message = (
                    f"✅ *Transaction Updated*\n\n"
                    f"*Description:* {transaction['Description']}\n"
                    f"*Amount:* {transaction['Amount']}\n"
                    f"*Category:* {category}\n"
                    f"*Type:* {'Shared' if is_shared else 'Solo'} expense\n"
                )

                if is_shared:
                    message += f"*Your Share:* {user_share}\n"
            else:
                message = (
                    f"❌ *Failed to Update Transaction*\n\n"
                    f"There was an error updating the transaction. "
                    f"Please try again later."
                )

            # Send confirmation message
            if hasattr(update, 'callback_query') and update.callback_query:
                await update.callback_query.edit_message_text(
                    text=message,
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    text=message,
                    parse_mode='Markdown'
                )

        except Exception as e:
            logger.error(f"Error completing transaction: {e}")
            error_message = f"An error occurred: {str(e)}"

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
    token = os.environ.get('TELEGRAM_TOKEN')

    try:
        # Initialize components
        sheet_monitor = SheetMonitor(CREDENTIALS_FILE, os.environ.get('SHEET_ID'), os.environ.get('SHEET_NAME'))
        config_manager = ConfigManager(CONFIG_FILE)

        # Create and start the bot
        bot = TelegramBot(token, sheet_monitor, config_manager)

        # Schedule periodic checks (every 5 minutes)
        job_queue = bot.application.job_queue
        job_queue.run_repeating(bot.periodic_check_task, interval=5, first=10)

        # Start the bot
        bot.run_polling()

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()