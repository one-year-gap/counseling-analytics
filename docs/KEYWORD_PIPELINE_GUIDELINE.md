# Keyword/Alias 3-Stage Pipeline Implementation Guide

이 문서는 "앱 시작 시 로딩 + 3단계 매칭(Exact/Aho-Corasick/Damerau-Levenshtein)"을
현재 프로젝트 구조에 맞춰 어디에 작성할지 가이드합니다.

## 1) 파일 배치 권장안

- 정규화 규칙(스프링과 동일): `app/pipeline/normalizer.py`
- Stage1 인덱스 생성: `app/pipeline/mapper.py`
- Stage2 오토마톤 생성/검색: `app/pipeline/extractor.py`
- Stage3 유사도 계산: `app/pipeline/scorer.py`
- 로더/캐시/스냅샷 관리: `app/services/alias_loader_service.py`
- 분석 오케스트레이션: `app/services/analyze_service.py`
- startup/reload 훅: `app/main.py`, `app/api/v1/ops.py`
- 설정값(임계치/토글): `app/core/config.py`

## 2) 런타임 객체(메모리) 설계

`alias_loader_service.py`에 아래 스냅샷 객체를 둡니다.

- `canon_norm_index: dict[str, list[int]]`
- `alias_norm_index: dict[str, list[int]]`
- `aho_automaton` (pyahocorasick)
- `keyword_meta: dict[int, dict]`  
  최소: `priority`, `match_mode`, `canon`, `aliases`
- `loaded_at`, `version`

핵심 원칙:
- 조회는 락 없이 읽고, 리로드 시 새 스냅샷을 만들어 "원자적 교체".
- 분석 요청은 항상 동일 스냅샷 1개를 참조.

## 3) Startup/Reload 위치

## 3-1) Startup (앱 시작)

`app/main.py`에서 FastAPI `lifespan` 또는 `startup` 이벤트 사용:

1. EFS/DB에서 business_keyword + alias 로드
2. 정규화
3. Stage1 index 생성
4. Stage2 Aho automaton build
5. app.state에 스냅샷 저장

## 3-2) Reload (운영 중 재로딩)

`app/api/v1/ops.py`에 예: `POST /ops/reload-keywords`

1. 백그라운드 또는 동기 reload 수행
2. 성공 시 app.state 스냅샷 교체
3. 실패 시 기존 스냅샷 유지 + 에러 로그

## 4) Stage별 구현 책임

## Stage1: Exact/Alias Index

작성 위치: `app/pipeline/mapper.py`

입력:
- keyword 원문, alias 목록

출력:
- `canon_norm_index`
- `alias_norm_index`

정규화 규칙:
- 반드시 Spring과 100% 동일 함수 사용
- 차이가 1개라도 나면 운영 오탐/미탐 발생

실무 팁:
- `dict[norm] -> list[keyword_id]`로 두고 다중충돌 허용
- 추후 priority로 최종 1건 선정

## Stage2: Aho-Corasick

작성 위치: `app/pipeline/extractor.py`

라이브러리:
- `pyahocorasick`

패턴:
- canon + alias 모두 등록 (필요 시 `match_mode`로 필터)

payload(필수):
- `keyword_id`
- `priority`
- `pattern_length`
- `source` (`CANON` | `ALIAS`)

검색 결과 후처리:
- 겹침(Overlapping) 처리 정책 명시
- 동일 위치 중복 매치 정리(긴 패턴 우선, priority 우선 등)

## Stage3: Damerau-Levenshtein

작성 위치: `app/pipeline/scorer.py`

라이브러리:
- `rapidfuzz.distance.DamerauLevenshtein.distance`

입력 후보:
- Stage2 히트 주변 토큰/구간
- 또는 Stage1/2에서 애매한 후보군

출력:
- distance / normalized score
- 임계치 통과 여부

권장:
- Stage2에서 후보를 강하게 줄인 뒤 Stage3 적용
- 전문 텍스트 전체에 Stage3 직접 적용 금지(비용 큼)

## 5) Analyze 흐름에 넣는 방식

작성 위치: `app/services/analyze_service.py`

요청 1건 처리 시:
1. 현재 스냅샷 참조
2. Stage1 exact hit 시 우선 확정
3. 미확정만 Stage2 실행
4. Stage2 결과 중 애매한 케이스만 Stage3 실행
5. 최종 키워드 목록 생성 후 결과 파일 저장

요약:
- Stage1: 빠른 정확 매칭
- Stage2: 빠른 대량 탐색
- Stage3: 비싼 정밀 판정

## 6) 설정값(필수)

`app/core/config.py`

- `keyword_reload_enabled: bool`
- `keyword_reload_interval_sec: int` (옵션)
- `dl_distance_threshold: int` 또는 `dl_score_threshold: float`
- `aho_case_sensitive: bool`
- `match_max_candidates: int`

## 7) 테스트 최소 기준

- normalizer parity test: Python vs Spring 동일 입력/출력
- index build test: 충돌/중복 alias 처리
- aho test: 겹침 패턴/긴 패턴 우선
- dl test: threshold 경계값
- e2e test: startup load -> analyze -> reload 후 analyze

## 8) 구현 순서 추천

1. normalizer parity 고정
2. Stage1 index 도입
3. Stage2 Aho 도입
4. Stage3 DL 도입
5. reload endpoint + 운영 메트릭

