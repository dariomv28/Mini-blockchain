Được. Với Phase 2, đừng vội nhìn vào `TxInput`, `UTXOSet`, `sign_transaction()` hay code. Bạn chỉ cần hiểu **một câu hỏi lớn**:

> **Trong blockchain kiểu Bitcoin, làm thế nào Alice chứng minh rằng cô ấy có coin và chuyển một phần coin đó cho Bob mà không thể tiêu cùng số coin hai lần?**

Toàn bộ Phase 2 được xây để trả lời câu hỏi đó. `phase2_plan.md` cũng giới hạn Phase 2 ở Transaction, TxInput/TxOutput, UTXO, chữ ký, validation, fee và chống double-spend; chưa có block, mining hay mempool. 

## 1. Trước tiên: Bitcoin-like blockchain không lưu `balance`

Đây là kiến thức quan trọng nhất.

Bạn có thể tưởng tượng hệ thống ngân hàng kiểu:

```text
Alice.balance = 10
Bob.balance   = 0
```

Alice gửi Bob 6:

```text
Alice.balance -= 6
Bob.balance   += 6
```

Đây gần với **account model**.

Nhưng project của bạn đang xây theo **UTXO model**. `phase2_plan.md` cũng yêu cầu không tạo bảng balance trực tiếp; balance phải suy ra từ UTXO Set. 

Nó không nói:

```text
Alice có balance = 10
```

mà nói:

```text
Có một output chưa tiêu trị giá 10 PYC
và output đó thuộc Alice.
```

Ví dụ:

```text
TX100
└── output[0]
    ├── amount = 10
    └── owner  = Alice
```

Output này chưa được tiêu nên gọi là:

```text
UTXO
=
Unspent Transaction Output
```

---

# 2. Transaction Output là gì?

Một transaction tạo ra các **output**.

Output cực kỳ đơn giản:

```text
TxOutput
├── amount
└── recipient_address
```

Ví dụ:

```text
TxOutput
├── amount = 10 PYC
└── address = Alice
```

Nghĩa là:

> Có 10 PYC mà người sở hữu address của Alice có quyền tiêu.

Bạn có thể tưởng tượng `TxOutput` như một **tờ tiền blockchain**.

Ví dụ Alice có:

```text
UTXO A = 3 PYC
UTXO B = 7 PYC
UTXO C = 2 PYC
```

Balance của Alice được tính:

```text
3 + 7 + 2 = 12 PYC
```

Chứ blockchain không cần:

```python
alice.balance = 12
```

Đây chính là cách `UTXO Set` được dùng để tính balance. 

---

# 3. Transaction Input là gì?

Đây là chỗ thường gây nhầm.

`TxInput` **không chứa coin**.

Nó chỉ nói:

> Tôi muốn tiêu một `TxOutput` cũ.

Ví dụ Alice có:

```text
TX100 output[0]
10 PYC → Alice
```

Muốn tiêu nó, transaction mới tạo:

```text
TxInput
├── previous_tx_id = TX100
└── output_index   = 0
```

Hai thông tin:

```text
TX100
0
```

xác định chính xác:

```text
TX100:0
```

tức:

```text
Transaction TX100
└── output số 0
```

Cho nên hãy nhớ:

```text
TxOutput = coin được tạo ra

TxInput = tham chiếu tới TxOutput cũ
          để tiêu nó
```

Đây cũng là một trong các câu hỏi kiến thức bắt buộc của Phase 2 trong plan. 

---

# 4. Tại sao input không có `amount`?

Giả sử hacker tạo:

```python
TxInput(
    previous_tx_id="TX100",
    output_index=0,
    amount=1_000_000
)
```

Nếu node tin `amount` mà sender khai thì blockchain chết ngay.

Node phải tự tra:

```text
TX100:0
     │
     ▼
UTXO Set
     │
     ▼
amount = 10
owner = Alice
```

Cho nên:

```text
TxInput
```

chỉ cần nói:

```text
Tôi muốn tiêu TX100:0
```

Node tự biết nó trị giá bao nhiêu từ UTXO Set.

Đây là nguyên tắc rất quan trọng:

> **Không tin dữ liệu tài chính do người gửi tự khai. Node phải tự derive nó từ blockchain state.**

`phase2_plan.md` cũng quy định rõ input amount phải lấy từ referenced UTXO. 

---

# 5. Alice gửi 6 PYC từ UTXO 10 PYC như thế nào?

Giả sử Alice có:

```text
TX100:0
10 PYC → Alice
```

Alice muốn:

```text
6 PYC → Bob
```

Không thể chỉ tiêu:

```text
6/10
```

của UTXO.

UTXO phải được tiêu **toàn bộ**.

Transaction mới:

```text
Transaction TX200

Input:
    TX100:0
    trị giá 10 PYC

Outputs:
    output[0] = 6 PYC → Bob
    output[1] = 4 PYC → Alice
```

Nhìn như:

```text
       10 PYC của Alice
              │
              ▼
        ┌───────────┐
        │ TX200     │
        └─────┬─────┘
              │
       ┌──────┴──────┐
       ▼             ▼
   Bob: 6        Alice: 4
```

4 PYC trả lại Alice gọi là:

```text
change
```

Tương tự bạn có tờ:

```text
100.000đ
```

mua món:

```text
60.000đ
```

thì:

```text
100.000
   ↓
60.000 → cửa hàng
40.000 → tiền thối
```

---

# 6. Nhưng làm sao biết người tiêu TX100:0 thật sự là Alice?

Đây là nơi Phase 1 được nối vào Phase 2.

Phase 1 bạn đã học:

```text
Private Key
     ↓
Public Key
     ↓
Address
```

và:

```text
Private Key
     ↓
Sign
     ↓
Signature

Public Key
     ↓
Verify
```

Phase 2 sử dụng chính kiến thức đó.

Alice tạo transaction:

```text
Input: TX100:0
Outputs:
    6 → Bob
    4 → Alice
```

Sau đó Alice ký bằng:

```text
Alice private key
```

TxInput cuối cùng có dạng:

```text
TxInput
├── previous_tx_id
├── output_index
├── public_key
└── signature
```

Node nhận transaction sẽ kiểm tra hai chuyện khác nhau.

### Kiểm tra 1: Public key này có phải owner không?

Node tính:

```text
public_key
    ↓
public_key_to_address()
    ↓
PYC_xxx
```

rồi so sánh với:

```text
recipient_address
```

trong UTXO cũ.

Nếu:

```text
address(public_key)
==
owner của UTXO
```

thì đúng public key.

### Kiểm tra 2: Người gửi có private key tương ứng không?

Node dùng:

```text
public key
+
signature
+
transaction data
```

để:

```text
verify_signature(...)
```

Nếu đúng:

```text
True
```

thì người gửi chứng minh rằng họ đang giữ private key tương ứng.

Vì vậy:

```text
Public key
```

trả lời:

> Coin này thuộc về key nào?

Còn:

```text
Signature
```

trả lời:

> Người đang yêu cầu tiêu coin có thực sự giữ private key không?

---

# 7. Tại sao chỉ ghi `sender = Alice` là không đủ?

Giả sử transaction là:

```text
sender = Alice
receiver = Bob
amount = 10
```

Hacker hoàn toàn có thể tự viết:

```text
sender = Alice
```

Chuỗi `"Alice"` chẳng chứng minh gì cả.

Ngay cả address:

```text
sender = PYC_abc123...
```

cũng không đủ.

Ai cũng biết address của Alice.

Blockchain cần:

```text
public key tạo đúng Alice address
+
signature hợp lệ
```

thì mới chứng minh quyền tiêu coin. Đây cũng là rule cụ thể trong plan. 

---

# 8. Signing payload là gì?

Đây là khái niệm hơi kỹ thuật nhưng rất quan trọng.

Alice có transaction:

```text
Input:
    TX100:0

Outputs:
    Bob   6
    Alice 4
```

Alice cần ký **nội dung transaction**.

Có thể tưởng tượng:

```text
Transaction data
      ↓
serialize
      ↓
hash
      ↓
ECDSA sign(private_key)
      ↓
signature
```

Nhưng có một vấn đề.

Nếu signature nằm bên trong transaction:

```text
Transaction
├── input
│   └── signature
└── outputs
```

thì bạn không thể nói:

```text
ký toàn bộ transaction bao gồm signature
```

vì:

```text
muốn tạo signature
→ cần transaction

nhưng transaction lại cần signature
→ mới hoàn chỉnh
```

Thành vòng lặp.

Cho nên có hai representation:

```text
Signing payload
```

không chứa signature.

Ví dụ:

```text
{
    input: TX100:0,
    outputs: [
        Bob: 6,
        Alice: 4
    ]
}
```

Alice ký payload này.

Sau đó mới gắn signature:

```text
Final Transaction
├── input
│   ├── TX100:0
│   ├── public_key
│   └── signature
│
└── outputs
    ├── Bob: 6
    └── Alice: 4
```

Đây là lý do plan yêu cầu **signing payload khác final transaction serialization**. 

---

# 9. Transaction ID — `txid` là gì?

Mỗi transaction cần một định danh duy nhất.

Ví dụ:

```text
TX200
```

thực tế sẽ là hash kiểu:

```text
7f31c8a9...
```

Ta lấy:

```text
final transaction
      ↓
serialize
      ↓
SHA-256
      ↓
txid
```

Nên:

```text
txid = hash(transaction)
```

Nếu thay:

```text
Bob nhận 6
```

thành:

```text
Bob nhận 7
```

serialized data thay đổi → hash thay đổi → txid thay đổi.

Về sau TxInput dùng txid này để tham chiếu:

```text
previous_tx_id = 7f31c8a9...
output_index = 0
```

---

# 10. UTXO Set là gì?

Blockchain về sau chứa rất nhiều transaction.

Giả sử:

```text
TX1 output[0] → Alice 5
TX2 output[0] → Bob   7
TX3 output[1] → Alice 3
TX4 output[0] → Carol 9
```

Nhưng một số đã tiêu.

Node chỉ cần giữ tập các output **chưa tiêu**:

```text
UTXO_SET

(TX1, 0) → Alice 5
(TX3, 1) → Alice 3
(TX4, 0) → Carol 9
```

Balance Alice:

```text
5 + 3
= 8
```

`phase2_plan.md` xác định UTXO bằng cặp `(txid, output_index)`. 

---

# 11. Khi transaction thành công, UTXO Set thay đổi thế nào?

Trước:

```text
UTXO SET

TX100:0 → Alice 10
```

Alice tạo:

```text
TX200

Input:
TX100:0

Outputs:
0 → Bob 6
1 → Alice 4
```

Khi transaction được apply:

```text
REMOVE
TX100:0
```

và:

```text
ADD
TX200:0 → Bob 6
TX200:1 → Alice 4
```

Sau đó:

```text
UTXO SET

TX200:0 → Bob   6
TX200:1 → Alice 4
```

Đây gần như là **state transition** cốt lõi của UTXO blockchain:

```text
State cũ
    ↓
Transaction
    ↓
State mới
```

---

# 12. Double-spend là gì?

Giả sử Alice chỉ có:

```text
TX100:0 → 10 PYC
```

Alice tạo Transaction A:

```text
TX100:0
    ↓
10 → Bob
```

Sau đó Alice lại tạo Transaction B:

```text
TX100:0
    ↓
10 → Carol
```

Cả hai đều muốn tiêu:

```text
TX100:0
```

Đó là:

```text
double-spend
```

Sau khi Transaction A được apply:

```text
TX100:0
```

đã bị xóa khỏi UTXO Set.

Khi Transaction B tới:

```text
lookup TX100:0
       ↓
NOT FOUND
       ↓
REJECT
```

Đó là cách UTXO Set giúp ngăn việc tiêu cùng một output hai lần ở state hiện tại. Plan cũng đặt đây là một yêu cầu bắt buộc của Phase 2. 

---

# 13. Transaction validation thực chất kiểm tra cái gì?

Đây là trung tâm Phase 2.

Node nhận:

```text
Transaction
```

và hỏi:

```text
1. Có input không?
        ↓
2. Có output không?
        ↓
3. Amount output > 0?
        ↓
4. Address hợp lệ?
        ↓
5. Input có bị lặp không?
        ↓
6. UTXO input tham chiếu có tồn tại?
        ↓
7. Public key có sở hữu UTXO đó?
        ↓
8. Signature đúng?
        ↓
9. Tổng input >= tổng output?
        ↓
10. PASS
```

Đây chính là nhóm validation rules được liệt kê trong Definition of Done của plan. 

---

# 14. Transaction fee từ đâu ra?

Ví dụ Alice tiêu:

```text
Input:
10 PYC
```

nhưng tạo:

```text
Output:
6 → Bob
3 → Alice
```

Tổng output:

```text
6 + 3 = 9
```

Input:

```text
10
```

Chênh lệch:

```text
10 - 9 = 1
```

Vậy:

```text
fee = 1 PYC
```

Công thức:

```text
fee =
sum(input values)
-
sum(output values)
```

Phase 2 chỉ cần **tính được fee**.

Chưa cần đưa 1 PYC đó cho miner, vì mining/coinbase thuộc phase sau. Điều này được ghi rõ trong plan. 

---

# 15. Toàn bộ Phase 2 thực ra chỉ là câu chuyện này

Bạn hãy nhớ duy nhất sơ đồ này:

```text
Alice hiện sở hữu

TX100:0
10 PYC
   │
   │
   │ Alice muốn tiêu
   ▼
TxInput
TX100:0
   │
   ▼
Transaction
├── Input:
│   └── TX100:0
│
└── Outputs:
    ├── Bob   6
    └── Alice 3
         +
       fee 1

Alice dùng private key
        │
        ▼
     Signature
        │
        ▼
Transaction hoàn chỉnh
        │
        ▼
Node validate
├── UTXO tồn tại?
├── đúng owner?
├── signature đúng?
├── input >= output?
└── chưa double-spend?
        │
       PASS
        ▼
Update UTXO Set
        │
        ├── remove TX100:0
        │
        ├── add TX200:0 → Bob 6
        └── add TX200:1 → Alice 3
```

Đây chính xác là luồng mà `phase2_plan.md` muốn bạn hiểu trước khi sang Phase 3. 

## 16. Liên hệ Phase 1 → Phase 2

Phase 1 bạn đã xây các **công cụ mật mã**:

```text
SHA-256
Private Key
Public Key
Address
ECDSA Signature
Serialization
```

Phase 2 bắt đầu sử dụng các công cụ đó vào một bài toán thực tế:

```text
PHASE 1
Crypto primitives
        │
        ▼
PHASE 2
Ai sở hữu coin?
        +
Làm sao tiêu coin?
        +
Làm sao chuyển coin?
        +
Làm sao chứng minh quyền tiêu?
        +
Làm sao chống tiêu hai lần?
```

Nên nếu nói cực ngắn:

```text
Phase 1 = Identity + Cryptography

Phase 2 = Money ownership + Money transfer
```

Và hiện tại **chưa cần học Block, Merkle Tree, Proof of Work hay Mining**. Chúng nằm ngoài scope Phase 2. 

Nếu bạn nắm chắc 6 khái niệm sau thì mới bắt đầu code Phase 2 là hợp lý:

```text
1. TxOutput
2. UTXO
3. TxInput
4. Transaction
5. Signature / ownership
6. UTXO Set + validation
```

Trong đó **TxOutput → UTXO → TxInput** là chuỗi quan trọng nhất. Nếu phần này vẫn mơ hồ, thì chưa cần học các phần còn lại.
