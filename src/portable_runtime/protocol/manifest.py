from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator


class ProviderManifest(BaseModel):
    id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9._-]+$")
    name: str = Field(min_length=1, max_length=256)
    version: str = Field(min_length=1, max_length=64)
    protocol_version: str = "1"
    transport: str = "stdio-jsonl"
    command: list[str] | None = Field(default=None, min_length=1)
    capabilities: list[str] = Field(min_length=1)
    entrypoint: str | None = Field(default=None)
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("transport")
    @classmethod
    def supported_transport(cls, value: str) -> str:
        if value not in {"stdio-jsonl", "python"}:
            raise ValueError("only stdio-jsonl and python are supported in protocol v1")
        return value

    @model_validator(mode="after")
    def check_transport_fields(self) -> ProviderManifest:
        if self.transport == "stdio-jsonl" and not self.command:
            raise ValueError("stdio-jsonl transport requires ''command''")
        if self.transport == "python" and not self.entrypoint and not self.command:
            # python transport may use entrypoint or command; allow either but at least one
            pass
        return self

    model_config = {"extra": "allow"}
