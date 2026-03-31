"""member_llm_context 기반 product_type 가중치."""

from .constants import SEGMENT_WEIGHT_CONFIG
from .utils import infer_product_types_from_tag, segment_key_from_ctx


def compute_product_type_weights(ctx: dict) -> dict[str, float]:
    weights: dict[str, float] = {}
    seg = segment_key_from_ctx(ctx)
    cfg = SEGMENT_WEIGHT_CONFIG.get(seg, SEGMENT_WEIGHT_CONFIG["NORMAL"])

    current_types = ctx.get("current_product_types")
    if isinstance(current_types, dict):
        for ptype, val in current_types.items():
            if val:
                key = (str(ptype) or "").strip().upper()
                if not key:
                    continue
                w = cfg.get("current_type", 1.0)
                weights[key] = weights.get(key, 0.0) + w

    clicks = ctx.get("product_type_clicks")
    if isinstance(clicks, dict) and clicks:
        items: list[tuple[str, int]] = []
        for ptype, c in clicks.items():
            if c is None:
                continue
            try:
                count = int(c)
            except (TypeError, ValueError):
                continue
            key = (str(ptype) or "").strip().upper()
            if not key:
                continue
            items.append((key, count))
        total_clicks = sum(c for _, c in items)
        if total_clicks > 0:
            click_weight = cfg.get("click", 1.0)
            for key, count in items:
                share = count / total_clicks
                w = click_weight * share
                weights[key] = weights.get(key, 0.0) + w

    recent_tags = ctx.get("recent_viewed_tags_top_3")
    if isinstance(recent_tags, list) and recent_tags:
        tag_weight = cfg.get("tag", 1.0)
        for raw_tag in recent_tags[:3]:
            for key in infer_product_types_from_tag(str(raw_tag or "")):
                weights[key] = weights.get(key, 0.0) + tag_weight

    return weights


def product_type_boost_from_weights(weights: dict[str, float]) -> tuple[str, float, str, float]:
    if not weights:
        return ("", 0.0, "", 0.0)
    items = sorted(weights.items(), key=lambda kv: kv[1], reverse=True)
    t1, w1 = items[0]
    if len(items) >= 2:
        t2, w2 = items[1]
    else:
        t2, w2 = t1, 0.0

    boost_scale_1 = 0.2
    boost_scale_2 = 0.1

    boost1 = boost_scale_1 * w1 if w1 > 0 else 0.0
    boost2 = boost_scale_2 * w2 if w2 > 0 else 0.0

    t1 = (t1 or "").strip()
    t2 = (t2 or "").strip()
    if not t1 and not t2:
        return ("", 0.0, "", 0.0)
    if t1 and not t2:
        t2, boost2 = t1, 0.0
    return (t1, boost1, t2, boost2)
