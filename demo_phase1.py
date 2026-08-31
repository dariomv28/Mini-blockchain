from crypto.keys import (
    generate_private_key,
    get_public_key,
    private_key_to_hex,
    public_key_to_hex,
)

from crypto.address import public_key_to_address

from crypto.signature import (
    sign_message,
    verify_signature,
)


print("=== CREATE IDENTITY ===")

private_key = generate_private_key()

public_key = get_public_key(
    private_key
)

address = public_key_to_address(
    public_key
)

print("Private key:")
print(private_key_to_hex(private_key))

print("\nPublic key:")
print(public_key_to_hex(public_key))

print("\nAddress:")
print(address)


message = b"Alice sends Bob 10 PYC"

print("\n=== SIGN ===")

signature = sign_message(
    private_key,
    message,
)

print(signature.hex())


print("\n=== VERIFY ORIGINAL ===")

print(
    verify_signature(
        public_key,
        message,
        signature,
    )
)


print("\n=== VERIFY TAMPERED ===")

tampered = b"Alice sends Hacker 1000 PYC"

print(
    verify_signature(
        public_key,
        tampered,
        signature,
    )
)
