from pydantic import BaseModel, ConfigDict, EmailStr, Field


_TOKEN_EXAMPLE = {
    "access_token": (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTQwMDAtODAwMC0wMDAwMDAwMDAwMDEiLCJyb2xlIjoiYWRtaW4ifQ."
        "signature"
    ),
    "token_type": "bearer",
    "role": "admin",
    "email": "admin@brokerbridge.local",
}


class TokenResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": _TOKEN_EXAMPLE,
            "examples": [_TOKEN_EXAMPLE],
        }
    )

    access_token: str = Field(
        examples=[
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJzdWIiOiIwMDAwMDAwMC0wMDAwLTQwMDAtODAwMC0wMDAwMDAwMDAwMDEiLCJyb2xlIjoiYWRtaW4ifQ."
            "signature"
        ]
    )
    token_type: str = Field(default="bearer", examples=["bearer"])
    role: str = Field(examples=["admin"])
    email: str = Field(examples=["admin@brokerbridge.local"])


class TokenRequest(BaseModel):
    email: EmailStr = Field(examples=["admin@brokerbridge.local"])
    password: str = Field(min_length=1, examples=["admin123!"])
