"""Versioned Fernet encryption of SECP256k1 private keys."""

from cryptography.fernet import Fernet, InvalidToken

from crypto.keys import private_key_from_hex, private_key_to_hex


class KeyStoreError(Exception):
    pass


class KeyStore:
    key_version = 1

    def __init__(self, master_key):
        try:
            self.fernet = Fernet(master_key.encode("ascii") if isinstance(master_key, str) else master_key)
        except (ValueError, TypeError, UnicodeError) as exc:
            raise KeyStoreError("Invalid wallet master key") from exc

    def encrypt_private_key(self, key):
        return self.fernet.encrypt(private_key_to_hex(key).encode("ascii"))

    def decrypt_private_key(self, encrypted, key_version=1):
        if key_version != self.key_version:
            raise KeyStoreError("Unsupported wallet key version")
        try:
            return private_key_from_hex(self.fernet.decrypt(encrypted).decode("ascii"))
        except (InvalidToken, ValueError, UnicodeError) as exc:
            raise KeyStoreError("Cannot decrypt wallet key") from exc

    def validate_database(self, database):
        marker = b"pychain-wallet-master-key-v1"
        record = database.execute("SELECT value FROM metadata WHERE name='wallet_key_check'").fetchone()
        if record is not None:
            try:
                if self.fernet.decrypt(record[0]) != marker:
                    raise KeyStoreError("Wallet master key does not match application database")
            except InvalidToken as exc:
                raise KeyStoreError("Wallet master key does not match application database") from exc
        for row in database.execute("SELECT encrypted_private_key,key_version,address,public_key FROM wallets"):
            from crypto.address import public_key_to_address
            from crypto.keys import public_key_to_hex
            key = self.decrypt_private_key(row[0], row[1])
            if public_key_to_address(key.get_verifying_key()) != row[2] or public_key_to_hex(key.get_verifying_key()) != row[3]:
                raise KeyStoreError("Wallet identity integrity failure")
        if record is None:
            database.execute("INSERT INTO metadata(name,value) VALUES('wallet_key_check',?)", (self.fernet.encrypt(marker),))
