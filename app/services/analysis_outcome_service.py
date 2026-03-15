from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Any

class AnalysisOutcomeService:
    def __init__(self, result_limit: int = 20) -> None:
        self._result_limit = max(1, result_limit)

    def build_http_outcome(
        self,
        case_id: int,
        analyzer_version: int,
        analysis_id: int | None,
        member_id: int,
        sentiment: str,
        mappings: list[dict[str, Any]],
        error_message: str | None = None
    ) -> dict[str, Any]:
        """
        단건 상담 분석 결과를 Spring API 서버로 전송할 JSON 페이로드로 변환
        """
        produced_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        status = "FAILED" if error_message else "COMPLETED"
        
        # HTTP 전송 멱등성을 위한 고유 요청 ID 생성 (예: req-1001-a1b2c3d4)
        dispatch_request_id = f"req-{case_id}-{uuid.uuid4().hex[:8]}"

        # 통계 계산
        keyword_types = len(mappings)
        keyword_hits = sum(m.get("count", 0) for m in mappings)

        # 출현 빈도(count)가 높은 순으로 정렬 후 최대 개수(result_limit) 제한
        sorted_mappings = sorted(mappings, key=lambda x: -x.get("count", 0))[:self._result_limit]

        # 키워드 결과 조립 (negativeWeight 포함)
        keyword_counts = []
        for m in sorted_mappings:
            keyword_counts.append({
                "keywordId": m["businessKeywordId"],
                "businessKeywordId": m["businessKeywordId"],
                "keywordCode": m["keywordCode"],
                "keywordName": m["keywordName"],
                "count": m["count"],
                "negativeWeight": m.get("negativeWeight", 0)
            })

        # 최종 HTTP POST용 JSON 딕셔너리
        return {
            "dispatchRequestId": dispatch_request_id,
            "caseId": case_id,
            "analyzerVersion": analyzer_version,
            "analysisId": analysis_id,
            "memberId": member_id,
            "status": status,
            "keywordTypes": keyword_types,
            "keywordHits": keyword_hits,
            "consultationType": sentiment,    
            "keywordCounts": keyword_counts,
            "error": error_message,
            "producedAt": produced_at,
        }