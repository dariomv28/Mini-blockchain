"""A reproducible ledger demo funded by mined coinbase outputs."""

from ecdsa import SECP256k1, SigningKey

from blockchain.block import Block
from blockchain.blockchain import Blockchain
from blockchain.genesis import GENESIS_TIMESTAMP
from blockchain.validation import rebuild_chain_state
from consensus.difficulty import MINING_DIFFICULTY
from crypto.address import public_key_to_address
from mining.coinbase import create_coinbase_transaction
from mining.miner import mine_block
from transaction.transaction import Transaction
from transaction.tx_input import TxInput
from transaction.tx_output import TxOutput


def mine(template: Block) -> Block:
    result = mine_block(template, max_nonce=100_000)
    if result is None:
        raise RuntimeError("Demo nonce range exhausted")
    return result


def main() -> None:
    # Public fixed keys for this educational demo only; never store real funds.
    alice_key = SigningKey.from_secret_exponent(101, curve=SECP256k1)
    bob_key = SigningKey.from_secret_exponent(102, curve=SECP256k1)
    miner_key = SigningKey.from_secret_exponent(103, curve=SECP256k1)
    alice = public_key_to_address(alice_key.get_verifying_key())
    bob = public_key_to_address(bob_key.get_verifying_key())
    miner = public_key_to_address(miner_key.get_verifying_key())
    now = GENESIS_TIMESTAMP + 100
    chain = Blockchain()

    funding = mine(chain.create_block_template(alice, timestamp=GENESIS_TIMESTAMP + 1))
    if not chain.add_block(funding, current_time=now):
        raise RuntimeError("Funding block was rejected")
    funding_txid = funding.transactions[0].txid()

    transfer = Transaction(
        inputs=[TxInput(funding_txid, 0)],
        outputs=[TxOutput(30, bob), TxOutput(18, alice)],
        timestamp=GENESIS_TIMESTAMP + 2,
    )
    transfer.sign_input(0, alice_key)
    template = chain.create_block_template(
        miner, transactions=[transfer], timestamp=GENESIS_TIMESTAMP + 2
    )
    if not chain.add_block(mine(template), current_time=now):
        raise RuntimeError("Signed transfer was rejected")

    print("=== PHASE 6 - UTXO LEDGER DEMO ===")
    print("Funding from mined coinbase:", 50)
    print("Transfer fee:", 2)
    print("Miner reward:", template.transactions[0].outputs[0].amount)
    print("Alice balance:", chain.get_balance(alice))
    print("Bob balance:", chain.get_balance(bob))
    print("Miner balance:", chain.get_balance(miner))
    print("Total unspent coins:", sum(
        output.amount for output in chain.utxo_set.to_dict().values()
    ))

    # Deliberately build a raw candidate: the safe template builder rejects
    # this double-spend before mining. add_block must reject it independently.
    double_spend = Transaction(
        inputs=[TxInput(funding_txid, 0)],
        outputs=[TxOutput(49, bob)],
        timestamp=GENESIS_TIMESTAMP + 3,
    )
    double_spend.sign_input(0, alice_key)
    rejected_candidate = mine(Block(
        transactions=[
            create_coinbase_transaction(miner, timestamp=GENESIS_TIMESTAMP + 3),
            double_spend,
        ],
        previous_block_hash=chain.get_latest_block().hash(),
        timestamp=GENESIS_TIMESTAMP + 3,
        difficulty=MINING_DIFFICULTY,
    ))
    before = (chain.chain, chain.utxo_set.to_dict())
    accepted = chain.add_block(rejected_candidate, current_time=now)
    unchanged = (chain.chain, chain.utxo_set.to_dict()) == before
    rebuilt = rebuild_chain_state(chain.chain, current_time=now)
    replay_matches = (
        rebuilt is not None
        and rebuilt.utxo_set.to_dict() == chain.utxo_set.to_dict()
    )

    print("Double-spend accepted:", accepted)
    print("Chain and UTXOs unchanged:", unchanged)
    print("Replay matches live UTXOs:", replay_matches)
    print("Chain valid:", chain.validate_chain(current_time=now))
    if accepted or not unchanged or not replay_matches:
        raise RuntimeError("Ledger checks did not match the expected outcome")


if __name__ == "__main__":
    main()
