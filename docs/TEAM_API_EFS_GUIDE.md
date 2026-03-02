# 우리 팀용 쉬운 가이드 (Spring -> FastAPI -> EFS)

이 문서는 어렵게 쓰지 않고, "무엇을 어디에 넣어야 하는지"만 설명합니다.

## 1) Spring이 FastAPI로 보내는 값

Spring은 아래 3개만 보내면 됩니다.

```json
{
  "requestId": "req-001",
  "jobInstanceId": "job-1001",
  "analysisVersion": "v1"
}
```

- `requestId`: 이번 요청 이름표
- `jobInstanceId`: 이번 배치 폴더 이름
- `analysisVersion`: 어떤 키워드 사전을 쓸지 버전

## 2) EFS에 미리 있어야 하는 입력 파일

기준 폴더: `/mnt/efs/analysis`

### 2-1) 상담 입력 파일

폴더:
- `/mnt/efs/analysis/req/{jobInstanceId}/`

파일 이름:
- `{chunkId}.input.jsonl.gz`

의미:
- chunk 파일 1개 = 상담 여러 건
- JSONL이라서 "한 줄 = 상담 1건"

상담 1줄 예시:
```json
{"caseId":1,"memberId":101,"categoryCode":"A01","title":"불안 상담","questionText":"요즘 잠이 안 와요","answerText":"수면 위생을 지켜보세요","status":"OPEN"}
```

### 2-2) 키워드/별칭 사전 파일

파일:
- `/mnt/efs/analysis/ref/{analysisVersion}.alias.jsonl.gz`

예: analysisVersion이 `v1`이면
- `/mnt/efs/analysis/ref/v1.alias.jsonl.gz`

한 줄 예시:
```json
{
  "businessKeywordId": 10,
  "keywordCode": "SLEEP",
  "keywordName": "수면문제",
  "aliases": [
    {"aliasId": 1, "aliasText": "잠이 안 와", "aliasNorm": "잠이 안 와"},
    {"aliasId": 2, "aliasText": "불면", "aliasNorm": "불면"}
  ]
}
```

## 3) FastAPI가 하는 일

1. `jobInstanceId` 폴더 안에 있는 모든 chunk 파일을 찾음
2. 각 상담 문장에서 alias가 몇 번 나오는지 셈
3. 결과를 EFS에 저장
4. 이미 결과가 있으면 그 chunk는 건너뜀(skip)

## 4) EFS 출력 파일

폴더:
- `/mnt/efs/analysis/res/{jobInstanceId}/`

chunk마다 2개 파일 생성:
- `{chunkId}.mapping.jsonl.gz` (상담별 결과)
- `{chunkId}.chunk.json` (요약)

## 5) 상담별 결과 형식 (중요)

`mapping.jsonl.gz` 안에서 한 줄은 상담 1건 결과입니다.

예시:
```json
{
  "requestId": "req-001",
  "jobInstanceId": "job-1001",
  "chunkId": "0001",
  "caseId": 1,
  "memberId": 101,
  "matchedKeywords": [
    {"businessKeywordId": 10, "keywordCode": "SLEEP", "keywordName": "수면문제", "count": 2},
    {"businessKeywordId": 20, "keywordCode": "ANX", "keywordName": "불안", "count": 3}
  ],
  "analysisVersion": "v1",
  "processedAt": "2026-03-02T01:23:45Z"
}
```

뜻:
- `caseId=1` 상담에서
- `수면문제`는 2번,
- `불안`은 3번 발견됨

## 6) "처리 완료"는 어떻게 판단하나?

아래 2개 파일이 둘 다 있으면, 그 chunk는 이미 처리한 것으로 봅니다.

- `{chunkId}.mapping.jsonl.gz`
- `{chunkId}.chunk.json`

그래서 다음 실행 때는 자동으로 skip 합니다.

## 7) 자주 나는 실수

1. `analysisVersion` 파일이 없음
- `/analysis/ref/{analysisVersion}.alias.jsonl.gz` 파일이 꼭 있어야 함

2. 파일 이름 규칙 안 맞음
- 입력은 반드시 `{chunkId}.input.jsonl.gz`

3. JSONL 형식 아님
- 배열 JSON이 아니라, 줄마다 JSON 1개여야 함

