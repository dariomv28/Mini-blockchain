"""Pending parent/child transfers, fee selection and partial confirmation."""

from ecdsa import SECP256k1, SigningKey

from blockchain.block import Block
from blockchain.blockchain import Blockchain
from blockchain.genesis import GENESIS_TIMESTAMP
from crypto.address import public_key_to_address
from mining.miner import mine_block
from transaction.transaction import Transaction
from transaction.tx_input import TxInput
from transaction.tx_output import TxOutput


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def mine(template: Block) -> Block:
    result = mine_block(template, max_nonce=100_000)
    if result is None:
        raise RuntimeError("Demo nonce range exhausted")
    return result


def main() -> None:
    # Public fixed keys are for this educational demo only, never real funds.
    keys = [SigningKey.from_secret_exponent(n, curve=SECP256k1)
            for n in (201, 202, 203, 204)]
    alice, bob, carol, miner = [
        public_key_to_address(key.get_verifying_key()) for key in keys
    ]
    now = GENESIS_TIMESTAMP + 100
    chain = Blockchain()
    funding = mine(chain.create_block_template(
        alice, timestamp=GENESIS_TIMESTAMP + 1
    ))
    require(chain.add_block(funding, current_time=now), "Funding rejected")

    parent = Transaction(
        inputs=[TxInput(funding.transactions[0].txid(), 0)],
        outputs=[TxOutput(30, bob), TxOutput(18, alice)],
        timestamp=GENESIS_TIMESTAMP + 2,
    )
    parent.sign_input(0, keys[0])
    child = Transaction(
        inputs=[TxInput(parent.txid(), 0)],
        outputs=[TxOutput(27, carol)],
        timestamp=GENESIS_TIMESTAMP + 3,
    )
    child.sign_input(0, keys[1])
    conflict = Transaction(
        inputs=[TxInput(funding.transactions[0].txid(), 0)],
        outputs=[TxOutput(1, bob)],
        timestamp=GENESIS_TIMESTAMP + 4,
    )
    conflict.sign_input(0, keys[0])

    print("=== PHASE 7 - MEMPOOL DEMO ===")
    orphan_accepted = chain.submit_transaction(child)
    require(not orphan_accepted, "Orphan child should be rejected")
    print("Child accepted before parent:", orphan_accepted)
    require(chain.submit_transaction(parent), "Parent admission failed")
    require(chain.submit_transaction(child), "Child admission failed")
    conflict_accepted = chain.submit_transaction(conflict)
    require(not conflict_accepted, "First-seen conflict should be rejected")
    print("Higher-fee double-spend accepted:", conflict_accepted)
    print("Pending transactions:", len(chain.mempool))
    print("Verified parent/child fees:",
          chain.mempool.get_entry(parent.txid()).fee,
          chain.mempool.get_entry(child.txid()).fee)
    print("Alice confirmed balance while pending:", chain.get_balance(alice))
    require(chain.get_balance(alice) == 50, "Pending transfer changed balance")
    require(not chain.has_transaction(parent.txid()), "Pending is not confirmed")

    # Child has a higher fee rate, but only its parent is dependency-ready.
    first = chain.create_mempool_block_template(
        miner, timestamp=GENESIS_TIMESTAMP + 2, max_transactions=1
    )
    require(first.transactions[1:] == [parent], "Parent must be selected first")
    first_block = mine(first)
    require(len(chain.mempool) == 2, "Mining alone must not remove entries")
    print("Pending after template/mining, before acceptance:", len(chain.mempool))
    require(chain.add_block(first_block, current_time=now), "Parent block rejected")
    print("First block miner reward:", first.transactions[0].outputs[0].amount)
    print("Pending after parent confirmation:", len(chain.mempool))
    print("Child remains pending:", chain.mempool.has_transaction(child.txid()))
    print("Bob confirmed balance before child confirmation:", chain.get_balance(bob))
    require(chain.has_transaction(parent.txid()), "Parent should be confirmed")
    require(chain.mempool.get_transactions() == [child], "Child must survive")

    second = chain.create_mempool_block_template(
        miner, timestamp=GENESIS_TIMESTAMP + 3
    )
    require(second.transactions[1:] == [child], "Child must now be ready")
    require(chain.add_block(mine(second), current_time=now), "Child block rejected")
    print("Second block miner reward:", second.transactions[0].outputs[0].amount)
    print("Pending after child confirmation:", len(chain.mempool))
    print("Final balances (Alice, Bob, Carol, miner):",
          *(chain.get_balance(address) for address in (alice, bob, carol, miner)))
    print("Chain valid:", chain.validate_chain(current_time=now))
    require(len(chain.mempool) == 0, "Confirmed transactions must leave pool")
    require(chain.has_transaction(child.txid()), "Child should be confirmed")
    require([chain.get_balance(address) for address in (alice, bob, carol, miner)]
            == [18, 0, 27, 105], "Unexpected final ledger balances")
    require(chain.validate_chain(current_time=now), "Chain replay failed")


if __name__ == "__main__":
    main()
