from telegram import InlineKeyboardButton

from constants import CALLBACK_CATEGORY_PREFIX, BUTTONS_PER_ROW, BTN_SHARED_EXPENSE, BTN_SOLO_EXPENSE, \
    CALLBACK_SHARE_NO, CALLBACK_SHARE_YES

# Define constants for expense categories
EXPENSE_CATEGORIES = [
    "Investment", "Home & Essentials", "Commute",
    "Discretionary", "Shopping", "Health & Wellbeing",
    "Miscellaneous"
]


async def get_category_keyboard(transaction_id: str):
    # Create inline keyboard for expense categories
    keyboard = []
    row = []
    for i, category in enumerate(EXPENSE_CATEGORIES):
        callback_data = f"{CALLBACK_CATEGORY_PREFIX}{transaction_id}_{i}"
        row.append(InlineKeyboardButton(category, callback_data=callback_data))

        # 3 buttons per row
        if (i + 1) % BUTTONS_PER_ROW == 0 or i == len(EXPENSE_CATEGORIES) - 1:
            keyboard.append(row)
            row = []
    return keyboard


async def get_sharing_type_keyboard(transaction_id: str):
    # Create keyboard for sharing selection
    keyboard = [
        [
            InlineKeyboardButton(BTN_SHARED_EXPENSE, callback_data=f"{CALLBACK_SHARE_YES}_{transaction_id}"),
            InlineKeyboardButton(BTN_SOLO_EXPENSE, callback_data=f"{CALLBACK_SHARE_NO}_{transaction_id}")
        ]
    ]
    return keyboard
