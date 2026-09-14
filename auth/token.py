"""HS256 JWTs are accepted only inside the HttpOnly session cookie."""

import secrets
import time
import jwt


class TokenError(Exception):
    pass


class TokenService:
    def __init__(self, secret, lifetime=3600):
        self.secret = secret
        self.lifetime = lifetime

    def create(self, user_id, csrf_token):
        now = int(time.time())
        claims = {"sub": str(user_id), "jti": secrets.token_hex(32), "iat": now,
                  "exp": now + self.lifetime, "iss": "pychain", "aud": "pychain-web", "csrf": csrf_token}
        return jwt.encode(claims, self.secret, algorithm="HS256"), claims

    def decode(self, token):
        try:
            claims = jwt.decode(token, self.secret, algorithms=["HS256"], issuer="pychain", audience="pychain-web",
                                options={"require": ["sub", "jti", "iat", "exp", "iss", "aud", "csrf"]})
            if not claims["sub"].isascii() or not claims["sub"].isdigit() or not (0 < int(claims["sub"]) <= 2**63-1):
                raise TokenError("Invalid session")
            if any(type(claims[name]) is not int for name in ("iat", "exp")):
                raise TokenError("Invalid session")
            if type(claims["csrf"]) is not str or type(claims["jti"]) is not str:
                raise TokenError("Invalid session")
            return claims
        except (jwt.InvalidTokenError, TypeError, ValueError, AttributeError) as exc:
            raise TokenError("Invalid session") from exc
