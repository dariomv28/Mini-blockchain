import asyncio
from collections import deque
import hashlib
import secrets
import time

from api.errors import APIError
from appdb.database import DuplicateAccountError
from auth.password import hash_password, verify_password
from crypto.address import public_key_to_address
from crypto.keys import generate_private_key, public_key_to_hex
from wallet.wallet import Wallet


class LoginGuard:
    """Bounded per-process attempt windows and failure cooldowns."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.attempts = {}
        self.failures = {}
        self.cooldowns = {}

    def check(self, ip, identifier):
        now = self.clock()
        for mapping in (self.attempts, self.failures):
            for key, times in list(mapping.items()):
                while times and times[0] <= now - 60:
                    times.popleft()
                if not times:
                    mapping.pop(key)
        self.cooldowns = {key: expiry for key, expiry in self.cooldowns.items() if expiry > now}
        # Untrusted identifiers must not create unbounded memory growth.
        keys = [("ip", ip), ("account", hashlib.sha256(identifier.encode()).hexdigest())]
        for key, limit in zip(keys, (20, 5)):
            if key in self.cooldowns or len(self.attempts.get(key, ())) >= limit:
                raise APIError(429, "LOGIN_RATE_LIMITED", "Too many login attempts; retry later")
        if len(self.attempts) + len(self.failures) + len(self.cooldowns) >= 10000:
            raise APIError(429, "LOGIN_RATE_LIMITED", "Too many login attempts; retry later")
        for key in keys:
            self.attempts.setdefault(key, deque()).append(now)
        return keys

    def failed(self, keys):
        now = self.clock()
        for key, threshold in zip(keys, (10, 5)):
            times = self.failures.setdefault(key, deque())
            times.append(now)
            if len(times) >= threshold:
                self.cooldowns[key] = now + 60


class AuthService:
    def __init__(self, database, keystore, dummy_hash):
        self.database = database
        self.keystore = keystore
        self.dummy_hash = dummy_hash
        self.guard = LoginGuard()
        # Each Argon2 job uses 64 MiB; bound concurrent jobs on the API process.
        self._password_jobs = asyncio.Semaphore(2)

    async def register(self, email, username, password):
        async with self._password_jobs:
            password_hash = await asyncio.to_thread(hash_password, password)
        key = generate_private_key()
        public = key.get_verifying_key()
        wallet = Wallet(public_key_to_address(public), public_key_to_hex(public), self.keystore.encrypt_private_key(key))
        del key
        try:
            return self.database.create_account(email, username, password_hash, wallet)
        except DuplicateAccountError:
            raise APIError(409, "ACCOUNT_EXISTS", "Email or username is already registered") from None

    async def login(self, identifier, password, ip):
        keys = self.guard.check(ip, identifier)
        user = self.database.find_user(identifier)
        async with self._password_jobs:
            valid = await asyncio.to_thread(verify_password, self.dummy_hash if user is None else user["password_hash"], password)
        if not valid or user is None:
            self.guard.failed(keys)
            raise APIError(401, "INVALID_CREDENTIALS", "Invalid credentials")
        return user
