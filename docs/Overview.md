Nếu mục tiêu của bạn là **hiểu sâu cấu trúc bên trong blockchain**, tôi khuyên đừng bắt đầu bằng smart contract hay Ethereum clone. Hãy tự xây một **Bitcoin-like blockchain bằng Python**, dùng **UTXO + Proof of Work + P2P**, nhưng đơn giản hóa vừa đủ để bạn có thể tự viết gần như toàn bộ hệ thống.

Mục tiêu cuối cùng sẽ là một hệ thống kiểu:

```text
                 ┌───────────────┐
                 │    Wallet     │
                 │ key / address │
                 └───────┬───────┘
                         │ create tx
                         ▼
┌─────────────────────────────────────────┐
│                 NODE                    │
│                                         │
│   ┌─────────────┐     ┌─────────────┐  │
│   │   Mempool   │────▶│ Block Miner │  │
│   └─────────────┘     └──────┬──────┘  │
│                               │         │
│                               ▼         │
│   ┌─────────────┐     ┌─────────────┐  │
│   │ Blockchain  │◀────│ Validation  │  │
│   └──────┬──────┘     └─────────────┘  │
│          │                              │
│          ▼                              │
│   ┌─────────────┐                       │
│   │  UTXO Set   │                       │
│   └─────────────┘                       │
│                                         │
│   ┌─────────────────────────────────┐   │
│   │            P2P Network          │   │
│   └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
             │                 │
             ▼                 ▼
          Node B            Node C
```

## 1. Kiến trúc tôi recommend

Project nên chia như sau:

```text
pychain/
│
├── blockchain/
│   ├── block.py
│   ├── blockchain.py
│   ├── genesis.py
│   └── validation.py
│
├── transaction/
│   ├── transaction.py
│   ├── tx_input.py
│   ├── tx_output.py
│   ├── utxo.py
│   └── mempool.py
│
├── crypto/
│   ├── hash.py
│   ├── keys.py
│   ├── signature.py
│   └── address.py
│
├── consensus/
│   ├── pow.py
│   ├── difficulty.py
│   └── fork_choice.py
│
├── network/
│   ├── node.py
│   ├── peer.py
│   ├── protocol.py
│   └── messages.py
│
├── storage/
│   ├── block_store.py
│   ├── chainstate.py
│   └── database.py
│
├── wallet/
│   ├── wallet.py
│   └── wallet_store.py
│
├── mining/
│   ├── miner.py
│   └── block_template.py
│
├── api/
│   ├── rpc.py
│   └── server.py
│
├── cli/
│   └── main.py
│
├── tests/
│
└── main.py
```

Điểm quan trọng là **không nhét mọi thứ vào `blockchain.py`**. Blockchain thực tế là tổ hợp của nhiều subsystem.

---

# 2. Crypto layer

Đây là tầng thấp nhất.

Bạn cần:

```text
SHA-256
Private Key
Public Key
Digital Signature
Address
```

Ví dụ:

```text
Private key
    ↓
Elliptic Curve
    ↓
Public key
    ↓
Hash
    ↓
Blockchain address
```

Transaction được ký:

```text
Transaction
     │
     ▼
   SHA256
     │
     ▼
transaction hash
     │
     ▼
Sign(private_key)
     │
     ▼
digital signature
```

Sau đó node khác dùng:

```text
verify(
    public_key,
    transaction_hash,
    signature
)
```

Nếu muốn Bitcoin-like thì dùng:

```text
ECDSA
secp256k1
SHA-256
```

Bạn **không nên tự implement elliptic-curve cryptography** ở project này. Viết logic blockchain, nhưng crypto primitive nên dùng thư viện đã kiểm chứng.

---

# 3. Transaction model

Tôi recommend dùng **UTXO**, vì nó buộc bạn phải hiểu blockchain sâu hơn account model.

Một transaction:

```text
Transaction
├── version
├── inputs[]
├── outputs[]
└── timestamp
```

Input:

```python
class TxInput:
    previous_tx_id
    output_index
    public_key
    signature
```

Output:

```python
class TxOutput:
    amount
    recipient_address
```

Ví dụ Alice có UTXO:

```text
TX A
output[0]
10 coin
owner = Alice
```

Alice muốn gửi Bob 6 coin.

Transaction mới:

```text
Input:
    TX A output[0]

Outputs:
    6 coin → Bob
    4 coin → Alice
```

Tức là:

```text
        previous UTXO
             │
             ▼
         10 coins
             │
             ▼
       ┌───────────┐
       │Transaction│
       └─────┬─────┘
             │
       ┌─────┴─────┐
       ▼           ▼
   Bob: 6       Alice: 4
```

Đây là concept rất quan trọng.

---

# 4. UTXO Set

Blockchain chứa toàn bộ lịch sử.

Nhưng node không nên scan toàn bộ blockchain mỗi lần kiểm tra balance.

Bạn duy trì:

```python
UTXO_SET = {
    (txid, output_index): TxOutput(...)
}
```

Ví dụ:

```text
UTXO Set

a82f...:0 → 5 BTC → Alice
8bc3...:1 → 2 BTC → Bob
193a...:0 → 8 BTC → Alice
```

Balance Alice:

```text
5 + 8 = 13
```

Khi transaction tiêu một output:

```text
remove old UTXO
add new UTXOs
```

---

# 5. Transaction validation

Đây là một trong những module quan trọng nhất.

Node phải kiểm tra:

```text
input UTXO tồn tại?
        │
        ▼
signature hợp lệ?
        │
        ▼
public key có thực sự sở hữu UTXO?
        │
        ▼
input amount >= output amount?
        │
        ▼
transaction chưa double-spend?
```

Transaction fee:

```text
fee =
sum(inputs)
-
sum(outputs)
```

Ví dụ:

```text
Input  = 10
Output = 9.8

Fee = 0.2
```

Miner nhận phần này.

---

# 6. Mempool

Transaction hợp lệ chưa lập tức vào blockchain.

Nó đi:

```text
Wallet
   │
   ▼
Transaction
   │
   ▼
Node
   │
validate
   ▼
Mempool
```

Mempool đơn giản:

```python
class Mempool:
    transactions: dict[str, Transaction]
```

Bạn nên có:

```python
add_transaction()
remove_transaction()
has_transaction()
get_transactions()
```

Sau này miner lấy transaction từ đây.

---

# 7. Block

Một block nên có:

```text
Block
├── header
│   ├── version
│   ├── previous_block_hash
│   ├── merkle_root
│   ├── timestamp
│   ├── difficulty
│   └── nonce
│
└── transactions[]
```

Ví dụ chain:

```text
Genesis
   │
   ▼
Block 1
   │
   ▼
Block 2
   │
   ▼
Block 3
```

Block 3:

```text
previous_hash = hash(Block 2)
```

Nếu sửa Block 2:

```text
hash(Block 2)
```

thay đổi.

Block 3 lập tức không còn hợp lệ.

---

# 8. Merkle Tree

Đây là thứ tôi rất khuyên bạn tự implement.

Ví dụ:

```text
         ROOT
        /    \
      H12    H34
     /  \    /  \
   H1   H2 H3   H4
```

Trong đó:

```text
H1 = SHA256(tx1)
H2 = SHA256(tx2)

H12 = SHA256(H1 || H2)
```

Cuối cùng:

```text
Merkle Root
```

được ghi vào block header.

Bạn sẽ hiểu được tại sao blockchain có thể chứng minh transaction nằm trong block mà không cần đưa toàn bộ block.

---

# 9. Proof of Work

Đây là consensus đầu tiên bạn nên implement.

Miner tìm:

```text
nonce
```

sao cho:

```text
SHA256(block_header) < target
```

Ví dụ đơn giản hóa:

```text
hash phải bắt đầu bằng:

0000
```

Pseudo-code:

```python
nonce = 0

while True:
    block.nonce = nonce

    h = block.hash()

    if h.startswith("0000"):
        break

    nonce += 1
```

Tất nhiên bản chuẩn nên dùng:

```text
hash < target
```

thay vì đếm zero.

---

# 10. Difficulty

Target càng nhỏ:

```text
mining càng khó
```

Ví dụ:

```text
target =
2^256 / difficulty
```

Bạn có thể đặt mục tiêu:

```text
1 block / 10 seconds
```

và cứ:

```text
10 blocks
```

thì điều chỉnh difficulty.

Ví dụ:

```text
Expected:

10 blocks × 10 sec
= 100 sec

Actual:
50 sec
```

Blockchain đang chạy quá nhanh.

→ tăng difficulty.

---

# 11. Coinbase transaction

Block đầu tiên phải có transaction đặc biệt:

```text
coinbase transaction
```

Không có input.

Ví dụ:

```text
Input:
    NONE

Output:
    50 coins → miner
```

Miner reward:

```text
block subsidy
+
transaction fees
```

Ví dụ:

```text
50
+
0.1
+
0.2
+
0.05

= 50.35 coins
```

---

# 12. Blockchain validation

Khi nhận block:

```text
Receive block
     │
     ▼
Check previous hash
     │
     ▼
Check PoW
     │
     ▼
Check timestamp
     │
     ▼
Check Merkle root
     │
     ▼
Validate transactions
     │
     ▼
Check coinbase
     │
     ▼
Update UTXO
```

Một block chỉ được commit nếu **tất cả validation đều pass**.

---

# 13. Fork

Đây là phần rất quan trọng nếu bạn muốn blockchain thật sự có nhiều node.

Có thể xảy ra:

```text
        Block 10
        /      \
 Block 11A    Block 11B
```

Sau đó:

```text
        Block 10
        /      \
 Block 11A    Block 11B
     │
 Block 12A
```

Chain A có cumulative work cao hơn.

Node chuyển sang:

```text
Block 10
↓
Block 11A
↓
Block 12A
```

Không nên implement đơn giản kiểu:

```text
longest chain
```

mà nên lưu:

```text
cumulative_work
```

rồi chọn:

```text
chain có accumulated PoW cao nhất
```

---

# 14. Storage

Đừng giữ blockchain chỉ trong RAM.

Bạn cần ít nhất:

```text
blocks database
chainstate / UTXO database
metadata
```

Có thể bắt đầu với SQLite:

```text
blocks
------
hash
height
previous_hash
data

utxos
------
txid
output_index
amount
address

metadata
--------
best_block
height
difficulty
```

Sau này có thể dùng:

```text
LevelDB
```

giống cách các blockchain database thường hoạt động.

---

# 15. P2P Network

Đây là bước biến project từ:

```text
blockchain toy
```

thành:

```text
distributed blockchain
```

Bạn chạy:

```text
Node A
Node B
Node C
```

trên các port:

```text
5001
5002
5003
```

Ví dụ:

```text
        Node A
       /      \
    Node B ── Node C
```

Các message:

```text
VERSION
PEERS
NEW_TRANSACTION
NEW_BLOCK
GET_BLOCK
BLOCK
GET_HEADERS
HEADERS
```

Ví dụ Alice gửi transaction:

```text
Wallet
 │
 ▼
Node A
 │
 ├────────→ Node B
 │
 └────────→ Node C
```

Các node validate độc lập.

---

# 16. Block synchronization

Giả sử Node C offline.

```text
Node A

height = 100
```

Node C:

```text
height = 70
```

C reconnect.

Nó hỏi:

```text
GET_HEADERS
```

A trả:

```text
71
72
73
...
100
```

C tải các blocks còn thiếu.

Đây là lúc bạn thực sự hiểu:

```text
blockchain synchronization
```

hoạt động như thế nào.

---

# 17. Node architecture

Cuối cùng `Node` của bạn sẽ gần như:

```python
class Node:

    blockchain

    mempool

    utxo_set

    peer_manager

    miner

    database

    wallet

    def receive_transaction():
        ...

    def receive_block():
        ...

    def broadcast_transaction():
        ...

    def broadcast_block():
        ...

    def sync_chain():
        ...
```

Conceptually:

```text
              NODE
 ┌─────────────────────────────┐
 │                             │
 │ P2P ──────► Transaction     │
 │               │             │
 │               ▼             │
 │           Validation        │
 │               │             │
 │               ▼             │
 │            Mempool          │
 │               │             │
 │               ▼             │
 │             Miner           │
 │               │             │
 │               ▼             │
 │             Block           │
 │               │             │
 │               ▼             │
 │          Blockchain         │
 │               │             │
 │               ▼             │
 │            UTXO DB          │
 │                             │
 └─────────────────────────────┘
```

---

# 18. Wallet

Wallet không phải chỉ là balance.

Bạn nên implement:

```text
Wallet
├── private_key
├── public_key
├── address
├── UTXOs
└── transaction builder
```

Command:

```bash
python wallet.py new
```

trả:

```text
Private key:
...

Public key:
...

Address:
PY1A8CX....
```

Sau đó:

```bash
python wallet.py balance
```

và:

```bash
python wallet.py send \
    --to PYxxxx \
    --amount 5
```

---

# 19. RPC/API

Sau khi node hoạt động, thêm HTTP API.

Ví dụ:

```text
GET /blocks

GET /block/{hash}

GET /transaction/{txid}

GET /balance/{address}

GET /mempool

POST /transaction
```

Dùng:

```text
FastAPI
```

là hợp lý.

Bạn có thể truy cập:

```text
localhost:8000/block/...
```

và xem blockchain của mình.

---

# 20. Blockchain explorer

Sau đó làm một UI nhỏ:

```text
PyChain Explorer

Latest Block
Height: 183

Hash:
00000392a8...

Transactions:
12

Difficulty:
18342
```

và:

```text
Block #183

Previous:
00005...

Merkle root:
9a21...

Nonce:
1294832

Transactions:
 ├── tx1
 ├── tx2
 └── tx3
```

Đến đây project nhìn đã rất giống một blockchain thực sự.

---

# Roadmap tôi khuyên bạn thực hiện

Đừng code tất cả một lần. Làm theo dependency:

```text
PHASE 1
Cryptography
    ↓
keys
address
signature
hash

PHASE 2
Transaction
    ↓
input
output
UTXO
signature validation

PHASE 3
Block
    ↓
block header
block hash
Merkle tree

PHASE 4
Blockchain
    ↓
genesis
chain
block validation

PHASE 5
Proof of Work
    ↓
mining
difficulty
coinbase

PHASE 6
UTXO State
    ↓
balance
transaction validation
double-spend prevention

PHASE 7
Mempool
    ↓
transaction pool
fee
selection

PHASE 8
Persistence
    ↓
SQLite / LevelDB

PHASE 9
P2P
    ↓
nodes
peer discovery
broadcast transaction
broadcast block

PHASE 10
Consensus
    ↓
fork
reorganization
cumulative work

PHASE 11
Wallet
    ↓
send
receive
balance

PHASE 12
RPC/API
    ↓
FastAPI

PHASE 13
Explorer

PHASE 14
Testing
    ↓
multiple nodes
fork
double spend
invalid transaction
invalid block
chain synchronization
```

## Sau khi hoàn thành, project của bạn sẽ có luồng đầy đủ

Ví dụ Alice gửi Bob 10 coin:

```text
Alice Wallet
     │
     │ create transaction
     ▼
select UTXO
     │
     ▼
sign transaction
     │
     ▼
Node A
     │
     ▼
validate
     │
     ▼
mempool
     │
     ├──────────────► Node B
     └──────────────► Node C
                         │
                         ▼
                      mempool
```

Miner:

```text
mempool
   │
   ▼
create candidate block
   │
   ▼
Merkle root
   │
   ▼
Proof of Work
   │
   ▼
new block
```

Broadcast:

```text
             Miner
               │
        new block found
               │
       ┌───────┴───────┐
       ▼               ▼
    Node B           Node C
       │               │
    validate         validate
       │               │
       ▼               ▼
   update UTXO      update UTXO
```

Bob:

```text
Bob address
     │
     ▼
UTXO Set
     │
     ▼
balance += 10
```

Đây mới thực sự là **end-to-end blockchain**.

## Tôi khuyên scope phiên bản đầu tiên

Bạn **chưa cần** đưa vào:

```text
Smart contracts
EVM
Proof of Stake
Sharding
Zero Knowledge Proof
Lightning
SegWit
HD Wallet
SPV
Script VM
```

Nếu đưa tất cả ngay từ đầu, project sẽ trở nên quá lớn.

Phiên bản đầu tiên nên có chính xác:

```text
SHA256
ECDSA secp256k1

Wallet
Address

Transaction
UTXO
Transaction signature
Transaction fees

Merkle tree

Block
Genesis block

Proof of Work
Difficulty adjustment

Coinbase transaction
Block reward

Mempool

Blockchain validation

SQLite persistence

P2P networking

Block propagation
Transaction propagation

Chain synchronization

Fork handling
Chain reorganization

CLI

HTTP RPC API

Blockchain explorer
```

Nếu bạn tự xây được **toàn bộ bộ này**, bạn sẽ hiểu phần lớn kiến trúc kỹ thuật cốt lõi của Bitcoin-style blockchain, thay vì chỉ biết khái niệm `block → hash → chain`.

Tôi recommend đặt tên project kiểu **PyChain** và xây theo 14 phase trên. Với hướng học của bạn, bước tiếp theo hợp lý nhất là tôi lập hẳn cho bạn **roadmap Phase 1 → Phase 14 cực chi tiết**, trong mỗi phase ghi rõ **lý thuyết phải hiểu → file cần tạo → class/function cần implement → test phải pass → output mong đợi**, để bạn có thể bắt đầu code từ Phase 1 mà không bị mơ hồ.
