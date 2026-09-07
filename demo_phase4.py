from blockchain.block import Block
from blockchain.blockchain import Blockchain
from blockchain.genesis import GENESIS_HASH, GENESIS_TIMESTAMP
from blockchain.validation import validate_chain
from crypto.address import public_key_to_address
from crypto.keys import generate_private_key, get_public_key
from mining.block_template import create_block_template
from mining.miner import mine_block


def make_miner_address() -> str:
    private_key = generate_private_key()
    return public_key_to_address(get_public_key(private_key))


def make_candidate(chain: Blockchain, miner_address: str) -> Block:
    tip = chain.get_latest_block()
    template = create_block_template(
        tip,
        miner_address,
        timestamp=tip.timestamp + 1,
    )
    candidate = mine_block(template, max_nonce=100_000)

    if candidate is None:
        raise RuntimeError("Mining range was unexpectedly exhausted")

    return candidate


def main() -> None:
    # Thời gian cố định giúp kết quả demo tái lập được.
    demo_now = GENESIS_TIMESTAMP + 100
    chain = Blockchain()
    miner_address = make_miner_address()

    print("=== PHASE 4 - BLOCKCHAIN API DEMO ===")
    print("Runs with the Phase 5 coinbase and PoW rules")
    print("Genesis hash:", GENESIS_HASH)
    print("Initial height:", chain.height)

    first = make_candidate(chain, miner_address)
    first_added = chain.add_block(first, current_time=demo_now)
    print("Add block 1:", first_added)
    second = make_candidate(chain, miner_address)
    second_added = chain.add_block(second, current_time=demo_now)
    print("Add block 2:", second_added)
    print("Block count:", len(chain))
    print("Chain height:", chain.height)
    print("Chain valid:", chain.validate_chain(current_time=demo_now))

    bad = make_candidate(chain, miner_address)
    bad.previous_block_hash = "f" * 64
    height_before = chain.height
    print("Add wrong-parent block:", chain.add_block(bad, current_time=demo_now))
    print("Height unchanged:", chain.height == height_before)
    print("Add duplicate block:", chain.add_block(second, current_time=demo_now))

    stored_hash = chain.get_latest_block().hash()
    second.nonce += 1
    print("Stored block unchanged:", chain.get_latest_block().hash() == stored_hash)

    snapshot = chain.chain
    snapshot[1].nonce += 1
    print("Tampered snapshot valid:", validate_chain(snapshot, current_time=demo_now))
    print("Live chain valid:", chain.validate_chain(current_time=demo_now))

    if not first_added or not second_added:
        raise RuntimeError("Expected both valid blocks to be added")


if __name__ == "__main__":
    main()
