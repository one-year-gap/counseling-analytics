#분석 결과 JSONL 상담 1건
from datetime import datetime
from pydantic import Field
from app.schemas.base import SchemaBase

class MatchedKeywordRecord(SchemaBase):
    business_keyword_id: int = Field(..., alias="businessKeywordId", ge=1)
    keyword_code: str = Field(..., alias="keywordCode", min_length=1, max_length=20)
    keyword_name: str = Field(..., alias="keywordName", min_length=1, max_length=100)

    matched_alias: str = Field(..., alias="matchedAlias", min_length=1, max_length=100)
    match_score: float = Field(..., alias="matchScore", ge=0.0, le=1.0)
    algorithm: str = Field(..., min_length=1, max_length=50)


class ResultRecord(SchemaBase):
    request_id: str = Field(..., alias="requestId")
    job_instance_id: int = Field(..., alias="jobInstanceId", ge=1)
    chunk_id: str = Field(..., alias="chunkId")

    case_id: int = Field(..., alias="caseId", ge=1)
    member_id: int = Field(..., alias="memberId", ge=1)

    # 매핑된 비즈니스 키워드 리스트
    matched_keywords: list[MatchedKeywordRecord] = Field(
        default_factory=list,
        alias="matchedKeywords",
    )
    # 분석기 버전
    analysis_version: str = Field(..., alias="analysisVersion")
    # 분석 종료 시간
    processed_at: datetime = Field(..., alias="processedAt")