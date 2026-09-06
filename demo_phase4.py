from blockchain.block import Block
from blockchain.blockchain import Blockchain
from blockchain.genesis import GENESIS_HASH, GENESIS_TIMESTAMP
from blockchain.validation import validate_chain


def make_candidate(chain: Blockchain) -> Block:
    tip = chain.get_latest_block()
    return Block(
        transactions=[],
        previous_block_hash=tip.hash(),
        timestamp=tip.timestamp + 1,
        version=1,
        difficulty=1,
        nonce=0,
    )


def main() -> None:
    # Thời gian cố định giúp kết quả demo tái lập được.
    demo_now = GENESIS_TIMESTAMP + 100
    chain = Blockchain()

    print("=== PHASE 4 - BLOCKCHAIN DEMO ===")
    print("Validation scope: structure and links")
    print("Genesis hash:", GENESIS_HASH)
    print("Initial height:", chain.height)

    first = make_candidate(chain)
    first_added = chain.add_block(first, current_time=demo_now)
    print("Add block 1:", first_added)
    second = make_candidate(chain)
    second_added = chain.add_block(second, current_time=demo_now)
    print("Add block 2:", second_added)
    print("Block count:", len(chain))
    print("Chain height:", chain.height)
    print("Chain valid:", chain.validate_chain(current_time=demo_now))

    bad = make_candidate(chain)
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
