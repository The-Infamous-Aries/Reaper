"""
IRSNationsDB — backward-compatibility shim.

IRSNations.db has been merged into GlobalNations.db.
IRSNationsDB is now an alias for GlobalNationsDB so all existing imports
continue to work without any changes to callers.

Import is deferred via module-level __getattr__ to break the circular chain:
  irs_nations_db → global_nations_db → PnWHarvester/db/__init__ → pnw_costs
                 → Systems/PnW/IA/costs → irs_nations_db  (circular!)

Usage (unchanged):
    from Systems.Functions.irs_nations_db import IRSNationsDB
    db = IRSNationsDB(path)
"""


def __getattr__(name: str):
    """Lazy-resolve IRSNationsDB on first access to avoid circular imports."""
    if name == "IRSNationsDB":
        from PnWHarvester.db.global_nations_db import GlobalNationsDB
        # Cache it on the module so subsequent accesses are direct
        import sys
        sys.modules[__name__].IRSNationsDB = GlobalNationsDB
        return GlobalNationsDB
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["IRSNationsDB"]
