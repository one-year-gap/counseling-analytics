from asyncpg import Pool, Record


class AnalysisRepository:
    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    # CDC로 감지된 특정 상담 건(case_id)의 내용만 바로 가져오는 쿼리
    async def find_case_by_id(self, case_id: int) -> Record | None:
        """
        CDC 이벤트를 통해 전달받은 case_id를 이용해 원본 상담 데이터를 조회
        """
        sql = """
        SELECT
            case_id,
            member_id,
            title,
            question_text
        FROM support_case
        WHERE case_id = $1
        """
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(sql, case_id)

    async def load_active_keyword_rows(self) -> list[Record]:
        sql = """
        SELECT
            bk.business_keyword_id,
            bk.keyword_code,
            bk.keyword_name,
            bk.negative_weight,
            bka.alias_id,
            bka.alias_text,
            bka.alias_norm
        FROM business_keyword bk
        LEFT JOIN business_keyword_alias bka
          ON bka.business_keyword_id = bk.business_keyword_id
         AND bka.is_active = TRUE
        WHERE bk.is_active = TRUE
        ORDER BY bk.business_keyword_id, bka.alias_id
        """
        async with self._pool.acquire() as conn:
            return await conn.fetch(sql)
        
    # 분석 완료 후 분석 내역 및 매핑 결과를 DB에 바로 저장하는 쿼리
    async def save_analysis_result(
        self, 
        case_id: int, 
        analyzer_version: int, 
        mappings: list[dict]
    ) -> int:
        """
        분석이 끝난 후 consultation_analysis와 매핑 결과를 DB에 INSERT
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # 1. 분석 내역(consultation_analysis) 적재
                analysis_sql = """
                INSERT INTO consultation_analysis 
                    (case_id, job_instance_id, analyzer_version)
                VALUES ($1, 0, $2)
                RETURNING analysis_id
                """
                analysis_id = await conn.fetchval(analysis_sql, case_id, analyzer_version)

                # 2. 키워드 매핑 결과 적재
                if mappings:
                    mapping_sql = """
                    INSERT INTO business_keyword_mapping_result 
                        (analysis_id, business_keyword_id, count)
                    VALUES ($1, $2, $3)
                    """
                    mapping_data = [
                        (analysis_id, m["businessKeywordId"], m["count"]) 
                        for m in mappings
                    ]
                    await conn.executemany(mapping_sql, mapping_data)

                return analysis_id
