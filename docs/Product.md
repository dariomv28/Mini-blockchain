Sau khi xây xong theo kiến trúc trên, blockchain của bạn sẽ không chỉ là demo “nối các block bằng hash”, mà sẽ là một **mạng tiền mã hóa mini hoạt động end-to-end**.

Cụ thể, nó sẽ làm được các chức năng chính sau:

* **Tạo ví**: sinh private key, public key, address.
* **Gửi coin giữa các ví**: Alice gửi Bob 10 coin bằng transaction có chữ ký số.
* **Xác minh quyền sở hữu**: node kiểm tra chữ ký và UTXO trước khi chấp nhận transaction.
* **Ngăn double-spend**: một UTXO đã tiêu thì không thể tiêu lần hai.
* **Tính balance**: số dư được suy ra từ UTXO set.
* **Mempool**: giữ các transaction hợp lệ nhưng chưa được đưa vào block.
* **Mining**: miner gom transaction, tạo block mới và chạy Proof of Work.
* **Block reward + transaction fee**: miner nhận coinbase reward và phí giao dịch.
* **Blockchain persistence**: block và chain state được lưu xuống database, restart node không mất dữ liệu.
* **Nhiều node chạy độc lập**: ví dụ Node A, B, C trên các port khác nhau.
* **Broadcast transaction**: một transaction được gửi từ node này sang toàn mạng.
* **Broadcast block**: block mới được lan truyền sang các node khác.
* **Đồng bộ blockchain**: node offline quay lại có thể tải các block còn thiếu.
* **Fork handling**: nếu hai miner tạo block cùng lúc, mạng xử lý hai nhánh.
* **Chain reorganization**: node có thể chuyển sang chain có cumulative work lớn hơn.
* **API/RPC**: bạn có thể query block, transaction, balance, mempool bằng HTTP.
* **Blockchain Explorer**: xem block, transaction, hash, nonce, difficulty, address balance qua giao diện web.

Ví dụ sau khi hoàn thiện, bạn có thể chạy 3 node:

```bash
python node.py --port 5001
python node.py --port 5002
python node.py --port 5003
```

Tạo hai ví:

```text
Alice
address = PY_A...

Bob
address = PY_B...
```

Alice gửi:

```text
Alice → Bob : 10 PYC
```

Node A nhận transaction, validate rồi broadcast:

```text
Alice Wallet
     │
     ▼
Transaction
     │
     ▼
Node A
     │
     ├────→ Node B
     │
     └────→ Node C
```

Sau đó miner tạo block:

```text
Block #42
├── previous_hash
├── merkle_root
├── timestamp
├── difficulty
├── nonce
│
└── transactions
     ├── Coinbase → Miner
     └── Alice → Bob : 10 PYC
```

Các node xác minh block và cập nhật state:

```text
Node A        Node B        Node C
  │             │             │
  └────── same blockchain ─────┘
```

Bob kiểm tra:

```bash
pychain balance PY_B...
```

và thấy:

```text
Balance: 10 PYC
```

Nói ngắn gọn, blockchain của bạn lúc đó sẽ là một **cryptocurrency blockchain mini kiểu Bitcoin**, có đủ:

```text
Wallet
   +
Transactions
   +
Digital signatures
   +
UTXO
   +
Blocks
   +
Merkle Tree
   +
Proof of Work
   +
Mining
   +
Mempool
   +
P2P Network
   +
Consensus
   +
Fork/Reorg
   +
Database
   +
API
   +
Explorer
```

Điều nó **chưa có** nếu chỉ làm theo scope này là smart contract kiểu Ethereum. Nếu muốn, sau khi hoàn thành core blockchain, bạn có thể nâng cấp thêm một **VM + smart contract layer**, lúc đó blockchain của bạn sẽ tiến gần mô hình Ethereum hơn thay vì chỉ là Bitcoin-like.
