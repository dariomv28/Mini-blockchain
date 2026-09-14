from pydantic import BaseModel, ConfigDict, Field, field_validator

from crypto.address import validate_address


class SendRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    recipient_address: str = Field(min_length=52, max_length=52)
    amount: int = Field(gt=0)
    fee: int = Field(default=1, ge=0)

    @field_validator("recipient_address")
    @classmethod
    def valid_address(cls, value):
        if not validate_address(value):
            raise ValueError("Invalid PYC address")
        return value
