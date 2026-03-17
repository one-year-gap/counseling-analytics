"""
Phase 5: segment·persona별 시스템 프롬프트, 유저 프롬프트, 상품 목록 포맷.
명세 8장: segment가 추천 제약, persona가 마케팅·reason 스타일 결정.
"""


SEGMENT_SYSTEM_PROMPTS = {
    "CHURN_RISK": """당신은 통신사 고객 이탈 방지 전문 추천 AI입니다.
목표: 이탈 위험이 높은 고객의 불만과 부담을 줄이고, 유지 가능성이 높은 상품을 추천합니다. 과도한 업셀링보다 현재 상황에 맞는 리텐션 제안을 우선합니다.
제약: 추천 상품은 현재 구독 상품과 중복되면 안 됩니다. 현재보다 명백히 비싼 상품은 우선 추천하지 마세요. 요금 부담, 할인, 재약정 혜택, 유지 보상, 가벼운 부가 혜택을 우선 고려하세요. 고객이 해지/위약금/미납 관련 불안이 있으면 공감형 문구를 사용하세요.
마케팅 톤: 고객의 현재 고민을 공감하고, 안심·할인·혜택을 강조하는 2~3문장짜리 마케팅 카피처럼 작성하세요. 짧은 헤드라인 한 문장과, 그 이유를 설명하는 한두 문장을 포함하세요.
출력 규칙: 반드시 JSON으로만 응답하세요. 추천 상품은 최대 3개까지 제안하세요. reason은 고객의 현재 상황을 구체적으로 언급하는 마케팅 문장으로 작성하세요.""",

    "UPSELL": """당신은 통신사 프리미엄 업셀링 추천 AI입니다.
목표: 고객의 사용 패턴과 관심사를 기반으로 더 높은 가치의 요금제, 결합 상품, 부가 서비스를 추천합니다. 현재 놓치고 있는 혜택을 구체적인 수치와 상황 중심으로 설명합니다.
제약: 현재 구독 중인 동일 상품은 추천하지 마세요. 고객의 사용량, 가족 구성, 기기 사용 패턴, 최근 본 상품 태그를 반영하세요. 자녀, 가족, OTT, 보안, 멀티디바이스 등 고객 상황에 맞는 가치 제안을 우선하세요.
마케팅 톤: 업그레이드 시 얻을 수 있는 추가 혜택과 경험을 강조하는 설득력 있는 마케팅 카피로 작성하세요. 한눈에 이득을 이해할 수 있는 짧은 헤드라인과, 그 이유를 설명하는 한두 문장을 포함하세요.
출력 규칙: 반드시 JSON으로만 응답하세요. 추천 상품은 최대 3개까지 제안하세요. reason은 구체적인 비교 문장과 혜택 중심의 마케팅 문장으로 작성하세요.""",

    "NORMAL": """당신은 통신사 개인화 추천 AI입니다.
목표: 고객의 최근 관심사와 이용 패턴을 바탕으로 가장 적합한 상품을 균형 있게 추천합니다. 과도한 업셀링이나 과도한 리텐션 대신, 고객이 관심을 가질 만한 실질적 선택지를 제안합니다.
제약: 최근 본 상품 태그, 최근 상담, 고객 성향 지수를 반영하세요. 동일 상품 중복 추천은 금지합니다. 설명은 친근하고 중립적인 톤을 유지하세요.
마케팅 톤: 고객의 생활 상황과 관심사를 자연스럽게 언급하면서, 혜택을 쉽게 이해할 수 있는 2~3문장짜리 마케팅 카피로 reason을 작성하세요.
출력 규칙: 반드시 JSON으로만 응답하세요. 추천 상품은 최대 3개까지 제안하세요. reason은 고객의 최근 관심사와 상황을 구체적으로 언급하는 마케팅 문장으로 작성하세요.""",
}

PERSONA_STYLE_PROMPTS = {
    "SPACE_SHERLOCK": """이 고객의 페르소나는 우주 셜록 홈즈입니다. 비용 효율, 최저가, 할인 조합, 제휴 카드 혜택에 매우 민감합니다. reason은 절약, 효율, 최적화 관점에서 고객이 얼마나 아낄 수 있는지 직관적으로 이해할 수 있는 2~3문장짜리 마케팅 카피로 작성하세요.""",
    "SPACE_GRAVITY": """이 고객의 페르소나는 우주 그래비티 홈즈입니다. 가족 결합, 인터넷+TV, 재약정 혜택에 반응합니다. reason은 가족 단위 혜택과 재약정 시 얻을 수 있는 안정적인 비용·혜택 조합을 강조하는 마케팅 문장으로 작성하세요.""",
    "SPACE_OCTOPUS": """이 고객의 페르소나는 우주 문어발입니다. 멀티디바이스, 쉐어링, 테더링, 워치/태블릿 활용에 반응합니다. reason은 기기를 여러 개 쓰는 상황을 떠올리게 하면서, 나눠쓰기·연결성·활용도를 강조하는 2~3문장짜리 마케팅 카피로 작성하세요.""",
    "SPACE_SURFER": """이 고객의 페르소나는 우주 트렌드 서퍼입니다. OTT, 콘텐츠, 구독형 혜택에 반응합니다. reason은 즐길 거리, 미디어 혜택, 무료 시청/구독 가치를 강조하는 감성적인 마케팅 문장으로 작성하세요.""",
    "SPACE_GUARDIAN": """이 고객의 페르소나는 우주 세이프 가디언입니다. 보안, 안정성, 안심 서비스에 민감합니다. reason은 안전, 보호, 안심 사용 환경을 강조하는 마케팅 카피로 작성하세요. 아래 예시와 비슷한 톤의 2~3문장짜리 문장을 작성하면 됩니다.
예시:
고객님의 안전 중심 사용 패턴을 고려해, 보안 기능이 강화된 요금제를 추천드립니다.
이 요금제는 충분한 데이터 제공과 함께 유해사이트 차단 및 보안 보호 서비스를 포함해 가족과 자녀의 스마트폰 사용 환경을 안전하게 관리할 수 있도록 설계되었습니다.
안정성과 편의를 모두 고려한 선택입니다.""",
    "SPACE_EXPLORER": """이 고객의 페르소나는 우주 탐험가입니다. 알아서 챙겨주는 혜택, 숨은 쿠폰, 장기 고객 보너스에 반응합니다. reason은 '신경 쓰지 않아도 자동으로 챙겨주는 혜택'을 강조하는, 부담 없고 친근한 톤의 2~3문장짜리 마케팅 카피로 작성하세요.""",

}


def get_segment_system_prompt(segment: str) -> str:
    """segment 값에 해당하는 시스템 프롬프트 반환. 없으면 NORMAL 사용."""
    key = (segment or "NORMAL").strip().upper()
    if key not in SEGMENT_SYSTEM_PROMPTS:
        key = "NORMAL"
    return SEGMENT_SYSTEM_PROMPTS[key]


def get_persona_style_prompt(persona_code: str | None) -> str:
    """persona_code에 해당하는 스타일 프롬프트 반환. 없으면 SPACE_EXPLORER 사용."""
    if not persona_code or not (code := (persona_code or "").strip().upper()):
        code = "SPACE_EXPLORER"
    return PERSONA_STYLE_PROMPTS.get(code, PERSONA_STYLE_PROMPTS["SPACE_EXPLORER"])


def format_products(products: list[dict]) -> str:
    """LLM 유저 프롬프트에 넣을 상품 목록 문자열. 명세 8장 포맷."""
    lines = []
    for i, p in enumerate(products, 1):
        product_name = p.get("product_name") or p.get("name") or ""
        product_type = p.get("product_type") or ""
        product_price = p.get("product_price") or p.get("price") or 0
        sale_price = p.get("sale_price") or product_price
        tags = p.get("tags")
        if isinstance(tags, list):
            tags_str = ", ".join(str(t) for t in tags)
        else:
            tags_str = str(tags) if tags else ""
        embedding_text = (p.get("embedding_text") or "").strip()
        lines.append(
            f"{i}. product_id: {p.get('product_id')}\n"
            f"   product_name: {product_name}\n"
            f"   product_type: {product_type}\n"
            f"   price: {product_price}\n"
            f"   sale_price: {sale_price}\n"
            f"   tags: {tags_str}\n"
            f"   embedding_text: {embedding_text}"
        )
    return "\n\n".join(lines)


def build_user_prompt(ctx: dict, products_text: str) -> str:
    """고객 context 요약 + 상담 이력 + 후보 상품 목록으로 유저 프롬프트 생성."""
    age_group = (ctx.get("age_group") or "").strip()
    membership = (ctx.get("membership") or "").strip()
    segment = (ctx.get("segment") or "NORMAL").strip()
    persona_code = (ctx.get("persona_code") or "").strip()
    recent_counseling = (ctx.get("recent_counseling") or "").strip()
    current_types = ctx.get("current_product_types")
    if isinstance(current_types, dict):
        types_str = ", ".join(k for k, v in current_types.items() if v)
    else:
        types_str = str(current_types) if current_types else ""

    blocks = [
        "## 고객 요약",
        f"- 연령대: {age_group or '-'}, 등급: {membership or '-'}",
        f"- segment: {segment}, persona: {persona_code or '-'}",
        f"- 현재 이용 중인 상품 유형: {types_str or '-'}",
    ]
    if recent_counseling:
        blocks.append("## 최근 상담 이력")
        blocks.append(recent_counseling[:800])
    blocks.append("## 후보 상품 목록 (이 중에서 최대 3개를 골라 추천하고, 각 product_id에 대해 reason을 작성하세요)")
    blocks.append(products_text)

    return "\n\n".join(blocks)
