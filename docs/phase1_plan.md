# PHASE 1 — Cryptography Layer

## 1. Mục tiêu cuối Phase 1

Kết thúc phase này, bạn phải chạy được một demo kiểu:

```text
=== CREATE IDENTITY ===

Private key:
8f91....

Public key:
03ab....

Address:
PYC_91ad....

=== SIGN MESSAGE ===

Message:
Alice sends Bob 10 PYC

Signature:
3045....

=== VERIFY ===

Original message:
True

Modified message:
False
```

Và quan trọng hơn, bạn phải hiểu được luồng:

```text
Random number
    ↓
Private Key
    ↓
Elliptic Curve secp256k1
    ↓
Public Key
    ↓
Hash
    ↓
Address
```

và:

```text
Transaction/Data
      ↓
    SHA-256
      ↓
message digest
      ↓
ECDSA Sign(private_key)
      ↓
Signature
```

Node khác:

```text
data
+
signature
+
public_key
      ↓
ECDSA Verify
      ↓
True / False
```

Sau này Phase 2 chỉ việc lấy crypto layer này để ký transaction.

---

# 2. Cấu trúc thư mục

Tạo project:

```text
pychain/
│
├── crypto/
│   ├── __init__.py
│   ├── hash.py
│   ├── keys.py
│   ├── signature.py
│   └── address.py
│
├── tests/
│   ├── __init__.py
│   ├── test_hash.py
│   ├── test_keys.py
│   ├── test_signature.py
│   └── test_address.py
│
├── demo_phase1.py
├── requirements.txt
└── README.md
```

Đừng tạo:

```text
block.py
transaction.py
mempool.py
miner.py
```

ở phase này.

Phase 1 chỉ tập trung:

```text
crypto/
```

---

# 3. Tạo virtual environment

Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
```

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Cài:

```bash
pip install ecdsa pytest
```

`requirements.txt`:

```text
ecdsa
pytest
```

Tài liệu định hướng dùng ECDSA + secp256k1 và cũng nhấn mạnh **không nên tự implement elliptic-curve cryptography**; project nên tập trung vào blockchain logic thay vì tự viết primitive mật mã. 

---

# 4. Bước 1 — Hashing

Trước tiên bạn cần hiểu:

```text
hash = fingerprint của dữ liệu
```

Ví dụ:

```text
"hello"
       ↓ SHA-256
2cf24dba5f...
```

Chỉ cần đổi:

```text
hello
```

thành:

```text
Hello
```

hash sẽ thay đổi rất mạnh.

## `crypto/hash.py`

Bạn nên xây ít nhất:

```python
import hashlib


def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
```

Lưu ý:

```python
sha256(...)
```

trả:

```text
bytes
```

còn:

```python
sha256_hex(...)
```

trả:

```text
string hex
```

Ví dụ:

```python
from crypto.hash import sha256_hex

message = b"hello"

print(sha256_hex(message))
```

---

# 5. Test hashing

`tests/test_hash.py`

Bạn cần test ít nhất ba tính chất.

### Test 1: cùng input → cùng hash

```python
def test_same_data_same_hash():
    data = b"hello"

    assert sha256(data) == sha256(data)
```

### Test 2: khác input → hash khác

```python
def test_different_data_different_hash():
    assert sha256(b"hello") != sha256(b"Hello")
```

### Test 3: SHA-256 luôn 32 bytes

```python
def test_sha256_length():
    result = sha256(b"hello")

    assert len(result) == 32
```

Vì:

```text
SHA-256
= 256 bits
= 32 bytes
= 64 hex characters
```

Đây là kiến thức bạn phải nhớ.

---

# 6. Bước 2 — Serialization

Mặc dù file roadmap chỉ nói hash, đây là phần bạn **nên bổ sung khi triển khai**, vì Phase 2 sẽ phải hash transaction.

Ví dụ Python có:

```python
transaction = {
    "sender": "Alice",
    "receiver": "Bob",
    "amount": 10,
}
```

Bạn không nên hash object Python trực tiếp.

Phải biến thành:

```text
object
 ↓
deterministic serialization
 ↓
bytes
 ↓
SHA256
```

Thêm vào `hash.py`:

```python
import json


def serialize(data: dict) -> bytes:
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
```

Ví dụ:

```python
a = {
    "sender": "Alice",
    "amount": 10,
}

b = {
    "amount": 10,
    "sender": "Alice",
}
```

Sau serialization:

```python
serialize(a) == serialize(b)
```

phải là:

```text
True
```

---

# 7. Vì sao serialization cực kỳ quan trọng?

Giả sử Node A tạo:

```text
{
 sender: Alice,
 amount: 10
}
```

Node B lại serialize:

```text
{
 amount: 10,
 sender: Alice
}
```

Nếu hai node tạo bytes khác nhau:

```text
Node A hash != Node B hash
```

Blockchain sẽ không thể đồng thuận.

Cho nên rule:

> Cùng dữ liệu logic phải tạo ra cùng chuỗi bytes.

Đây sẽ trở thành một concept rất quan trọng khi bạn làm transaction ID và block hash.

---

# 8. Bước 3 — Private Key

Bây giờ đến phần identity.

Private key về bản chất là một số bí mật rất lớn.

Concept:

```text
Private Key
=
secret number
```

Ví dụ mang tính minh họa:

```text
192381029381029381029...
```

Không bao giờ:

```text
private key → gửi cho node khác
```

Private key chỉ người sở hữu giữ.

---

# 9. Sinh private key

`crypto/keys.py`

```python
from ecdsa import SigningKey, SECP256k1


def generate_private_key() -> SigningKey:
    return SigningKey.generate(curve=SECP256k1)
```

Ở đây:

```text
SigningKey
```

chính là private key object.

Còn:

```text
SECP256k1
```

là elliptic curve bạn đang sử dụng.

Đây đúng với kiến trúc Bitcoin-like mà tài liệu đề xuất. 

---

# 10. Public Key

Public key được suy ra từ private key.

```text
private key
    ↓
Elliptic Curve multiplication
    ↓
public key
```

Thêm:

```python
def get_public_key(private_key: SigningKey):
    return private_key.get_verifying_key()
```

Sử dụng:

```python
private_key = generate_private_key()

public_key = get_public_key(private_key)
```

---

# 11. Điều cực kỳ quan trọng cần hiểu

Quan hệ:

```text
Private Key
      ↓
Public Key
```

là dễ tính.

Nhưng:

```text
Public Key
      ↓
Private Key
```

là computationally infeasible.

Đó là lý do bạn có thể công khai:

```text
public_key
```

nhưng vẫn giữ bí mật:

```text
private_key
```

---

# 12. Serialize key

Bạn cũng cần chuyển key sang bytes/hex để lưu hoặc truyền qua network.

Ví dụ:

```python
def private_key_to_hex(private_key: SigningKey) -> str:
    return private_key.to_string().hex()


def public_key_to_hex(public_key) -> str:
    return public_key.to_string().hex()
```

Demo:

```python
private_key = generate_private_key()
public_key = get_public_key(private_key)

print(private_key_to_hex(private_key))
print(public_key_to_hex(public_key))
```

Output dạng:

```text
Private:
a18274f94d...

Public:
9ad21a03f5...
```

---

# 13. Test key generation

`tests/test_keys.py`

### Private key tồn tại

```python
def test_generate_private_key():
    private_key = generate_private_key()

    assert private_key is not None
```

### Public key được sinh đúng

```python
def test_public_key_generation():
    private_key = generate_private_key()

    public_key = get_public_key(private_key)

    assert public_key is not None
```

### Hai lần tạo phải khác nhau

```python
def test_private_keys_are_unique():
    key1 = generate_private_key()
    key2 = generate_private_key()

    assert key1.to_string() != key2.to_string()
```

---

# 14. Bước 4 — Digital Signature

Đây là phần quan trọng nhất Phase 1.

Giả sử Alice muốn gửi:

```text
Alice → Bob : 10 PYC
```

Một attacker có thể tự viết:

```text
Alice → Hacker : 100 PYC
```

Blockchain phải trả lời:

> Có thật Alice tạo transaction này không?

Giải pháp:

```text
Digital Signature
```

---

# 15. Luồng ký

Alice có:

```text
private_key_A
public_key_A
```

Transaction:

```text
Alice → Bob 10
```

Ta làm:

```text
Transaction
     ↓
serialize
     ↓
SHA256
     ↓
digest
     ↓
sign(private_key_A)
     ↓
signature
```

Sau đó Alice broadcast:

```text
transaction
public_key_A
signature
```

Không broadcast:

```text
private_key_A
```

---

# 16. `crypto/signature.py`

Bạn có thể làm:

```python
from ecdsa import SigningKey, VerifyingKey, BadSignatureError
import hashlib


def sign_message(
    private_key: SigningKey,
    message: bytes,
) -> bytes:

    return private_key.sign_deterministic(
        message,
        hashfunc=hashlib.sha256,
    )
```

Verify:

```python
def verify_signature(
    public_key: VerifyingKey,
    message: bytes,
    signature: bytes,
) -> bool:

    try:
        return public_key.verify(
            signature,
            message,
            hashfunc=hashlib.sha256,
        )

    except BadSignatureError:
        return False
```

---

# 17. Demo signature

```python
private_key = generate_private_key()

public_key = get_public_key(private_key)

message = b"Alice sends Bob 10 PYC"

signature = sign_message(
    private_key,
    message,
)

print(
    verify_signature(
        public_key,
        message,
        signature,
    )
)
```

Kết quả:

```text
True
```

---

# 18. Thử tampering

Đây là lab bạn nhất định phải làm.

Ban đầu:

```text
Alice sends Bob 10 PYC
```

Alice ký:

```text
signature = ...
```

Attacker sửa:

```text
Alice sends Hacker 1000 PYC
```

Verify:

```python
verify_signature(
    public_key,
    b"Alice sends Hacker 1000 PYC",
    signature,
)
```

phải trả:

```text
False
```

Đây chính là một trong những nền tảng của transaction validation sau này.

---

# 19. Test signature

`tests/test_signature.py`

Bạn cần ít nhất 4 test.

### Đúng key + đúng message

```text
True
```

### Đúng key + message bị sửa

```text
False
```

### Sai public key

Alice ký:

```text
private_A
```

nhưng verify bằng:

```text
public_B
```

phải:

```text
False
```

### Signature bị sửa

Phải:

```text
False
```

Đây là test cực kỳ quan trọng.

---

# 20. Bước 5 — Address

Bây giờ bạn đã có:

```text
private_key
public_key
```

Nhưng không muốn người dùng phải gửi tiền đến:

```text
0498248fa882713...
```

nên blockchain tạo:

```text
address
```

Tài liệu hiện tại chỉ xác định luồng tổng quát:

```text
Private key
    ↓
Public key
    ↓
Hash
    ↓
Blockchain address
```

chứ chưa quy định format address cụ thể. 

Vì vậy cho PyChain version đầu tiên, tôi khuyên làm format đơn giản.

---

# 21. Address PyChain đơn giản

Ví dụ:

```text
PYC_<hash>
```

`crypto/address.py`:

```python
import hashlib


def public_key_to_address(public_key) -> str:
    public_key_bytes = public_key.to_string()

    digest = hashlib.sha256(
        public_key_bytes
    ).hexdigest()

    return "PYC_" + digest[:40]
```

Ví dụ:

```text
PYC_04f9c1a94acb...
```

Đây **không phải format Bitcoin thật**.

Nó là format giáo dục cho blockchain của bạn.

Sau này bạn có thể nâng cấp thành:

```text
SHA256
 ↓
RIPEMD160
 ↓
version byte
 ↓
checksum
 ↓
Base58Check
```

giống kiểu Bitcoin address.

Nhưng chưa cần ở Phase 1.

---

# 22. Vì sao address không nên bằng private key?

Không bao giờ:

```text
address = private_key
```

vì như vậy bạn công khai luôn quyền sở hữu tài sản.

Cũng không nhất thiết:

```text
address = public_key
```

Thông thường architecture là:

```text
Private Key
      ↓
Public Key
      ↓
Hash
      ↓
Address
```

---

# 23. Test address

`tests/test_address.py`

### Public key giống nhau → address giống nhau

```python
assert (
    public_key_to_address(pub)
    ==
    public_key_to_address(pub)
)
```

### Public key khác nhau → address khác nhau

```text
pub A → address A

pub B → address B
```

phải:

```text
address A != address B
```

### Prefix đúng

```python
assert address.startswith("PYC_")
```

---

# 24. Bước 6 — Tạo identity hoàn chỉnh

Đến đây bạn có thể viết abstraction:

```text
Identity
├── private_key
├── public_key
└── address
```

Ví dụ:

```python
private_key = generate_private_key()

public_key = get_public_key(
    private_key
)

address = public_key_to_address(
    public_key
)
```

Ta có:

```text
Alice

Private Key
8ab2....

Public Key
9fa4....

Address
PYC_9238....
```

Đây chính là identity cơ bản mà wallet Phase sau sẽ quản lý.

---

# 25. `demo_phase1.py`

Demo hoàn chỉnh nên chạy:

```python
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
```

---

# 26. Output mong đợi

Chạy:

```bash
python demo_phase1.py
```

Bạn sẽ thấy tương tự:

```text
=== CREATE IDENTITY ===

Private key:
a19027cd...

Public key:
91a270ab...

Address:
PYC_a51290ca...

=== SIGN ===

Signature:
01ab78cd...

=== VERIFY ORIGINAL ===

True

=== VERIFY TAMPERED ===

False
```

Nếu được như vậy thì crypto pipeline đã hoạt động.

---

# 27. Chạy toàn bộ test

```bash
pytest -v
```

Bạn nên có khoảng:

```text
test_hash.py
  ✓ same data
  ✓ modified data
  ✓ hash size

test_keys.py
  ✓ create private key
  ✓ derive public key
  ✓ unique keys

test_signature.py
  ✓ valid signature
  ✓ modified message
  ✓ wrong public key
  ✓ modified signature

test_address.py
  ✓ deterministic address
  ✓ unique addresses
  ✓ prefix
```

Mục tiêu:

```text
13 passed
```

---

# 28. Những kiến thức phải hiểu trước khi qua Phase 2

Bạn không cần học toán elliptic curve cực sâu, nhưng phải giải thích được những câu sau.

### Câu 1

SHA-256 làm gì?

Bạn phải trả lời gần như:

> Chuyển dữ liệu có độ dài bất kỳ thành digest 256-bit có kích thước cố định.

---

### Câu 2

Private key là gì?

> Một secret value dùng để chứng minh quyền sở hữu và tạo digital signature.

---

### Câu 3

Public key có tác dụng gì?

> Được suy ra từ private key và có thể dùng để verify chữ ký mà không tiết lộ private key.

---

### Câu 4

Address đến từ đâu?

```text
private
 ↓
public
 ↓
hash
 ↓
address
```

---

### Câu 5

Signature có phải encryption không?

Không.

```text
Encryption
→ bảo mật nội dung
```

trong khi:

```text
Signature
→ chứng minh authenticity/integrity
```

---

### Câu 6

Tại sao transaction không chứa private key?

Vì:

```text
private key = quyền kiểm soát coin
```

Transaction chỉ cần:

```text
public key
+
signature
```

---

### Câu 7

Nếu attacker sửa amount sau khi transaction đã ký thì sao?

Ví dụ:

```text
10 PYC
```

thành:

```text
1000 PYC
```

Dữ liệu thay đổi:

```text
hash thay đổi
```

nên:

```text
signature verification
→ False
```

---

# 29. Luồng Phase 1 hoàn chỉnh

Bạn nên hình dung cả Phase 1 như thế này:

```text
               CRYPTO LAYER

                   RNG
                    │
                    ▼
              Private Key
                    │
                    │ secp256k1
                    ▼
               Public Key
                    │
                    │ SHA256
                    ▼
                 Address


Transaction data
      │
      ▼
Serialization
      │
      ▼
    SHA256
      │
      ▼
     Hash
      │
      │
Private Key
      │
      ▼
 ECDSA Signature
      │
      ▼
 ┌────────────────────┐
 │ data               │
 │ public key         │
 │ signature          │
 └─────────┬──────────┘
           │
           ▼
        Verify
           │
      ┌────┴────┐
      ▼         ▼
    True      False
```

Đây là thứ bạn cần hiểu, chứ không phải chỉ viết 4 file Python.

---

# 30. Phase 1 liên quan gì tới blockchain sau này?

Hiện tại bạn chỉ đang ký:

```text
Alice sends Bob 10
```

Phase 2 sẽ thay bằng object thật:

```text
Transaction
├── inputs[]
├── outputs[]
├── public_key
└── signature
```

Alice tạo:

```text
Input:
    UTXO ABC:0

Output:
    6 PYC → Bob
    4 PYC → Alice
```

Sau đó:

```text
serialize transaction
        ↓
hash
        ↓
sign Alice private key
        ↓
signature
```

Node nhận transaction:

```text
Transaction
     ↓
get Alice public key
     ↓
verify signature
     ↓
True
```

rồi mới kiểm tra:

```text
UTXO có tồn tại?
Alice có sở hữu nó?
amount hợp lệ?
double spend không?
```

Đó chính là **Phase 2 — Transaction + UTXO** trong roadmap. 

---

# 31. Checklist Phase 1

Đừng chuyển phase nếu chưa tick hết:

```text
[ ] Hiểu SHA-256
[ ] Tự gọi hashlib.sha256

[ ] Hiểu bytes vs hex

[ ] Có deterministic serialization

[ ] Sinh được private key

[ ] Derive được public key

[ ] Dùng secp256k1

[ ] Serialize được private/public key

[ ] Tạo được digital signature

[ ] Verify đúng signature

[ ] Verify fail khi message bị sửa

[ ] Verify fail khi dùng sai public key

[ ] Tạo được address từ public key

[ ] Có unit tests

[ ] pytest pass

[ ] Có demo_phase1.py

[ ] Giải thích được:
    private key
    public key
    address
    hash
    signature
```

## Giao phẩm cuối Phase 1

```text
pychain/
│
├── crypto/
│   ├── hash.py
│   ├── keys.py
│   ├── signature.py
│   └── address.py
│
├── tests/
│   ├── test_hash.py
│   ├── test_keys.py
│   ├── test_signature.py
│   └── test_address.py
│
├── demo_phase1.py
├── requirements.txt
└── README.md
```

**Nếu bạn hoàn thành đúng bộ này thì Phase 1 coi như xong.** Đặc biệt, đừng chỉ chạy code thấy `True` là qua phase; hãy tự sửa message, signature và public key để quan sát từng trường hợp verification thất bại. Đó mới là phần giúp bạn hiểu tại sao crypto layer bảo vệ transaction của blockchain. 
