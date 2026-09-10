"""Run one persistent educational TCP node; stop with Ctrl+C."""

import argparse
import asyncio
import logging
from pathlib import Path
import signal

from network import Node, NodeConfig


def _endpoint(value: str) -> tuple[str, int]:
    try:
        host, raw_port = value.rsplit(":", 1)
        port = int(raw_port)
        if not host or not 1 <= port <= 65535:
            raise ValueError
        return host, port
    except ValueError as error:
        raise argparse.ArgumentTypeError("seed must be an IPv4 address:port") from error


def _port(value: str) -> int:
    try:
        port = int(value)
        if not 1 <= port <= 65535:
            raise ValueError
        return port
    except ValueError as error:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535") from error


async def _run(config: NodeConfig) -> int:
    node = Node(config)
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    old_handlers = {}
    # add_signal_handler is unavailable on Windows' default event loop.
    # signal.signal also lets SIGTERM request the same orderly cleanup as SIGINT.
    def stop_requested(signum, frame):
        loop.call_soon_threadsafe(stopped.set)

    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            old_handlers[signum] = signal.signal(signum, stop_requested)
        await node.start()
        logging.getLogger(__name__).info(
            "Listening on %s:%d; persistent database %s",
            *node.endpoint, config.db_path,
        )
        while not stopped.is_set() and node.state == "RUNNING":
            try:
                await asyncio.wait_for(stopped.wait(), timeout=0.5)
            except asyncio.TimeoutError:
                pass
        return 1 if node.state == "FAILED" else 0
    finally:
        await node.stop()
        for signum, handler in old_handlers.items():
            signal.signal(signum, handler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path,
                        help="SQLite database to create or reopen; its directory must exist")
    parser.add_argument("--host", default="127.0.0.1", help="IPv4 bind address")
    parser.add_argument("--port", type=_port, default=5001)
    parser.add_argument("--seed", action="append", type=_endpoint, default=[],
                        help="seed IPv4 address:port; may be repeated")
    parser.add_argument("--allow-cidr", action="append", default=[],
                        help="explicit private LAN subnet to allow, in addition to loopback")
    args = parser.parse_args(argv)
    try:
        config = NodeConfig(
            host=args.host, port=args.port, db_path=args.db,
            seeds=tuple(args.seed),
            allowed_cidrs=("127.0.0.0/8", *args.allow_cidr),
        )
    except (TypeError, ValueError) as error:
        parser.error(str(error))
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        return asyncio.run(_run(config))
    except KeyboardInterrupt:
        return 0
    except Exception:
        logging.getLogger(__name__).exception("Node could not continue")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
