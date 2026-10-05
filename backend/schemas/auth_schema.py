"""Authentication inputs and shared strict input configuration."""
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

Role = Literal["citizen", "admin", "response_team"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Register(Input):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(max_length=254)
    password: str = Field(min_length=10, max_length=128)
    district: str = Field(default="Alappuzha", min_length=2, max_length=80)

    @field_validator("email")
    @classmethod
    def email_format(cls, value):
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid email address")
        return value.lower()


class Login(Input):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class TokenBody(Input):
    refresh_token: str = Field(min_length=20, max_length=200)


class ForgotPassword(Input):
    email: str = Field(min_length=3, max_length=254)


class ResetPassword(Input):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=10, max_length=128)
