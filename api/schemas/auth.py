import re

from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, ConfigDict, Field, field_validator


def normalize_email(value):
    """Use the same IDNA/Unicode canonical identity for register and login."""
    try:
        return validate_email(value.strip(), check_deliverability=False).normalized.casefold()
    except EmailNotValidError:
        raise ValueError("Invalid email address") from None


class RegisterRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)
    email: str = Field(min_length=3, max_length=254)
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=12, max_length=1024, repr=False)

    @field_validator("email")
    @classmethod
    def email_valid(cls, value):
        return normalize_email(value)

    @field_validator("username")
    @classmethod
    def username_valid(cls, value):
        if not re.fullmatch(r"[A-Za-z0-9_]{3,32}", value):
            raise ValueError("Username must contain 3-32 ASCII letters, digits or underscores")
        return value.lower()


class LoginRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)
    identifier: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=1024, repr=False)

    @field_validator("identifier")
    @classmethod
    def normalize(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Identifier is required")
        if "@" in value:
            try:
                return normalize_email(value)
            except ValueError:
                # Invalid/unknown emails still get the same credential error.
                pass
        return value.casefold()
