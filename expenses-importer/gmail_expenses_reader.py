import base64
import datetime
import os
import pickle
import re

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from commons.constants import ENV_SHEET_ID, ENV_SHEET_NAME, ENV_SHEET_NAME_POST_REVIEW
from commons.google_sheets_manager import GoogleSheetsManager
from env import TOKEN_PATH, GMAIL__OAUTH_CREDENTIALS_PATH
from helpers import parse_by_bank, detect_bank
from persistence.models import Transaction
from utils import get_transaction_id

# Scope for reading Gmail messages
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']


# Authenticate with Google API
def authenticate():
    creds = None
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, 'rb') as token:
            creds = pickle.load(token)

    # If there are no (valid) credentials available, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(GMAIL__OAUTH_CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=8080)

        # Save the credentials for the next run
        with open(TOKEN_PATH, 'wb') as token:
            pickle.dump(creds, token)

    return build('gmail', 'v1', credentials=creds)


# Parsing functions (these can be refined based on the real email content)
def parse_hdfc(body):
    amount_match = re.search(r'7883\s+for\s+(?:Rs\.?|INR|\b[A-Z]{3}\b)\s+([\d,]+(\.\d{1,})?)', body)
    description_match = re.search(r'at\s+(.*?)\s+on', body)
    if amount_match and description_match:
        amount = float(amount_match[1].replace(',', ''))
        description = description_match[1].strip()
        return {"description": description, "amount": amount}
    return None


def parse_icici(body):
    amount_match = re.search(r'transaction\s+of\s+(?:Rs\.?|INR|\b[A-Z]{3}\b)\s+([\d,]+(\.\d{1,})?)', body)
    description_match = re.search(r'Info:\s+(.*?)\.', body)
    if amount_match and description_match:
        amount = float(amount_match[1].replace(',', ''))
        description = description_match[1].strip()
        return {"description": description, "amount": amount}
    return None


# Add similar parse functions for HSBC, Axis, and Federal...
def get_label_id_by_name(service, label_name):
    labels = service.users().labels().list(userId='me').execute().get('labels', [])
    for label in labels:
        if label['name'] == label_name:
            return label['id']
    return None

def convert_epoch_ms_to_datetime(epoch_ms: int):
    """
    Convert epoch timestamp in milliseconds to a formatted date and time string.

    Args:
        epoch_ms (int): Epoch time in milliseconds.
        to_utc (bool): If True, returns time in UTC. Otherwise, returns local time.

    Returns:
        str: Formatted datetime string (YYYY-MM-DD HH:MM:SS)
    """
    epoch_sec = epoch_ms / 1000  # Convert to seconds

    dt = datetime.datetime.fromtimestamp(epoch_sec)
    return dt.strftime('%Y-%m-%d %H:%M:%S')

def process_emails(service, label_name='CreditCardTransactions'):
    gsheets_manager = GoogleSheetsManager(
        os.environ.get(ENV_SHEET_ID),
        os.environ.get(ENV_SHEET_NAME),
        os.environ.get(ENV_SHEET_NAME_POST_REVIEW)
    )

    # Getting all threads under the CreditCardTransactions label but not yet processed
    label_id = get_label_id_by_name(service, label_name)
    if not label_id:
        raise Exception(f'No labels with name {label_name} were found')

    processed_label_id = get_label_id_by_name(service, 'Processed')
    results = service.users().messages().list(userId='me', labelIds=[label_id], q='-label:Processed').execute()
    threads = results.get('messages', [])

    # Mocking the spreadsheet (you can integrate it with Google Sheets API)
    # Creating a simple dataframe to store processed transactions
    transaction_ids = set()

    print(f"Found {len(threads)} credit card transaction entries to process!")

    for thread in threads:
        try:
            message = service.users().messages().get(userId='me', id=thread['id']).execute()

            # Parse out the body
            body = base64.urlsafe_b64decode(message['payload']['parts'][0]['body']['data']).decode('utf-8')
            sender = list(filter(lambda item: item['name'] == 'From', message['payload']['headers']))[0]['value']
            email_date = convert_epoch_ms_to_datetime(int(message['internalDate']))

            # Detect the bank
            bank = detect_bank(sender, body)

            parsed = parse_by_bank(bank, body)

            if parsed:
                recipient, amount = parsed["description"], parsed["amount"]
                transaction_id = get_transaction_id(email_date, recipient, amount, bank)
                if transaction_id not in transaction_ids:
                    print(f"Processing: {bank}: {parsed}")
                    gsheets_manager.add_raw_transaction(
                        Transaction(
                            transaction_id,
                            email_date.split(' ')[0],
                            email_date.split(' ')[1],
                            recipient,
                            amount,
                            bank,
                            "CreditCard"
                        )
                    )
                    transaction_ids.add(transaction_id)
                else:
                    print("Entry already processed. Skipping.")

            # Mark the thread as processed (use Gmail API to label it as 'Processed')
            service.users().messages().modify(userId='me', id=message['id'],
                                              body={'addLabelIds': [processed_label_id]}).execute()

        except HttpError as error:
            print(f'An error occurred: {error}')

    # Optionally: Save the data into Google Sheets using gspread or any other method
    print("Processing complete.")


if __name__ == '__main__':
    try:
        service = authenticate()
        process_emails(service)
    except Exception as e:
        print(f"Error: {e}")
