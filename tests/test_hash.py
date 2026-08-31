import hashlib

from crypto.hash import serialize, sha256, hash_object


def test_sha256():
    data = b"hello"
    expected = hashlib.sha256(data).digest()
    assert sha256(data) == expected


def test_sha256_same_input_same_hash():
    data = b"blockchain"
    hash1 = sha256(data)
    hash2 = sha256(data)
    assert hash1 == hash2


def test_sha256_different_input_different_hash():
    hash1 = sha256(b"Alice")
    hash2 = sha256(b"Bob")
    assert hash1 != hash2


def test_serialize_is_deterministic():
    obj1 = {
        "sender": "Alice",
        "receiver": "Bob",
        "amount": 10,
    }
    obj2 = {
        "amount": 10,
        "receiver": "Bob",
        "sender": "Alice",
    }
    assert serialize(obj1) == serialize(obj2)


def test_hash_object_same_data_same_hash():
    obj1 = {
        "sender": "Alice",
        "amount": 10,
    }
    obj2 = {
        "amount": 10,
        "sender": "Alice",
    }
    assert hash_object(obj1) == hash_object(obj2)


def test_hash_object_changes_when_data_changes():
    obj1 = {
        "sender": "Alice",
        "amount": 10,
    }
    obj2 = {
        "sender": "Alice",
        "amount": 100,
    }
    assert hash_object(obj1) != hash_object(obj2)