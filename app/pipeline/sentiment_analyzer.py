import logging
from typing import Any
from transformers import pipeline

logger = logging.getLogger(__name__)

class SentimentAnalyzer:
    """
    KoELECTRA 기반 감정 분석 모듈
    - 상담 텍스트의 문맥을 파악하여 긍정(POSITIVE) 또는 부정(NEGATIVE)을 반환
    """
    def __init__(self, model_name: str = "monologg/koelectra-small-finetuned-nsmc"):
        logger.info(f"KoELECTRA '{model_name}' 감정 분석 모델 로딩 시작...")
        # 파이프라인 초기화: 서버가 켜질 때 딱 한 번만 무거운 모델을 메모리에 올림
        self.classifier = pipeline("sentiment-analysis", model=model_name)
        logger.info("KoELECTRA 모델 로딩 완료!")

    def analyze(self, text: str) -> str:
        """
        텍스트의 긍정/부정을 판단하여 'POSITIVE' 또는 'NEGATIVE'로만 반환
        (중립/단순 문의는 POSITIVE로 간주)
        """
        # 1. 빈 문자열이나 공백은 악의/불만이 없으므로 POSITIVE 처리
        if not text or not text.strip():
            return "POSITIVE"

        try:
            truncated_text = text[:500] 
            
            # 파이프라인 감정 분석 수행
            result = self.classifier(truncated_text)[0]
            label = str(result['label']).lower()
            score = float(result['score']) # 모델의 확신도 (0.0 ~ 1.0)
            
            # 2. 모델이 긍정이라고 하면 그대로 POSITIVE
            if label in ['positive', '1']:
                return "POSITIVE"
            
            # 3. 모델이 부정(NEGATIVE)이라고 한 경우의 룰 기반(Rule-based) 보정
            else:
                # 확신도가 80%(0.80) 미만인 '약한 부정'은 단순 문의일 확률이 높음
                # 이탈 위험이 아니라고 판단하여 POSITIVE로 끌어올림
                if score < 0.80:
                    return "POSITIVE"
                
                # 확신도가 80% 이상인 '강한 부정'만 진짜 NEGATIVE로 반환
                return "NEGATIVE"
                
        except Exception as e:
            logger.error(f"감정 분석 중 오류 발생: {e}", exc_info=True)
            # 시스템 에러 시 이탈로 잘못 잡히지 않도록 기본값 POSITIVE 반환
            return "POSITIVE"


# 테스트 코드
if __name__ == "__main__":
    # 로깅 설정
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    
    print("\n" + "="*50)
    print("감정 분석 모델 로컬 테스트를 시작합니다!")
    print("="*50)
    
    # 1. 모델 인스턴스 생성 (최초 실행 시 허깅페이스에서 모델 다운로드 발생)
    analyzer = SentimentAnalyzer()
    
    # 2. 상담 데이터
    test_cases = [
        "요금이 이번 달에 왜 이렇게 많이 나왔어요? 진짜 짜증나네요 빨리 확인해주세요.", # 명백한 부정
        "상담사님이 너무 친절하게 안내해주셔서 문제 잘 해결했습니다! 감사합니다~",    # 명백한 긍정
        "인터넷 연결이 자꾸 끊깁니다. 업무를 할 수가 없어요.",                  # 불만 (부정)
        "앱에서 자동이체 계좌 변경하는 방법 좀 알려주실 수 있나요?",             # 단순 문의
        "",                                                         # 예외 케이스 (빈 문자열)
        "인터넷 속도 문의 요즘 인터넷 속도가 너무 느려요. 요금조회 해보고 싶은데 어떻게 하나요?"
    ]
    
    print("\n--- 분석 결과 ---")
    for idx, text in enumerate(test_cases, 1):
        sentiment = analyzer.analyze(text)
        print(f"[{idx}] 원문: '{text}'")
        print(f"    ➔ 판별 결과: {sentiment}\n")