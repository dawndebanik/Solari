import hashlib


def get_fingerprint_for_transaction(date, description, amount, bank):
    return f"{date}|{description}|{amount}|{bank}"


def generate_transaction_id(fingerprint):
    fingerprint_bytes = fingerprint.encode('utf-8')
    md5_hash = hashlib.md5(fingerprint_bytes).digest()
    return ''.join('{:02x}'.format(b) for b in md5_hash)


def get_transaction_id(date, description, amount, bank):
    fingerprint = get_fingerprint_for_transaction(date, description, amount, bank)
    return generate_transaction_id(fingerprint)
