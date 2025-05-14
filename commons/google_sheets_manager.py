import logging
from typing import List, Tuple, Dict

import gspread
from google.auth.exceptions import GoogleAuthError
from google.oauth2.service_account import Credentials
from gspread import WorksheetNotFound

from constants import KEY_TRANSACTION_ID, KEY_DATE, KEY_TIME, KEY_RECIPIENT, KEY_AMOUNT, KEY_BANK, KEY_MODE, \
    COL_CATEGORY, COL_IS_SHARED, COL_USER_SHARE, YES_VALUE, NO_VALUE, NA_VALUE, COL_BANK, COL_MODE, COL_AMOUNT, \
    COL_RECIPIENT, COL_TIME, COL_DATE, COL_TRANSACTION_ID
from env import SERVICE_ACCOUNT_CREDENTIALS_PATH
from persistence.models import Transaction

logger = logging.getLogger(__name__)

# Google Sheets configuration constants
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]


class GoogleSheetsManager:
    """Class for monitoring and interacting with Google Sheets"""

    def __init__(self, sheet_id: str, sheet_name: str, write_sheet_name: str):
        """Initialize the Sheet Monitor with credentials and sheet information"""
        self.sheet_id = sheet_id
        self.credentials_file = SERVICE_ACCOUNT_CREDENTIALS_PATH
        self.sheet_name = sheet_name
        self.write_sheet_name = write_sheet_name
        self.client = None
        self.sheet = None
        self.write_sheet = None
        self.connect()

    def create_sheet_if_not_exists(self, sheet_name: str):
        try:
            sheet = self.spreadsheet.worksheet(sheet_name)
        except WorksheetNotFound:
            # Sheet not found, create it
            sheet = self.spreadsheet.add_worksheet(title=sheet_name, rows=100, cols=20)

        return sheet

    def connect(self) -> None:
        """Establish connection to Google Sheets API"""
        try:
            credentials = Credentials.from_service_account_file(
                self.credentials_file, scopes=SCOPES
            )
            self.client = gspread.authorize(credentials)
            self.spreadsheet = self.client.open_by_key(self.sheet_id)
            self.sheet = self.create_sheet_if_not_exists(self.sheet_name)
            self.write_sheet = self.create_sheet_if_not_exists(self.write_sheet_name)
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

    def add_reviewed_transaction(self, transaction: Transaction) -> bool:
        """
        Append a new transaction to the Google Sheet.

        Args:
            transaction: A Transaction object containing all transaction details.

        Returns:
            True if the write was successful, False otherwise.
        """
        try:
            # Get existing headers
            headers = self.write_sheet.row_values(1)

            # Define expected headers and values
            expected_headers = [
                COL_TRANSACTION_ID, COL_DATE, COL_TIME, COL_RECIPIENT, COL_AMOUNT,
                COL_BANK, COL_MODE, COL_CATEGORY, COL_IS_SHARED, COL_USER_SHARE
            ]
            header_map = {header: index for index, header in enumerate(headers)}

            # Add any missing headers
            for idx, expected_header in enumerate(expected_headers):
                if expected_header not in header_map:
                    self.write_sheet.update_cell(1, len(headers) + 1, expected_header)
                    headers.append(expected_header)
                    header_map[expected_header] = len(headers) - 1

            # Build row in correct order
            row = [object()] * len(headers)
            row[header_map[COL_TRANSACTION_ID]] = transaction.transaction_id
            row[header_map[COL_DATE]] = transaction.date
            row[header_map[COL_TIME]] = transaction.time
            row[header_map[COL_RECIPIENT]] = transaction.recipient
            row[header_map[COL_AMOUNT]] = transaction.amount
            row[header_map[COL_BANK]] = transaction.bank
            row[header_map[COL_MODE]] = transaction.mode
            row[header_map[COL_CATEGORY]] = transaction.category
            row[header_map[COL_IS_SHARED]] = YES_VALUE if transaction.is_shared else NO_VALUE
            row[header_map[COL_USER_SHARE]] = transaction.user_share

            # Append the row
            self.write_sheet.append_row(row)
            return True
        except Exception as e:
            logger.error(f"Failed to write transaction: {e}")
            return False

    def add_raw_transaction(self, transaction: Transaction) -> bool:
        """
        Append a new transaction to the Google Sheet.

        Args:
            transaction: A Transaction object containing all transaction details.

        Returns:
            True if the write was successful, False otherwise.
        """
        try:
            # Get existing headers
            headers = self.sheet.row_values(1)

            # Define expected headers and values
            expected_headers = [
                COL_TRANSACTION_ID, COL_DATE, COL_TIME, COL_RECIPIENT, COL_AMOUNT,
                COL_BANK, COL_MODE
            ]
            header_map = {header: index for index, header in enumerate(headers)}

            # Add any missing headers
            for idx, expected_header in enumerate(expected_headers):
                if expected_header not in header_map:
                    self.sheet.update_cell(1, len(headers) + 1, expected_header)
                    headers.append(expected_header)
                    header_map[expected_header] = len(headers) - 1

            # Build row in correct order
            row = [""] * len(headers)
            row[header_map[COL_TRANSACTION_ID]] = transaction.transaction_id
            row[header_map[COL_DATE]] = transaction.date
            row[header_map[COL_TIME]] = transaction.time
            row[header_map[COL_RECIPIENT]] = transaction.recipient
            row[header_map[COL_AMOUNT]] = str(transaction.amount)
            row[header_map[COL_BANK]] = transaction.bank
            row[header_map[COL_MODE]] = transaction.mode

            # Append the row
            self.sheet.append_row(row)
            return True
        except Exception as e:
            logger.error(f"Failed to write transaction: {e}")
            return False
