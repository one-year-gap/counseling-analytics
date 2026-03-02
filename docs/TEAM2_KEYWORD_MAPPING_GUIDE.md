# Team2 Guide: 키워드 추출 + 매핑 알고리즘 구현

이 문서는 Team2가 FastAPI 서비스에 키워드 매핑 알고리즘을 붙일 때 필요한 기준을 정리합니다.

## 1) 구현 목표

현재 `matchedKeywords=[]` 상태를 아래 3단계 매칭으로 교체한다.

1. Stage1: 정규화 exact 매칭 (`canon/alias` 인덱스)
2. Stage2: Aho-Corasick 후보 추출
3. Stage3: Damerau-Levenshtein 정밀 판정

최종 출력은 `ResultRecord.matchedKeywords`에 채운다.

## 2) 반드시 먼저 확정할 것

1. Spring 정규화 규칙 문서
- Python 정규화 함수와 100% 동일해야 함
- 불일치 시 운영 오탐/미탐 발생

2. 키워드/별칭 원천 데이터 스키마
- 필수: `keyword_id`, `keyword_name`, `priority`, `alias_text`
- 선택: `match_mode`, `active`, `version`

3. 매칭 정책
- 같은 텍스트에 여러 후보가 걸리면 우선순위 규칙
- 겹침 매치 처리 규칙(긴 패턴 우선/priority 우선)
- Stage3 임계값

## 3) 파일별 책임 (현재 프로젝트 기준)

## 3-1) `app/pipeline/normalizer.py`

책임:
- Spring과 동일한 `normalize_text(text)` 구현

필수 함수:
- `normalize_text(text: str) -> str`

## 3-2) `app/pipeline/mapper.py` (Stage1)

책임:
- exact 매칭용 인덱스 생성

필수 구조:
- `canon_norm_index: dict[str, list[int]]`
- `alias_norm_index: dict[str, list[int]]`

권장 함수:
- `build_exact_indexes(keywords, aliases) -> tuple[dict, dict]`
- `match_exact(norm_text, canon_index, alias_index) -> list[candidate]`

## 3-3) `app/pipeline/extractor.py` (Stage2)

책임:
- Aho-Corasick 오토마톤 구성 + 후보 추출

라이브러리:
- `pyahocorasick`

오토마톤 payload 최소 필드:
- `keyword_id`
- `priority`
- `pattern_length`
- `source` (`CANON` | `ALIAS`)

권장 함수:
- `build_automaton(pattern_rows) -> automaton`
- `extract_candidates(text, automaton) -> list[candidate]`

## 3-4) `app/pipeline/scorer.py` (Stage3)

책임:
- Damerau-Levenshtein 기반 정밀 점수 계산

라이브러리:
- `rapidfuzz.distance.DamerauLevenshtein.distance`

권장 함수:
- `dl_distance(a, b) -> int`
- `dl_score(a, b) -> float` (정규화 점수)
- `is_match(score, threshold) -> bool`

## 3-5) `app/services/alias_loader_service.py`

책임:
- 앱 시작/리로드 시 키워드+alias 로딩
- Stage1/Stage2 준비물(인덱스/오토마톤) 생성
- 메모리 스냅샷 관리

권장 스냅샷:
- `canon_norm_index`
- `alias_norm_index`
- `aho_automaton`
- `keyword_meta`
- `loaded_at`, `version`

## 3-6) `app/services/analyze_service.py`

책임:
- 요청 처리 시 Stage1 -> Stage2 -> Stage3 순으로 적용
- 최종 후보를 `matchedKeywords`로 변환

처리 순서 권장:
1. Stage1 exact로 빠른 확정
2. 미확정 건에 Stage2 적용
3. 애매한 후보에만 Stage3 적용
4. 중복 제거 + 우선순위 정렬
5. `MatchedKeywordRecord` 작성

## 4) 앱 시작/리로드 연결

## Startup
- 위치: `app/main.py`
- 앱 시작 시 `alias_loader_service`로 스냅샷 로드

## Reload
- 위치: `app/api/v1/ops.py`
- `POST /ops/reload-keywords` 추가 권장
- 리로드 실패 시 기존 스냅샷 유지

## 5) 데이터/성능 가이드

1. Stage3는 비용이 크므로 후보 축소 후 수행
2. 오토마톤은 요청마다 빌드 금지(시작/리로드 시 1회 빌드)
3. 스냅샷 교체는 원자적으로 수행
4. `keyword_id` 기준 중복 제거 필수

## 6) 최소 테스트 체크리스트

1. 정규화 동일성 테스트
- 같은 입력에 Spring/Python 출력이 완전 동일

2. Stage1 테스트
- exact hit / no hit / 충돌(hit 다수) 검증

3. Stage2 테스트
- 겹침 매치 / 긴 패턴 우선 정책 검증

4. Stage3 테스트
- threshold 경계값 검증

5. 통합 테스트
- 상담 입력 1건 -> expected `matchedKeywords`와 동일

## 7) 구현 순서(추천)

1. `normalizer.py` 고정 (Spring parity)
2. `mapper.py` Stage1 완성
3. `extractor.py` Stage2 완성
4. `scorer.py` Stage3 완성
5. `alias_loader_service.py` 스냅샷 로딩 연결
6. `analyze_service.py`에서 단계 호출 통합
7. 테스트/벤치마크

## 8) 완료 정의(Definition of Done)

아래를 모두 만족하면 완료:

1. `matchedKeywords`가 실제 매칭 결과로 채워짐
2. 정규화 parity 테스트 통과
3. Stage1/2/3 단위 테스트 통과
4. E2E 테스트(샘플 상담셋) 통과
5. 리로드 후 신규 사전 반영 확인

