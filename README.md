# Gmail Expenses Importer

A Python application that automatically processes transaction emails from Gmail, specifically designed to handle credit card and UPI transactions. The application extracts transaction details from emails, processes them, and stores them in Google Sheets for easy tracking and management.

## Features

- Automated email processing for transaction-related emails
- Support for multiple transaction types:
  - Credit Card transactions
  - UPI transactions
- Automatic bank detection from email content
- Transaction deduplication using unique transaction IDs
- Integration with Google Sheets for data storage
- Email labeling system to track processed messages

## Components

### 1. Gmail Integration (`gmail_expenses_reader.py`)
- Handles Gmail API authentication and authorization
- Processes emails with specific labels
- Extracts email content and metadata
- Manages email labeling for processed messages

### 2. Transaction Processing
- Bank detection from email content
- Transaction parsing for different types:
  - Credit card transactions
  - UPI transactions
- Transaction deduplication using unique IDs

### 3. Google Sheets Integration
- Stores processed transactions in Google Sheets
- Maintains separate sheets for raw transactions and post-review data

## Developer Setup Guide

### Prerequisites
- Python 3.x
- Google Cloud Platform account
- Gmail account with transaction emails

### Setup Steps

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd <repository-name>
   ```

2. **Set up Python virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Google Cloud Setup**
   - Create a project in Google Cloud Console
   - Enable Gmail API and Google Sheets API
   - Create OAuth 2.0 credentials
   - Download the credentials and save as `credentials.json`

5. **Environment Variables**
   Create a `.env` file with the following variables:
   ```
   ENV_SHEET_ID=<your-google-sheet-id>
   ENV_SHEET_NAME=<sheet-name-for-raw-transactions>
   ENV_SHEET_NAME_POST_REVIEW=<sheet-name-for-post-review>
   ```

6. **First Run**
   - Run the application:
     ```bash
     python expenses-importer/gmail_expenses_reader.py
     ```
   - On first run, it will open a browser window for Gmail authentication
   - Grant necessary permissions
   - The application will create a token file for future authentication

### Project Structure
```
.
├── expenses-importer/
│   ├── gmail_expenses_reader.py
│   ├── helpers.py
│   └── utils.py
├── commons/
│   ├── constants.py
│   └── google_sheets_manager.py
├── persistence/
│   └── models.py
├── requirements.txt
└── README.md
```

## Usage

1. Label your transaction emails in Gmail with either:
   - `CreditCardTransactions`
   - `UPITransactions`

2. Run the application:
   ```bash
   python expenses-importer/gmail_expenses_reader.py
   ```

3. The application will:
   - Process all unprocessed emails with the specified labels
   - Extract transaction details
   - Store them in Google Sheets
   - Mark processed emails with a 'Processed' label

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License
TODO 