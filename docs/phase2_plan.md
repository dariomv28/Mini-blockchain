# PHASE 2 — Transaction + UTXO + Transaction Validation

## 1. Phase 2 đang đứng ở đâu trong toàn bộ project?

Phase 1 trong `phase1_passed.zip` đã hoàn thành Crypto Layer:

```text
crypto/
├── hash.py
├── keys.py
├── signature.py
└── address.py
```

Các primitive đã có và Phase 2 sẽ tái sử dụng trực tiếp:

```text
sha256(...)
sha256_hex(...)
serialize(...)
hash_object(...)

generate_private_key()
get_public_key()
public_key_to_hex()

sign_message()
verify_signature()

public_key_to_address()
validate_address()
```

Luồng Phase 1:

```text
Private Key
    ↓
Public Key
    ↓
Address

Data
 ↓
Sign(private key)
 ↓
Signature
 ↓
Verify(public key)
```

Phase 2 biến các primitive đó thành giao dịch blockchain thật sự:

```text
Previous UTXO
      │
      ▼
   TxInput
      │
      │ ký bằng private key
      ▼
 Transaction
      │
      ├──────────► TxOutput → Bob
      └──────────► TxOutput → Alice (change)
      │
      ▼
Transaction Validation
      │
      ▼
   UTXO Set
```

---

# 2. Mục tiêu cuối Phase 2

Kết thúc Phase 2, project phải làm được demo kiểu:

```text
=== CREATE USERS ===

Alice address:
PYC_...

Bob address:
PYC_...

=== SEED DEMO UTXO ===

Alice owns:
10 PYC

=== CREATE TRANSACTION ===

Input:
10 PYC owned by Alice

Outputs:
6 PYC -> Bob
3 PYC -> Alice

Fee:
1 PYC

=== SIGN TRANSACTION ===

Signature:
...

=== VALIDATE ===

Valid transaction:
True

=== APPLY TRANSACTION ===

Alice balance: 3 PYC
Bob balance:   6 PYC

=== SECURITY TEST ===

Modified amount:
False

Wrong private key:
False

Spend same UTXO again:
False
```

Quan trọng hơn, bạn phải hiểu được luồng:

```text
UTXO cũ
   │
   ▼
TxInput tham chiếu tới UTXO
   │
   ▼
Transaction chứa outputs mới
   │
   ▼
Owner ký transaction
   │
   ▼
Node kiểm tra ownership + signature + amount
   │
   ▼
UTXO cũ bị remove
   │
   ▼
UTXO mới được tạo
```

---

# 3. Scope chính xác của Phase 2

Phase này chỉ làm:

```text
Transaction
TxInput
TxOutput
Transaction ID
Transaction signing
Transaction signature verification
UTXO Set
Balance từ UTXO
Ownership validation
Amount validation
Double-spend prevention ở UTXO state
Transaction fee calculation
```

Chưa làm:

```text
Block
Merkle Tree
Genesis Block
Proof of Work
Mining
Coinbase transaction
Mempool
P2P
Database persistence
Wallet CLI
HTTP API
```

Đặc biệt:

> Không đưa `mempool.py` vào Phase 2 dù kiến trúc tổng thể có file đó.
>
> Mempool sẽ cần transaction validator của Phase 2, nên phải làm transaction core ổn định trước.

---

# 4. Cấu trúc thư mục sau Phase 2

Giữ nguyên toàn bộ Phase 1 và thêm:

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
├── transaction/
│   ├── __init__.py
│   ├── tx_input.py
│   ├── tx_output.py
│   ├── transaction.py
│   ├── utxo.py
│   └── validation.py
│
├── tests/
│   ├── test_hash.py
│   ├── test_keys.py
│   ├── test_signature.py
│   ├── test_address.py
│   ├── test_tx_input.py
│   ├── test_tx_output.py
│   ├── test_transaction.py
│   ├── test_utxo.py
│   └── test_transaction_validation.py
│
├── demo_phase1.py
└── demo_phase2.py
```

Không cần tạo các folder khác ở phase này.

---

# 5. Concept quan trọng nhất — UTXO

UTXO = **Unspent Transaction Output**.

Nó không có nghĩa là:

```text
Alice.balance = 10
```

Mà có nghĩa là blockchain đang biết Alice sở hữu một hoặc nhiều output chưa bị tiêu.

Ví dụ:

```text
TX_100 output[0]
5 PYC → Alice

TX_135 output[1]
3 PYC → Alice

TX_201 output[0]
2 PYC → Alice
```

UTXO Set:

```text
(TX_100, 0) → 5 PYC → Alice
(TX_135, 1) → 3 PYC → Alice
(TX_201, 0) → 2 PYC → Alice
```

Balance Alice:

```text
5 + 3 + 2 = 10 PYC
```

Không cần lưu biến:

```python
alice.balance = 10
```

Balance phải được suy ra từ UTXO state.

---

# 6. Một transaction tiêu coin như thế nào?

Giả sử Alice có:

```text
TX_A output[0]
10 PYC → Alice
```

Alice muốn gửi Bob 6 PYC.

Không được sửa output cũ thành:

```text
4 PYC → Alice
6 PYC → Bob
```

Blockchain coi output cũ là bất biến.

Transaction mới phải:

```text
Input:
    tham chiếu TX_A output[0]

Outputs:
    6 PYC → Bob
    4 PYC → Alice
```

Sơ đồ:

```text
        TX_A output[0]
          10 PYC
             │
             │ spend
             ▼
       ┌─────────────┐
       │ New TX      │
       └──────┬──────┘
              │
       ┌──────┴──────┐
       ▼             ▼
  Bob: 6 PYC    Alice: 4 PYC
```

Output 4 PYC quay lại Alice được gọi là:

```text
change output
```

---

# 7. Amount phải dùng integer

Không dùng:

```python
amount = 0.1
```

vì floating point có thể tạo sai số.

Phase 2 nên quy ước:

```text
amount luôn là int > 0
```

Ví dụ đơn giản ở giai đoạn học:

```python
amount = 10
```

nghĩa là:

```text
10 PYC
```

Sau này nếu muốn giống cryptocurrency thực hơn, có thể quy định:

```text
1 PYC = 100_000_000 smallest units
```

nhưng Phase 2 chưa cần làm decimal layer.

---

# 8. Bước 1 — `TxOutput`

Tạo:

```text
transaction/tx_output.py
```

Một output nói rằng:

> Một lượng coin cụ thể được khóa cho một blockchain address cụ thể.

Data model:

```python
from dataclasses import dataclass


@dataclass
class TxOutput:
    amount: int
    recipient_address: str
```

Nên có:

```python
def to_dict(self) -> dict:
    ...
```

Output serialized phải có dạng ổn định:

```text
{
    "amount": 6,
    "recipient_address": "PYC_..."
}
```

Không lưu:

```text
recipient_name = "Bob"
```

Blockchain chỉ quan tâm address.

---

# 9. Test `TxOutput`

`tests/test_tx_output.py` nên kiểm tra ít nhất:

```text
1. tạo TxOutput thành công
2. amount được giữ đúng
3. recipient_address được giữ đúng
4. to_dict() deterministic
```

Validation về amount/address có thể để ở `transaction/validation.py` để model không bị nhồi quá nhiều logic.

---

# 10. Bước 2 — `TxInput`

Tạo:

```text
transaction/tx_input.py
```

Input **không chứa amount**.

Input chỉ tham chiếu tới một output cũ:

```text
previous_tx_id
+
output_index
```

và cung cấp bằng chứng quyền sở hữu:

```text
public_key
signature
```

Data model:

```python
from dataclasses import dataclass


@dataclass
class TxInput:
    previous_tx_id: str
    output_index: int
    public_key: str = ""
    signature: str = ""
```

Trong đó:

```text
previous_tx_id
```

là ID của transaction tạo ra UTXO cũ.

```text
output_index
```

là vị trí output trong transaction đó.

Ví dụ:

```text
TX_A.outputs[0]
```

được tham chiếu bằng:

```text
previous_tx_id = TX_A.txid
output_index   = 0
```

---

# 11. Vì sao input phải mang public key?

UTXO cũ chỉ lưu:

```text
recipient_address = PYC_...
```

Khi Alice muốn tiêu UTXO, Alice gửi:

```text
public key
+
signature
```

Node sẽ kiểm tra:

```text
public key
   │
   ▼
public_key_to_address(...)
   │
   ▼
PYC_...
```

sau đó so sánh với:

```text
UTXO.recipient_address
```

Nếu giống nhau:

```text
public key này tương ứng với address sở hữu UTXO
```

Nhưng vẫn chưa đủ.

Node còn phải verify signature để chứng minh người gửi thật sự giữ private key tương ứng.

---

# 12. Bổ sung nhỏ vào Phase 1 — parse public key từ hex

Phase 1 hiện đã có:

```python
public_key_to_hex(public_key)
```

Nhưng transaction cần truyền public key dưới dạng dữ liệu serializable.

Vì vậy Phase 2 nên bổ sung vào:

```text
crypto/keys.py
```

helper:

```python
from ecdsa import VerifyingKey, SECP256k1


def public_key_from_hex(public_key_hex: str) -> VerifyingKey:
    return VerifyingKey.from_string(
        bytes.fromhex(public_key_hex),
        curve=SECP256k1,
    )
```

Luồng:

```text
VerifyingKey object
      │
      ▼
public_key_to_hex()
      │
      ▼
transaction data / network-safe string
      │
      ▼
public_key_from_hex()
      │
      ▼
VerifyingKey object
      │
      ▼
verify_signature()
```

Thêm test vào `tests/test_keys.py`:

```text
public key → hex → public key
```

phải trả lại cùng key.

---

# 13. Bước 3 — `Transaction`

Tạo:

```text
transaction/transaction.py
```

Data model tối thiểu:

```python
class Transaction:
    version
    inputs
    outputs
    timestamp
```

Có thể dùng `dataclass`:

```python
@dataclass
class Transaction:
    inputs: list[TxInput]
    outputs: list[TxOutput]
    timestamp: int
    version: int = 1
```

Không cần lưu `txid` thành mutable field nếu có thể tính từ nội dung transaction.

---

# 14. Serialization của Transaction

Transaction phải có:

```python
def to_dict(self, include_signatures: bool = True) -> dict:
    ...
```

Ví dụ transaction hoàn chỉnh:

```text
{
  "version": 1,
  "inputs": [
    {
      "previous_tx_id": "abc...",
      "output_index": 0,
      "public_key": "12ab...",
      "signature": "3045..."
    }
  ],
  "outputs": [
    {
      "amount": 6,
      "recipient_address": "PYC_BOB..."
    },
    {
      "amount": 3,
      "recipient_address": "PYC_ALICE..."
    }
  ],
  "timestamp": 1234567890
}
```

Sau đó dùng primitive Phase 1:

```python
serialize(transaction.to_dict())
```

Không tự viết serializer thứ hai.

---

# 15. Bước 4 — Transaction ID

Transaction ID nên được tính bằng hash của **transaction hoàn chỉnh**:

```text
Transaction
   │
   ▼
to_dict(include_signatures=True)
   │
   ▼
serialize(...)
   │
   ▼
SHA-256
   │
   ▼
txid
```

Ví dụ method:

```python
def txid(self) -> str:
    ...
```

có thể dùng:

```python
sha256_hex(
    serialize(self.to_dict(include_signatures=True))
)
```

Yêu cầu:

```text
cùng transaction hoàn chỉnh
→ cùng txid
```

và:

```text
đổi amount / input / signature
→ txid đổi
```

---

# 16. Cực kỳ quan trọng — Không ký `txid`

Không làm:

```text
transaction
   ↓
txid
   ↓
sign(txid)
   ↓
signature được thêm vào transaction
   ↓
txid thay đổi
```

Đây là circular dependency.

Thay vào đó phải có hai representation:

```text
1. Signing payload
   → KHÔNG chứa signatures

2. Final transaction serialization
   → CÓ chứa signatures
```

Sơ đồ:

```text
transaction fields
      │
      ├──────────────► signing payload
      │                    │
      │                    ▼
      │                  sign
      │                    │
      │                    ▼
      │               signature
      │                    │
      └────────────────────┘
               │
               ▼
       final transaction
               │
               ▼
             txid
```

---

# 17. Bước 5 — Signing payload

Transaction nên có method kiểu:

```python
def signing_dict(self, input_index: int) -> dict:
    ...
```

Payload phải khóa được các dữ liệu quan trọng:

```text
version
all previous outpoints
all outputs
amounts
recipient addresses
timestamp
input đang ký
public key của input đang ký
```

Nhưng **không chứa signature**.

Một thiết kế đơn giản cho project:

```text
{
  "version": 1,
  "inputs": [
    {
      "previous_tx_id": "...",
      "output_index": 0
    }
  ],
  "outputs": [...],
  "timestamp": ...,
  "signing_input_index": 0,
  "public_key": "..."
}
```

Sau đó:

```python
signing_bytes = serialize(
    transaction.signing_dict(input_index)
)
```

và dùng Phase 1:

```python
sign_message(private_key, signing_bytes)
```

Lợi ích:

```text
attacker sửa recipient
→ payload thay đổi
→ signature invalid

attacker sửa amount
→ payload thay đổi
→ signature invalid

attacker đổi previous UTXO
→ payload thay đổi
→ signature invalid
```

---

# 18. Bước 6 — Ký từng input

Transaction nên có helper kiểu:

```python
def sign_input(
    self,
    input_index: int,
    private_key,
) -> None:
    ...
```

Luồng:

```text
private key
    │
    ▼
get_public_key()
    │
    ▼
public_key_to_hex()
    │
    ▼
set input.public_key
    │
    ▼
build signing payload
    │
    ▼
serialize
    │
    ▼
sign_message()
    │
    ▼
signature.hex()
    │
    ▼
set input.signature
```

Nếu transaction có nhiều input:

```text
input[0] → signature[0]
input[1] → signature[1]
input[2] → signature[2]
```

Mỗi input chứng minh quyền được tiêu UTXO mà nó tham chiếu.

---

# 19. Test transaction signing

`tests/test_transaction.py` nên có ít nhất:

```text
1. transaction serialization deterministic
2. same fully-signed transaction → same txid
3. modify output amount → txid changes
4. sign_input() fills public_key
5. sign_input() fills signature
6. signing payload không chứa signature
7. sửa amount sau khi ký → signature verification fail
8. sửa recipient sau khi ký → signature verification fail
```

---

# 20. Bước 7 — UTXO Set

Tạo:

```text
transaction/utxo.py
```

UTXO key nên là một outpoint:

```text
(txid, output_index)
```

Ví dụ:

```python
UTXO_SET = {
    ("abc...", 0): TxOutput(...),
    ("def...", 1): TxOutput(...),
}
```

Nên gói bằng class thay vì dùng global dict:

```python
class UTXOSet:
    def __init__(self):
        self._utxos = {}
```

API tối thiểu:

```python
add(txid, output_index, output)
get(txid, output_index)
exists(txid, output_index)
spend(txid, output_index)
get_balance(address)
add_transaction_outputs(transaction)
apply_transaction(transaction)
```

Khuyến nghị:

```text
apply_transaction(transaction)
```

chỉ được gọi **sau khi transaction đã validate thành công**.

Nếu muốn tên an toàn hơn có thể dùng:

```python
apply_valid_transaction(transaction)
```

---

# 21. UTXO state update

Khi transaction hợp lệ được apply:

## Bước A — remove UTXO bị tiêu

Với mỗi input:

```text
(previous_tx_id, output_index)
```

remove khỏi UTXO set.

## Bước B — add outputs mới

Giả sử transaction mới có:

```text
txid = XYZ
```

và:

```text
outputs[0] → Bob 6
outputs[1] → Alice 3
```

UTXO mới:

```text
(XYZ, 0) → Bob 6
(XYZ, 1) → Alice 3
```

Luồng:

```text
Before
------
(OLD, 0) → Alice 10

Apply transaction

After
-----
(NEW, 0) → Bob 6
(NEW, 1) → Alice 3
```

UTXO cũ biến mất.

---

# 22. Bước 8 — Balance

Balance không nằm trong transaction.

Nó được tính:

```python
def get_balance(address: str) -> int:
    total = 0

    for output in utxos:
        if output.recipient_address == address:
            total += output.amount

    return total
```

Test:

```text
Alice có UTXO 5 + 3 + 2
→ balance = 10
```

Sau khi tiêu UTXO 10 thành:

```text
6 → Bob
3 → Alice
1 → fee
```

thì:

```text
Alice = 3
Bob   = 6
```

Fee 1 PYC chưa trở thành UTXO ở Phase 2.

Sau này Mining/Coinbase Phase sẽ đưa fee cho miner.

---

# 23. Bước 9 — Transaction validation

Tạo:

```text
transaction/validation.py
```

Đây là file quan trọng nhất của Phase 2.

Function chính:

```python
def validate_transaction(
    transaction: Transaction,
    utxo_set: UTXOSet,
) -> bool:
    ...
```

Không validate theo kiểu:

```text
signature đúng → transaction đúng
```

Một transaction chỉ hợp lệ nếu **toàn bộ rule đều pass**.

---

# 24. Validation Rule 1 — phải có input

Trong Phase 2, transaction thường phải có:

```text
len(inputs) >= 1
```

Transaction không input sẽ dành cho:

```text
coinbase transaction
```

nhưng coinbase chưa thuộc Phase 2.

Do đó:

```text
0 input → invalid
```

---

# 25. Validation Rule 2 — phải có output

```text
len(outputs) >= 1
```

Transaction tiêu coin nhưng không tạo output nào chưa có ý nghĩa trong scope hiện tại.

---

# 26. Validation Rule 3 — output amount hợp lệ

Mỗi output phải:

```text
isinstance(amount, int)
amount > 0
```

Không cho:

```text
0 PYC
-5 PYC
1.5 PYC
```

ở Phase 2.

---

# 27. Validation Rule 4 — recipient address hợp lệ

Dùng primitive Phase 1:

```python
validate_address(output.recipient_address)
```

Nếu address bị sửa checksum:

```text
invalid transaction
```

Không copy/paste lại logic checksum vào `validation.py`.

---

# 28. Validation Rule 5 — không được duplicate input trong cùng transaction

Transaction này phải invalid:

```text
inputs[0] → (TX_A, 0)
inputs[1] → (TX_A, 0)
```

vì cùng một UTXO đang bị tính hai lần.

Dùng set:

```text
seen_outpoints
```

Nếu gặp lại cùng:

```text
(previous_tx_id, output_index)
```

→ reject.

Đây là một dạng double-spend ngay bên trong cùng transaction.

---

# 29. Validation Rule 6 — referenced UTXO phải tồn tại

Với mỗi input:

```text
(previous_tx_id, output_index)
```

phải có trong UTXO Set.

Nếu không tồn tại, có thể là:

```text
UTXO chưa từng tồn tại
```

hoặc:

```text
UTXO đã bị tiêu trước đó
```

Cả hai trường hợp đều:

```text
invalid
```

Đây là nền tảng ngăn double-spend.

---

# 30. Validation Rule 7 — public key phải sở hữu UTXO

Với input:

```text
input.public_key
```

node làm:

```text
public_key hex
    │
    ▼
public_key_from_hex(...)
    │
    ▼
public_key_to_address(...)
    │
    ▼
derived address
```

Sau đó lấy referenced output:

```text
utxo.recipient_address
```

Check:

```text
derived_address == utxo.recipient_address
```

Nếu Bob lấy UTXO của Alice nhưng gắn public key Bob:

```text
Bob public key
     ↓
Bob address
     !=
Alice address trong UTXO
```

→ invalid.

---

# 31. Validation Rule 8 — signature phải hợp lệ

Sau khi ownership pass, node reconstruct signing payload:

```text
transaction.signing_dict(input_index)
        │
        ▼
serialize(...)
        │
        ▼
signing bytes
```

Sau đó:

```python
verify_signature(
    public_key,
    signing_bytes,
    bytes.fromhex(input.signature),
)
```

Nếu attacker sửa:

```text
amount
recipient
previous_tx_id
output_index
```

sau khi Alice ký:

```text
signature verification = False
```

---

# 32. Validation Rule 9 — tổng input không được nhỏ hơn tổng output

Tổng input được lấy từ **UTXO Set**, không lấy từ field mà sender tự khai.

Ví dụ:

```text
Input UTXO = 10
```

Transaction muốn tạo:

```text
Bob   = 9
Alice = 5
```

Total output:

```text
14
```

Node kiểm tra:

```text
10 >= 14
```

False.

→ invalid.

Nếu không có rule này, attacker có thể tự tạo coin từ không khí.

---

# 33. Transaction fee

Fee:

```text
fee = sum(inputs) - sum(outputs)
```

Ví dụ:

```text
Input:
10

Outputs:
6 → Bob
3 → Alice
```

thì:

```text
fee = 10 - 9 = 1
```

Tạo helper:

```python
def calculate_transaction_fee(
    transaction,
    utxo_set,
) -> int:
    ...
```

Phase 2 chỉ tính fee.

Chưa cần trả fee cho miner.

Sau này:

```text
Coinbase reward
=
block subsidy
+
transaction fees
```

---

# 34. Thứ tự validation được khuyên dùng

```text
Transaction received
       │
       ▼
inputs tồn tại?
       │
       ▼
outputs tồn tại?
       │
       ▼
output amount hợp lệ?
       │
       ▼
address hợp lệ?
       │
       ▼
duplicate input?
       │
       ▼
referenced UTXO tồn tại?
       │
       ▼
public key parse được?
       │
       ▼
public key sở hữu UTXO?
       │
       ▼
signature đúng?
       │
       ▼
sum(inputs) >= sum(outputs)?
       │
       ▼
VALID
```

Chỉ sau khi VALID mới update state.

---

# 35. Bước 10 — Ngăn double-spend

Giả sử ban đầu:

```text
(FUNDING_TX, 0) → Alice 10
```

Alice tạo TX1:

```text
Input:
(FUNDING_TX, 0)

Outputs:
6 → Bob
4 → Alice
```

TX1 hợp lệ và được apply.

UTXO:

```text
(FUNDING_TX, 0)
```

bị remove.

Nếu Alice hoặc attacker gửi TX2 cũng tham chiếu:

```text
(FUNDING_TX, 0)
```

validator hỏi:

```text
UTXO tồn tại?
```

Kết quả:

```text
False
```

TX2 bị reject.

Đây là double-spend prevention ở state level.

---

# 36. Lưu ý về double-spend ở Phase 2

Phase 2 chỉ xử lý trường hợp:

```text
transaction đã apply vào UTXO Set
→ UTXO biến mất
→ transaction sau không thể dùng lại
```

Chưa xử lý trường hợp:

```text
TX1 và TX2 cùng nằm trong mempool
và cùng muốn tiêu một UTXO
```

vì mempool chưa tồn tại.

Rule mempool conflict sẽ làm ở Phase Mempool sau.

---

# 37. Test bắt buộc cho validation

`tests/test_transaction_validation.py` nên có ít nhất các case sau.

## Valid cases

```text
1. owner đúng + signature đúng + đủ input → valid
2. transaction có change output → valid
3. fee = input - output được tính đúng
```

## Invalid ownership/signature

```text
4. wrong public key → invalid
5. wrong private key/signature → invalid
6. modified amount after signing → invalid
7. modified recipient after signing → invalid
8. corrupted signature → invalid
```

## Invalid UTXO

```text
9. referenced UTXO does not exist → invalid
10. duplicate same input in one transaction → invalid
11. spend an already-spent UTXO → invalid
```

## Invalid amounts

```text
12. output amount = 0 → invalid
13. output amount < 0 → invalid
14. output amount is float → invalid
15. sum(outputs) > sum(inputs) → invalid
```

## Invalid address

```text
16. malformed address → invalid
17. checksum-modified address → invalid
```

---

# 38. Test UTXO Set

`tests/test_utxo.py` nên có:

```text
1. add UTXO
2. exists() returns True
3. get() returns correct output
4. spend() removes UTXO
5. get_balance() sums only matching address
6. apply transaction removes inputs
7. apply transaction creates new outputs
8. balance changes correctly after apply
```

Ví dụ:

```text
Before:
Alice = 10
Bob   = 0

TX:
6 → Bob
3 → Alice
fee = 1

After:
Alice = 3
Bob   = 6
```

---

# 39. Demo Phase 2 không cần blockchain thật

Ở Phase 2 chưa có Genesis Block hoặc Mining.

Vì vậy demo được phép **seed một UTXO giả lập** để test transaction engine.

Ví dụ:

```python
funding_txid = sha256_hex(b"phase2-demo-funding")
```

Sau đó:

```text
(funding_txid, 0)
→ 10 PYC
→ Alice address
```

được add trực tiếp vào UTXO Set.

Điều này chỉ là bootstrap cho demo Phase 2.

Sau khi có blockchain thật, UTXO sẽ được sinh ra từ outputs của transactions trong blocks.

---

# 40. `demo_phase2.py` nên chạy theo luồng nào?

## Step 1 — tạo Alice và Bob

```text
Alice private key
Alice public key
Alice address

Bob private key
Bob public key
Bob address
```

## Step 2 — seed funding UTXO

```text
Alice receives 10 PYC
```

UTXO Set:

```text
(FUNDING, 0) → Alice 10
```

## Step 3 — tạo transaction

Input:

```text
(FUNDING, 0)
```

Outputs:

```text
6 → Bob
3 → Alice
```

## Step 4 — Alice ký input

```text
Alice private key
      ↓
sign transaction input
```

## Step 5 — validate

Expected:

```text
True
```

## Step 6 — tính fee

Expected:

```text
1 PYC
```

## Step 7 — apply transaction

Expected:

```text
Alice balance = 3
Bob balance = 6
```

## Step 8 — thử double-spend

Tạo transaction mới vẫn dùng:

```text
(FUNDING, 0)
```

Expected:

```text
False
```

---

# 41. Output mong đợi của `demo_phase2.py`

Ví dụ:

```text
=== PHASE 2 — TRANSACTION DEMO ===

Alice:
PYC_a1...

Bob:
PYC_b2...

=== INITIAL UTXO ===
Alice balance: 10 PYC
Bob balance:   0 PYC

=== TRANSACTION ===
Input:
<funding_txid>:0

Outputs:
6 PYC -> Bob
3 PYC -> Alice

Fee:
1 PYC

Transaction ID:
7f3a...

=== VALIDATION ===
Valid: True

=== APPLY ===
Alice balance: 3 PYC
Bob balance:   6 PYC

=== DOUBLE SPEND TEST ===
Second transaction valid: False
```

---

# 42. Không mutate transaction sau khi đã ký

Một nguyên tắc nên giữ:

```text
build transaction
      ↓
sign transaction
      ↓
không sửa inputs/outputs nữa
```

Nếu sửa:

```text
amount
recipient
input reference
```

sau khi ký thì signature phải fail.

Đây là behavior đúng.

---

# 43. Không tin dữ liệu do sender tự khai

Ví dụ tuyệt đối không cho `TxInput` có:

```python
amount = 1000
```

rồi validator tin con số đó.

Amount input phải lấy từ:

```text
referenced UTXO
```

Tức:

```text
input says:
(TX_A, 0)

node looks up:
UTXO_SET[(TX_A, 0)]

node discovers:
amount = 10
owner  = Alice
```

Blockchain node phải derive state từ dữ liệu đã biết, không tin claim của người gửi.

---

# 44. Không dùng sender address như bằng chứng ownership

Không thiết kế transaction kiểu:

```text
sender = AliceAddress
receiver = BobAddress
amount = 6
```

rồi coi:

```text
sender == AliceAddress
```

là đủ.

Ai cũng có thể viết chuỗi:

```text
sender = AliceAddress
```

Bằng chứng thật phải là:

```text
public key maps to owner address
+
valid ECDSA signature
```

---

# 45. Không tự tạo balance table ở Phase 2

Không làm:

```python
balances = {
    alice_address: 10,
    bob_address: 0,
}
```

và update trực tiếp.

Đó là account model.

Project này đang học Bitcoin-like UTXO model.

State chuẩn phải là:

```text
UTXO Set
```

Balance chỉ là query từ state đó.

---

# 46. Suggested API cuối Phase 2

Sau Phase 2, code nên có API gần như sau:

```python
# transaction/tx_output.py
class TxOutput:
    amount: int
    recipient_address: str

    def to_dict(self) -> dict:
        ...


# transaction/tx_input.py
class TxInput:
    previous_tx_id: str
    output_index: int
    public_key: str
    signature: str

    def to_dict(self, include_signature=True) -> dict:
        ...


# transaction/transaction.py
class Transaction:
    version: int
    inputs: list[TxInput]
    outputs: list[TxOutput]
    timestamp: int

    def to_dict(self, include_signatures=True) -> dict:
        ...

    def signing_dict(self, input_index: int) -> dict:
        ...

    def signing_bytes(self, input_index: int) -> bytes:
        ...

    def sign_input(self, input_index: int, private_key) -> None:
        ...

    def txid(self) -> str:
        ...


# transaction/utxo.py
class UTXOSet:
    def add(self, txid, output_index, output):
        ...

    def get(self, txid, output_index):
        ...

    def exists(self, txid, output_index):
        ...

    def spend(self, txid, output_index):
        ...

    def get_balance(self, address):
        ...

    def add_transaction_outputs(self, transaction):
        ...

    def apply_valid_transaction(self, transaction):
        ...


# transaction/validation.py
def calculate_transaction_fee(transaction, utxo_set) -> int:
    ...


def validate_transaction(transaction, utxo_set) -> bool:
    ...
```

Tên function có thể thay đổi nhẹ, nhưng responsibility nên giữ đúng như trên.

---

# 47. Dependency giữa các file

Nên giữ dependency một chiều:

```text
crypto/hash.py
crypto/keys.py
crypto/signature.py
crypto/address.py
       │
       ▼
transaction/tx_input.py
transaction/tx_output.py
       │
       ▼
transaction/transaction.py
       │
       ├────────────► transaction/utxo.py
       │
       └────────────► transaction/validation.py
```

Không để:

```text
crypto/ import transaction/
```

Crypto layer phải độc lập với transaction layer.

---

# 48. Thứ tự code Phase 2

Không viết tất cả một lần.

Làm theo thứ tự:

```text
STEP 1
TxOutput
   ↓
test TxOutput

STEP 2
TxInput
   ↓
test TxInput

STEP 3
public_key_from_hex()
   ↓
test round-trip public key

STEP 4
Transaction serialization
   ↓
test deterministic serialization

STEP 5
Signing payload
   ↓
sign_input()
   ↓
test signature

STEP 6
txid
   ↓
test transaction ID

STEP 7
UTXOSet
   ↓
add / get / spend / balance
   ↓
test UTXO

STEP 8
validate_transaction()
   ↓
ownership
signature
amount
UTXO existence
   ↓
test validator

STEP 9
apply_valid_transaction()
   ↓
test state transition

STEP 10
double-spend test

STEP 11
demo_phase2.py

STEP 12
run all Phase 1 + Phase 2 tests
```

---

# 49. Command chạy test

Từ root project:

```bash
python -m pytest -v
```

Yêu cầu:

```text
Phase 1 tests vẫn pass
+
Phase 2 tests pass
```

Không được sửa Phase 1 theo cách làm test cũ fail.

Chạy riêng Phase 2:

```bash
python -m pytest tests/test_tx_input.py -v
python -m pytest tests/test_tx_output.py -v
python -m pytest tests/test_transaction.py -v
python -m pytest tests/test_utxo.py -v
python -m pytest tests/test_transaction_validation.py -v
```

Demo:

```bash
python demo_phase2.py
```

---

# 50. Definition of Done — Phase 2 chỉ được coi là hoàn thành khi

## Data model

- [ ] Có `TxInput`.
- [ ] Có `TxOutput`.
- [ ] Có `Transaction`.
- [ ] Serialization deterministic.
- [ ] Amount dùng integer.

## Cryptographic authorization

- [ ] Transaction input lưu public key dạng hex.
- [ ] Transaction input lưu signature dạng hex.
- [ ] Có `public_key_from_hex()`.
- [ ] Owner có thể ký input bằng private key.
- [ ] Node verify được signature bằng public key.
- [ ] Sửa amount sau khi ký làm signature fail.
- [ ] Sửa recipient sau khi ký làm signature fail.

## Transaction ID

- [ ] Có deterministic `txid`.
- [ ] `txid` được tính từ final serialized transaction.
- [ ] Signing payload không phụ thuộc vào signature.

## UTXO

- [ ] Có `UTXOSet`.
- [ ] UTXO được định danh bằng `(txid, output_index)`.
- [ ] Add/get/spend hoạt động.
- [ ] Balance được tính từ UTXO Set.
- [ ] Apply transaction remove input UTXO.
- [ ] Apply transaction tạo output UTXO mới.

## Validation

- [ ] Reject zero-input normal transaction.
- [ ] Reject zero-output transaction.
- [ ] Reject invalid output amount.
- [ ] Reject invalid address/checksum.
- [ ] Reject duplicate input.
- [ ] Reject nonexistent UTXO.
- [ ] Reject wrong public key ownership.
- [ ] Reject bad signature.
- [ ] Reject `sum(outputs) > sum(inputs)`.
- [ ] Calculate fee đúng.
- [ ] Reject spending an already spent UTXO.

## Regression

- [ ] Tất cả Phase 1 tests vẫn pass.
- [ ] Tất cả Phase 2 tests pass.
- [ ] `demo_phase2.py` chạy end-to-end.

---

# 51. Kiến thức bạn phải tự giải thích được sau Phase 2

Nếu hoàn thành code nhưng chưa trả lời được các câu dưới đây thì chưa nên qua Phase 3.

### Câu 1

UTXO là gì?

### Câu 2

Vì sao Alice không có một biến `balance` nằm trong blockchain?

### Câu 3

`TxInput(previous_tx_id, output_index)` đang tham chiếu tới cái gì?

### Câu 4

Vì sao transaction input không cần tự khai amount?

### Câu 5

Vì sao public key chưa đủ để chứng minh quyền sở hữu?

### Câu 6

Signature chứng minh điều gì?

### Câu 7

Node biết public key thuộc owner của UTXO bằng cách nào?

### Câu 8

Vì sao signing payload phải khác final transaction serialization?

### Câu 9

Vì sao không nên ký `txid` nếu `txid` lại chứa signature?

### Câu 10

Double-spend bị chặn như thế nào bằng UTXO Set?

### Câu 11

Transaction fee đến từ đâu?

### Câu 12

Nếu input = 10 và outputs = 6 + 3 thì 1 PYC còn lại đi đâu?

Đáp án Phase 2:

```text
đó là transaction fee;
Phase 2 mới tính fee,
Phase Mining sau mới đưa fee vào coinbase reward của miner.
```

---

# 52. Luồng hoàn chỉnh cần nhớ

```text
Alice has private key
        │
        ▼
Alice address owns UTXO
        │
        ▼
(FUNDING_TX, 0) → 10 PYC
        │
        ▼
Alice builds Transaction
        │
        ├── Input:  FUNDING_TX:0
        │
        ├── Output: Bob   6
        │
        └── Output: Alice 3
        │
        ▼
Transaction creates signing payload
        │
        ▼
Alice signs with private key
        │
        ▼
public key + signature stored in input
        │
        ▼
Node receives transaction
        │
        ▼
Find referenced UTXO
        │
        ▼
public key → address
        │
        ▼
compare with UTXO owner
        │
        ▼
verify ECDSA signature
        │
        ▼
check total input >= total output
        │
        ▼
VALID
        │
        ▼
remove FUNDING_TX:0
        │
        ▼
add NEW_TX:0 → Bob 6
add NEW_TX:1 → Alice 3
        │
        ▼
Alice balance = 3
Bob balance   = 6
fee           = 1
```

---

# 53. Phase 2 sẽ chuẩn bị gì cho Phase 3?

Sau Phase 2 bạn đã có object quan trọng nhất mà block sẽ chứa:

```text
Transaction
```

Phase tiếp theo có thể bắt đầu xây:

```text
Block
├── Block Header
├── previous_block_hash
├── timestamp
├── transactions[]
└── Merkle Root
```

Tức dependency là:

```text
PHASE 1
Crypto
   ↓
PHASE 2
Transaction + UTXO + Validation
   ↓
PHASE 3
Block + Merkle Tree
```

Không nên sang Block trước khi transaction signing/validation và UTXO tests đã ổn định.

---

# 54. Kết quả thực sự của Phase 2

Phase 1 mới chứng minh:

```text
"Tôi có thể tạo key và ký dữ liệu."
```

Phase 2 phải chứng minh:

```text
"Tôi có thể dùng key để chứng minh quyền tiêu một UTXO,
chuyển giá trị sang các output mới,
kiểm tra transaction độc lập,
và ngăn cùng một coin bị tiêu lại."
```

Đây là lúc project bắt đầu chuyển từ một demo cryptography thành **transaction engine của một Bitcoin-like blockchain**.
