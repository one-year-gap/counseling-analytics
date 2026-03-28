import asyncio
import logging
import httpx
from typing import Any
from asyncpg import Connection

from app.core.config import Settings
from app.infra.pinpoint_tracing import traced_root_transaction
from app.infra.postgres.analysis_repository import AnalysisRepository
from app.infra.postgres.client import create_postgres_pool
from app.services.analysis_outcome_service import AnalysisOutcomeService
from app.services.sql_keyword_analysis_service import SqlKeywordAnalysisService

logger = logging.getLogger(__name__)

class CdcAnalysisService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._db_pool = None
        self._analysis_repository = None
        self._analysis_service = SqlKeywordAnalysisService()
        self._outcome_service = AnalysisOutcomeService(result_limit=20)
        
        # 알림을 받으면 순서대로 처리하기 위한 비동기 큐 (대기열)
        self._queue: asyncio.Queue[int] = asyncio.Queue()
        self._stop_event = asyncio.Event()
        self._tasks: list[asyncio.Task] = []
        
        # Spring API 서버 주소
        self._spring_api_url = self._settings.spring_api_url

    async def start(self) -> None:
        logger.info("CDC Analysis Service 시작 준비 중...")
        self._db_pool = await create_postgres_pool(self._settings)
        self._analysis_repository = AnalysisRepository(self._db_pool)

        # 1. 비즈니스 키워드 사전 및 감정 분석 모델 사전 로드
        keyword_rows = await self._analysis_repository.load_active_keyword_rows()
        self._analysis_service.load_dictionary([dict(r) for r in keyword_rows])

        # 2. DB 알림(NOTIFY)을 듣기 위한 전용 커넥션 생성 및 리스너 등록
        self._listen_conn = await self._db_pool.acquire()
        await self._listen_conn.add_listener('support_case_channel', self._on_db_notify)

        self._stop_event.clear()
        
        # 3. 큐에 쌓인 데이터를 꺼내서 분석하는 워커 태스크 실행
        worker_task = asyncio.create_task(self._worker_loop(), name="cdc-worker")
        self._tasks.append(worker_task)
        
        logger.info("CDC 감지 시작: 'support_case_channel' 채널 구독 완료. 대기 중...")

    async def stop(self) -> None:
        self._stop_event.set()
        
        # 리스너 해제 및 커넥션 반환
        if hasattr(self, '_listen_conn') and self._listen_conn:
            await self._listen_conn.remove_listener('support_case_channel', self._on_db_notify)
            await self._db_pool.release(self._listen_conn)
            
        for task in self._tasks:
            task.cancel()
        
        if self._db_pool:
            await self._db_pool.close()
        logger.info("CDC Analysis Service 안전하게 종료됨.")

    def _on_db_notify(self, connection: Connection, pid: int, channel: str, payload: str) -> None:
        """
        DB 트리거가 pg_notify 방송을 울리면 즉시 실행되는 콜백 함수
        payload 안에는 방송된 case_id 문자가 들어있음
        """
        try:
            case_id = int(payload)
            logger.info(f"[CDC 감지] 상담 데이터 변경 알림 수신: case_id={case_id}")
            # 작업 대기열에 case_id 추가 (워커가 곧바로 가져가서 처리함)
            self._queue.put_nowait(case_id)
        except ValueError:
            logger.error(f"잘못된 CDC payload 수신: {payload}")

    async def _worker_loop(self) -> None:
        """
        큐에 데이터가 들어오면 하나씩 꺼내서 [조회 ➔ 분석 ➔ HTTP 전송 ➔ DB 덮어쓰기]를 수행
        """
        # HTTP 연결을 재사용하여 통신 속도를 높이기 위한 AsyncClient 생성
        async with httpx.AsyncClient(timeout=10.0) as http_client:
            while not self._stop_event.is_set():
                case_id: int | None = None
                task_received = False
                try:
                    # 큐에 case_id가 들어올 때까지 조용히 대기
                    case_id = await self._queue.get()
                    task_received = True

                    async with traced_root_transaction(
                        "cdc.worker.process",
                        f"/internal/cdc/support-case/{case_id}",
                        request_client="postgresql-notify",
                    ):
                        # 1. DB에서 원본 상담 데이터 조회
                        case_record = await self._analysis_repository.find_case_by_id(case_id)
                        if not case_record:
                            logger.warning(f"case_id={case_id} 데이터를 찾을 수 없어 분석을 건너뜁니다.")
                            continue
                        
                        # 분석기 파라미터 규격에 맞게 딕셔너리 포맷팅
                        target = dict(case_record)
                        target["analysis_id"] = None
                        target["analyzer_version"] = 1 
                        
                        # 2. 분석 파이프라인 돌리기 (KoELECTRA 감정 분석 + 키워드 추출)
                        analysis_result = self._analysis_service.analyze_single_target(target)
                        
                        # 3. DB에 분석 결과 먼저 안전하게 덮어쓰기 (UPSERT)
                        # 여기서 DB가 방금 생성한 analysis_id를 받아옴
                        analysis_id = await self._analysis_repository.save_analysis_result(
                            case_id=case_id, 
                            analyzer_version=1, 
                            mappings=analysis_result["mappings"]
                        )
                        logger.info(f"[DB 저장 성공] case_id={case_id} 자체 DB 저장 완료 (analysis_id={analysis_id})")

                        # 4. JSON 조립하기
                        payload = self._outcome_service.build_http_outcome(
                            case_id=case_id,
                            analyzer_version=1,
                            analysis_id=analysis_id, # null 대신 진짜 ID 주입
                            member_id=target["member_id"],
                            sentiment=analysis_result["sentiment"],
                            mappings=analysis_result["mappings"],
                        )

                        # import json
                        # logger.info(f"[분석 완료 - JSON 결과물]\n{json.dumps(payload, ensure_ascii=False, indent=2)}")

                        # 5. 마지막으로 Spring API 서버로 HTTP POST 전송 시도
                        response = await http_client.post(self._spring_api_url, json=payload)
                        response.raise_for_status() # 200번대 성공이 아니면 여기서 HTTPError 발생
                        logger.info(f"[전송 성공] case_id={case_id} Spring API 전송 완료")
                    
                except httpx.HTTPError as e:
                    logger.error(f"[HTTP 전송 실패] case_id={case_id} API 연동 중 오류 발생: {e}")
                except Exception as e:
                    logger.error(f"[시스템 오류] case_id={case_id} 처리 중 알 수 없는 예외 발생: {e}", exc_info=True)
                finally:
                    # 큐 작업 하나가 끝났음을 알려줌
                    if task_received:
                        self._queue.task_done()
