from copy import deepcopy

from blockchain.blockchain import Blockchain
from blockchain.genesis import GENESIS_TIMESTAMP
from consensus.difficulty import target_from_difficulty
from consensus.pow import validate_proof_of_work
from crypto.address import public_key_to_address
from crypto.keys import generate_private_key, get_public_key
from mining.block_template import create_block_template
from mining.miner import mine_block


def make_miner_address() -> str:
    private_key = generate_private_key()
    return public_key_to_address(get_public_key(private_key))


def make_proof_invalid(block) -> None:
    block.nonce += 1

    while validate_proof_of_work(block):
        block.nonce += 1


def main() -> None:
    demo_now = GENESIS_TIMESTAMP + 100
    chain = Blockchain()
    miner_address = make_miner_address()
    template = create_block_template(
        chain.get_latest_block(),
        miner_address,
        timestamp=GENESIS_TIMESTAMP + 1,
    )
    mined = mine_block(template, max_nonce=100_000)

    if mined is None:
        raise RuntimeError("Mining range was unexpectedly exhausted")

    target = target_from_difficulty(mined.difficulty)

    print("=== PHASE 5 - PROOF OF WORK DEMO ===")
    print("Miner address:", miner_address)
    print("Coinbase reward:", mined.transactions[0].outputs[0].amount)
    print("Difficulty:", mined.difficulty)
    print("Target:", f"{target:064x}")
    print("Nonce:", mined.nonce)
    print("Block hash:", mined.hash())
    print("PoW valid:", validate_proof_of_work(mined))
    print("Add mined block:", chain.add_block(mined, current_time=demo_now))
    print("Chain height:", chain.height)

    tampered = deepcopy(mined)
    make_proof_invalid(tampered)
    height_before = chain.height
    print("Tampered PoW valid:", validate_proof_of_work(tampered))
    print(
        "Add tampered block:",
        chain.add_block(tampered, current_time=demo_now),
    )
    print("Height unchanged:", chain.height == height_before)
    print("Chain valid:", chain.validate_chain(current_time=demo_now))


if __name__ == "__main__":
    main()
