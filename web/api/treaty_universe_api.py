from fastapi import APIRouter
from Systems.Functions.db_paths import TREATIES_DB_STR, GLOBAL_NATIONS_DB_STR
from PnWHarvester.db.treaties_db import TreatiesDB
from PnWHarvester.db.global_nations_db import GlobalNationsDB
import logging

router = APIRouter()
logger = logging.getLogger("Reaper.WebServer.TreatyUniverse")

@router.get("/treaties/ac_data")
async def treaty_ac_data():
    """
    Return a lightweight list of alliances for the autocomplete dropdown.
    Reads from Treaties.db (alliances that appear in active treaties) and enriches
    with member counts from GlobalNationsDB.
    """
    alliances = {}
    alliance_ids = set()

    # First, get alliance IDs from TreatiesDB (alliances with active treaties)
    if TREATIES_DB_STR:
        try:
            treaties_db = TreatiesDB(TREATIES_DB_STR)
            treaty_alliances = await treaties_db.get_distinct_alliances()
            
            for row in treaty_alliances:
                alliance_id = row['alliance_id']
                alliance_ids.add(alliance_id)
                alliances[alliance_id] = {
                    'id': alliance_id,
                    'name': row['alliance_name'],
                    'member_count': 0  # Will be populated from GlobalNationsDB
                }
            
            logger.info(f"treaty_ac_data: Found {len(alliance_ids)} alliances from TreatiesDB")
            
        except Exception as e:
            logger.warning(f"treaty_ac_data TreatiesDB error: {e}")

    # Enrich with member counts from GlobalNationsDB
    if GLOBAL_NATIONS_DB_STR and alliance_ids:
        try:
            gn_db = GlobalNationsDB(GLOBAL_NATIONS_DB_STR)
            summary = await gn_db.get_alliance_summary()
            
            for row in summary:
                alliance_id = row['alliance_id']
                if alliance_id in alliances:
                    alliances[alliance_id]['member_count'] = row['member_count']
            
            logger.info(f"treaty_ac_data: Enriched {len(alliance_ids)} alliances with member counts")
            
        except Exception as e:
            logger.warning(f"treaty_ac_data GlobalNationsDB error: {e}")

    # Convert to list and sort alphabetically
    alliance_list = list(alliances.values())
    alliance_list.sort(key=lambda a: (a.get('name') or '').lower())
    
    return {'alliances': alliance_list}

def calculate_flag_size(alliance_score, min_top_50_score, max_top_50_score):
    """Calculate flag display size based on alliance score."""
    if alliance_score >= min_top_50_score:
        size = 64 + ((alliance_score - min_top_50_score) / (max_top_50_score - min_top_50_score)) * 64
    elif alliance_score >= 1000:
        size = 48 + ((alliance_score - 1000) / (min_top_50_score - 1000)) * 16
    else:
        size = 40
    return max(40, min(128, size))

@router.get("/treaties/universe")
async def get_treaty_universe():
    # 1. Fetch all active treaties from TreatiesDB
    treaties_db = TreatiesDB(TREATIES_DB_STR)
    treaties = await treaties_db.get_active_treaties()
    
    # 2. Get distinct alliances from TreatiesDB (primary source)
    treaty_alliances = await treaties_db.get_distinct_alliances()
    
    # 3. Build alliance stats dict from TreatiesDB data first
    alliance_stats = {}
    for row in treaty_alliances:
        alliance_id = row['alliance_id']
        alliance_stats[alliance_id] = {
            'id': alliance_id,
            'name': row['alliance_name'],
            'member_count': 0,  # Will be populated from GlobalNationsDB if available
            'avg_score': 0,     # Will be populated from GlobalNationsDB if available
            'total_score': 0,   # Will be populated from GlobalNationsDB if available
            'max_score': 0,     # Will be populated from GlobalNationsDB if available
            'min_score': 0,     # Will be populated from GlobalNationsDB if available
            'total_cities': 0,  # Will be populated from GlobalNationsDB if available
            'flag': None
        }
    
    logger.info(f"Total alliances from treaties: {len(alliance_stats)}")
    
    # 4. Fetch alliance stats from GlobalNationsDB (fallback/enrichment)
    if GLOBAL_NATIONS_DB_STR:
        try:
            gn_db = GlobalNationsDB(GLOBAL_NATIONS_DB_STR)
            summary = await gn_db.get_alliance_summary()
            
            for row in summary:
                alliance_id = row['alliance_id']
                if alliance_id in alliance_stats:  # Only update if alliance exists in treaties
                    alliance_stats[alliance_id].update({
                        'member_count': row['member_count'],
                        'avg_score': row['avg_score'],
                        'total_score': row['avg_score'] * row['member_count'],
                        'max_score': row['max_score'],
                        'min_score': row['min_score'],
                        'total_cities': row['total_cities']
                    })
        except Exception as e:
            logger.warning(f"Failed to fetch alliance stats from GlobalNationsDB: {e}")
    
    # 5. Filter treaties to only include alliances that exist in treaties
    valid_alliance_ids = set(alliance_stats.keys())
    filtered_treaties = []
    for treaty in treaties:
        a1 = treaty.get('alliance1_id')
        a2 = treaty.get('alliance2_id')
        if a1 in valid_alliance_ids and a2 in valid_alliance_ids:
            filtered_treaties.append(treaty)
    
    logger.info(f"Filtered treaties: {len(treaties)} -> {len(filtered_treaties)} (removed {len(treaties) - len(filtered_treaties)} treaties with invalid alliances)")
    treaties = filtered_treaties
    
    # 6. Fetch alliance flags from treaties first (most reliable)
    for treaty in treaties:
        for side in ['alliance1', 'alliance2']:
            aid = treaty.get(f'{side}_id')
            flag = treaty.get(f'{side}_flag')
            if aid and flag and aid in alliance_stats and not alliance_stats[aid]['flag']:
                alliance_stats[aid]['flag'] = flag
    
    # 7. For alliances without flags from treaties, try GlobalNationsDB
    for alliance_id, stats in alliance_stats.items():
        if not stats['flag'] and GLOBAL_NATIONS_DB_STR:
            try:
                gn_db = GlobalNationsDB(GLOBAL_NATIONS_DB_STR)
                flag = await gn_db.get_alliance_flag(alliance_id)
                if flag:
                    alliance_stats[alliance_id]['flag'] = flag
            except Exception as e:
                logger.warning(f"Failed to fetch flag for alliance {alliance_id}: {e}")
    
    # 8. Calculate score ranges (only for alliances with score data)
    scored_alliances = {aid: stats for aid, stats in alliance_stats.items() if stats['total_score'] > 0}
    if scored_alliances:
        scores = [s['total_score'] for s in scored_alliances.values()]
        sorted_scores = sorted(scores, reverse=True)
        min_top_50 = sorted_scores[49] if len(sorted_scores) >= 50 else sorted_scores[-1] if sorted_scores else 0
        max_top_50 = sorted_scores[0] if sorted_scores else 0
        min_overall = min(scores) if scores else 0
        max_overall = max(scores) if scores else 0
        
        # Calculate flag sizes for scored alliances
        for aid, stats in scored_alliances.items():
            stats['flag_size'] = calculate_flag_size(
                stats['total_score'], min_top_50, max_top_50
            )
    else:
        min_top_50 = max_top_50 = min_overall = max_overall = 0
        
        # Default flag size for alliances without score data
        for aid, stats in alliance_stats.items():
            stats['flag_size'] = 48  # Default size
    
    # 9. Build response (alliances and treaties only, no blocs)
    return {
        "alliances": alliance_stats,
        "treaties": treaties,
        "score_range": {
            "min_top_50": min_top_50,
            "max_top_50": max_top_50,
            "min_overall": min_overall,
            "max_overall": max_overall
        }
    }
