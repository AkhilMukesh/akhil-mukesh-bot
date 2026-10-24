from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, content: str) -> str:
        if not content.strip():
            raise ValueError("Message content must not be blank.")
        return content


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)
    history: List[ChatMessage] = Field(default_factory=list, max_length=20)

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, message: str) -> str:
        if not message.strip():
            raise ValueError("Message must not be blank.")
        return message

    @model_validator(mode="after")
    def total_conversation_must_be_bounded(self) -> "ChatRequest":
        total_length = len(self.message) + sum(len(item.content) for item in self.history)
        if total_length > 12000:
            raise ValueError("The conversation is too long. Start a new chat.")
        return self


class ChatResponse(BaseModel):
    answer: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
