"""Transport failures; these never stand in for local storage failures."""


class NetworkError(RuntimeError):
    """A networking operation could not complete."""


class ProtocolError(NetworkError):
    """The remote message violates the wire protocol."""


class PolicyLimitError(NetworkError):
    """An item or operation exceeds a local resource budget."""


class PeerDisconnectedError(NetworkError):
    """The connection closed before an operation completed."""


class NodeClosedError(NetworkError):
    """The node is not running or is no longer usable."""


class NodeBusyError(NetworkError):
    """The bounded dispatcher cannot accept another command."""
