import logging
from typing import List, Tuple, Dict

import gspread
from google.auth.exceptions import GoogleAuthError
from google.oauth2.service_account import Credentials

from constants import KEY_TRANSACTION_ID, KEY_DATE, KEY_TIME, KEY_RECIPIENT, KEY_AMOUNT, KEY_BANK, KEY_MODE, \
    COL_CATEGORY, COL_IS_SHARED, COL_USER_SHARE, YES_VALUE, NO_VALUE, NA_VALUE


logger = logging.getLogger(__name__)

# Google Sheets configuration constants
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

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
            min_expected_columns = 7  # Adjust based on expected number of columns
            if len(headers) < min_expected_columns:
                logger.error(f"Sheet doesn't have expected columns. Found: {headers}")
                return [], last_processed_row

            new_rows = []
            # Start from the row after the last processed one, skipping header
            for i in range(max(1, last_processed_row + 1), len(rows)):
                row = rows[i]
                if len(row) >= min_expected_columns:  # Ensure the row has all required fields
                    row_dict = {
                        KEY_TRANSACTION_ID: row[0],
                        KEY_DATE: row[1],
                        KEY_TIME: row[2],
                        KEY_RECIPIENT: row[3],
                        KEY_AMOUNT: row[4],
                        KEY_BANK: row[5],
                        KEY_MODE: row[6]
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
            if COL_CATEGORY not in headers:
                self.sheet.update_cell(1, len(headers) + 1, COL_CATEGORY)
            category_col = headers.index(COL_CATEGORY) + 1 if COL_CATEGORY in headers else len(headers) + 1

            if COL_IS_SHARED not in headers:
                self.sheet.update_cell(1, len(headers) + 2, COL_IS_SHARED)
            shared_col = headers.index(COL_IS_SHARED) + 1 if COL_IS_SHARED in headers else len(headers) + 2

            if COL_USER_SHARE not in headers:
                self.sheet.update_cell(1, len(headers) + 3, COL_USER_SHARE)
            user_share_col = headers.index(COL_USER_SHARE) + 1 if COL_USER_SHARE in headers else len(headers) + 3

            # Update cells
            self.sheet.update_cell(actual_row, category_col, category)
            self.sheet.update_cell(actual_row, shared_col, YES_VALUE if is_shared else NO_VALUE)
            if is_shared and user_share is not None:
                self.sheet.update_cell(actual_row, user_share_col, str(user_share))
            else:
                self.sheet.update_cell(actual_row, user_share_col, NA_VALUE)

            return True
        except Exception as e:
            logger.error(f"Failed to update transaction details: {e}")
            return False
