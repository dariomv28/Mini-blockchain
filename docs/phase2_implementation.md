Nếu bạn làm **Phase 2 hoàn toàn thủ công**, tôi khuyên tạo đúng theo dependency, không tạo tất cả file rồi mới code. Theo `phase2_plan.md`, Phase 2 chỉ gồm Transaction, UTXO, signing/validation, fee và double-spend; **chưa có Block, Mining, Mempool**.

Luồng làm sẽ là:

```text
Phase 1 hiện tại
      │
      ▼
1. sửa crypto/keys.py
      │
      ▼
2. transaction/tx_output.py
      │
      ▼
3. transaction/tx_input.py
      │
      ▼
4. transaction/transaction.py
      │
      ▼
5. transaction/utxo.py
      │
      ▼
6. transaction/validation.py
      │
      ▼
7. tests
      │
      ▼
8. demo_phase2.py
```

---

# 0. Cấu trúc ban đầu

Sau khi giải nén `phase1_passed.zip`, hiện tại bạn có đại khái:

```text
Mini Blockchain/
│
├── crypto/
│   ├── __init__.py
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
└── demo_phase1.py
```

Tạo folder mới:

```powershell
mkdir transaction
```

Sau Phase 2 sẽ thành:

```text
Mini Blockchain/
│
├── crypto/
│
├── transaction/
│   ├── __init__.py
│   ├── tx_output.py
│   ├── tx_input.py
│   ├── transaction.py
│   ├── utxo.py
│   └── validation.py
│
├── tests/
│   ├── ...
│   ├── test_tx_output.py
│   ├── test_tx_input.py
│   ├── test_transaction.py
│   ├── test_utxo.py
│   └── test_transaction_validation.py
│
├── demo_phase1.py
└── demo_phase2.py
```

Đúng với kiến trúc được chốt trong plan. 

---

# 1. Đầu tiên sửa `crypto/keys.py`

Hiện tại Phase 1 đã có:

```python
public_key_to_hex()
```

Nhưng Phase 2 sẽ lưu public key trong transaction dưới dạng string hex.

Khi validate phải đổi:

```text
hex string
   ↓
VerifyingKey
```

nên cần hàm ngược lại.

Mở:

```text
crypto/keys.py
```

và sửa thành:

```python
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
```

Ý nghĩa:

```text
VerifyingKey
    │
    ▼
public_key_to_hex()
    │
    ▼
"abc123..."
    │
    ▼
public_key_from_hex()
    │
    ▼
VerifyingKey
```

Thêm vào cuối `tests/test_keys.py`:

```python
def test_public_key_hex_round_trip():
    from crypto.keys import public_key_from_hex, public_key_to_hex

    private_key = generate_private_key()
    public_key = get_public_key(private_key)

    public_key_hex = public_key_to_hex(public_key)
    restored_public_key = public_key_from_hex(public_key_hex)

    assert restored_public_key.to_string() == public_key.to_string()
```

Chạy:

```powershell
python -m pytest tests/test_keys.py -v
```

Phải pass rồi mới đi tiếp.

---

# 2. Tạo `transaction/__init__.py`

Tạo:

```text
transaction/__init__.py
```

Hiện tại để **trống**:

```python
```

Không cần làm gì thêm.

---

# 3. Tạo `transaction/tx_output.py`

Đây nên là file transaction đầu tiên vì nó đơn giản nhất.

Tạo:

```text
transaction/tx_output.py
```

Nội dung:

```python
from dataclasses import dataclass


@dataclass
class TxOutput:
    amount: int
    recipient_address: str

    def to_dict(self) -> dict:
        return {
            "amount": self.amount,
            "recipient_address": self.recipient_address,
        }
```

Hiểu class này là:

```text
TxOutput
├── amount
└── recipient_address
```

Ví dụ:

```python
output = TxOutput(
    amount=6,
    recipient_address=bob_address,
)
```

nghĩa là:

```text
6 PYC → Bob
```

`to_dict()` cần vì sau này transaction phải serialize.

Ví dụ:

```python
output.to_dict()
```

ra:

```python
{
    "amount": 6,
    "recipient_address": "PYC_..."
}
```

### Test

Tạo:

```text
tests/test_tx_output.py
```

```python
from transaction.tx_output import TxOutput


def test_tx_output():
    output = TxOutput(
        amount=6,
        recipient_address="PYC_test",
    )

    assert output.amount == 6
    assert output.recipient_address == "PYC_test"


def test_tx_output_to_dict():
    output = TxOutput(
        amount=6,
        recipient_address="PYC_test",
    )

    assert output.to_dict() == {
        "amount": 6,
        "recipient_address": "PYC_test",
    }
```

Chạy:

```powershell
python -m pytest tests/test_tx_output.py -v
```

---

# 4. Tạo `transaction/tx_input.py`

Tiếp theo mới tạo input.

Tạo:

```text
transaction/tx_input.py
```

```python
from dataclasses import dataclass


@dataclass
class TxInput:
    previous_tx_id: str
    output_index: int
    public_key: str = ""
    signature: str = ""

    def to_dict(
        self,
        include_signature: bool = True,
    ) -> dict:

        data = {
            "previous_tx_id": self.previous_tx_id,
            "output_index": self.output_index,
            "public_key": self.public_key,
        }

        if include_signature:
            data["signature"] = self.signature

        return data

    def outpoint_dict(self) -> dict:
        return {
            "previous_tx_id": self.previous_tx_id,
            "output_index": self.output_index,
        }
```

Đây là phần rất quan trọng.

Một input:

```python
TxInput(
    previous_tx_id="abc...",
    output_index=0,
)
```

có nghĩa:

> Tôi muốn tiêu `output[0]` của transaction `"abc..."`.

Nó **không chứa amount**.

```text
TxInput
├── previous_tx_id
├── output_index
├── public_key
└── signature
```

`outpoint_dict()` chỉ trả:

```text
previous_tx_id
output_index
```

để sau này dùng khi ký.

### Test

Tạo:

```text
tests/test_tx_input.py
```

```python
from transaction.tx_input import TxInput


def test_tx_input():
    tx_input = TxInput(
        previous_tx_id="abc",
        output_index=0,
    )

    assert tx_input.previous_tx_id == "abc"
    assert tx_input.output_index == 0


def test_tx_input_to_dict():
    tx_input = TxInput(
        previous_tx_id="abc",
        output_index=0,
        public_key="public",
        signature="signature",
    )

    assert tx_input.to_dict() == {
        "previous_tx_id": "abc",
        "output_index": 0,
        "public_key": "public",
        "signature": "signature",
    }


def test_outpoint_dict():
    tx_input = TxInput(
        previous_tx_id="abc",
        output_index=0,
        public_key="public",
        signature="signature",
    )

    assert tx_input.outpoint_dict() == {
        "previous_tx_id": "abc",
        "output_index": 0,
    }
```

Chạy:

```powershell
python -m pytest tests/test_tx_input.py -v
```

---

# 5. Tạo `transaction/transaction.py`

Bây giờ bạn đã có:

```text
TxInput
TxOutput
```

mới đủ để tạo:

```text
Transaction
```

Tạo:

```text
transaction/transaction.py
```

Nội dung:

```python
import time
from dataclasses import dataclass, field

from ecdsa import SigningKey

from crypto.hash import serialize, sha256_hex
from crypto.keys import (
    get_public_key,
    public_key_to_hex,
)
from crypto.signature import sign_message

from transaction.tx_input import TxInput
from transaction.tx_output import TxOutput


@dataclass
class Transaction:
    inputs: list[TxInput]
    outputs: list[TxOutput]

    timestamp: int = field(
        default_factory=lambda: int(time.time())
    )

    version: int = 1

    def to_dict(
        self,
        include_signatures: bool = True,
    ) -> dict:

        return {
            "version": self.version,

            "inputs": [
                tx_input.to_dict(
                    include_signature=include_signatures
                )
                for tx_input in self.inputs
            ],

            "outputs": [
                tx_output.to_dict()
                for tx_output in self.outputs
            ],

            "timestamp": self.timestamp,
        }

    def signing_dict(
        self,
        input_index: int,
    ) -> dict:

        if (
            input_index < 0
            or input_index >= len(self.inputs)
        ):
            raise IndexError(
                "input_index out of range"
            )

        return {
            "version": self.version,

            "inputs": [
                tx_input.outpoint_dict()
                for tx_input in self.inputs
            ],

            "outputs": [
                tx_output.to_dict()
                for tx_output in self.outputs
            ],

            "timestamp": self.timestamp,

            "signing_input_index": input_index,

            "public_key":
                self.inputs[input_index].public_key,
        }

    def signing_bytes(
        self,
        input_index: int,
    ) -> bytes:

        return serialize(
            self.signing_dict(input_index)
        )

    def sign_input(
        self,
        input_index: int,
        private_key: SigningKey,
    ) -> None:

        if (
            input_index < 0
            or input_index >= len(self.inputs)
        ):
            raise IndexError(
                "input_index out of range"
            )

        public_key = get_public_key(
            private_key
        )

        self.inputs[
            input_index
        ].public_key = public_key_to_hex(
            public_key
        )

        message = self.signing_bytes(
            input_index
        )

        signature = sign_message(
            private_key,
            message,
        )

        self.inputs[
            input_index
        ].signature = signature.hex()

    def txid(self) -> str:
        transaction_bytes = serialize(
            self.to_dict(
                include_signatures=True
            )
        )

        return sha256_hex(
            transaction_bytes
        )
```

Đây là file trung tâm.

---

## `to_dict()` làm gì?

Biến:

```python
Transaction(...)
```

thành:

```python
{
    "version": 1,
    "inputs": [...],
    "outputs": [...],
    "timestamp": ...
}
```

để có thể:

```text
Transaction
    ↓
dict
    ↓
serialize()
    ↓
bytes
```

---

## `signing_dict()` làm gì?

Tạo dữ liệu **để ký**.

Nó cố tình không chứa:

```text
signature
```

Luồng:

```text
Transaction chưa ký
       │
       ▼
signing_dict()
       │
       ▼
serialize()
       │
       ▼
sign_message(private_key)
       │
       ▼
signature
```

---

## `sign_input()` làm gì?

Ví dụ:

```python
transaction.sign_input(
    0,
    alice_private_key,
)
```

Nó thực hiện:

```text
Alice private key
       │
       ▼
Alice public key
       │
       ▼
đưa public key vào input[0]
       │
       ▼
tạo signing data
       │
       ▼
Alice ký
       │
       ▼
đưa signature vào input[0]
```

---

## `txid()` làm gì?

```text
Transaction hoàn chỉnh
       ↓
serialize
       ↓
SHA-256
       ↓
Transaction ID
```

Plan yêu cầu `txid` được tính từ transaction hoàn chỉnh, trong khi signing payload không chứa signature để tránh circular dependency. 

---

# 6. Test `Transaction`

Tạo:

```text
tests/test_transaction.py
```

```python
from crypto.keys import (
    generate_private_key,
    public_key_from_hex,
)
from crypto.signature import verify_signature

from transaction.transaction import Transaction
from transaction.tx_input import TxInput
from transaction.tx_output import TxOutput


def create_transaction():
    return Transaction(
        inputs=[
            TxInput(
                previous_tx_id="funding",
                output_index=0,
            )
        ],
        outputs=[
            TxOutput(
                amount=6,
                recipient_address="PYC_BOB",
            ),
            TxOutput(
                amount=3,
                recipient_address="PYC_ALICE",
            ),
        ],
        timestamp=1234567890,
    )


def test_sign_input():
    private_key = generate_private_key()

    transaction = create_transaction()

    transaction.sign_input(
        0,
        private_key,
    )

    assert transaction.inputs[0].public_key
    assert transaction.inputs[0].signature


def test_signature_is_valid():
    private_key = generate_private_key()

    transaction = create_transaction()

    transaction.sign_input(
        0,
        private_key,
    )

    public_key = public_key_from_hex(
        transaction.inputs[0].public_key
    )

    signature = bytes.fromhex(
        transaction.inputs[0].signature
    )

    assert verify_signature(
        public_key,
        transaction.signing_bytes(0),
        signature,
    )


def test_txid_is_deterministic():
    private_key = generate_private_key()

    transaction = create_transaction()

    transaction.sign_input(
        0,
        private_key,
    )

    txid1 = transaction.txid()
    txid2 = transaction.txid()

    assert txid1 == txid2


def test_modify_transaction_changes_txid():
    private_key = generate_private_key()

    transaction = create_transaction()

    transaction.sign_input(
        0,
        private_key,
    )

    original_txid = transaction.txid()

    transaction.outputs[0].amount = 7

    assert transaction.txid() != original_txid
```

Chạy:

```powershell
python -m pytest tests/test_transaction.py -v
```

---

# 7. Tạo `transaction/utxo.py`

Bây giờ mới tạo state chứa các output chưa tiêu.

Tạo:

```text
transaction/utxo.py
```

```python
from transaction.transaction import Transaction
from transaction.tx_output import TxOutput


class UTXOSet:
    def __init__(self):
        self._utxos: dict[
            tuple[str, int],
            TxOutput,
        ] = {}

    def add(
        self,
        txid: str,
        output_index: int,
        output: TxOutput,
    ) -> None:

        self._utxos[
            (txid, output_index)
        ] = output

    def get(
        self,
        txid: str,
        output_index: int,
    ) -> TxOutput | None:

        return self._utxos.get(
            (txid, output_index)
        )

    def exists(
        self,
        txid: str,
        output_index: int,
    ) -> bool:

        return (
            txid,
            output_index,
        ) in self._utxos

    def spend(
        self,
        txid: str,
        output_index: int,
    ) -> TxOutput:

        return self._utxos.pop(
            (txid, output_index)
        )

    def get_balance(
        self,
        address: str,
    ) -> int:

        total = 0

        for output in self._utxos.values():
            if (
                output.recipient_address
                == address
            ):
                total += output.amount

        return total

    def add_transaction_outputs(
        self,
        transaction: Transaction,
    ) -> None:

        txid = transaction.txid()

        for output_index, output in enumerate(
            transaction.outputs
        ):
            self.add(
                txid,
                output_index,
                output,
            )

    def apply_valid_transaction(
        self,
        transaction: Transaction,
    ) -> None:

        # Xóa UTXO cũ đã bị tiêu.
        for tx_input in transaction.inputs:
            self.spend(
                tx_input.previous_tx_id,
                tx_input.output_index,
            )

        # Tạo UTXO mới.
        self.add_transaction_outputs(
            transaction
        )
```

Cấu trúc bên trong:

```python
self._utxos = {
    ("tx123", 0): TxOutput(...),
    ("tx456", 1): TxOutput(...),
}
```

Ví dụ:

```text
("AAA", 0)
    → Alice 10
```

sau khi Alice tiêu:

```text
remove ("AAA", 0)

add ("BBB", 0) → Bob 6
add ("BBB", 1) → Alice 3
```

Đây chính là state transition mà plan yêu cầu. 

---

# 8. Test `UTXOSet`

Tạo:

```text
tests/test_utxo.py
```

```python
from transaction.tx_output import TxOutput
from transaction.utxo import UTXOSet


def test_add_and_get_utxo():
    utxos = UTXOSet()

    output = TxOutput(
        amount=10,
        recipient_address="Alice",
    )

    utxos.add(
        "tx1",
        0,
        output,
    )

    assert utxos.exists(
        "tx1",
        0,
    )

    assert utxos.get(
        "tx1",
        0,
    ) == output


def test_spend_utxo():
    utxos = UTXOSet()

    output = TxOutput(
        amount=10,
        recipient_address="Alice",
    )

    utxos.add(
        "tx1",
        0,
        output,
    )

    utxos.spend(
        "tx1",
        0,
    )

    assert not utxos.exists(
        "tx1",
        0,
    )


def test_get_balance():
    utxos = UTXOSet()

    utxos.add(
        "tx1",
        0,
        TxOutput(5, "Alice"),
    )

    utxos.add(
        "tx2",
        0,
        TxOutput(3, "Alice"),
    )

    utxos.add(
        "tx3",
        0,
        TxOutput(7, "Bob"),
    )

    assert utxos.get_balance(
        "Alice"
    ) == 8

    assert utxos.get_balance(
        "Bob"
    ) == 7
```

Chạy:

```powershell
python -m pytest tests/test_utxo.py -v
```

---

# 9. Cuối cùng mới tạo `transaction/validation.py`

Đây là file quan trọng nhất Phase 2.

Nó phụ thuộc vào tất cả những thứ trước:

```text
Address
Keys
Signature
Transaction
UTXOSet
```

Tạo:

```text
transaction/validation.py
```

```python
from ecdsa.errors import MalformedPointError

from crypto.address import (
    public_key_to_address,
    validate_address,
)
from crypto.keys import public_key_from_hex
from crypto.signature import verify_signature

from transaction.transaction import Transaction
from transaction.utxo import UTXOSet


def calculate_transaction_fee(
    transaction: Transaction,
    utxo_set: UTXOSet,
) -> int:

    total_input = 0

    for tx_input in transaction.inputs:
        utxo = utxo_set.get(
            tx_input.previous_tx_id,
            tx_input.output_index,
        )

        if utxo is None:
            raise ValueError(
                "Referenced UTXO does not exist"
            )

        total_input += utxo.amount

    total_output = sum(
        output.amount
        for output in transaction.outputs
    )

    return total_input - total_output


def validate_transaction(
    transaction: Transaction,
    utxo_set: UTXOSet,
) -> bool:

    # Rule 1:
    # Transaction thường phải có input.
    if not transaction.inputs:
        return False

    # Rule 2:
    # Phải tạo ít nhất một output.
    if not transaction.outputs:
        return False

    # Rule 3 + 4:
    # Kiểm tra amount và address.
    for output in transaction.outputs:

        # bool là subclass của int trong Python,
        # nên phải loại riêng.
        if (
            not isinstance(output.amount, int)
            or isinstance(output.amount, bool)
        ):
            return False

        if output.amount <= 0:
            return False

        if not validate_address(
            output.recipient_address
        ):
            return False

    seen_outpoints = set()

    total_input = 0

    for input_index, tx_input in enumerate(
        transaction.inputs
    ):

        outpoint = (
            tx_input.previous_tx_id,
            tx_input.output_index,
        )

        # Rule 5:
        # Không được dùng cùng UTXO hai lần
        # trong cùng một transaction.
        if outpoint in seen_outpoints:
            return False

        seen_outpoints.add(
            outpoint
        )

        # Rule 6:
        # UTXO phải tồn tại.
        utxo = utxo_set.get(
            *outpoint
        )

        if utxo is None:
            return False

        if (
            not tx_input.public_key
            or not tx_input.signature
        ):
            return False

        # Chuyển public key hex
        # về VerifyingKey.
        try:
            public_key = public_key_from_hex(
                tx_input.public_key
            )

            signature = bytes.fromhex(
                tx_input.signature
            )

        except (
            ValueError,
            TypeError,
            MalformedPointError,
        ):
            return False

        # Rule 7:
        # Public key phải tạo ra đúng address
        # sở hữu UTXO.
        derived_address = (
            public_key_to_address(
                public_key
            )
        )

        if (
            derived_address
            != utxo.recipient_address
        ):
            return False

        # Rule 8:
        # Signature phải hợp lệ.
        signing_bytes = (
            transaction.signing_bytes(
                input_index
            )
        )

        if not verify_signature(
            public_key,
            signing_bytes,
            signature,
        ):
            return False

        # Amount input luôn lấy từ UTXO,
        # KHÔNG lấy từ sender.
        total_input += utxo.amount

    total_output = sum(
        output.amount
        for output in transaction.outputs
    )

    # Rule 9:
    # Không được tạo coin từ không khí.
    if total_input < total_output:
        return False

    return True
```

Đây chính xác là logic:

```text
transaction
     │
     ▼
có inputs?
     │
     ▼
có outputs?
     │
     ▼
amount > 0?
     │
     ▼
address hợp lệ?
     │
     ▼
input có duplicate?
     │
     ▼
UTXO tồn tại?
     │
     ▼
public key đúng owner?
     │
     ▼
signature đúng?
     │
     ▼
input >= output?
     │
     ▼
VALID
```

Plan xác định đây là file trọng tâm của Phase 2 và validation không thể chỉ kiểm tra chữ ký. 

---

# 10. Tạo test validation

Tạo:

```text
tests/test_transaction_validation.py
```

Bản đầu tiên bạn nên viết các test quan trọng nhất:

```python
from crypto.address import public_key_to_address
from crypto.keys import (
    generate_private_key,
    get_public_key,
)

from transaction.transaction import Transaction
from transaction.tx_input import TxInput
from transaction.tx_output import TxOutput
from transaction.utxo import UTXOSet

from transaction.validation import (
    calculate_transaction_fee,
    validate_transaction,
)


def create_valid_transaction():

    alice_private = generate_private_key()
    bob_private = generate_private_key()

    alice_public = get_public_key(
        alice_private
    )

    bob_public = get_public_key(
        bob_private
    )

    alice_address = (
        public_key_to_address(
            alice_public
        )
    )

    bob_address = (
        public_key_to_address(
            bob_public
        )
    )

    utxos = UTXOSet()

    # Alice hiện sở hữu 10 PYC.
    utxos.add(
        "funding",
        0,
        TxOutput(
            amount=10,
            recipient_address=alice_address,
        ),
    )

    transaction = Transaction(
        inputs=[
            TxInput(
                previous_tx_id="funding",
                output_index=0,
            )
        ],
        outputs=[
            TxOutput(
                amount=6,
                recipient_address=bob_address,
            ),
            TxOutput(
                amount=3,
                recipient_address=alice_address,
            ),
        ],
        timestamp=1234567890,
    )

    transaction.sign_input(
        0,
        alice_private,
    )

    return (
        transaction,
        utxos,
        alice_private,
        bob_private,
    )


def test_valid_transaction():
    transaction, utxos, _, _ = (
        create_valid_transaction()
    )

    assert validate_transaction(
        transaction,
        utxos,
    )


def test_transaction_fee():
    transaction, utxos, _, _ = (
        create_valid_transaction()
    )

    assert calculate_transaction_fee(
        transaction,
        utxos,
    ) == 1


def test_wrong_owner():
    (
        transaction,
        utxos,
        _,
        bob_private,
    ) = create_valid_transaction()

    # Bob thử ký UTXO của Alice.
    transaction.sign_input(
        0,
        bob_private,
    )

    assert not validate_transaction(
        transaction,
        utxos,
    )


def test_modified_amount():
    transaction, utxos, _, _ = (
        create_valid_transaction()
    )

    # Transaction đã ký xong nhưng
    # attacker sửa amount.
    transaction.outputs[0].amount = 7

    assert not validate_transaction(
        transaction,
        utxos,
    )


def test_missing_utxo():
    transaction, _, _, _ = (
        create_valid_transaction()
    )

    empty_utxos = UTXOSet()

    assert not validate_transaction(
        transaction,
        empty_utxos,
    )


def test_output_exceeds_input():
    (
        transaction,
        utxos,
        alice_private,
        _,
    ) = create_valid_transaction()

    transaction.outputs[0].amount = 20

    # Phải ký lại để tránh fail chỉ
    # vì signature cũ.
    transaction.sign_input(
        0,
        alice_private,
    )

    assert not validate_transaction(
        transaction,
        utxos,
    )


def test_double_spend():
    transaction, utxos, _, _ = (
        create_valid_transaction()
    )

    assert validate_transaction(
        transaction,
        utxos,
    )

    # Transaction thứ nhất đã tiêu UTXO.
    utxos.apply_valid_transaction(
        transaction
    )

    # Transaction cũ cố dùng lại
    # funding:0.
    assert not validate_transaction(
        transaction,
        utxos,
    )
```

Chạy:

```powershell
python -m pytest tests/test_transaction_validation.py -v
```

Sau khi bản cơ bản pass, mới bổ sung những case còn lại trong plan như zero amount, float amount, invalid checksum, corrupted signature, duplicate input. 

---

# 11. Tạo `demo_phase2.py`

Khi tất cả module đã xong mới viết demo.

Tạo ngay root:

```text
demo_phase2.py
```

Nội dung:

```python
from crypto.address import public_key_to_address
from crypto.hash import sha256_hex
from crypto.keys import (
    generate_private_key,
    get_public_key,
)

from transaction.transaction import Transaction
from transaction.tx_input import TxInput
from transaction.tx_output import TxOutput
from transaction.utxo import UTXOSet

from transaction.validation import (
    calculate_transaction_fee,
    validate_transaction,
)


def main():

    # ========================================
    # 1. CREATE ALICE AND BOB
    # ========================================

    alice_private = generate_private_key()

    alice_public = get_public_key(
        alice_private
    )

    alice_address = public_key_to_address(
        alice_public
    )

    bob_private = generate_private_key()

    bob_public = get_public_key(
        bob_private
    )

    bob_address = public_key_to_address(
        bob_public
    )

    # ========================================
    # 2. CREATE UTXO SET
    # ========================================

    utxos = UTXOSet()

    funding_txid = sha256_hex(
        b"phase2-demo-funding"
    )

    # Giả lập Alice đã có 10 PYC.
    utxos.add(
        funding_txid,
        0,
        TxOutput(
            amount=10,
            recipient_address=alice_address,
        ),
    )

    print(
        "=== PHASE 2 - TRANSACTION DEMO ==="
    )

    print()
    print("Alice:", alice_address)
    print("Bob:  ", bob_address)

    print()
    print("=== INITIAL UTXO ===")

    print(
        "Alice balance:",
        utxos.get_balance(
            alice_address
        ),
        "PYC",
    )

    print(
        "Bob balance:",
        utxos.get_balance(
            bob_address
        ),
        "PYC",
    )

    # ========================================
    # 3. BUILD TRANSACTION
    # ========================================

    transaction = Transaction(
        inputs=[
            TxInput(
                previous_tx_id=funding_txid,
                output_index=0,
            )
        ],

        outputs=[
            # Bob nhận 6.
            TxOutput(
                amount=6,
                recipient_address=bob_address,
            ),

            # Alice nhận lại 3.
            TxOutput(
                amount=3,
                recipient_address=alice_address,
            ),
        ],
    )

    # ========================================
    # 4. SIGN
    # ========================================

    transaction.sign_input(
        0,
        alice_private,
    )

    print()
    print("=== TRANSACTION ===")

    print(
        "Input:",
        f"{funding_txid}:0",
    )

    print("6 PYC -> Bob")
    print("3 PYC -> Alice")

    print(
        "Fee:",
        calculate_transaction_fee(
            transaction,
            utxos,
        ),
        "PYC",
    )

    print(
        "Transaction ID:",
        transaction.txid(),
    )

    # ========================================
    # 5. VALIDATE
    # ========================================

    print()
    print("=== VALIDATION ===")

    valid = validate_transaction(
        transaction,
        utxos,
    )

    print(
        "Valid:",
        valid,
    )

    # ========================================
    # 6. APPLY
    # ========================================

    if valid:
        utxos.apply_valid_transaction(
            transaction
        )

    print()
    print("=== APPLY ===")

    print(
        "Alice balance:",
        utxos.get_balance(
            alice_address
        ),
        "PYC",
    )

    print(
        "Bob balance:",
        utxos.get_balance(
            bob_address
        ),
        "PYC",
    )

    # ========================================
    # 7. DOUBLE SPEND
    # ========================================

    print()
    print(
        "=== DOUBLE SPEND TEST ==="
    )

    valid_again = validate_transaction(
        transaction,
        utxos,
    )

    print(
        "Second transaction valid:",
        valid_again,
    )


if __name__ == "__main__":
    main()
```

---

# 12. Sau đó chạy toàn bộ project

Đứng ở root:

```text
Mini Blockchain/
```

chạy:

```powershell
python -m pytest -v
```

Phase 1 vẫn phải pass.

Phase 2 cũng phải pass.

Sau đó:

```powershell
python demo_phase2.py
```

Kết quả mong đợi gần như:

```text
=== PHASE 2 - TRANSACTION DEMO ===

Alice: PYC_...
Bob:   PYC_...

=== INITIAL UTXO ===
Alice balance: 10 PYC
Bob balance: 0 PYC

=== TRANSACTION ===
Input: 123abc...:0
6 PYC -> Bob
3 PYC -> Alice
Fee: 1 PYC
Transaction ID: abcdef...

=== VALIDATION ===
Valid: True

=== APPLY ===
Alice balance: 3 PYC
Bob balance: 6 PYC

=== DOUBLE SPEND TEST ===
Second transaction valid: False
```

Đây cũng chính là output cuối Phase 2 mà plan đặt ra. 

---

# Thứ tự bạn thực sự nên code

Nếu bạn đang ngồi trước VS Code và muốn **tự tay làm để hiểu**, thì đừng copy tất cả cùng lúc. Làm đúng từng bước:

```text
① crypto/keys.py
   thêm public_key_from_hex()
          ↓
   pytest test_keys.py

② transaction/__init__.py
          ↓

③ transaction/tx_output.py
          ↓
   tests/test_tx_output.py
          ↓
   pytest

④ transaction/tx_input.py
          ↓
   tests/test_tx_input.py
          ↓
   pytest

⑤ transaction/transaction.py
          ↓
   tests/test_transaction.py
          ↓
   pytest

⑥ transaction/utxo.py
          ↓
   tests/test_utxo.py
          ↓
   pytest

⑦ transaction/validation.py
          ↓
   tests/test_transaction_validation.py
          ↓
   pytest

⑧ demo_phase2.py
          ↓
   python demo_phase2.py

⑨ cuối cùng
   python -m pytest -v
```

Và khi code thủ công, tôi đặc biệt khuyên **đừng chuyển sang file tiếp theo nếu file hiện tại bạn chưa hiểu**. Dependency của Phase 2 được thiết kế để kiến thức tăng dần:

```text
TxOutput
   │
   │ "coin nằm ở đâu?"
   ▼
TxInput
   │
   │ "tiêu coin cũ thế nào?"
   ▼
Transaction
   │
   │ "chuyển coin thế nào?"
   ▼
UTXOSet
   │
   │ "state tiền hiện tại là gì?"
   ▼
Validation
   │
   │ "làm sao biết giao dịch hợp lệ?"
   ▼
Double-spend prevention
```

Nếu học theo cách này thì **file bạn nên bắt đầu viết ngay bây giờ là `transaction/tx_output.py`**, sau khi thêm helper `public_key_from_hex()` vào `crypto/keys.py`.
