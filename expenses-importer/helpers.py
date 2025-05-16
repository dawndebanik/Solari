import re


# Function to detect the bank based on email sender
def detect_bank(sender, body):
    if 'hdfc' in sender.lower() or 'hdfc bank' in body.lower():
        return "HDFC"
    elif 'icici' in sender.lower() or 'icici bank' in body.lower():
        return "ICICI"
    elif 'hsbc' in sender.lower() or 'hsbc bank' in body.lower():
        return "HSBC"
    elif 'axis' in sender.lower() or 'axis bank' in body.lower():
        return "Axis"
    elif 'federal' in sender.lower() or 'federal bank' in body.lower():
        return "Federal"
    elif 'kotak' in sender.lower() or 'kotak bank' in body.lower():
        return "Kotak"

    return None


def parse_common(body, amount_pattern, description_pattern):
    amount_match = re.search(amount_pattern, body, re.I)
    description_match = re.search(description_pattern, body, re.I)

    if amount_match and description_match:
        amount = float(amount_match.group(1).replace(',', ''))
        description = description_match.group(1).strip()
        return {'description': description, 'amount': amount}

    if re.search(r'has\s+been\s+reversed|declined|not\s+be\s+completed', body, re.I):
        return None

    raise Exception("Unparseable transaction:\n" + body)


def parse_cc_transaction(bank, body):
    parsed = None
    if bank == "HDFC":
        parsed = parse_common(body, r'7883\s+for\s+(?:Rs\.?|INR)\s+([\d,]+(\.\d+)?)', r'at\s+(.*?)\s+on')
    if bank == "ICICI":
        parsed = parse_common(body, r'transaction\s+of\s+(?:Rs\.?|INR)\s+([\d,]+(\.\d+)?)', r'Info:\s+(.*?)\.')
    if bank == "HSBC":
        parsed = parse_common(body, r'been\s+used\s+for\s+(?:Rs\.?|INR)\s+([\d,]+(\.\d+)?)', r'payment to\s+(.*?)\s+on')
    if bank == "Axis":
        parsed = parse_common(body, r'9339\s+for\s+(?:Rs\.?|INR)\s+([\d,]+(\.\d+)?)', r'at\s+(.*?)\s+on')
    if bank == "Federal":
        parsed = parse_common(body, r'txn\s+of\s+(?:₹|Rs\.?|INR)\s*([\d,]+(\.\d+)?)', r'at\s+(.*?)\s+on')
    return parsed, "CreditCard"


def parse_upi_transaction(bank, body):
    parsed = None
    if bank == "Federal":
        parsed = parse_common(body,
                            r'(?:₹|Rs\.?|INR|\b[A-Z]{3}\b)\s*([\d,]+(\.\d{1,})?)',
                            r'to\s+(.*?)\.')
    elif bank == "Kotak":
        parsed = parse_common(body,
                            r'Sent\s+(?:₹|Rs\.?|INR|\b[A-Z]{3}\b)(.*?)\s+',
                            r'to\s+(.*?)on')
    return parsed, "UPI"
