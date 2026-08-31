from crypto.keys import generate_private_key, get_public_key


def test_generate_private_key():
    private_key = generate_private_key()
    assert private_key is not None


def test_generate_public_key():
    private_key = generate_private_key()
    public_key = get_public_key(private_key)
    assert public_key is not None


def test_same_private_key_produces_same_public_key():
    private_key = generate_private_key()
    public_key1 = get_public_key(private_key)
    public_key2 = get_public_key(private_key)
    assert public_key1 == public_key2


def test_different_private_keys():
    private_key1 = generate_private_key()
    private_key2 = generate_private_key()
    assert private_key1 != private_key2


def test_different_private_keys_produce_different_public_keys():
    private_key1 = generate_private_key()
    private_key2 = generate_private_key()
    public_key1 = get_public_key(private_key1)
    public_key2 = get_public_key(private_key2)
    assert public_key1 != public_key2