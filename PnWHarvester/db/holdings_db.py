"""
HoldingsDB — per-nation running ledger of cash and resources on hand.

One row per nation. This is the SOLE source of truth for Est Loot on the
raids page. The raids command reads holdings directly — it never touches
loot.db or bankrecs.db at query time.

How it works
------------
Live maintenance (subscription-driven, all applied immediately):
  warattack/create (win attack)
    → Defender LOST the looted amounts — deduct from their holdings.
      We also back-calculate their full pre-loot holdings from the loot
      amount + war type + policies, then SET their holdings to that value
      minus what was looted. This gives us the most accurate baseline.
    → Attacker GAINED the looted amounts — add to their holdings.

  bankrec/create
    → Nation received cash/resources (receiver_type=1) → ADD to holdings.
    → Nation sent cash/resources (sender_type=1) → SUBTRACT from holdings.
    Applied immediately in BankrecsSubscription so holdings is always
    current. The raids command never needs to read bankrecs.

  nation/update + city/update
    → Detect purchases (city, infra, land, improvements, projects) by
      diffing old vs new state BEFORE saving to GlobalNationsDB.
    → DEDUCT the cash cost from money_held.

Confidence levels
-----------------
  'tracked' — at least one live subscription event has updated this row
  'fresh'   — row was reset by a live loot event (most accurate baseline)

Loot percentage formula
-----------------------
  base_pct  = war_type_base  (raid=0.075, ordinary=0.05, attrition=0.06)
  att_mult  = 1.4 if attacker is Pirate else 1.0
  att_mult *= 1.1 if attacker has APE else 1.0
  def_mult  = 0.6 if defender is Moneybags else 1.0
  loot_pct  = base_pct * att_mult * def_mult

  holdings_at_loot_time = looted / loot_pct

Schema
------
  nation_id       INTEGER PRIMARY KEY
  nation_name     TEXT
  money_held      REAL    -- estimated cash on hand (can be negative if spending detected before baseline)
  coal_held       REAL
  oil_held        REAL
  uranium_held    REAL
  iron_held       REAL
  bauxite_held    REAL
  lead_held       REAL
  gasoline_held   REAL
  munitions_held  REAL
  steel_held      REAL
  aluminum_held   REAL
  food_held       REAL
  confidence      TEXT    -- 'tracked' | 'fresh'
  last_loot_date  TEXT    -- timestamp of the loot event that last reset this row
  last_event_date TEXT    -- timestamp of the most recent event that touched this row
  updated_at      TEXT
"""

import sqlite3
import logging
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

RESOURCE_COLS = (
    "coal", "oil", "uranium", "iron", "bauxite", "lead",
    "gasoline", "munitions", "steel", "aluminum", "food",
)

_WAR_TYPE_BASE: Dict[str, float] = {
    "raid":      0.075,
    "ordinary":  0.050,
    "attrition": 0.060,
}
_DEFAULT_BASE = 0.075


def _calc_loot_pct(
    war_type: Optional[str] = None,
    att_war_policy: Optional[str] = None,
    def_war_policy: Optional[str] = None,
    att_has_ape: bool = False,
) -> float:
    wt   = (war_type or "").lower().replace("_war", "").replace(" ", "_")
    base = _WAR_TYPE_BASE.get(wt, _DEFAULT_BASE)
    att_mult = 1.0
    if (att_war_policy or "").lower() == "pirate":
        att_mult *= 1.4
    if att_has_ape:
        att_mult *= 1.1
    def_mult = 0.6 if (def_war_policy or "").lower() == "moneybags" else 1.0
    return base * att_mult * def_mult


class HoldingsDB:
    """
    Per-nation running ledger of cash and resources on hand.

    Concurrency model
    -----------------
    Three subscriptions write to this DB concurrently:
      - nations_subscription  → deduct_spending()   (city/infra/land/project purchases)
      - wars_subscription     → apply_loot_event()  (ground-win attacks)
      - bankrecs_subscription → apply_bankrec()     (bank transfers)

    We use SQLite WAL mode so concurrent writers don't block each other.
    Each public method opens its own short-lived connection and commits
    immediately — no long-held locks, no asyncio.Lock contention.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock   = asyncio.Lock()
        self._init_database()

    # ── Schema ────────────────────────────────────────────────────────────────

    def _init_database(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                # WAL mode: readers never block writers, writers never block readers
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                c = conn.cursor()
                c.execute("""
                    CREATE TABLE IF NOT EXISTS nation_holdings (
                        nation_id       INTEGER PRIMARY KEY,
                        nation_name     TEXT,
                        money_held      REAL    NOT NULL DEFAULT 0,
                        coal_held       REAL    NOT NULL DEFAULT 0,
                        oil_held        REAL    NOT NULL DEFAULT 0,
                        uranium_held    REAL    NOT NULL DEFAULT 0,
                        iron_held       REAL    NOT NULL DEFAULT 0,
                        bauxite_held    REAL    NOT NULL DEFAULT 0,
                        lead_held       REAL    NOT NULL DEFAULT 0,
                        gasoline_held   REAL    NOT NULL DEFAULT 0,
                        munitions_held  REAL    NOT NULL DEFAULT 0,
                        steel_held      REAL    NOT NULL DEFAULT 0,
                        aluminum_held   REAL    NOT NULL DEFAULT 0,
                        food_held       REAL    NOT NULL DEFAULT 0,
                        confidence      TEXT    NOT NULL DEFAULT 'tracked',
                        last_loot_date  TEXT,
                        last_event_date TEXT,
                        updated_at      TEXT    NOT NULL
                    )
                """)
                c.execute("""
                    CREATE TABLE IF NOT EXISTS spending_log (
                        id              INTEGER PRIMARY KEY AUTOINCREMENT,
                        nation_id       INTEGER NOT NULL,
                        event_type      TEXT    NOT NULL,
                        cash_delta      REAL    NOT NULL DEFAULT 0,
                        description     TEXT,
                        event_date      TEXT,
                        recorded_at     TEXT    NOT NULL
                    )
                """)
                c.execute("CREATE INDEX IF NOT EXISTS idx_nh_nation_id  ON nation_holdings(nation_id)")
                c.execute("CREATE INDEX IF NOT EXISTS idx_sl_nation_id  ON spending_log(nation_id)")
                c.execute("CREATE INDEX IF NOT EXISTS idx_sl_event_date ON spending_log(event_date DESC)")
                conn.commit()
                logger.info("HoldingsDB initialised (WAL mode)")
        except Exception as e:
            logger.error(f"HoldingsDB init error: {e}", exc_info=True)
            raise

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _ensure_row_sql() -> str:
        return """
            INSERT OR IGNORE INTO nation_holdings (
                nation_id, nation_name, money_held,
                coal_held, oil_held, uranium_held, iron_held,
                bauxite_held, lead_held, gasoline_held, munitions_held,
                steel_held, aluminum_held, food_held,
                confidence, last_loot_date, last_event_date, updated_at
            ) VALUES (?, ?, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 'tracked', NULL, ?, ?)
        """

    def _conn(self) -> sqlite3.Connection:
        """Open a WAL-mode connection for a single operation."""
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _bankrec_parties(rec: Dict[str, Any]):
        """
        Yield (nation_id, sign) for every nation-type party in a bank record.

        sender_type=1   → nation sent funds  → sign = -1 (subtract from holdings)
        receiver_type=1 → nation received funds → sign = +1 (add to holdings)
        """
        sender_id   = rec.get("sender_id")
        sender_type = int(rec.get("sender_type") or 0)
        receiver_id   = rec.get("receiver_id")
        receiver_type = int(rec.get("receiver_type") or 0)

        if sender_id and sender_type == 1:
            yield (int(sender_id), -1)
        if receiver_id and receiver_type == 1:
            yield (int(receiver_id), +1)

    # ── Ensure row exists ─────────────────────────────────────────────────────

    async def ensure_nation(self, nation_id: int, nation_name: Optional[str] = None) -> bool:
        """Insert a zero-balance row if one doesn't exist. Never overwrites."""
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    now = self._now()
                    conn.execute(self._ensure_row_sql(), (nation_id, nation_name, now, now))
                    conn.commit()
                    return True
            except Exception as e:
                logger.error(f"HoldingsDB.ensure_nation({nation_id}): {e}")
                return False

    # ── Deduct spending (city/infra/land/improvements/projects) ──────────────

    async def deduct_spending(
        self,
        nation_id: int,
        cash_cost: float,
        event_type: str,
        description: str = "",
        event_date: Optional[str] = None,
        nation_name: Optional[str] = None,
    ) -> bool:
        """
        Deduct a cash purchase from a nation's money_held.
        Allows going negative — a negative balance means we detected spending
        before we had a loot-event baseline, which is fine; it will self-correct
        when the next loot event arrives.
        """
        if cash_cost <= 0:
            return True

        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    now = self._now()
                    ev_date = event_date or now

                    conn.execute(self._ensure_row_sql(), (nation_id, nation_name, ev_date, now))

                    conn.execute("""
                        UPDATE nation_holdings
                        SET money_held      = money_held - ?,
                            confidence      = CASE WHEN confidence = 'seeded' THEN 'tracked' ELSE confidence END,
                            last_event_date = ?,
                            updated_at      = ?
                        WHERE nation_id = ?
                    """, (cash_cost, ev_date, now, nation_id))

                    conn.execute("""
                        INSERT INTO spending_log
                            (nation_id, event_type, cash_delta, description, event_date, recorded_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (nation_id, event_type, -cash_cost, description, ev_date, now))

                    conn.commit()
                    return True
            except Exception as e:
                logger.error(f"HoldingsDB.deduct_spending({nation_id}, {event_type}): {e}", exc_info=True)
                return False

    # ── Apply loot event (war win attack) ─────────────────────────────────────

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
        A ground-win attack occurred.

        Defender:
          Only updates holdings if actual loot occurred (money_looted > 0 OR
          any resource > 0). Back-calculates their full holdings at the moment
          of the loot using the correct loot percentage, then SETs their
          holdings to the post-loot value. Confidence is set to 'fresh'.

          If no loot occurred (e.g. a ground win with zero loot), we do NOT
          touch the defender's holdings — wiping them to zero would be wrong.

        Attacker:
          Add the looted amounts to their holdings (only if loot > 0).
        """
        # Check if any loot actually occurred
        total_looted = money_looted + sum(resources_looted.get(r, 0.0) for r in RESOURCE_COLS)
        if total_looted <= 0:
            return True  # no loot — nothing to update

        loot_pct = _calc_loot_pct(
            war_type=war_type,
            att_war_policy=att_war_policy,
            def_war_policy=def_war_policy,
            att_has_ape=att_has_ape,
        )
        if loot_pct <= 0:
            loot_pct = _DEFAULT_BASE

        def _post(looted: float) -> float:
            if looted <= 0:
                return 0.0
            return max(0.0, looted / loot_pct - looted)

        def_money = _post(money_looted)
        def_rss   = {r: _post(resources_looted.get(r, 0.0)) for r in RESOURCE_COLS}

        try:
            now = self._now()
            with self._conn() as conn:
                # Defender: SET to post-loot value (fresh baseline)
                conn.execute(self._ensure_row_sql(), (defender_id, defender_name, loot_date, now))
                conn.execute("""
                    UPDATE nation_holdings SET
                        money_held      = ?,
                        coal_held       = ?, oil_held        = ?, uranium_held    = ?,
                        iron_held       = ?, bauxite_held    = ?, lead_held       = ?,
                        gasoline_held   = ?, munitions_held  = ?, steel_held      = ?,
                        aluminum_held   = ?, food_held       = ?,
                        confidence      = 'fresh',
                        last_loot_date  = ?,
                        last_event_date = ?,
                        updated_at      = ?
                    WHERE nation_id = ?
                """, (
                    def_money,
                    def_rss["coal"],    def_rss["oil"],      def_rss["uranium"],
                    def_rss["iron"],    def_rss["bauxite"],  def_rss["lead"],
                    def_rss["gasoline"],def_rss["munitions"],def_rss["steel"],
                    def_rss["aluminum"],def_rss["food"],
                    loot_date, loot_date, now, defender_id,
                ))

                # Attacker: ADD looted amounts
                conn.execute(self._ensure_row_sql(), (attacker_id, attacker_name, loot_date, now))
                conn.execute("""
                    UPDATE nation_holdings SET
                        money_held      = money_held + ?,
                        coal_held       = coal_held + ?,      oil_held        = oil_held + ?,
                        uranium_held    = uranium_held + ?,   iron_held       = iron_held + ?,
                        bauxite_held    = bauxite_held + ?,   lead_held       = lead_held + ?,
                        gasoline_held   = gasoline_held + ?,  munitions_held  = munitions_held + ?,
                        steel_held      = steel_held + ?,     aluminum_held   = aluminum_held + ?,
                        food_held       = food_held + ?,
                        confidence      = CASE WHEN confidence = 'seeded' THEN 'tracked' ELSE confidence END,
                        last_event_date = ?,
                        updated_at      = ?
                    WHERE nation_id = ?
                """, (
                    money_looted,
                    resources_looted.get("coal", 0),    resources_looted.get("oil", 0),
                    resources_looted.get("uranium", 0), resources_looted.get("iron", 0),
                    resources_looted.get("bauxite", 0), resources_looted.get("lead", 0),
                    resources_looted.get("gasoline", 0),resources_looted.get("munitions", 0),
                    resources_looted.get("steel", 0),   resources_looted.get("aluminum", 0),
                    resources_looted.get("food", 0),
                    loot_date, now, attacker_id,
                ))
                conn.commit()
            return True
        except Exception as e:
            logger.error(
                f"HoldingsDB.apply_loot_event(att={attacker_id}, def={defender_id}): {e}",
                exc_info=True,
            )
            return False

    # ── Apply bankrec ─────────────────────────────────────────────────────────

    async def apply_bankrec(self, rec: Dict[str, Any]) -> bool:
        """
        Apply a bank record to holdings for all nation-type parties.

        Called directly from BankrecsSubscription on every bankrec/create event
        so holdings is always current — the raids command never needs to read
        bankrecs.db at query time.

        Receiver (receiver_type=1): ADD cash + resources.
        Sender   (sender_type=1):   SUBTRACT cash + resources.

        Cash (money_held) can go negative — that's valid and means the nation
        sent more than we currently have tracked (will self-correct on next
        loot event). Resources are floored at 0 since you can't hold negative
        resources in PnW.
        """
        parties = list(self._bankrec_parties(rec))
        if not parties:
            return True  # no nation parties — nothing to do

        rec_date = str(rec.get("date") or self._now()).replace("T", " ")

        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    now = self._now()
                    for nation_id, sign in parties:
                        conn.execute(self._ensure_row_sql(), (nation_id, None, rec_date, now))

                        money_delta = sign * float(rec.get("money") or 0)
                        rss_deltas  = {r: sign * float(rec.get(r) or 0) for r in RESOURCE_COLS}

                        conn.execute("""
                            UPDATE nation_holdings SET
                                money_held      = money_held + ?,
                                coal_held       = MAX(0, coal_held + ?),
                                oil_held        = MAX(0, oil_held + ?),
                                uranium_held    = MAX(0, uranium_held + ?),
                                iron_held       = MAX(0, iron_held + ?),
                                bauxite_held    = MAX(0, bauxite_held + ?),
                                lead_held       = MAX(0, lead_held + ?),
                                gasoline_held   = MAX(0, gasoline_held + ?),
                                munitions_held  = MAX(0, munitions_held + ?),
                                steel_held      = MAX(0, steel_held + ?),
                                aluminum_held   = MAX(0, aluminum_held + ?),
                                food_held       = MAX(0, food_held + ?),
                                confidence      = CASE WHEN confidence = 'seeded' THEN 'tracked' ELSE confidence END,
                                last_event_date = ?,
                                updated_at      = ?
                            WHERE nation_id = ?
                        """, (
                            money_delta,
                            rss_deltas["coal"],    rss_deltas["oil"],
                            rss_deltas["uranium"], rss_deltas["iron"],
                            rss_deltas["bauxite"], rss_deltas["lead"],
                            rss_deltas["gasoline"],rss_deltas["munitions"],
                            rss_deltas["steel"],   rss_deltas["aluminum"],
                            rss_deltas["food"],
                            rec_date, now,
                            nation_id,
                        ))

                    conn.commit()
                    return True
            except Exception as e:
                logger.error(f"HoldingsDB.apply_bankrec: {e}", exc_info=True)
                return False

    # ── Queries ───────────────────────────────────────────────────────────────

    async def get_holdings(self, nation_id: int) -> Optional[Dict[str, Any]]:
        """Get the holdings row for a nation, or None if not tracked."""
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    row = conn.execute(
                        "SELECT * FROM nation_holdings WHERE nation_id = ?", (nation_id,)
                    ).fetchone()
                    return dict(row) if row else None
            except Exception as e:
                logger.error(f"HoldingsDB.get_holdings({nation_id}): {e}")
                return None

    async def get_holdings_bulk(self, nation_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        """Fetch holdings for multiple nations in one query."""
        if not nation_ids:
            return {}
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    ph = ",".join("?" * len(nation_ids))
                    rows = conn.execute(
                        f"SELECT * FROM nation_holdings WHERE nation_id IN ({ph})",
                        nation_ids,
                    ).fetchall()
                    return {int(r["nation_id"]): dict(r) for r in rows}
            except Exception as e:
                logger.error(f"HoldingsDB.get_holdings_bulk: {e}")
                return {}

    async def get_stats(self) -> Dict[str, Any]:
        """Return summary stats for logging/monitoring."""
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    total = conn.execute("SELECT COUNT(*) FROM nation_holdings").fetchone()[0]
                    by_conf = conn.execute(
                        "SELECT confidence, COUNT(*) FROM nation_holdings GROUP BY confidence"
                    ).fetchall()
                    log_count = conn.execute("SELECT COUNT(*) FROM spending_log").fetchone()[0]
                    return {
                        "total_nations": total,
                        "by_confidence": {r[0]: r[1] for r in by_conf},
                        "spending_log_entries": log_count,
                    }
            except Exception as e:
                logger.error(f"HoldingsDB.get_stats: {e}")
                return {}
    # ── Live subscription methods (no lock — WAL handles concurrency) ─────────

    async def ensure_nation(self, nation_id: int, nation_name: Optional[str] = None) -> bool:
        """Insert a zero-balance row if one doesn't exist. Never overwrites."""
        try:
            now = self._now()
            with self._conn() as conn:
                conn.execute(self._ensure_row_sql(), (nation_id, nation_name, now, now))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"HoldingsDB.ensure_nation({nation_id}): {e}")
            return False

    async def deduct_spending(
        self,
        nation_id: int,
        cash_cost: float,
        event_type: str,
        description: str = "",
        event_date: Optional[str] = None,
        nation_name: Optional[str] = None,
    ) -> bool:
        """
        Deduct a cash purchase from money_held.
        Called by nations_subscription on city/infra/land/project purchases.
        No lock — WAL mode handles concurrent writes safely.
        Allows going negative (self-corrects on next loot event).
        """
        if cash_cost <= 0:
            return True
        try:
            now     = self._now()
            ev_date = event_date or now
            with self._conn() as conn:
                conn.execute(self._ensure_row_sql(), (nation_id, nation_name, ev_date, now))
                conn.execute("""
                    UPDATE nation_holdings
                    SET money_held      = money_held - ?,
                        confidence      = CASE WHEN confidence = 'seeded' THEN 'tracked' ELSE confidence END,
                        last_event_date = ?,
                        updated_at      = ?
                    WHERE nation_id = ?
                """, (cash_cost, ev_date, now, nation_id))
                conn.execute("""
                    INSERT INTO spending_log
                        (nation_id, event_type, cash_delta, description, event_date, recorded_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (nation_id, event_type, -cash_cost, description, ev_date, now))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"HoldingsDB.deduct_spending({nation_id}, {event_type}): {e}", exc_info=True)
            return False

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
        Ground-win attack: SET defender to post-loot holdings, ADD to attacker.
        Called by wars_subscription. No lock — WAL mode handles concurrency.
        """
        loot_pct = _calc_loot_pct(war_type, att_war_policy, def_war_policy, att_has_ape)
        if loot_pct <= 0:
            loot_pct = _DEFAULT_BASE

        def _post(looted: float) -> float:
            return max(0.0, looted / loot_pct - looted) if looted > 0 else 0.0

        def_money = _post(money_looted)
        def_rss   = {r: _post(resources_looted.get(r, 0.0)) for r in RESOURCE_COLS}

        try:
            now = self._now()
            with self._conn() as conn:
                # Defender: SET to post-loot value (fresh baseline)
                conn.execute(self._ensure_row_sql(), (defender_id, defender_name, loot_date, now))
                conn.execute("""
                    UPDATE nation_holdings SET
                        money_held      = ?,
                        coal_held       = ?, oil_held        = ?, uranium_held    = ?,
                        iron_held       = ?, bauxite_held    = ?, lead_held       = ?,
                        gasoline_held   = ?, munitions_held  = ?, steel_held      = ?,
                        aluminum_held   = ?, food_held       = ?,
                        confidence      = 'fresh',
                        last_loot_date  = ?,
                        last_event_date = ?,
                        updated_at      = ?
                    WHERE nation_id = ?
                """, (
                    def_money,
                    def_rss["coal"],    def_rss["oil"],      def_rss["uranium"],
                    def_rss["iron"],    def_rss["bauxite"],  def_rss["lead"],
                    def_rss["gasoline"],def_rss["munitions"],def_rss["steel"],
                    def_rss["aluminum"],def_rss["food"],
                    loot_date, loot_date, now, defender_id,
                ))
                # Attacker: ADD looted amounts
                conn.execute(self._ensure_row_sql(), (attacker_id, attacker_name, loot_date, now))
                conn.execute("""
                    UPDATE nation_holdings SET
                        money_held      = money_held + ?,
                        coal_held       = coal_held + ?,      oil_held        = oil_held + ?,
                        uranium_held    = uranium_held + ?,   iron_held       = iron_held + ?,
                        bauxite_held    = bauxite_held + ?,   lead_held       = lead_held + ?,
                        gasoline_held   = gasoline_held + ?,  munitions_held  = munitions_held + ?,
                        steel_held      = steel_held + ?,     aluminum_held   = aluminum_held + ?,
                        food_held       = food_held + ?,
                        confidence      = CASE WHEN confidence = 'seeded' THEN 'tracked' ELSE confidence END,
                        last_event_date = ?,
                        updated_at      = ?
                    WHERE nation_id = ?
                """, (
                    money_looted,
                    resources_looted.get("coal", 0),    resources_looted.get("oil", 0),
                    resources_looted.get("uranium", 0), resources_looted.get("iron", 0),
                    resources_looted.get("bauxite", 0), resources_looted.get("lead", 0),
                    resources_looted.get("gasoline", 0),resources_looted.get("munitions", 0),
                    resources_looted.get("steel", 0),   resources_looted.get("aluminum", 0),
                    resources_looted.get("food", 0),
                    loot_date, now, attacker_id,
                ))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"HoldingsDB.apply_loot_event(att={attacker_id}, def={defender_id}): {e}", exc_info=True)
            return False

    async def apply_bankrec(self, rec: Dict[str, Any]) -> bool:
        """
        Apply a bank record to holdings for all nation-type parties.
        Called by bankrecs_subscription. No lock — WAL mode handles concurrency.
        Receiver (type=1): ADD. Sender (type=1): SUBTRACT.
        Cash can go negative; resources floored at 0.
        """
        parties = list(self._bankrec_parties(rec))
        if not parties:
            return True
        rec_date = str(rec.get("date") or self._now()).replace("T", " ")
        try:
            now = self._now()
            with self._conn() as conn:
                for nation_id, sign in parties:
                    conn.execute(self._ensure_row_sql(), (nation_id, None, rec_date, now))
                    money_delta = sign * float(rec.get("money") or 0)
                    rss_deltas  = {r: sign * float(rec.get(r) or 0) for r in RESOURCE_COLS}
                    conn.execute("""
                        UPDATE nation_holdings SET
                            money_held      = money_held + ?,
                            coal_held       = MAX(0, coal_held + ?),
                            oil_held        = MAX(0, oil_held + ?),
                            uranium_held    = MAX(0, uranium_held + ?),
                            iron_held       = MAX(0, iron_held + ?),
                            bauxite_held    = MAX(0, bauxite_held + ?),
                            lead_held       = MAX(0, lead_held + ?),
                            gasoline_held   = MAX(0, gasoline_held + ?),
                            munitions_held  = MAX(0, munitions_held + ?),
                            steel_held      = MAX(0, steel_held + ?),
                            aluminum_held   = MAX(0, aluminum_held + ?),
                            food_held       = MAX(0, food_held + ?),
                            confidence      = CASE WHEN confidence = 'seeded' THEN 'tracked' ELSE confidence END,
                            last_event_date = ?,
                            updated_at      = ?
                        WHERE nation_id = ?
                    """, (
                        money_delta,
                        rss_deltas["coal"],    rss_deltas["oil"],      rss_deltas["uranium"],
                        rss_deltas["iron"],    rss_deltas["bauxite"],  rss_deltas["lead"],
                        rss_deltas["gasoline"],rss_deltas["munitions"],rss_deltas["steel"],
                        rss_deltas["aluminum"],rss_deltas["food"],
                        rec_date, now, nation_id,
                    ))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"HoldingsDB.apply_bankrec: {e}", exc_info=True)
            return False

    # ── Queries (read-only, no lock needed) ───────────────────────────────────

    async def get_holdings(self, nation_id: int) -> Optional[Dict[str, Any]]:
        try:
            with self._conn() as conn:
                row = conn.execute(
                    "SELECT * FROM nation_holdings WHERE nation_id = ?", (nation_id,)
                ).fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"HoldingsDB.get_holdings({nation_id}): {e}")
            return None

    async def get_holdings_bulk(self, nation_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        if not nation_ids:
            return {}
        try:
            with self._conn() as conn:
                ph   = ",".join("?" * len(nation_ids))
                rows = conn.execute(
                    f"SELECT * FROM nation_holdings WHERE nation_id IN ({ph})",
                    nation_ids,
                ).fetchall()
                return {int(r["nation_id"]): dict(r) for r in rows}
        except Exception as e:
            logger.error(f"HoldingsDB.get_holdings_bulk: {e}")
            return {}

    async def get_stats(self) -> Dict[str, Any]:
        try:
            with self._conn() as conn:
                total     = conn.execute("SELECT COUNT(*) FROM nation_holdings").fetchone()[0]
                by_conf   = conn.execute(
                    "SELECT confidence, COUNT(*) FROM nation_holdings GROUP BY confidence"
                ).fetchall()
                log_count = conn.execute("SELECT COUNT(*) FROM spending_log").fetchone()[0]
                return {
                    "total_nations": total,
                    "by_confidence": {r[0]: r[1] for r in by_conf},
                    "spending_log_entries": log_count,
                }
        except Exception as e:
            logger.error(f"HoldingsDB.get_stats: {e}")
            return {}

    async def get_all_tracked_nation_ids(self) -> List[int]:
        """Return all nation_ids currently in the holdings ledger."""
        try:
            with self._conn() as conn:
                rows = conn.execute(
                    "SELECT nation_id FROM nation_holdings"
                ).fetchall()
                return [int(r[0]) for r in rows]
        except Exception as e:
            logger.error(f"HoldingsDB.get_all_tracked_nation_ids: {e}")
            return []

    async def apply_turn_revenue(
        self,
        nation_id: int,
        money_delta: float,
        resource_deltas: Dict[str, float],
        turn_date: str,
        nation_name: Optional[str] = None,
    ) -> bool:
        """
        Add one turn's worth of net revenue to a nation's holdings.

        Called by TurnRevenueLoop at midnight UTC and every 2 hours after.
        money_delta      : net cash income for this turn (net_cash_num from revenue_calc).
                           Can be negative if upkeep exceeds income.
        resource_deltas  : net resource production per turn (positive = produced,
                           negative = consumed). Resources are floored at 0 since
                           you can't hold negative resources.
        turn_date        : ISO-ish timestamp of the turn boundary.
        """
        try:
            now = self._now()
            with self._conn() as conn:
                conn.execute(self._ensure_row_sql(), (nation_id, nation_name, turn_date, now))
                conn.execute("""
                    UPDATE nation_holdings SET
                        money_held      = money_held + ?,
                        coal_held       = MAX(0, coal_held + ?),
                        oil_held        = MAX(0, oil_held + ?),
                        uranium_held    = MAX(0, uranium_held + ?),
                        iron_held       = MAX(0, iron_held + ?),
                        bauxite_held    = MAX(0, bauxite_held + ?),
                        lead_held       = MAX(0, lead_held + ?),
                        gasoline_held   = MAX(0, gasoline_held + ?),
                        munitions_held  = MAX(0, munitions_held + ?),
                        steel_held      = MAX(0, steel_held + ?),
                        aluminum_held   = MAX(0, aluminum_held + ?),
                        food_held       = MAX(0, food_held + ?),
                        confidence      = CASE WHEN confidence = 'seeded' THEN 'tracked' ELSE confidence END,
                        last_event_date = ?,
                        updated_at      = ?
                    WHERE nation_id = ?
                """, (
                    money_delta,
                    resource_deltas.get("coal", 0),
                    resource_deltas.get("oil", 0),
                    resource_deltas.get("uranium", 0),
                    resource_deltas.get("iron", 0),
                    resource_deltas.get("bauxite", 0),
                    resource_deltas.get("lead", 0),
                    resource_deltas.get("gasoline", 0),
                    resource_deltas.get("munitions", 0),
                    resource_deltas.get("steel", 0),
                    resource_deltas.get("aluminum", 0),
                    resource_deltas.get("food", 0),
                    turn_date, now, nation_id,
                ))
                conn.commit()
            return True
        except Exception as e:
            logger.error(
                f"HoldingsDB.apply_turn_revenue(nation={nation_id}): {e}",
                exc_info=True,
            )
            return False
