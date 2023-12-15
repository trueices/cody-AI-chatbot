import hmac
import hashlib
import time
import secrets


def parse_header(header):
    if not isinstance(header, str):
        return None
    header_details = {'timestamp': -1, 'signature': ''}
    elements = header.split(',')
    for element in elements:
        key, value = element.split('=')
        if key.strip() == 't':
            header_details['timestamp'] = int(value.strip())
        elif key.strip() == 'v1':
            header_details['signature'] = value.strip()
    return header_details


def compute_signature(timestamp, payload, secret):
    signed_payload = f"{timestamp}.{payload}"
    hashed = hmac.new(secret.encode(
        'utf-8'), msg=signed_payload.encode('utf-8'), digestmod=hashlib.sha256)
    return hashed.hexdigest()


def verify_signature(header, request_body, secret, tolerance=10):
    header_details = parse_header(header)
    if header_details is None:
        return False
    timestamp = header_details['timestamp']
    expected_signature = compute_signature(timestamp, request_body, secret)
    received_signature = header_details['signature']

    # Protect against timing attacks
    if secrets.compare_digest(expected_signature, received_signature):
        # Check if timestamp is within tolerance
        current_time = int(time.time())
        if abs(current_time - timestamp) <= tolerance:
            return True
    return False
