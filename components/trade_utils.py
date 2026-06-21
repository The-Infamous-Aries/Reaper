"""
Shared helpers for normalizing PnW trade rows/events.

PnW trade.buy_or_sell describes the posted offer side:
- buy:  sender posted a buy offer, receiver sold into it
- sell: sender posted a sell offer, receiver bought it
"""

from __future__ import annotations

from typing import Any, Dict, Optional


TRADE_RESOURCE_FIELDS = (
    "coal", "oil", "uranium", "iron", "bauxite", "lead",
    "gasoline", "munitions", "steel", "aluminum", "food", "credit",
)


def obj_to_dict(obj: Any) -> Dict[str, Any]:
    """Convert pnwkit objects and dict-like payloads to plain dictionaries."""
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, dict):
        return dict(obj)
    return vars(obj)


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if value is None:
        return {}
    try:
        return vars(value)
    except TypeError:
        return {}


def _to_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "accepted"}
    return False


def _clean_resource(resource: Any) -> Optional[str]:
    if not resource:
        return None
    name = str(resource).strip().lower()
    if name == "credits":
        return "credit"
    return name


def _identity_from_obj(obj: Dict[str, Any]) -> Dict[str, Any]:
    alliance = _as_dict(obj.get("alliance"))
    return {
        "id": _to_int(obj.get("id")),
        "name": obj.get("nation_name") or obj.get("name"),
        "flag": obj.get("flag"),
        "alliance_id": _to_int(alliance.get("id") or obj.get("alliance_id")),
        "alliance_name": alliance.get("name") or obj.get("alliance_name"),
        "alliance_flag": alliance.get("flag") or obj.get("alliance_flag"),
    }


def _merge_identity(base: Dict[str, Any], extra: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not extra:
        return base
    merged = dict(base)
    for key in ("name", "flag", "alliance_id", "alliance_name", "alliance_flag"):
        if merged.get(key) in (None, "") and extra.get(key) not in (None, ""):
            merged[key] = extra.get(key)
    return merged


def normalize_trade_event(
    event: Any,
    identity_by_id: Optional[Dict[int, Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """Normalize subscription or GraphQL trade payloads into one completed-trade shape."""
    trade = obj_to_dict(event)
    trade_id = _to_int(trade.get("id"))
    if not trade_id:
        return None

    buy_or_sell_raw = trade.get("buy_or_sell")
    buy_or_sell = str(buy_or_sell_raw or "").strip().lower()
    if buy_or_sell not in {"buy", "sell"}:
        if _to_bool(trade.get("buying")):
            buy_or_sell = "buy"
        elif _to_bool(trade.get("selling")):
            buy_or_sell = "sell"
        else:
            return None

    date_accepted = trade.get("date_accepted") or trade.get("accept_date")
    accepted = _to_bool(trade.get("accepted")) or bool(date_accepted)
    rejected = _to_bool(trade.get("rejected"))
    seller_cancelled = _to_bool(trade.get("seller_cancelled"))
    completed = accepted and not rejected and not seller_cancelled

    sender = _identity_from_obj(_as_dict(trade.get("sender")))
    receiver = _identity_from_obj(_as_dict(trade.get("receiver")))

    sender["id"] = _to_int(trade.get("sender_id")) or sender.get("id")
    receiver["id"] = (
        _to_int(trade.get("receiver_id"))
        or _to_int(trade.get("recipient_id"))
        or _to_int(trade.get("rid"))
        or receiver.get("id")
    )

    if buy_or_sell == "buy":
        buyer = sender
        seller = receiver
    else:
        buyer = receiver
        seller = sender

    nested_nation = _identity_from_obj(_as_dict(trade.get("nation")))
    nested_buyer = _identity_from_obj(_as_dict(trade.get("buyer_nation")))
    nested_seller = _identity_from_obj(_as_dict(trade.get("seller_nation")))
    if _to_bool(trade.get("buying")):
        buyer = _merge_identity(buyer, nested_nation)
        seller = _merge_identity(seller, nested_seller)
    elif _to_bool(trade.get("selling")):
        seller = _merge_identity(seller, nested_nation)
        buyer = _merge_identity(buyer, nested_buyer)

    if identity_by_id:
        buyer = _merge_identity(buyer, identity_by_id.get(int(buyer["id"] or 0)))
        seller = _merge_identity(seller, identity_by_id.get(int(seller["id"] or 0)))

    offer_resource = _clean_resource(trade.get("offer_resource"))
    offer_amount = _to_float(trade.get("offer_amount"))
    price_per_unit = _to_float(trade.get("price") or trade.get("ppu"))
    money_amount = _to_float(trade.get("money") or trade.get("total"))
    if money_amount <= 0 and offer_amount > 0 and price_per_unit > 0:
        money_amount = offer_amount * price_per_unit

    resources_traded = {r: _to_float(trade.get(r)) for r in TRADE_RESOURCE_FIELDS}
    if offer_resource and offer_amount > 0:
        resources_traded[offer_resource] = offer_amount

    total_resources = sum(v for v in resources_traded.values() if v > 0)
    if price_per_unit <= 0 and total_resources > 0 and money_amount > 0:
        price_per_unit = money_amount / total_resources

    return {
        "id": trade_id,
        "date": trade.get("date"),
        "date_accepted": date_accepted,
        "accepted": accepted,
        "completed": completed,
        "rejected": rejected,
        "seller_cancelled": seller_cancelled,
        "buy_or_sell": buy_or_sell,
        "buyer": buyer,
        "seller": seller,
        "buyer_id": buyer.get("id"),
        "seller_id": seller.get("id"),
        "money_amount": money_amount,
        "resources_traded": resources_traded,
        "price_per_unit": price_per_unit,
        "offer_resource": offer_resource,
        "offer_amount": offer_amount,
        "raw": trade,
    }


def normalized_trade_to_news_payload(normalized: Dict[str, Any]) -> Dict[str, Any]:
    """Return the payload expected by TradeNewsGenerator."""
    buyer = normalized["buyer"]
    seller = normalized["seller"]
    buying_offer = normalized["buy_or_sell"] == "buy"

    def nation_obj(identity: Dict[str, Any]) -> Dict[str, Any]:
        alliance = None
        if identity.get("alliance_id") or identity.get("alliance_name"):
            alliance = {
                "id": identity.get("alliance_id"),
                "name": identity.get("alliance_name"),
                "flag": identity.get("alliance_flag"),
            }
        return {
            "id": identity.get("id"),
            "nation_name": identity.get("name"),
            "flag": identity.get("flag"),
            "alliance": alliance,
        }

    payload = {
        "id": normalized["id"],
        "date": normalized.get("date"),
        "accept_date": normalized.get("date_accepted"),
        "buying": buying_offer,
        "selling": not buying_offer,
        "money": normalized.get("money_amount") or 0.0,
    }
    if buying_offer:
        payload["nation"] = nation_obj(buyer)
        payload["seller_nation"] = nation_obj(seller)
    else:
        payload["nation"] = nation_obj(seller)
        payload["buyer_nation"] = nation_obj(buyer)

    for resource, amount in normalized.get("resources_traded", {}).items():
        payload[resource] = amount
    return payload
