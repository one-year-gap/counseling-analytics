#스키마 공통 규칙 부모 클래스
from pydantic import BaseModel, ConfigDict

class SchemaBase(BaseModel):
    model_config: ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
    )