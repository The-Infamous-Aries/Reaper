# Standard Library Imports
import logging
import re
from datetime import date
from typing import Any, Dict, List, Optional

# Third-Party Imports
import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# --- Setup ---
logger = logging.getLogger("Reaper.AstrologyAPI")
router = APIRouter()

# --- Models ---
class AstrologyRequest(BaseModel):
    month: int
    day: int
    year: int

# --- Helper Functions ---

import json
from pathlib import Path

# Cache for astrology data
_astrology_cache = {}

async def _get_astrology_json_data(filename: str) -> List[Dict[str, Any]]:
    """Load astrology JSON data with caching."""
    cache_key = f"astrology_{filename}"
    if cache_key in _astrology_cache:
        return _astrology_cache[cache_key]
    
    # Construct an absolute path to the Zodiac directory
    base_path = Path(__file__).parent.parent.parent / "Systems" / "Astrology" / "Zodiac"
    path = base_path / filename
    
    if not path.exists():
        logger.error(f"Astrology data file not found at {path}")
        return []
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            _astrology_cache[cache_key] = data
            logger.info(f"Sending equipment data for {len(data)} categories")
        return data
    except Exception as e:
        logger.error(f"Error loading astrology data from {filename}: {e}")
        return []

def _zodiac_for_date(bday: date) -> str:
    """Return the zodiac sign name for given date (month/day boundaries)."""
    m, d = bday.month, bday.day
    if (m == 12 and d >= 22) or (m == 1 and d <= 19):
        return "Capricorn"
    if (m == 1 and d >= 20) or (m == 2 and d <= 18):
        return "Aquarius"
    if (m == 2 and d >= 19) or (m == 3 and d <= 20):
        return "Pisces"
    if (m == 3 and d >= 21) or (m == 4 and d <= 19):
        return "Aries"
    if (m == 4 and d >= 20) or (m == 5 and d <= 20):
        return "Taurus"
    if (m == 5 and d >= 21) or (m == 6 and d <= 20):
        return "Gemini"
    if (m == 6 and d >= 21) or (m == 7 and d <= 22):
        return "Cancer"
    if (m == 7 and d >= 23) or (m == 8 and d <= 22):
        return "Leo"
    if (m == 8 and d >= 23) or (m == 9 and d <= 22):
        return "Virgo"
    if (m == 9 and d >= 23) or (m == 10 and d <= 22):
        return "Libra"
    if (m == 10 and d >= 23) or (m == 11 and d <= 21):
        return "Scorpio"
    return "Sagittarius"

async def _find_western_sign_data(sign_name: str) -> Optional[Dict[str, Any]]:
    """Find Western zodiac sign data."""
    logger.info(f"Looking for Western sign data: {sign_name}")
    data = await _get_astrology_json_data("astrology.json")
    logger.info(f"Loaded astrology.json with {len(data)} entries")
    for entry in data:
        if entry.get("name", "").lower() == sign_name.lower():
            logger.info(f"Found Western sign data for {sign_name}")
            return entry
    logger.warning(f"No Western sign data found for {sign_name}")
    return None

async def _find_chinese_sign_by_birthday(user_birthday: date) -> Optional[Dict[str, Any]]:
    """Determine Chinese zodiac sign accounting for actual Chinese New Year of that year."""
    logger.info(f"Looking for Chinese sign for birthday: {user_birthday}")
    # Chinese New Year dates (simplified for web version)
    CHINESE_NEW_YEAR_DATES = {
        1900: date(1900, 1, 31), 1901: date(1901, 2, 19), 1902: date(1902, 2, 8), 1903: date(1903, 1, 29),
        1904: date(1904, 2, 16), 1905: date(1905, 2, 4), 1906: date(1906, 1, 25), 1907: date(1907, 2, 13),
        1908: date(1908, 2, 2), 1909: date(1909, 1, 22), 1910: date(1910, 2, 10), 1911: date(1911, 1, 30),
        1912: date(1912, 2, 18), 1913: date(1913, 2, 6), 1914: date(1914, 1, 26), 1915: date(1915, 2, 14),
        1916: date(1916, 2, 3), 1917: date(1917, 1, 23), 1918: date(1918, 2, 11), 1919: date(1919, 2, 1),
        1920: date(1920, 2, 20), 1921: date(1921, 2, 8), 1922: date(1922, 1, 28), 1923: date(1923, 2, 16),
        1924: date(1924, 2, 5), 1925: date(1925, 1, 24), 1926: date(1926, 2, 13), 1927: date(1927, 2, 2),
        1928: date(1928, 1, 23), 1929: date(1929, 2, 10), 1930: date(1930, 1, 30), 1931: date(1931, 2, 17),
        1932: date(1932, 2, 6), 1933: date(1933, 1, 26), 1934: date(1934, 2, 14), 1935: date(1935, 2, 4),
        1936: date(1936, 1, 24), 1937: date(1937, 2, 11), 1938: date(1938, 1, 31), 1939: date(1939, 2, 19),
        1940: date(1940, 2, 8), 1941: date(1941, 1, 27), 1942: date(1942, 2, 15), 1943: date(1943, 2, 5),
        1944: date(1944, 1, 25), 1945: date(1945, 2, 13), 1946: date(1946, 2, 2), 1947: date(1947, 1, 22),
        1948: date(1948, 2, 10), 1949: date(1949, 1, 29), 1950: date(1950, 2, 17), 1951: date(1951, 2, 6),
        1952: date(1952, 1, 27), 1953: date(1953, 2, 14), 1954: date(1954, 2, 3), 1955: date(1955, 1, 24),
        1956: date(1956, 2, 12), 1957: date(1957, 1, 31), 1958: date(1958, 2, 18), 1959: date(1959, 2, 8),
        1960: date(1960, 1, 28), 1961: date(1961, 2, 15), 1962: date(1962, 2, 5), 1963: date(1963, 1, 25),
        1964: date(1964, 2, 13), 1965: date(1965, 2, 2), 1966: date(1966, 1, 21), 1967: date(1967, 2, 9),
        1968: date(1968, 1, 30), 1969: date(1969, 2, 17), 1970: date(1970, 2, 6), 1971: date(1971, 1, 27),
        1972: date(1972, 2, 15), 1973: date(1973, 2, 3), 1974: date(1974, 1, 23), 1975: date(1975, 2, 11),
        1976: date(1976, 1, 31), 1977: date(1977, 2, 18), 1978: date(1978, 2, 7), 1979: date(1979, 1, 28),
        1980: date(1980, 2, 16), 1981: date(1981, 2, 5), 1982: date(1982, 1, 25), 1983: date(1983, 2, 13),
        1984: date(1984, 2, 2), 1985: date(1985, 2, 20), 1986: date(1986, 2, 9), 1987: date(1987, 1, 29),
        1988: date(1988, 2, 17), 1989: date(1989, 2, 6), 1990: date(1990, 1, 27), 1991: date(1991, 2, 15),
        1992: date(1992, 2, 4), 1993: date(1993, 1, 23), 1994: date(1994, 2, 10), 1995: date(1995, 1, 31),
        1996: date(1996, 2, 19), 1997: date(1997, 2, 7), 1998: date(1998, 1, 28), 1999: date(1999, 2, 16),
        2000: date(2000, 2, 5), 2001: date(2001, 1, 24), 2002: date(2002, 2, 12), 2003: date(2003, 2, 1),
        2004: date(2004, 1, 22), 2005: date(2005, 2, 9), 2006: date(2006, 1, 29), 2007: date(2007, 2, 18),
        2008: date(2008, 2, 7), 2009: date(2009, 1, 26), 2010: date(2010, 2, 14), 2011: date(2011, 2, 3),
        2012: date(2012, 1, 23), 2013: date(2013, 2, 10), 2014: date(2014, 1, 31), 2015: date(2015, 2, 19),
        2016: date(2016, 2, 8), 2017: date(2017, 1, 28), 2018: date(2018, 2, 16), 2019: date(2019, 2, 5),
        2020: date(2020, 1, 25), 2021: date(2021, 2, 12), 2022: date(2022, 2, 1), 2023: date(2023, 1, 22),
        2024: date(2024, 2, 10), 2025: date(2025, 1, 29), 2026: date(2026, 2, 17), 2027: date(2027, 2, 6),
    }
    
    year = user_birthday.year
    cny = CHINESE_NEW_YEAR_DATES.get(year, date(year, 2, 4))
    chinese_year = year if user_birthday >= cny else year - 1
    
    # Calculate animal based on year
    animals = ["Rat", "Ox", "Tiger", "Rabbit", "Dragon", "Snake", "Horse", "Goat", "Monkey", "Rooster", "Dog", "Pig"]
    index = (chinese_year - 4) % 12
    animal_name = animals[index]
    
    data = await _get_astrology_json_data("chinese_astrology.json")
    for entry in data:
        if entry.get("Name", "").lower() == animal_name.lower():
            return entry
    
    logger.warning(f"Chinese animal '{animal_name}' not found in database, returning default")
    return {"Name": animal_name, "Emoji": "🔮", "Description": "Unknown"}

async def _find_primal_entry(western_sign: str, chinese_animal: str) -> Optional[Dict[str, Any]]:
    """Find Primal Astrology combination with more robust matching."""
    logger.info(f"Looking for primal entry: {western_sign} / {chinese_animal}")
    if not western_sign or not chinese_animal:
        logger.warning(f"Missing western_sign or chinese_animal: {western_sign}, {chinese_animal}")
        return None

    data = await _get_astrology_json_data("primal_astrology.json")
    if not data:
        logger.warning("primal_astrology.json is empty or could not be loaded.")
        return None

    # Normalize inputs
    western_sign = western_sign.strip()
    chinese_animal = chinese_animal.strip()

    # Define known alternate names for Chinese animals
    alternates = {
        "Goat": "Sheep", "Sheep": "Goat",
        "Rat": "Mouse", "Mouse": "Rat",
        "Ox": "Cow", "Cow": "Ox",
        "Rabbit": "Cat", "Cat": "Rabbit",
        "Rooster": "Chicken", "Chicken": "Rooster",
        "Pig": "Boar", "Boar": "Pig"
    }

    possible_chinese_names = {chinese_animal, alternates.get(chinese_animal)}
    possible_chinese_names.discard(None)

    # Iterate through all possible combinations
    for entry in data:
        sign_combination = entry.get("Sign Combination", "").strip()
        if not sign_combination:
            continue

        # Split the combination into parts (e.g., "Aries / Rat")
        parts = [part.strip() for part in re.split(r'[\/,-]', sign_combination)]
        if len(parts) != 2:
            continue

        # Check if the parts match the western and any of the possible Chinese names
        part1, part2 = parts
        for name in possible_chinese_names:
            if (part1.lower() == western_sign.lower() and part2.lower() == name.lower()) or \
               (part2.lower() == western_sign.lower() and part1.lower() == name.lower()):
                logger.info(f"Found primal match for {western_sign}/{chinese_animal} -> {sign_combination}")
                return entry

    logger.warning(f"No primal astrology match found for {western_sign} / {chinese_animal}")
    return None

async def _fetch_horoscope_data(sign: str, day: str = "today") -> tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Fetch horoscope data with fallback generation."""
    import random
    
    sign_slug = str(sign).strip().lower()
    
    # Fallback horoscope templates based on sign characteristics
    horoscope_templates = {
        "aries": [
            "Today brings new opportunities for leadership and action.",
            "Your natural courage will help you overcome challenges.",
            "Energy and enthusiasm are your allies today."
        ],
        "taurus": [
            "Stability and comfort are highlighted today.",
            "Your practical nature will serve you well.",
            "Focus on building solid foundations."
        ],
        "gemini": [
            "Communication is key today - express yourself clearly.",
            "Your adaptability will be an asset.",
            "New ideas and connections are favored."
        ],
        "cancer": [
            "Emotional connections are emphasized today.",
            "Trust your intuition in decision making.",
            "Home and family matters may require attention."
        ],
        "leo": [
            "Your natural charisma shines brightly today.",
            "Creative expression is favored.",
            "Leadership opportunities may arise."
        ],
        "virgo": [
            "Attention to detail brings rewards.",
            "Organization and planning are highlighted.",
            "Health and wellness matters may need focus."
        ],
        "libra": [
            "Balance and harmony are important today.",
            "Relationships may need attention and care.",
            "Aesthetic and artistic pursuits are favored."
        ],
        "scorpio": [
            "Transformation and renewal are themes today.",
            "Deep insights may come through introspection.",
            "Passion and intensity are your allies."
        ],
        "sagittarius": [
            "Adventure and exploration are calling.",
            "Your optimistic outlook attracts positive energy.",
            "Learning and growth opportunities abound."
        ],
        "capricorn": [
            "Hard work and discipline pay off today.",
            "Long-term planning is favored.",
            "Professional matters may come into focus."
        ],
        "aquarius": [
            "Innovation and originality are highlighted.",
            "Your unique perspective is valuable.",
            "Group activities and friendships are favored."
        ],
        "pisces": [
            "Intuition and creativity flow strongly.",
            "Compassion and empathy serve you well.",
            "Spiritual and artistic pursuits are favored."
        ]
    }
    
    templates = horoscope_templates.get(sign_slug, ["Today brings new opportunities and experiences."])
    text = random.choice(templates)
    
    # Generate some basic stats
    lucky_numbers = ["3", "7", "9", "11", "21", "27"]
    colors = ["Blue", "Red", "Green", "Purple", "Gold", "Silver"]
    moods = ["Energetic", "Calm", "Focused", "Creative", "Social", "Reflective"]
    
    # Get date range for sign
    date_ranges = {
        "aries": "March 21 - April 19",
        "taurus": "April 20 - May 20",
        "gemini": "May 21 - June 20",
        "cancer": "June 21 - July 22",
        "leo": "July 23 - August 22",
        "virgo": "August 23 - September 22",
        "libra": "September 23 - October 22",
        "scorpio": "October 23 - November 21",
        "sagittarius": "November 22 - December 21",
        "capricorn": "December 22 - January 19",
        "aquarius": "January 20 - February 18",
        "pisces": "February 19 - March 20",
    }
    
    stats = {
        "mood": random.choice(moods),
        "color": random.choice(colors),
        "lucky_number": random.choice(lucky_numbers),
        "lucky_time": f"{random.randint(1, 12)}:00 {'AM' if random.random() < 0.5 else 'PM'}",
        "compatibility": random.choice(list(horoscope_templates.keys())),
        "date_range": date_ranges.get(sign.lower(), "Unknown"),
        "current_date": datetime.now().strftime("%B %d, %Y")
    }
    
    return text, stats

@router.get("/horoscope-proxy")
async def horoscope_proxy(request: Request, sign: str, day: str = "today"):
    """Proxy for the external horoscope API to avoid CORS issues."""
    try:
        # Validate sign
        valid_signs = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
                      "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]
        sign_match = next((s for s in valid_signs if s.lower() == sign.lower()), None)
        if not sign_match:
            return JSONResponse(content={"error": "Invalid sign"}, status_code=400)

        # Validate day parameter
        valid_days = ["today", "yesterday", "tomorrow"]
        if day.lower() not in valid_days:
            day = "today"  # Default to today if invalid day provided

        # Use the new free horoscope API - note: this API only supports daily horoscopes
        # For yesterday/tomorrow, we'll use the current day's horoscope as a fallback
        url = f"https://freehoroscopeapi.com/api/v1/get-horoscope/daily?sign={sign_match.lower()}"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
            
            api_data = response.json()
            logger.info(f"Successfully proxied horoscope for {sign_match} ({day})")
            
            # Transform the new API format to match the old format for compatibility
            if "data" in api_data:
                # Adjust date based on the day parameter
                from datetime import datetime, timedelta
                base_date = datetime.strptime(api_data["data"]["date"], "%Y-%m-%d")
                
                if day.lower() == "yesterday":
                    adjusted_date = base_date - timedelta(days=1)
                elif day.lower() == "tomorrow":
                    adjusted_date = base_date + timedelta(days=1)
                else:  # today
                    adjusted_date = base_date
                
                transformed_data = {
                    "date": adjusted_date.strftime("%Y-%m-%d"),
                    "horoscope": api_data["data"]["horoscope"],
                    "sunsign": api_data["data"]["sign"]
                }

                # Task tracking — get_horoscope (once per day, only for "today")
                if day.lower() == "today":
                    user = request.session.get("discord_user")
                    if user and user.get("id"):
                        try:
                            from web.api.tasks_api import record_action as _task_record
                            await _task_record(str(user["id"]), "get_horoscope")
                        except Exception as e:
                            logger.warning(f"horoscope-proxy task tracking failed for {user.get('id')}: {e}")

                return JSONResponse(content=transformed_data)
            else:
                return JSONResponse(content=api_data)

    except httpx.RequestError as e:
        logger.error(f"Error fetching horoscope from external API for {sign}: {e}")
        return JSONResponse(content={"error": "Failed to fetch horoscope from the external source."}, status_code=502) # Bad Gateway
    except Exception as e:
        logger.error(f"Error in horoscope proxy endpoint: {e}", exc_info=True)
        return JSONResponse(content={"error": "Internal server error in proxy."}, status_code=500)


@router.post("/astrology/signs")
async def get_astrology_signs(request: AstrologyRequest):
    """Get Western, Eastern, and Spirit Animal signs for a birth date."""
    try:
        logger.info(f"Received astrology signs request: {request.month}/{request.day}/{request.year}")
        
        # Validate date
        try:
            user_birthday = date(request.year, request.month, request.day)
            logger.info(f"Validated birth date: {user_birthday}")
        except ValueError:
            logger.error(f"Invalid date provided: {request.month}/{request.day}/{request.year}")
            return JSONResponse(
                content={"error": "Invalid date. Please check the month/day combination."},
                status_code=400
            )
        
        if user_birthday > date.today():
            logger.error(f"Future date provided: {user_birthday}")
            return JSONResponse(
                content={"error": "Date cannot be in the future."},
                status_code=400
            )
        
        # Get Western sign
        western_sign = _zodiac_for_date(user_birthday)
        logger.info(f"Western sign: {western_sign}")
        western_data = await _find_western_sign_data(western_sign)
        
        if not western_data:
            logger.error(f"No Western zodiac data found for {western_sign}")
            return JSONResponse(
                content={"error": f"Could not find Western zodiac data for {western_sign}."},
                status_code=404
            )
        
        # Get Chinese sign
        chinese_data = await _find_chinese_sign_by_birthday(user_birthday)
        logger.info(f"Chinese data: {chinese_data}")
        
        # Get Spirit Animal (Primal Astrology)
        chinese_animal = chinese_data.get("Name", "") if chinese_data else ""
        logger.info(f"Chinese animal: {chinese_animal}")
        spirit_data = await _find_primal_entry(western_sign, chinese_animal)
        logger.info(f"Spirit data: {spirit_data}")
        
        # Format response
        response = {
            "western": western_data,
            "chinese": chinese_data,
            "spirit": spirit_data,
            "birth_date": user_birthday.isoformat()
        }
        
        logger.info(f"Returning astrology response: {response}")
        return JSONResponse(content=response)
        
    except Exception as e:
        logger.error(f"Error in astrology signs endpoint: {e}", exc_info=True)
        return JSONResponse(
            content={"error": "Internal server error"},
            status_code=500
        )

@router.get("/astrology/horoscope")
async def get_horoscope(request: Request, sign: str, day: str = "today"):
    """Get daily horoscope for a zodiac sign."""
    try:
        # Validate sign
        valid_signs = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
                      "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]
        
        sign_match = next((s for s in valid_signs if s.lower() == sign.lower()), None)
        
        if not sign_match:
            return JSONResponse(
                content={"error": f"Invalid sign '{sign}'. Valid signs: {', '.join(valid_signs)}"},
                status_code=400
            )
        
        # Validate day
        valid_days = ["yesterday", "today", "tomorrow"]
        if day not in valid_days:
            return JSONResponse(
                content={"error": f"Invalid day '{day}'. Valid days: {', '.join(valid_days)}"},
                status_code=400
            )
        
        # Get horoscope text and stats
        text, stats = await _fetch_horoscope_data(sign_match, day)
        
        if not text:
            return JSONResponse(
                content={"error": f"Could not generate horoscope for {sign_match} for {day}."},
                status_code=500
            )
        
        # Get additional sign data
        sign_data = await _find_western_sign_data(sign_match)
        
        response = {
            "sign": sign_match,
            "day": day,
            "text": text,
            "stats": stats,
            "sign_data": sign_data
        }

        # Task tracking — get_horoscope (once per day, only for "today")
        if day == "today":
            user = request.session.get("discord_user")
            if user and user.get("id"):
                try:
                    from web.api.tasks_api import record_action as _task_record
                    await _task_record(str(user["id"]), "get_horoscope")
                except Exception as e:
                    logger.warning(f"get_horoscope task tracking failed for {user.get('id')}: {e}")

        return JSONResponse(content=response)
        
    except Exception as e:
        logger.error(f"Error in horoscope endpoint: {e}", exc_info=True)
        return JSONResponse(
            content={"error": "Internal server error"},
            status_code=500
        )