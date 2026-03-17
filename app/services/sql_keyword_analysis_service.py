from typing import Any

from app.pipeline.extractor import AhoCorasickExtractor
from app.pipeline.mapper import ExactMapper
from app.pipeline.normalizer import normalize_with_offsets
from app.pipeline.scorer import ContextScorer
from app.pipeline.sentiment_analyzer import SentimentAnalyzer

class SqlKeywordAnalysisService:
    def __init__(self) -> None:
        self.mapper = ExactMapper()
        self.extractor = AhoCorasickExtractor()
        self.scorer = ContextScorer()
        self.sentiment_analyzer = SentimentAnalyzer()  # 감정 분석기 초기화
        self.keyword_meta: dict[str, dict[str, Any]] = {}

    def load_dictionary(self, keyword_rows: list[dict[str, Any]]) -> None:
        self.mapper = ExactMapper()
        self.extractor = AhoCorasickExtractor()
        self.keyword_meta = {}

        dict_rows: list[dict[str, Any]] = []
        seen_codes: set[str] = set()
        for row in keyword_rows:
            code = str(row["keyword_code"])
            if code not in seen_codes:
                seen_codes.add(code)
                self.keyword_meta[code] = {
                    "id": int(row["business_keyword_id"]),
                    "name": row["keyword_name"],
                    "negative_weight": row.get("negative_weight", 0)  # DB에서 꺼내온 부정 가중치 저장
                }
                dict_rows.append(
                    {
                        "schema": "dict.keyword.v1",
                        "label_id": code,
                        "business_keyword": row["keyword_name"],
                    }
                )

            alias_text = row.get("alias_text")
            alias_norm = row.get("alias_norm")
            if alias_text:
                dict_rows.append(
                    {
                        "schema": "dict.alias.v1",
                        "label_id": code,
                        "business_keyword": row["keyword_name"],
                        "alias_text": alias_text,
                        "alias_norm": alias_norm or alias_text,
                    }
                )

        self.mapper.build_index(dict_rows)
        self.extractor.build_automaton(dict_rows)

    # CDC 데몬에서 딱 1건씩 호출하기 위해 만든 심플한 분석 함수
    def analyze_single_target(self, target: dict[str, Any]) -> dict[str, Any]:
        title = target.get("title") or ""
        question = target.get("question_text") or ""
        full_text = " ".join(part for part in [title, question] if part)

        # 1. 기존 알고리즘 파이프라인 돌려서 키워드 추출
        matches = self._run_full_pipeline(full_text)
        
        keyword_count_by_code: dict[str, int] = {}
        for match in matches:
            code = match["keyword_id"]
            keyword_count_by_code[code] = keyword_count_by_code.get(code, 0) + 1

        # 2. 키워드 매핑 결과 조립 (negative_weight 포함)
        mappings = []
        for code, count in keyword_count_by_code.items():
            meta = self.keyword_meta.get(code)
            if not meta:
                continue
            mappings.append({
                "businessKeywordId": meta["id"],
                "keywordCode": code,
                "keywordName": meta["name"],
                "count": count,
                "negativeWeight": meta["negative_weight"]  # 가중치 담기
            })

        # 3. 텍스트 감정 분석 (KoELECTRA)
        sentiment = self.sentiment_analyzer.analyze(full_text)

        # 4. 분석 결과 반환 (CDC 워커가 받아서 처리함)
        return {
            "sentiment": sentiment,
            "mappings": mappings
        }

    def _run_full_pipeline(self, text: str) -> list[dict[str, Any]]:
        norm_text, offset_map = normalize_with_offsets(text)
        if not norm_text:
            return []

        step1_results = self.mapper.exact_match(text)
        masked_raw = self._apply_masking(text, step1_results)
        norm_masked, _ = normalize_with_offsets(masked_raw)
        step2_results = self.extractor.extract_keywords(norm_masked, offset_map)

        all_matches_so_far = step1_results + step2_results
        masked_v2 = self._apply_masking(text, all_matches_so_far)
        doc = self.scorer.parse_document(text)
        step3_results = self.scorer.rescue_typos(
            doc=doc,
            masked_text=masked_v2,
            canon_index=self.mapper.canon_norm_index,
            alias_index=self.mapper.alias_norm_index,
        )

        return step1_results + step2_results + step3_results

    def _apply_masking(self, text: str, matches: list[dict[str, Any]]) -> str:
        chars = list(text)
        for match in matches:
            for idx in range(match["orig_start"], match["orig_end"] + 1):
                if idx < len(chars):
                    chars[idx] = "*"
        return "".join(chars)
