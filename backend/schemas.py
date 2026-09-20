from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    StringConstraints,
)


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=2,
            max_length=100,
        ),
    ]
    email: EmailStr
    password: SecretStr = Field(min_length=15, max_length=128)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: SecretStr = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 900


class UserResponse(BaseModel):
    id: str
    name: str
    email: EmailStr
    role: Literal["employee", "manager", "admin"]