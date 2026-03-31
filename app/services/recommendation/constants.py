"""추천 파이프라인 SQL·상수."""

from sqlalchemy import bindparam, text

FETCH_MEMBER_LLM_CONTEXT_SQL = text("""
SELECT
    member_id, membership, age_group, join_months, children_count,
    family_group_num, family_role, persona_code, segment,
    current_subscriptions, current_product_types, product_type_clicks, current_data_usage_ratio,
    data_usage_pattern, churn_score, churn_tier, recent_counseling,
    recent_viewed_tags_top_3, contract_expiry_within_3m, updated_at
FROM member_llm_context
WHERE member_id = :member_id
""")

FETCH_SUBSCRIPTION_PRICES_SQL = text("""
SELECT product_id, price, sale_price, product_type
FROM product
WHERE product_id IN :ids
""").bindparams(bindparam("ids", expanding=True))

SEARCH_SIMILAR_SQL = text("""
SELECT product_id
FROM product
WHERE embedding_vector IS NOT NULL
  AND (NOT (product_id = ANY(:exclude_ids)))
ORDER BY embedding_vector <#> :query_vec
LIMIT :k
""")

SEARCH_SIMILAR_WITH_TYPE_BOOST_SQL = text("""
SELECT product_id
FROM product
WHERE embedding_vector IS NOT NULL
  AND (NOT (product_id = ANY(:exclude_ids)))
ORDER BY (embedding_vector <#> :query_vec)
  - (CASE
       WHEN product_type = :boost_type1 THEN :boost1
       WHEN product_type = :boost_type2 THEN :boost2
       ELSE 0
     END)
LIMIT :k
""")

SEARCH_SIMILAR_MAIN_TYPES_WINDOW_SQL = text("""
SELECT product_id, product_type, rn
FROM (
  SELECT
    product_id,
    product_type,
    ROW_NUMBER() OVER (
      PARTITION BY product_type
      ORDER BY embedding_vector <#> :query_vec
    ) AS rn
  FROM product
  WHERE embedding_vector IS NOT NULL
    AND product_type IN :main_types
    AND (NOT (product_id = ANY(:exclude_ids)))
) ranked
WHERE ranked.rn <= :per_type_k
""").bindparams(bindparam("main_types", expanding=True))

FETCH_PRODUCTS_FULL_SQL = text("""
SELECT
    p.product_id, p.name, p.product_type, p.price, p.sale_price, p.tags, p.embedding_text,
    COALESCE(mp.data_amount, tw.data_amount) AS data_amount
FROM product p
LEFT JOIN mobile_plan mp ON p.product_id = mp.product_id
LEFT JOIN tab_watch_plan tw ON p.product_id = tw.product_id
WHERE p.product_id IN :ids
""").bindparams(bindparam("ids", expanding=True))

FETCH_DEFAULT_PRODUCTS_SQL = text("""
SELECT
    p.product_id, p.name, p.product_type, p.price, p.sale_price, p.tags, p.embedding_text,
    NULL::integer AS data_amount
FROM product p
WHERE p.embedding_text IS NOT NULL
ORDER BY p.product_id
LIMIT :k
""")

RETRIEVAL_CANDIDATES_K = 30

MAIN_PRODUCT_TYPES: tuple[str, ...] = (
    "MOBILE_PLAN",
    "INTERNET",
    "IPTV",
    "TAB_WATCH_PLAN",
    "ADDON",
)
RETRIEVAL_PER_TYPE_K = 10

DEFAULT_RETRIEVAL_QUERY = "통신 요금제, 데이터 요금제, 부가서비스 추천"

EMBEDDING_DIMENSION = 1536

UNLIMITED_DATA_TAG_MARKER = "무제한"

MAX_PRODUCTS_PER_TYPE = 2

DEFAULT_PRODUCT_REASON_TEXT = "고객님께 가장 적합한 상품을 추천드립니다!"
NO_CANDIDATE_MESSAGE = "추천할 수 있는 상품이 없습니다."
NO_MATCHED_MESSAGE = "조건에 맞는 추천 상품이 없습니다."
FALLBACK_CACHED_MESSAGE = "고객님의 이용 패턴과 관심사를 반영한 요금제·부가서비스 추천입니다."
FALLBACK_VECTOR_SUMMARY = "고객님께 어울리는 상품을 추천해드릴게요!"

CHURN_MAX_PRICE_RATIO = 1.1

SEGMENT_WEIGHT_CONFIG: dict[str, dict[str, float]] = {
    "CHURN_RISK": {
        "current_type": 1.5,
        "click": 0.7,
        "tag": 0.5,
    },
    "UPSELL": {
        "current_type": 1.0,
        "click": 1.5,
        "tag": 1.2,
    },
    "NORMAL": {
        "current_type": 0.8,
        "click": 1.3,
        "tag": 1.3,
    },
}
