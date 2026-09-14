import pytest
from cryptography.fernet import Fernet

from crypto.address import public_key_to_address
from crypto.keys import generate_private_key, private_key_from_hex, private_key_to_hex
from wallet.keystore import KeyStore, KeyStoreError


def test_key_roundtrip_and_ciphertext_is_not_plaintext():
    key = generate_private_key()
    hex_key = private_key_to_hex(key)
    assert private_key_from_hex(hex_key).to_string() == key.to_string()
    store = KeyStore(Fernet.generate_key())
    encrypted = store.encrypt_private_key(key)
    assert hex_key.encode() not in encrypted
    assert encrypted != key.to_string()
    decrypted = store.decrypt_private_key(encrypted)
    assert public_key_to_address(decrypted.get_verifying_key()) == public_key_to_address(key.get_verifying_key())
    with pytest.raises(KeyStoreError):
        KeyStore(Fernet.generate_key()).decrypt_private_key(encrypted)
    with pytest.raises(KeyStoreError):
        store.decrypt_private_key(encrypted, key_version=2)
    with pytest.raises(KeyStoreError):
        store.decrypt_private_key(encrypted[:-2] + b"xx")


@pytest.mark.parametrize("value", ["", "00", "g" * 64, "0" * 64, "f" * 64, True])
def test_invalid_private_keys_rejected(value):
    with pytest.raises((ValueError, AssertionError)):
        private_key_from_hex(value)
