from crypto.keys import generate_private_key, get_public_key
from crypto.address import public_key_to_address, validate_address


def test_generate_address():
    private_key = generate_private_key()
    public_key = get_public_key(private_key)
    address = public_key_to_address(public_key)
    assert address is not None
    assert isinstance(address, str)
    assert len(address) > 0


def test_same_public_key_same_address():
    private_key = generate_private_key()
    public_key = get_public_key(private_key)
    address1 = public_key_to_address(public_key)
    address2 = public_key_to_address(public_key)
    assert address1 == address2


def test_different_public_keys_different_addresses():
    private_key1 = generate_private_key()
    private_key2 = generate_private_key()
    public_key1 = get_public_key(private_key1)
    public_key2 = get_public_key(private_key2)
    address1 = public_key_to_address(public_key1)
    address2 = public_key_to_address(public_key2)
    assert address1 != address2


def test_valid_address():
    private_key = generate_private_key()
    public_key = get_public_key(private_key)
    address = public_key_to_address(public_key)
    assert validate_address(address)


def test_modified_address_is_invalid():
    private_key = generate_private_key()
    public_key = get_public_key(private_key)
    address = public_key_to_address(public_key)

    # Thay ký tự cuối để phá checksum
    replacement = "1" if address[-1] != "1" else "2"
    corrupted_address = (
        address[:-1]
        + replacement
    )

    assert not validate_address(corrupted_address)