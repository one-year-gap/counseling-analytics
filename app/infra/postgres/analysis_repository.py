from __future__ import annotations

try:
    from pinpointPy import Defines
except Exception:  # pragma: no cover
    Defines = None  # type: ignore[assignment]

from asyncpg import Pool, Record

from app.infra.pinpoint_tracing import resolve_postgresql_destination, traced_external_span

POSTGRES_SERVER_TYPE = getattr(Defines, "PP_POSTGRESQL", "2501")


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
            async with traced_external_span(
                "asyncpg.fetchrow",
                POSTGRES_SERVER_TYPE,
                resolve_postgresql_destination(conn),
                sql=sql,
                args_value=f"case_id={case_id}",
            ):
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
            async with traced_external_span(
                "asyncpg.fetch",
                POSTGRES_SERVER_TYPE,
                resolve_postgresql_destination(conn),
                sql=sql,
            ):
                return await conn.fetch(sql)
        
    # 분석 완료 후 분석 내역 및 매핑 결과를 DB에 바로 저장하는 쿼리
    # UPSERT를 적용하여 수정(UPDATE)된 상담글의 재분석 결과 덮어쓰기 지원
    async def save_analysis_result(
        self, 
        case_id: int, 
        analyzer_version: int, 
        mappings: list[dict]
    ) -> int:
        """
        분석 완료 후 분석 내역과 매핑 결과를 DB에 저장
        (고객이 글을 수정해 재분석된 경우 기존 데이터를 덮어씀)
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # 1. UPSERT (분석 내역이 없으면 INSERT, 이미 있으면 updated_at만 갱신)
                analysis_sql = """
                INSERT INTO consultation_analysis 
                    (case_id, job_instance_id, analyzer_version)
                VALUES ($1, 0, $2)
                ON CONFLICT (case_id) 
                DO UPDATE SET updated_at = NOW(), analyzer_version = EXCLUDED.analyzer_version
                RETURNING analysis_id
                """
                async with traced_external_span(
                    "asyncpg.fetchval",
                    POSTGRES_SERVER_TYPE,
                    resolve_postgresql_destination(conn),
                    sql=analysis_sql,
                    args_value=f"case_id={case_id}, analyzer_version={analyzer_version}",
                ):
                    analysis_id = await conn.fetchval(analysis_sql, case_id, analyzer_version)

                # 2. 기존 키워드 매핑 결과 초기화 (싹 비우기)
                # 고객이 글을 수정하면서 기존에 있던 키워드가 사라졌을 수도 있으므로,
                # 옛날 분석 결과는 깔끔하게 삭제
                delete_mapping_sql = """
                DELETE FROM business_keyword_mapping_result 
                WHERE analysis_id = $1
                """
                async with traced_external_span(
                    "asyncpg.execute",
                    POSTGRES_SERVER_TYPE,
                    resolve_postgresql_destination(conn),
                    sql=delete_mapping_sql,
                    args_value=f"analysis_id={analysis_id}",
                ):
                    await conn.execute(delete_mapping_sql, analysis_id)

                # 3. 새로운(또는 변경된) 키워드 매핑 결과 적재
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
                    async with traced_external_span(
                        "asyncpg.executemany",
                        POSTGRES_SERVER_TYPE,
                        resolve_postgresql_destination(conn),
                        sql=mapping_sql,
                        args_value=f"analysis_id={analysis_id}, mapping_count={len(mapping_data)}",
                    ):
                        await conn.executemany(mapping_sql, mapping_data)

                return analysis_id
