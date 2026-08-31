import hashlib

from ecdsa import VerifyingKey


def public_key_to_address(public_key: VerifyingKey) -> str:
    public_key_bytes = public_key.to_string()

    public_key_hash = hashlib.sha256(
        public_key_bytes
    ).hexdigest()[:40]

    checksum = hashlib.sha256(
        public_key_hash.encode()
    ).hexdigest()[:8]

    return "PYC_" + public_key_hash + checksum


def validate_address(address: str) -> bool:
    if not isinstance(address, str):
        return False

    if not address.startswith("PYC_"):
        return False

    data = address[4:]

    # 40 ký tự hash + 8 ký tự checksum
    if len(data) != 48:
        return False

    public_key_hash = data[:40]
    checksum = data[40:]

    # Tính lại checksum
    expected_checksum = hashlib.sha256(
        public_key_hash.encode()
    ).hexdigest()[:8]

    return checksum == expected_checksum