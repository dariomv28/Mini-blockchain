from ecdsa import SigningKey, VerifyingKey, SECP256k1

def generate_private_key() -> SigningKey:
    return SigningKey.generate(curve=SECP256k1)

def get_public_key(private_key: SigningKey) -> VerifyingKey:
    return private_key.get_verifying_key()

def private_key_to_hex(private_key: SigningKey) -> str:
    return private_key.to_string().hex()

def public_key_to_hex(public_key: VerifyingKey) -> str:
    return public_key.to_string().hex()

def public_key_from_hex(public_key_hex: str) -> VerifyingKey:
    return VerifyingKey.from_string(
        bytes.fromhex(public_key_hex),
        curve=SECP256k1,
    )