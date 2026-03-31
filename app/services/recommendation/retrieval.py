"""pgvector 검색·구독 가격 조회."""

from sqlalchemy.ext.asyncio import AsyncSession

from .constants import (
    FETCH_SUBSCRIPTION_PRICES_SQL,
    MAIN_PRODUCT_TYPES,
    SEARCH_SIMILAR_MAIN_TYPES_WINDOW_SQL,
)
from .utils import exclude_ids_from_context


async def retrieve_product_ids_per_main_type_window(
    session: AsyncSession,
    query_vec: list[float],
    exclude_ids: list[int],
    per_type_k: int,
) -> list[int]:
    result = await session.execute(
        SEARCH_SIMILAR_MAIN_TYPES_WINDOW_SQL,
        {
            "query_vec": query_vec,
            "exclude_ids": exclude_ids,
            "per_type_k": per_type_k,
            "main_types": list(MAIN_PRODUCT_TYPES),
        },
    )
    rows = result.fetchall()
    by_type: dict[str, list[tuple[int, int]]] = {}
    for row in rows:
        pid = int(row[0])
        ptype = (str(row[1]) if row[1] is not None else "").strip().upper()
        rn = int(row[2])
        by_type.setdefault(ptype, []).append((pid, rn))
    for key in by_type:
        by_type[key].sort(key=lambda x: x[1])
    product_ids: list[int] = []
    seen: set[int] = set()
    for ptype in MAIN_PRODUCT_TYPES:
        for pid, _ in by_type.get(ptype, []):
            if pid not in seen:
                product_ids.append(pid)
                seen.add(pid)
    return product_ids


async def get_subscription_max_price_by_type(session: AsyncSession, ctx: dict) -> dict[str, int]:
    exclude_ids = exclude_ids_from_context(ctx)
    if not exclude_ids or exclude_ids == [0]:
        return {}

    result = await session.execute(FETCH_SUBSCRIPTION_PRICES_SQL, {"ids": exclude_ids})
    by_type: dict[str, int] = {}
    for row in result.mappings():
        r = dict(row)
        ptype = (r.get("product_type") or "").strip()
        if not ptype:
            continue
        sale = r.get("sale_price")
        price = r.get("price")
        val = int(sale if sale is not None else price or 0)
        if ptype not in by_type or by_type[ptype] < val:
            by_type[ptype] = val
    return by_type
