from crypto.keys import generate_private_key, get_public_key
from crypto.signature import sign_message, verify_signature


def test_sign_and_verify():
    private_key = generate_private_key()
    public_key = get_public_key(private_key)
    message = b"Alice sends Bob 10 PYC"
    signature = sign_message(private_key, message)
    assert signature is not None
    assert verify_signature(public_key, message, signature)


def test_modified_message_fails_verification():
    private_key = generate_private_key()
    public_key = get_public_key(private_key)
    original_message = b"Alice sends Bob 10 PYC"
    signature = sign_message(
        private_key,
        original_message,
    )
    modified_message = b"Alice sends Bob 1000 PYC"
    assert not verify_signature(
        public_key,
        modified_message,
        signature,
    )


def test_wrong_public_key_fails_verification():
    alice_private_key = generate_private_key()
    alice_public_key = get_public_key(alice_private_key)
    bob_private_key = generate_private_key()
    bob_public_key = get_public_key(bob_private_key)
    message = b"Alice sends Bob 10 PYC"
    signature = sign_message(
        alice_private_key,
        message,
    )
    assert verify_signature(
        alice_public_key,
        message,
        signature,
    )
    assert not verify_signature(
        bob_public_key,
        message,
        signature,
    )


def test_different_message_cannot_reuse_signature():
    private_key = generate_private_key()
    public_key = get_public_key(private_key)
    message1 = b"transaction 1"
    message2 = b"transaction 2"
    signature = sign_message(
        private_key,
        message1,
    )
    assert verify_signature(
        public_key,
        message1,
        signature,
    )
    assert not verify_signature(
        public_key,
        message2,
        signature,
    )