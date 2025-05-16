import datetime
import os
import base64
import email
from typing import List

from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from commons.constants import ENV_SHEET_ID, ENV_SHEET_NAME, ENV_SHEET_NAME_POST_REVIEW
from commons.google_sheets_manager import GoogleSheetsManager
from env import TOKEN_PATH, GMAIL_OAUTH_CREDENTIALS_PATH
from helpers import parse_cc_transaction, detect_bank, parse_upi_transaction
from persistence.models import Transaction
from utils import get_transaction_id

# Scope for reading Gmail messages
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']


# Authenticate with Google API
def authenticate():
    creds = None

    # Load credentials from the token file if it exists
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    # If there are no valid creds, initiate the OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(GMAIL_OAUTH_CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=8080, access_type='offline', prompt='consent')

        # Save credentials in JSON format for future use
        with open(TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)


def get_or_create_label_id_by_name(service, label_name):
    # Get existing labels
    labels = service.users().labels().list(userId='me').execute().get('labels', [])
    for label in labels:
        if label['name'] == label_name:
            return label['id']

    # Label not found, so create it
    label_body = {
        'name': label_name,
        'labelListVisibility': 'labelShow',
        'messageListVisibility': 'show'
    }
    created_label = service.users().labels().create(userId='me', body=label_body).execute()
    return created_label['id']


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


def extract_from_email(message):
    """
    Given a Gmail API message with format='raw', returns the decoded email body as plain text.
    If plain text is not found, falls back to HTML.
    """
    # Decode the raw message
    raw_data = base64.urlsafe_b64decode(message['raw'].encode('UTF-8'))
    mime_msg = email.message_from_bytes(raw_data)

    text_body = None
    html_body = None
    sender = mime_msg['From'] if mime_msg['From'] else None

    if mime_msg.is_multipart():
        for part in mime_msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))

            if "attachment" in content_disposition:
                continue  # Skip attachments

            payload = part.get_payload(decode=True)
            if payload:
                if content_type == "text/plain":
                    text_body = payload.decode(errors='replace')
                elif content_type == "text/html" and not html_body:
                    html_body = payload.decode(errors='replace')
    else:
        # Non-multipart message
        payload = mime_msg.get_payload(decode=True)
        content_type = mime_msg.get_content_type()
        if content_type == "text/plain":
            text_body = payload.decode(errors='replace')
        elif content_type == "text/html":
            html_body = payload.decode(errors='replace')

    if text_body:
        return text_body, sender
    elif html_body:
        # Parse HTML to plain text
        soup = BeautifulSoup(html_body, 'html.parser')
        plain_text = soup.get_text(separator='\n')  # preserve some formatting with new lines
        return plain_text, sender
    else:
        return "", sender


def get_all_messages_with_labels(service, label_names: List[str]):
    all_messages = []

    for label_name in label_names:
        next_page_token = None
        label_query = f'label:{label_name} -label:Processed'

        while True:
            response = service.users().messages().list(
                userId='me',
                q=label_query,
                pageToken=next_page_token
            ).execute()

            messages = response.get('messages', [])
            if not messages:
                break

            for msg in messages:
                metadata = service.users().messages().get(
                    userId='me',
                    id=msg['id'],
                    format='metadata'
                ).execute()
                msg['internalDate'] = int(metadata['internalDate'])
                msg['label'] = label_name  # Associate label name with message
                all_messages.append(msg)

            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break

    # Sort messages by internalDate (ascending = oldest first)
    sorted_messages = sorted(all_messages, key=lambda x: x['internalDate'])
    return sorted_messages


def process_emails(source_label_names: List[str], label_to_parser_func):
    service = authenticate()
    gsheets_manager = GoogleSheetsManager(
        os.environ.get(ENV_SHEET_ID),
        os.environ.get(ENV_SHEET_NAME),
        os.environ.get(ENV_SHEET_NAME_POST_REVIEW)
    )

    processed_label_id = get_or_create_label_id_by_name(service, 'Processed')
    threads = get_all_messages_with_labels(service, source_label_names)

    # Mocking the spreadsheet (you can integrate it with Google Sheets API)
    # Creating a simple dataframe to store processed transactions
    transaction_ids = set()

    print(f"Found {len(threads)} transaction entries to process!")

    for thread in threads:
        try:
            message = service.users().messages().get(userId='me', id=thread['id'], format='raw').execute()

            # Parse out the body
            body, sender = extract_from_email(message)
            email_date = convert_epoch_ms_to_datetime(int(message['internalDate']))

            # Detect the bank and parse
            bank = detect_bank(sender, body)
            parser_func = label_to_parser_func.get(thread['label'])
            parsed, mode = parser_func(bank, body)

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
                            mode
                        )
                    )
                    transaction_ids.add(transaction_id)
                else:
                    print("Entry already processed. Skipping.")

            # Mark the thread as processed (use Gmail API to label it as 'Processed')
            service.users().messages().modify(userId='me', id=message['id'],
                                              body={'addLabelIds': [processed_label_id]}).execute()

        except Exception as error:
            print(f'An error occurred: {error}')

    # Optionally: Save the data into Google Sheets using gspread or any other method
    print("Processing complete.")


if __name__ == '__main__':
    try:
        process_emails(['CreditCardTransactions', 'UPITransactions'],
                       {'CreditCardTransactions': parse_cc_transaction, 'UPITransactions': parse_upi_transaction})
    except Exception as e:
        print(f"Error: {e}")
