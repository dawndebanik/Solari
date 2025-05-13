ENV_TELEGRAM_TOKEN = 'TELEGRAM_TOKEN'
ENV_SHEET_ID = 'SHEET_ID'
ENV_SHEET_NAME = 'SHEET_NAME'
ENV_SHEET_NAME_POST_REVIEW = 'SHEET_NAME_POST_REVIEW'
ENV_POSTGRES_CONNECTION_STRING = 'POSTGRES_CONNECTION_STRING'
CMD_START = "start"
CMD_CHECK = "check"
CMD_AUTHORIZE = "authorize"
CMD_CANCEL = "cancel"
CALLBACK_CATEGORY_PREFIX = "cat_"
CALLBACK_SHARE_PREFIX = "share_"
CALLBACK_SHARE_YES = "share_yes"
CALLBACK_SHARE_NO = "share_no"
MSG_START = (
    "Hi {first_name}! I'm your expense tracking bot. "
    "I'll notify you when new expenses are added to your Google Sheet.\n\n"
    "<b>Commands:</b>\n"
    "/check - Manually check for new transactions\n"
)
MSG_CHECKING = "Checking for new transactions..."
MSG_NO_TRANSACTIONS = "No new transactions found."
MSG_FOUND_TRANSACTIONS = "Found {count} new transactions."
MSG_TRANSACTION_NOTIFICATION = (
    "📝 <b>New Transaction</b>\n\n"
    "<b>Date:</b> {date}\n"
    "<b>Recipient:</b> {recipient}\n"
    "<b>Amount:</b> {amount}\n"
    "<b>Bank:</b> {bank}\n"
    "<b>Mode:</b> {mode}\n\n"
    "Please categorize this transaction:"
)
MSG_TRANSACTION_NOT_FOUND = "Error: Transaction not found."
MSG_CATEGORY_SELECTED = (
    "Category selected: <b>{category}</b>\n\n"
    "Is this a shared expense or solo expense?"
)
MSG_CONTEXT_NOT_FOUND = "Error: Conversation context not found. Please try again."
MSG_SHARED_EXPENSE = (
    "This is a shared expense.\n\n"
    "Total amount: <b>{amount}</b>\n\n"
    "Please enter your share amount:"
)
MSG_INVALID_SHARE_NEGATIVE = "Share amount cannot be negative. Please enter a valid amount:"
MSG_INVALID_SHARE_EXCEEDS_TOTAL = (
    "Share amount ({share}) cannot be greater than "
    "total amount ({total}). Please enter a valid amount:"
)
MSG_INVALID_AMOUNT_FORMAT = "Invalid amount format. Please enter a numeric value:"
MSG_TRANSACTION_UPDATED = (
    "✅ <b>Transaction Updated</b>\n\n"
    "<b>Recipient:</b> {recipient}\n"
    "<b>Amount:</b> {amount}\n"
    "<b>Category:</b> {category}\n"
    "<b>Type:</b> {type} expense\n"
    "{share_info}"
)
MSG_TRANSACTION_UPDATE_FAILED = (
    "❌ <b>Failed to Update Transaction</b>\n\n"
    "There was an error updating the transaction. "
    "Please try again later."
)
MSG_TRANSACTION_CANCELLED = "Transaction categorization cancelled."
MSG_ERROR = "An error occurred: {error}"
MSG_GENERAL_ERROR = "An error occurred. Please try again later."

# Column names
COL_BANK = "Bank"
COL_MODE = "Mode"
COL_AMOUNT = "Amount"
COL_RECIPIENT = "Recipient"
COL_TIME = "Time"
COL_DATE = "Date"
COL_TRANSACTION_ID = "Transaction ID"
COL_CATEGORY = "Category"
COL_IS_SHARED = "Is Shared"
COL_USER_SHARE = "User Share"


KEY_TRANSACTION_ID = "transaction_id"
KEY_DATE = "date"
KEY_TIME = "time"
KEY_RECIPIENT = "recipient"
KEY_AMOUNT = "amount"
KEY_BANK = "bank"
KEY_MODE = "mode"


CONFIG_LAST_PROCESSED_ROW = "last_processed_row"
CONFIG_USER_IDS = "user_ids"
CONTEXT_TRANSACTION = "transaction"
CONTEXT_ROW_INDEX = "row_index"
CONTEXT_CATEGORY = "category"
CONTEXT_IS_SHARED = "is_shared"
CONTEXT_USER_SHARE = "user_share"
BTN_SHARED_EXPENSE = "Shared Expense"
BTN_SOLO_EXPENSE = "Solo Expense"
YES_VALUE = "Yes"
NO_VALUE = "No"
NA_VALUE = "N/A"
DEFAULT_LAST_PROCESSED_ROW = 0
DEBANIKS_USER_ID = 6585093194
BUTTONS_PER_ROW = 2
CHECK_INTERVAL_SECONDS = 5
FIRST_CHECK_DELAY_SECONDS = 10
HTML_PARSE_MODE = 'HTML'
SHARED_TYPE = 'Shared'
SOLO_TYPE = 'Solo'
