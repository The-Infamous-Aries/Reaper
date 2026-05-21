"""
HoldingsDB -- adapter over GlobalNationsDB nations table.

ALL cash/resource/military data lives in GlobalNations.db (one file, all nations).
IRSNations.db is the NW-only snapshot DB managed by nations_subscription — HoldingsDB
never touches it. This eliminates phantom NW rows for non-NW nations and the
confusion of dual-write paths.

Column mapping (holdings API -> nations table):
  money_held      -> money
  coal_held       -> coal  (and all other resources)
  soldiers_held   -> soldiers  (and all other military units)

Extra tracking columns added to nations table via migration:
  confidence        TEXT DEFAULT 'seeded'
  last_loot_date    TEXT
  last_bankrec_date TEXT
  last_revenue_date TEXT
  last_event_date   TEXT

Loot formula (apply_loot_event):
  loot_pct = base(war_type) × att_policy_mult × ape_mult × def_policy_mult
  looted   = holdings × loot_pct          (what the attacker takes)
  remaining = holdings - looted           (what the defender has left)
  → defender SET to remaining = looted × (1/loot_pct - 1)
  → attacker ADD looted amounts

Now inherits from BaseDB for unified async patterns and connection management.
"""

import sqlite3
import logging
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from .base_db import BaseDB, AsyncMode

logger = logging.getLogger(__name__)

RESOURCE_COLS = (
    "coal", "oil", "uranium", "iron", "bauxite", "lead",
    "gasoline", "munitions", "steel", "aluminum", "food",
)
MILITARY_COLS = ("soldiers", "tanks", "aircraft", "ships", "missiles", "nukes", "spies")

# War-type base loot percentages — used by apply_loot_event to back-calculate
# the defender's exact post-loot balance via: remaining = looted * (1/pct - 1)
_WAR_TYPE_BASE: Dict[str, float] = {
    "raid":      0.075,
    "ordinary":  0.050,
    "attrition": 0.060,
}
_DEFAULT_BASE = 0.075

# Military unit purchase costs (cash + resources per unit)
MILITARY_COSTS: Dict[str, Dict[str, float]] = {
    "soldiers": {"cash": 5.0},
    "tanks":    {"cash": 60.0,      "steel": 0.5},
    "aircraft": {"cash": 4000.0,    "aluminum": 10.0},
    "ships":    {"cash": 50000.0,   "steel": 30.0},
    "missiles": {"cash": 150000.0,  "gasoline": 100.0, "munitions": 100.0, "aluminum": 150.0},
    "nukes":    {"cash": 1750000.0, "uranium": 500.0,  "gasoline": 500.0,  "aluminum": 1000.0},
    "spies":    {"cash": 50000.0},
}


def _calc_loot_pct(
    war_type: Optional[str] = None,
    att_war_policy: Optional[str] = None,
    def_war_policy: Optional[str] = None,
    att_has_ape: bool = False,
) -> float:
    """
    Return the fraction of a defender's holdings looted per ground-win attack.

    Multipliers:
      Pirate war policy (attacker): ×1.4
      Advanced Pirate Economy (attacker project): ×1.1
      Turtle war policy (defender): ×1.2  (defender loses 20% more loot)
      Moneybags war policy (defender): ×0.6  (defender keeps more)
    """
    wt   = (war_type or "").lower().replace("_war", "").replace(" ", "_")
    base = _WAR_TYPE_BASE.get(wt, _DEFAULT_BASE)
    mult = 1.0
    if (att_war_policy or "").lower() == "pirate":
        mult *= 1.4
    if att_has_ape:
        mult *= 1.1
    if (def_war_policy or "").lower() == "turtle":
        mult *= 1.2
    if (def_war_policy or "").lower() == "moneybags":
        mult *= 0.6
    return base * mult


class HoldingsDB(BaseDB):
    """
    Single-DB adapter: all holdings data lives in GlobalNations.db.
    Never writes to IRSNations.db — that DB is managed exclusively by
    nations_subscription for NW-member snapshots.

    Now inherits from BaseDB for unified async patterns and connection management.
    """

    def __init__(self, db_path: str):
        """
        Initialize HoldingsDB with BaseDB infrastructure.
        
        Args:
            db_path: Path to the database (kept for backward compat; actual storage is in GLOBAL_NATIONS_DB)
        """
        from Systems.Functions.db_paths import GLOBAL_NATIONS_DB_STR
        # Always use GlobalNations.db — that's where the nations table lives.
        # The db_path argument is accepted for backward-compat but ignored;
        # overwriting self.db_path after super().__init__ was the root cause
        # of the "no such table: nations" errors.
        super().__init__(
            db_path=GLOBAL_NATIONS_DB_STR,
            async_mode=AsyncMode.THREAD_POOL,
            wal_mode=True,
            synchronous="NORMAL",
            busy_timeout=15000,
            wal_autocheckpoint=1000,
            enable_locking=True,
            use_lock_manager=True,
        )
        # self.db_path is already GLOBAL_NATIONS_DB_STR — do NOT overwrite it.
        self._global_path = GLOBAL_NATIONS_DB_STR
        # Ensure extra columns exist
        self._ensure_extra_columns()

    # ── Schema migration ──────────────────────────────────────────────────────

    def _ensure_extra_columns(self):
        """Add tracking columns to GlobalNations.db if not present."""
        extra = [
            ("confidence",        "TEXT DEFAULT 'seeded'"),
            ("last_loot_date",    "TEXT"),
            ("last_bankrec_date", "TEXT"),
            ("last_revenue_date", "TEXT"),
            ("last_event_date",   "TEXT"),
            ("alliance_flag",     "TEXT"),
        ]
        try:
            with self._get_connection() as conn:
                for col, typedef in extra:
                    try:
                        conn.execute(f"ALTER TABLE nations ADD COLUMN {col} {typedef}")
                    except sqlite3.OperationalError:
                        pass  # already exists
                conn.execute(
                    "UPDATE nations SET confidence='seeded' WHERE confidence IS NULL"
                )
                conn.commit()
        except Exception as e:
            logger.warning(f"HoldingsDB._ensure_extra_columns: {e}")

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    def _conn(self) -> sqlite3.Connection:
        """Get a configured connection using BaseDB infrastructure."""
        return self._get_connection()

    def _row_to_holdings(self, row: sqlite3.Row) -> Dict[str, Any]:
        """Convert a nations table row to the holdings dict format consumers expect."""
        d = dict(row)
        result = {
            "nation_id":          d.get("id"),
            "nation_name":        d.get("nation_name"),
            "money_held":         float(d.get("money") or 0),
            "confidence":         d.get("confidence") or "seeded",
            "last_loot_date":     d.get("last_loot_date"),
            "last_bankrec_date":  d.get("last_bankrec_date"),
            "last_revenue_date":  d.get("last_revenue_date"),
            "last_event_date":    d.get("last_event_date"),
        }
        for r in RESOURCE_COLS:
            result[f"{r}_held"] = float(d.get(r) or 0)
        for m in MILITARY_COLS:
            result[f"{m}_held"] = int(d.get(m) or 0)
        return result

    def _ensure_row(self, conn: sqlite3.Connection, nation_id: int, nation_name: Optional[str]):
        """INSERT OR IGNORE a minimal row so UPDATE has something to hit."""
        conn.execute(
            "INSERT OR IGNORE INTO nations (id, nation_name, confidence) VALUES (?,?,?)",
            (nation_id, nation_name or None, "seeded"),
        )

    # ── Public API ────────────────────────────────────────────────────────────

    async def ensure_nation(self, nation_id: int, nation_name: Optional[str] = None) -> bool:
        """Ensure a row exists in GlobalNations.db. INSERT OR IGNORE."""
        def _work():
            with self._conn() as conn:
                self._ensure_row(conn, nation_id, nation_name)
                conn.commit()
        try:
            await self._run_sync(_work)
            return True
        except Exception as e:
            logger.error(f"ensure_nation({nation_id}): {e}")
            return False

    async def get_holdings(self, nation_id: int) -> Optional[Dict[str, Any]]:
        def _work():
            with self._conn() as conn:
                row = conn.execute("SELECT * FROM nations WHERE id=?", (nation_id,)).fetchone()
                return self._row_to_holdings(row) if row else None
        try:
            return await self._run_sync(_work)
        except Exception as e:
            logger.error(f"get_holdings({nation_id}): {e}")
            return None

    async def get_holdings_bulk(self, nation_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        if not nation_ids:
            return {}
        def _work():
            ph = ",".join("?" * len(nation_ids))
            with self._conn() as conn:
                rows = conn.execute(
                    f"SELECT * FROM nations WHERE id IN ({ph})", nation_ids
                ).fetchall()
                return {int(r["id"]): self._row_to_holdings(r) for r in rows}
        try:
            return await self._run_sync(_work)
        except Exception as e:
            logger.error(f"get_holdings_bulk: {e}")
            return {}

    async def get_all_tracked_nation_ids(self) -> List[int]:
        def _work():
            with self._conn() as conn:
                rows = conn.execute("SELECT id FROM nations").fetchall()
                return [int(r[0]) for r in rows]
        try:
            return await self._run_sync(_work)
        except Exception as e:
            logger.error(f"get_all_tracked_nation_ids: {e}")
            return []

    async def get_stats(self) -> Dict[str, Any]:
        def _work():
            with self._conn() as conn:
                total = conn.execute("SELECT COUNT(*) FROM nations").fetchone()[0]
                by_conf = conn.execute(
                    "SELECT confidence, COUNT(*) FROM nations GROUP BY confidence"
                ).fetchall()
                return {
                    "total_nations": total,
                    "by_confidence": {r[0]: r[1] for r in by_conf},
                }
        try:
            return await self._run_sync(_work)
        except Exception as e:
            logger.error(f"get_stats: {e}")
            return {}

    async def apply_loot_event(
        self,
        attacker_id: int,
        defender_id: int,
        money_looted: float,
        resources_looted: Dict[str, float],
        loot_date: str,
        war_type: Optional[str] = None,
        att_war_policy: Optional[str] = None,
        def_war_policy: Optional[str] = None,
        att_has_ape: bool = False,
        attacker_name: Optional[str] = None,
        defender_name: Optional[str] = None,
    ) -> bool:
        """
        On a ground-win attack:
          - Defender: SET holdings to the back-calculated post-loot value.
            We know exactly what was looted and the loot percentage, so we can
            derive the defender's exact remaining balance:
              remaining = looted * (1/loot_pct - 1)
            This gives a fresh, accurate baseline regardless of prior drift.
            Mark confidence='fresh' and record last_loot_date.
          - Attacker: ADD looted amounts to their holdings.

        Using SET (not DEDUCT) for the defender is critical: it resets their
        holdings to a known-correct value after each loot, preventing compounding
        errors from prior drift. The loot percentage is calculated from war_type,
        attacker policy, APE project, and defender policy.
        """
        total = money_looted + sum(resources_looted.get(r, 0.0) for r in RESOURCE_COLS)
        if total <= 0:
            return True

        loot_date_str = str(loot_date or self._now()).replace("T", " ")

        # ── Calculate loot percentage to back-derive defender's remaining balance ──
        loot_pct = _calc_loot_pct(war_type, att_war_policy, def_war_policy, att_has_ape)

        # remaining = looted * (1/loot_pct - 1)
        # Guard against division by zero (loot_pct should always be > 0)
        if loot_pct > 0:
            money_remaining = money_looted * (1.0 / loot_pct - 1.0)
            rss_remaining   = {
                r: resources_looted.get(r, 0.0) * (1.0 / loot_pct - 1.0)
                for r in RESOURCE_COLS
            }
        else:
            # Fallback: can't back-calculate, floor at 0
            money_remaining = 0.0
            rss_remaining   = {r: 0.0 for r in RESOURCE_COLS}

        # Sanity floor — remaining can't be negative
        money_remaining = max(0.0, money_remaining)
        rss_remaining   = {r: max(0.0, v) for r, v in rss_remaining.items()}

        def _work():
            with self._conn() as conn:
                # Ensure both rows exist
                self._ensure_row(conn, defender_id, defender_name)
                self._ensure_row(conn, attacker_id, attacker_name)

                # ── Defender: SET to back-calculated post-loot balance ────────
                # Build a single UPDATE covering money + all resources atomically
                # so a partial failure can't leave money SET but resources stale.
                def_rss_parts = ", ".join(f"{r}=?" for r in RESOURCE_COLS)
                def_rss_vals  = [max(0.0, rss_remaining.get(r, 0.0)) for r in RESOURCE_COLS]
                conn.execute(
                    f"UPDATE nations SET "
                    f"money=?, {def_rss_parts}, "
                    f"confidence='fresh', "
                    f"last_loot_date=?, "
                    f"last_event_date=? "
                    f"WHERE id=?",
                    [money_remaining] + def_rss_vals + [loot_date_str, loot_date_str, defender_id],
                )

                # ── Attacker: ADD looted money + resources in one statement ───
                att_rss_parts = []
                att_rss_vals  = []
                for r in RESOURCE_COLS:
                    v = resources_looted.get(r, 0.0)
                    if v > 0:
                        att_rss_parts.append(f"{r}=MAX(0, COALESCE({r},0)+?)")
                        att_rss_vals.append(v)
                att_extra = (", " + ", ".join(att_rss_parts)) if att_rss_parts else ""
                conn.execute(
                    f"UPDATE nations SET "
                    f"money=MAX(0, COALESCE(money,0)+?), "
                    f"confidence=CASE WHEN confidence='seeded' THEN 'tracked' ELSE confidence END, "
                    f"last_event_date=?"
                    f"{att_extra} WHERE id=?",
                    [money_looted, loot_date_str] + att_rss_vals + [attacker_id],
                )

                conn.commit()

        try:
            await self._run_sync(_work)
            logger.info(
                f"Holdings loot SET: att={attacker_id}({attacker_name}) "
                f"def={defender_id}({defender_name}) "
                f"war_type={war_type} loot_pct={loot_pct:.4f} "
                f"money_looted=${money_looted:,.0f} → def_remaining=${money_remaining:,.0f}"
                + (
                    " | resources looted: " + ", ".join(
                        f"{r}={v:,.2f}" for r, v in resources_looted.items() if v > 0
                    ) if any(v > 0 for v in resources_looted.values()) else ""
                )
            )
            return True
        except Exception as e:
            logger.error(
                f"apply_loot_event(att={attacker_id}, def={defender_id}): {e}",
                exc_info=True,
            )
            return False

    async def apply_bankrec(self, rec: Dict[str, Any]) -> bool:
        """Apply a bank record: deduct from sender nation, add to receiver nation.

        Deposit  (nation→alliance): sender_type=1, receiver_type=2 — deduct from nation.
        Withdrawal (alliance→nation): sender_type=2, receiver_type=1 — add to nation.
        Transfer (nation→nation): both type=1 — deduct from sender, add to receiver.
        """
        sender_id   = rec.get("sender_id")
        sender_type = int(rec.get("sender_type") or 0)
        recv_id     = rec.get("receiver_id")
        recv_type   = int(rec.get("receiver_type") or 0)

        # sender_type/receiver_type == 1 means nation; 2 means alliance bank
        parties = []
        if sender_id and sender_type == 1:
            parties.append((int(sender_id), -1))
        if recv_id and recv_type == 1:
            parties.append((int(recv_id), +1))
        if not parties:
            return True

        rec_date = str(rec.get("date") or self._now()).replace("T", " ")
        money    = float(rec.get("money") or 0)
        rss      = {r: float(rec.get(r) or 0) for r in RESOURCE_COLS}

        def _work():
            with self._conn() as conn:
                for nation_id, sign in parties:
                    self._ensure_row(conn, nation_id, None)
                    if sign > 0:
                        conn.execute(
                            "UPDATE nations SET "
                            "money=COALESCE(money,0)+?, "
                            "confidence=CASE WHEN confidence='seeded' THEN 'tracked' ELSE confidence END, "
                            "last_bankrec_date=?, last_event_date=? WHERE id=?",
                            (money, rec_date, rec_date, nation_id),
                        )
                    else:
                        conn.execute(
                            "UPDATE nations SET "
                            "money=MAX(0, COALESCE(money,0)-?), "
                            "confidence=CASE WHEN confidence='seeded' THEN 'tracked' ELSE confidence END, "
                            "last_bankrec_date=?, last_event_date=? WHERE id=?",
                            (money, rec_date, rec_date, nation_id),
                        )
                    for r, v in rss.items():
                        if v != 0:
                            if sign > 0:
                                conn.execute(
                                    f"UPDATE nations SET {r}=COALESCE({r},0)+? WHERE id=?",
                                    (v, nation_id),
                                )
                            else:
                                conn.execute(
                                    f"UPDATE nations SET {r}=MAX(0, COALESCE({r},0)-?) WHERE id=?",
                                    (v, nation_id),
                                )
                conn.commit()

        try:
            await self._run_sync(_work)
            return True
        except Exception as e:
            logger.error(f"apply_bankrec: {e}", exc_info=True)
            return False

    async def apply_turn_revenue(
        self,
        nation_id: int,
        money_delta: float,
        resource_deltas: Dict[str, float],
        turn_date: str,
        nation_name: Optional[str] = None,
    ) -> bool:
        """Apply one turn of revenue to a nation in GlobalNations.db."""
        def _work():
            with self._conn() as conn:
                self._ensure_row(conn, nation_id, nation_name)
                conn.execute(
                    "UPDATE nations SET "
                    "money=COALESCE(money,0)+?, "
                    "confidence=CASE WHEN confidence='seeded' THEN 'tracked' ELSE confidence END, "
                    "last_revenue_date=?, last_event_date=? WHERE id=?",
                    (money_delta, turn_date, turn_date, nation_id),
                )
                for r, v in resource_deltas.items():
                    if v != 0 and r in RESOURCE_COLS:
                        conn.execute(
                            f"UPDATE nations SET {r}=MAX(0, COALESCE({r},0)+?) WHERE id=?",
                            (v, nation_id),
                        )
                conn.commit()
        try:
            await self._run_sync(_work)
            return True
        except Exception as e:
            logger.error(f"apply_turn_revenue({nation_id}): {e}", exc_info=True)
            return False

    async def deduct_spending(
        self,
        nation_id: int,
        cash_cost: float,
        event_type: str,
        description: str = "",
        event_date: Optional[str] = None,
        nation_name: Optional[str] = None,
        item_type: Optional[str] = None,
        item_quantity: Optional[float] = None,
        item_details: Optional[str] = None,
        resource_costs: Optional[Dict[str, float]] = None,
    ) -> bool:
        """Deduct cash (and optionally resources) for a purchase event."""
        if cash_cost <= 0 and not resource_costs:
            return True
        ev_date = event_date or self._now()
        def _work():
            with self._conn() as conn:
                self._ensure_row(conn, nation_id, nation_name)
                if cash_cost > 0:
                    conn.execute(
                        "UPDATE nations SET "
                        "money=MAX(0, COALESCE(money,0)-?), "
                        "confidence=CASE WHEN confidence='seeded' THEN 'tracked' ELSE confidence END, "
                        "last_event_date=? WHERE id=?",
                        (cash_cost, ev_date, nation_id),
                    )
                for resource, amount in (resource_costs or {}).items():
                    if amount > 0 and resource in RESOURCE_COLS:
                        conn.execute(
                            f"UPDATE nations SET {resource}=MAX(0, COALESCE({resource},0)-?) WHERE id=?",
                            (amount, nation_id),
                        )
                conn.commit()
        try:
            await self._run_sync(_work)
            return True
        except Exception as e:
            logger.error(f"deduct_spending({nation_id}): {e}", exc_info=True)
            return False

    async def apply_military_update(
        self,
        nation_id: int,
        old_military: Dict[str, int],
        new_military: Dict[str, int],
        event_date: Optional[str] = None,
        nation_name: Optional[str] = None,
    ) -> bool:
        """
        Called by nations_subscription on every nation/update event.

        - Units INCREASED (purchased): update count + deduct cash AND resources.
        - Units DECREASED (lost/disbanded): update count only, no cost deducted.

        Both dicts must contain the same keys — the caller already filters to
        only keys present in the incoming event payload.
        """
        ev_date = event_date or self._now()
        total_cash_cost = 0.0
        resource_costs: Dict[str, float] = {}
        mil_updates: Dict[str, Any] = {}

        for unit in MILITARY_COLS:
            if unit not in old_military or unit not in new_military:
                continue
            old_v = int(old_military[unit] or 0)
            new_v = int(new_military[unit] or 0)
            if new_v == old_v:
                continue
            mil_updates[unit] = new_v
            if new_v > old_v:
                bought = new_v - old_v
                costs  = MILITARY_COSTS.get(unit, {})
                total_cash_cost += costs.get("cash", 0.0) * bought
                for resource, per_unit in costs.items():
                    if resource == "cash":
                        continue
                    resource_costs[resource] = resource_costs.get(resource, 0.0) + per_unit * bought

        if not mil_updates:
            return True

        def _work():
            with self._conn() as conn:
                self._ensure_row(conn, nation_id, nation_name)
                row = conn.execute(
                    "SELECT confidence FROM nations WHERE id=?", (nation_id,)
                ).fetchone()
                is_fresh = row is not None and (row["confidence"] or "seeded") not in ("seeded",)

                set_clause = ", ".join(f"{k}=?" for k in mil_updates)
                conn.execute(
                    f"UPDATE nations SET {set_clause}, "
                    "confidence=CASE WHEN confidence='seeded' THEN 'tracked' ELSE confidence END, "
                    "last_event_date=? WHERE id=?",
                    list(mil_updates.values()) + [ev_date, nation_id],
                )

                if is_fresh:
                    if total_cash_cost > 0:
                        conn.execute(
                            "UPDATE nations SET money=MAX(0, COALESCE(money,0)-?) WHERE id=?",
                            (total_cash_cost, nation_id),
                        )
                    for resource, amount in resource_costs.items():
                        if amount > 0 and resource in RESOURCE_COLS:
                            conn.execute(
                                f"UPDATE nations SET {resource}=MAX(0, COALESCE({resource},0)-?) WHERE id=?",
                                (amount, nation_id),
                            )
                conn.commit()
            return is_fresh

        try:
            is_fresh = await self._run_sync(_work)

            if is_fresh and (total_cash_cost > 0 or resource_costs):
                rss_str = ", ".join(f"{r}={v:,.1f}" for r, v in resource_costs.items())
                logger.info(
                    f"Holdings: nation {nation_id} military purchase "
                    f"${total_cash_cost:,.0f} cash"
                    + (f" + {rss_str}" if rss_str else "")
                )

            # ── News: record each unit type purchased ─────────────────────────
            try:
                import asyncio as _asyncio
                import PnWHarvester.db.news_writer as _nw
                _nation_row: Dict[str, Any] = {}
                try:
                    def _fetch_nation_info():
                        with self._conn() as _c:
                            try:
                                _r = _c.execute(
                                    "SELECT alliance_id, alliance_name, alliance_flag, flag "
                                    "FROM nations WHERE id=?",
                                    (nation_id,),
                                ).fetchone()
                            except Exception:
                                _r = _c.execute(
                                    "SELECT alliance_id, alliance_name, flag "
                                    "FROM nations WHERE id=?",
                                    (nation_id,),
                                ).fetchone()
                            return dict(_r) if _r else {}
                    _nation_row = await self._run_sync(_fetch_nation_info)
                except Exception:
                    pass
                _alliance_id   = _nation_row.get("alliance_id") or None
                _alliance_name = _nation_row.get("alliance_name") or None
                _alliance_flag = _nation_row.get("alliance_flag") or None
                _nation_flag   = _nation_row.get("flag") or None
                for unit in MILITARY_COLS:
                    if unit not in old_military or unit not in new_military:
                        continue
                    _old_v = int(old_military[unit] or 0)
                    _new_v = int(new_military[unit] or 0)
                    if _new_v <= _old_v:
                        continue
                    _bought     = _new_v - _old_v
                    _unit_costs = MILITARY_COSTS.get(unit, {})
                    _cash_cost  = _unit_costs.get("cash", 0.0) * _bought
                    _res_costs: Dict[str, float] = {
                        res: per_unit * _bought
                        for res, per_unit in _unit_costs.items()
                        if res != "cash" and per_unit > 0
                    }
                    if _cash_cost < 100_000 and not _res_costs:
                        continue
                    _asyncio.create_task(_nw.record_military_purchase(
                        nation_id=nation_id,
                        nation_name=nation_name,
                        nation_flag=_nation_flag,
                        alliance_id=_alliance_id,
                        alliance_name=_alliance_name,
                        alliance_flag=_alliance_flag,
                        unit_type=unit,
                        quantity=_bought,
                        cash_cost=_cash_cost,
                        resource_costs=_res_costs or None,
                        event_date=ev_date,
                    ))
            except Exception as _ne:
                logger.debug(f"news military_purchase: {_ne}")

            return True
        except Exception as e:
            logger.error(f"apply_military_update({nation_id}): {e}", exc_info=True)
            return False

    async def apply_war_consumption(
        self,
        nation_id: int,
        gasoline: float,
        munitions: float,
        event_date: Optional[str] = None,
        nation_name: Optional[str] = None,
    ) -> bool:
        """Deduct gasoline and/or munitions consumed by a war attack."""
        if gasoline <= 0 and munitions <= 0:
            return True
        ev_date = event_date or self._now()
        def _work():
            with self._conn() as conn:
                self._ensure_row(conn, nation_id, nation_name)
                if gasoline > 0:
                    conn.execute(
                        "UPDATE nations SET gasoline=MAX(0, COALESCE(gasoline,0)-?), "
                        "last_event_date=? WHERE id=?",
                        (gasoline, ev_date, nation_id),
                    )
                if munitions > 0:
                    conn.execute(
                        "UPDATE nations SET munitions=MAX(0, COALESCE(munitions,0)-?), "
                        "last_event_date=? WHERE id=?",
                        (munitions, ev_date, nation_id),
                    )
                conn.commit()
        try:
            await self._run_sync(_work)
            return True
        except Exception as e:
            logger.error(f"apply_war_consumption({nation_id}): {e}", exc_info=True)
            return False

    async def apply_combat_losses(
        self,
        attacker_id: int,
        defender_id: int,
        att_losses: Dict[str, int],
        def_losses: Dict[str, int],
        event_date: Optional[str] = None,
        attacker_name: Optional[str] = None,
        defender_name: Optional[str] = None,
    ) -> bool:
        """
        Subtract military unit losses from war attacks.
        Only decrements unit counts — no cash or resource deduction.
        """
        ev_date = event_date or self._now()
        def _work():
            with self._conn() as conn:
                for nation_id, losses, name in [
                    (attacker_id, att_losses, attacker_name),
                    (defender_id, def_losses, defender_name),
                ]:
                    if not any(losses.values()):
                        continue
                    self._ensure_row(conn, nation_id, name)
                    for unit, lost in losses.items():
                        if lost > 0 and unit in MILITARY_COLS:
                            conn.execute(
                                f"UPDATE nations SET {unit}=MAX(0, COALESCE({unit},0)-?), "
                                "last_event_date=? WHERE id=?",
                                (lost, ev_date, nation_id),
                            )
                conn.commit()
        try:
            await self._run_sync(_work)
            return True
        except Exception as e:
            logger.error(f"apply_combat_losses: {e}", exc_info=True)
            return False

    async def set_complete_holdings(
        self,
        nation_id: int,
        money: float,
        resources: Dict[str, float],
        military: Dict[str, int],
        confidence: str = "fresh",
        event_date: Optional[str] = None,
        nation_name: Optional[str] = None,
        description: str = "",
    ) -> bool:
        ev_date = event_date or self._now()
        updates: Dict[str, Any] = {
            "money":           money,
            "confidence":      confidence,
            "last_event_date": ev_date,
        }
        for r in RESOURCE_COLS:
            updates[r] = resources.get(r, 0.0)
        for m in MILITARY_COLS:
            updates[m] = military.get(m, 0)

        def _work():
            with self._conn() as conn:
                self._ensure_row(conn, nation_id, nation_name)
                if nation_name:
                    conn.execute(
                        "UPDATE nations SET nation_name=? WHERE id=? AND nation_name IS NULL",
                        (nation_name, nation_id),
                    )
                set_clause = ", ".join(f"{k}=?" for k in updates)
                conn.execute(
                    f"UPDATE nations SET {set_clause} WHERE id=?",
                    list(updates.values()) + [nation_id],
                )
                conn.commit()
        try:
            await self._run_sync(_work)
            return True
        except Exception as e:
            logger.error(f"set_complete_holdings({nation_id}): {e}", exc_info=True)
            return False

    # ── Compat stubs ──────────────────────────────────────────────────────────

    async def get_holdings_history(self, nation_id: int, **kwargs) -> List[Dict[str, Any]]:
        """Stub — audit log removed; returns empty list."""
        return []

    async def get_spending_summary(self, nation_id: int, **kwargs) -> List[Dict[str, Any]]:
        """Stub — spending log removed; returns empty list."""
        return []

    async def cleanup_old_logs(self, days: int = 90) -> Dict[str, int]:
        """Stub — no separate log tables."""
        return {"holdings_log": 0, "spending_log": 0}
