import hashlib
from ecdsa import SigningKey, VerifyingKey, BadSignatureError

def sign_message(private_key: SigningKey, message: bytes) -> bytes:
    return private_key.sign_deterministic(message, hashfunc=hashlib.sha256)

def verify_signature(public_key: VerifyingKey, message: bytes, signature: bytes) -> bool:
    try:
        return public_key.verify(signature, message, hashfunc=hashlib.sha256)
    except BadSignatureError:
        return False