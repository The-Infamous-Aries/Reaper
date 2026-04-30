import json
import logging
import re
import asyncio
import random
from datetime import datetime, date, timedelta, time as dt_time, timezone
from typing import Optional, Dict, Any, List
from pathlib import Path

import discord
from discord.ext import commands, tasks
from discord import app_commands
from Systems.Functions import config
try:
    import aiohttp
except Exception:
    aiohttp = None

logger = logging.getLogger("AstrologyCog")

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

class AstrologyView(discord.ui.View):
    """View with buttons to switch between Western, Eastern, and Primal astrology pages."""
    def __init__(self, cog, western_data, chinese_data, spirit_data, user_birthday, western_sign, chinese_animal):
        super().__init__(timeout=180)
        self.cog = cog
        self.western_data = western_data
        self.chinese_data = chinese_data
        self.spirit_data = spirit_data
        self.user_birthday = user_birthday
        self.western_sign = western_sign
        self.chinese_animal = chinese_animal
        self.current_page = "western"

    def get_embed(self):
        if self.current_page == "western":
            return self.cog._build_western_embed(self.western_data, self.user_birthday, self.western_sign)
        elif self.current_page == "eastern":
            return self.cog._build_eastern_embed(self.chinese_data, self.user_birthday, self.chinese_animal)
        else:
            return self.cog._build_primal_embed(self.spirit_data, self.western_data, self.chinese_data, self.user_birthday, self.western_sign, self.chinese_animal)

    @discord.ui.button(label="Western", style=discord.ButtonStyle.primary, emoji="♈")
    async def western_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = "western"
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="Eastern", style=discord.ButtonStyle.success, emoji="🐉")
    async def eastern_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = "eastern"
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="Spirit Animal", style=discord.ButtonStyle.secondary, emoji="🌀")
    async def primal_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = "primal"
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

class AstrologyCog(commands.Cog):
    """Slash command to show zodiac info from astrology.json based on birthday."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._zodiac_data_cache = {}

    async def _get_json_data(self, filename: str) -> List[Dict[str, Any]]:
        if filename in self._zodiac_data_cache:
            return self._zodiac_data_cache[filename]
        
        path = Path(__file__).resolve().parent / "Zodiac" / filename
        if not path.exists():
            return []
        
        try:
            text = path.read_text(encoding="utf-8")
            data = json.loads(text)
            self._zodiac_data_cache[filename] = data
            return data
        except Exception:
            return []

    async def _fetch_horoscope_data(self, sign: str, day: str = "today") -> (Optional[str], Optional[Dict[str, Any]]):
        """Fetch horoscope data with improved error handling."""
        import config
        
        sign_slug = str(sign).strip().lower()
        
        # Try Aztro API first (most reliable free API)
        try:
            if aiohttp is None:
                return None, None
                
            url = f"https://aztro.sameerkumar.website/?sign={sign_slug}&day={day}"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        text = str(data.get("description") or "").strip() or None
                        if text:
                            stats = {
                                "mood": data.get("mood"),
                                "color": data.get("color"),
                                "lucky_number": data.get("lucky_number"),
                                "lucky_time": data.get("lucky_time"),
                                "compatibility": data.get("compatibility"),
                                "date_range": data.get("date_range"),
                                "current_date": data.get("current_date"),
                            }
                            stats = {k: v for k, v in stats.items() if v}
                            return text, (stats or None)
                    else:
                        print(f"Aztro API returned status {resp.status}")
                        
        except Exception as e:
            print(f"Aztro API error: {e}")
        
        # If Aztro fails and we have an API key, try alternative APIs
        if config.HORSCOPE_API:
            try:
                # Try RapidAPI horoscope service
                url = f"https://sameer-kumar-aztro-v1.p.rapidapi.com/?sign={sign_slug}&day={day}"
                headers = {
                    "X-RapidAPI-Key": config.HORSCOPE_API,
                    "X-RapidAPI-Host": "sameer-kumar-aztro-v1.p.rapidapi.com"
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, headers=headers, timeout=15) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            text = str(data.get("description") or "").strip() or None
                            if text:
                                stats = {
                                    "mood": data.get("mood"),
                                    "color": data.get("color"),
                                    "lucky_number": data.get("lucky_number"),
                                    "lucky_time": data.get("lucky_time"),
                                    "compatibility": data.get("compatibility"),
                                    "date_range": data.get("date_range"),
                                    "current_date": data.get("current_date"),
                                }
                                stats = {k: v for k, v in stats.items() if v}
                                return text, (stats or None)
                                
            except Exception as e:
                print(f"RapidAPI horoscope error: {e}")
        
        # Final fallback - generate a simple horoscope
        try:
            import random
            
            # Simple horoscope templates based on sign characteristics
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
            
            stats = {
                "mood": random.choice(moods),
                "color": random.choice(colors),
                "lucky_number": random.choice(lucky_numbers),
                "lucky_time": f"{random.randint(1, 12)}:00 {'AM' if random.random() < 0.5 else 'PM'}",
                "compatibility": random.choice(list(horoscope_templates.keys())),
                "date_range": self._get_date_range_for_sign(sign),
                "current_date": datetime.now().strftime("%B %d, %Y")
            }
            
            return text, stats
            
        except Exception as e:
            print(f"Fallback horoscope generation error: {e}")
            return None, None
    
    def _get_date_range_for_sign(self, sign: str) -> str:
        """Get date range for a zodiac sign as fallback."""
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
        return date_ranges.get(sign.lower(), "Unknown")

    def _build_horoscope_embed(self, sign: str, text: str, stats: Optional[Dict[str, Any]], sign_data: Optional[Dict[str, Any]] = None, day: str = "today") -> discord.Embed:
        """Create a rich embed for horoscope with emojis and all available Aztro stats."""
        zodiac_emojis = {
            "Aries": "♈", "Taurus": "♉", "Gemini": "♊", "Cancer": "♋",
            "Leo": "♌", "Virgo": "♍", "Libra": "♎", "Scorpio": "♏",
            "Sagittarius": "♐", "Capricorn": "♑", "Aquarius": "♒", "Pisces": "♓",
        }
        emoji = zodiac_emojis.get(sign, "🔮")
        title_day = "Daily" if day == "today" else day.capitalize()
        embed = discord.Embed(
            title=f"{emoji} {sign} {title_day} Horoscope",
            description=text,
            color=discord.Color.blurple(),
            timestamp=datetime.utcnow(),
        )

        # Add Static Info if available
        if sign_data:
            planet = sign_data.get("ruling_planet", "Unknown")
            element = sign_data.get("element", "Unknown")
            stones = ", ".join(sign_data.get("stones", []))
            
            static_info = f"🪐 **Planet:** {planet} • 🔥 **Element:** {element}"
            if stones:
                static_info += f"\n💎 **Stones:** {stones}"
            
            embed.add_field(name="Zodiac Info", value=static_info, inline=False)

        # Add all available API stats as separate fields
        if stats:
            if stats.get("date_range"):
                embed.add_field(name="Date Range", value=f"📅 {stats['date_range']}", inline=False)
            if stats.get("current_date"):
                embed.add_field(name="Date", value=f"📅 {stats['current_date']}", inline=True)
            if stats.get("mood"):
                embed.add_field(name="Mood", value=f"🧠 {stats['mood']}", inline=True)
            if stats.get("color"):
                embed.add_field(name="Daily Color", value=f"🎨 {stats['color']}", inline=True)
            if stats.get("lucky_number"):
                embed.add_field(name="Daily Lucky #", value=f"🔢 {stats['lucky_number']}", inline=True)
            if stats.get("lucky_time"):
                embed.add_field(name="Lucky Time", value=f"⏰ {stats['lucky_time']}", inline=True)
            if stats.get("compatibility"):
                embed.add_field(name="Compatibility", value=f"❤️ {stats['compatibility']}", inline=True)
        
        embed.set_footer(text="Powered by Aztro API • Allspark Astrology")
        return embed

    _WESTERN_SIGNS = [
        "Aries","Taurus","Gemini","Cancer","Leo","Virgo",
        "Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"
    ]

    @staticmethod
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

    async def _find_sign_data(self, sign_name: str) -> Optional[Dict[str, Any]]:
        data = await self._get_json_data("astrology.json")
        for entry in data:
            if entry.get("name", "").lower() == sign_name.lower():
                return entry
        return None

    def _normalize_chinese_to_primal(self, animal_name: str) -> str:
        """Normalize Chinese animal names to match Primal Astrology combinations."""
        mapping = {"Goat": "Sheep"}
        return mapping.get(animal_name, animal_name)

    def _convert_time_24_to_12(self, t: str) -> str:
        """Convert a single 24-hour time like '15:00' or '5' to '3:00 PM' or '5:00 AM'."""
        m = re.match(r"^\s*(\d{1,2})(?::(\d{2}))?\s*$", t)
        if not m:
            return t.strip()
        hour = int(m.group(1))
        minute = m.group(2) or "00"
        hour12 = hour % 12
        if hour12 == 0:
            hour12 = 12
        ampm = "AM" if hour < 12 else "PM"
        return f"{hour12}:{minute} {ampm}"

    def _format_hours_24_to_12(self, hours: str) -> str:
        """Format a 24-hour range like '15:00 – 17:00' or '15:00-17:00' to '3:00 PM – 5:00 PM'."""
        s = hours.strip()
        if not s:
            return hours
        separators = [" – ", "–", "—", " - ", "-", " to "]
        for sep in separators:
            if sep in s:
                parts = [p.strip() for p in s.split(sep) if p.strip()]
                if len(parts) == 2:
                    start = self._convert_time_24_to_12(parts[0])
                    end = self._convert_time_24_to_12(parts[1])
                    return f"{start} – {end}"
        return self._convert_time_24_to_12(s)

    async def _find_primal_entry(self, western_sign: str, chinese_animal: str) -> Optional[Dict[str, Any]]:
        
        data = await self._get_json_data("primal_astrology.json")
        
        # Try direct combination first
        combo = f"{western_sign} / {chinese_animal}"
        
        for entry in data:
            if entry.get("Sign Combination", "").lower() == combo.lower():
                return entry
                
        # Try alternate names for Chinese sign
        alternates = {"Goat": "Sheep", "Sheep": "Goat", "Rat": "Mouse", "Mouse": "Rat", "Ox": "Cow", "Cow": "Ox", "Rabbit": "Cat", "Cat": "Rabbit", "Rooster": "Chicken", "Chicken": "Rooster", "Pig": "Boar", "Boar": "Pig"}
        alt_animal = alternates.get(chinese_animal)
        if alt_animal:
             combo_alt = f"{western_sign} / {alt_animal}"
             for entry in data:
                if entry.get("Sign Combination", "").lower() == combo_alt.lower():
                    return entry
                    
        return None

    def _get_chinese_new_year_date(self, year: int) -> Optional[date]:
        return CHINESE_NEW_YEAR_DATES.get(year)

    async def _find_chinese_sign_by_birthday(self, user_birthday: date) -> Optional[Dict[str, Any]]:
        """Determine Chinese zodiac sign accounting for actual Chinese New Year of that year."""
        year = user_birthday.year
        cny = self._get_chinese_new_year_date(year)
        if cny is None:
            # Fallback estimation if date not in lookup
            try:
                cny = date(year, 2, 4)
            except Exception:
                cny = date(year, 2, 1)
        
        chinese_year = year if user_birthday >= cny else year - 1
        
        # Calculate animal based on year
        # 1924 was Rat. (1924 - 4) % 12 = 0.
        animals = ["Rat", "Ox", "Tiger", "Rabbit", "Dragon", "Snake", "Horse", "Goat", "Monkey", "Rooster", "Dog", "Pig"]
        index = (chinese_year - 4) % 12
        animal_name = animals[index]
        
        data = await self._get_json_data("chinese_astrology.json")
        for entry in data:
            # Check name match
            if entry.get("Name", "").lower() == animal_name.lower():
                return entry
            # Also check if year is explicitly in list (fallback)
            if chinese_year in entry.get("Years", []):
                return entry
                
        return {"Name": animal_name, "Emoji": "🔮", "Description": "Unknown"}


    def _calculate_next_birthday_countdown(self, user_birthday: date) -> str:
        """Calculate time until next birthday in weeks/days/hours format."""
        today = date.today()
        current_year = today.year       
        next_birthday = date(current_year, user_birthday.month, user_birthday.day)
        if next_birthday <= today:
            next_birthday = date(current_year + 1, user_birthday.month, user_birthday.day)
        delta = next_birthday - today
        total_days = delta.days
        weeks = total_days // 7
        remaining_days = total_days % 7
        hours = 0 
        parts = []
        if weeks > 0:
            parts.append(f"{weeks} week{'s' if weeks != 1 else ''}")
        if remaining_days > 0:
            parts.append(f"{remaining_days} day{'s' if remaining_days != 1 else ''}")
        if not parts:  
            return "Today!"
        
        return ", ".join(parts)

    def _build_western_embed(self, western_data: Dict[str, Any], user_birthday: date, western_sign: str) -> discord.Embed:
        """Build the Western Zodiac page embed."""
        western_emoji = western_data.get("emoji", "")
        embed = discord.Embed(
            title=f"{western_emoji} Western Zodiac: {western_sign}",
            description=western_data.get("description", "No description available."),
            color=discord.Color.from_rgb(255, 69, 0),  # Orange Red
            timestamp=discord.utils.utcnow(),
        )

        western_element = western_data.get("element", "")
        western_modality = western_data.get("modality", "")
        western_planet = western_data.get("ruling_planet", "")
        western_house = western_data.get("house", "")
        western_body = western_data.get("body_part", "")
        western_tarot = western_data.get("tarot_card", "")
        western_stones = western_data.get("stones", [])
        western_lucky_nums = western_data.get("lucky_numbers", [])
        western_lucky_cols = western_data.get("lucky_colors", [])
        western_traits = western_data.get("traits", [])
        western_compat = western_data.get("compatibility", [])
        western_date_range = western_data.get("date_range", "")

        # Row 1: Dates, Element, Modality
        info_parts = []
        if western_date_range: info_parts.append(f"🗓️ **Dates:** {western_date_range}")
        if western_element: info_parts.append(f"🔥 **Element:** {western_element}")
        if western_modality: info_parts.append(f"🔄 **Modality:** {western_modality}")
        if info_parts: embed.add_field(name="Basics", value=" • ".join(info_parts), inline=False)

        # Row 2: Planet, House, Tarot
        astro_parts = []
        if western_planet: astro_parts.append(f"🪐 **Planet:** {western_planet}")
        if western_house: astro_parts.append(f"🏠 **House:** {western_house}")
        if western_tarot: astro_parts.append(f"🃏 **Tarot:** {western_tarot}")
        if astro_parts: embed.add_field(name="Astrological", value=" • ".join(astro_parts), inline=False)

        # Traits & Stones
        if western_traits:
            embed.add_field(name="✨ Traits", value=", ".join(western_traits), inline=True)
        if western_stones:
            embed.add_field(name="💎 Stones", value=", ".join(western_stones), inline=True)

        # Lucky Info
        lucky_parts = []
        if western_lucky_nums:
            lucky_parts.append(f"🔢 **Numbers:** {', '.join(map(str, western_lucky_nums))}")
        if western_lucky_cols:
            lucky_parts.append(f"🎨 **Colors:** {', '.join(western_lucky_cols)}")
        if lucky_parts: embed.add_field(name="Lucky Info", value=" • ".join(lucky_parts), inline=False)

        if western_compat:
            embed.add_field(name="❤️ Compatibility", value=", ".join(western_compat), inline=False)

        countdown = self._calculate_next_birthday_countdown(user_birthday)
        embed.set_footer(text=f"Birthday: {user_birthday.strftime('%B %d, %Y')} • Next: {countdown} • Page 1/3")
        return embed

    def _build_eastern_embed(self, chinese_data: Dict[str, Any], user_birthday: date, chinese_animal: str) -> discord.Embed:
        """Build the Eastern Zodiac page embed."""
        chinese_emoji = chinese_data.get("Emoji", "🔮")
        embed = discord.Embed(
            title=f"{chinese_emoji} Eastern Zodiac: {chinese_animal}",
            description=chinese_data.get("Description", "No description available."),
            color=discord.Color.from_rgb(255, 215, 0),  # Gold
            timestamp=discord.utils.utcnow(),
        )

        chinese_yin_yang = chinese_data.get("Yin_Yang", "")
        chinese_element = chinese_data.get("Fixed_Element", "")
        chinese_trine = chinese_data.get("Trine", "")
        chinese_hours = chinese_data.get("Hours", "")
        chinese_lucky_nums = chinese_data.get("Lucky_Numbers", [])
        chinese_lucky_colors = chinese_data.get("Lucky_Colors", [])
        chinese_lucky_flowers = chinese_data.get("Lucky_Flowers", [])
        chinese_traits = chinese_data.get("Traits", [])
        chinese_compat = chinese_data.get("Compatibility", "")
        chinese_incompat = chinese_data.get("Incompatible", "")

        # Row 1: Polarity, Element, Trine
        row1 = []
        if chinese_yin_yang: row1.append(f"☯️ **Polarity:** {chinese_yin_yang}")
        if chinese_element: row1.append(f"🪵 **Element:** {chinese_element}")
        if chinese_trine: row1.append(f"📐 **Trine:** {chinese_trine}")
        if row1: embed.add_field(name="Basics", value=" • ".join(row1), inline=False)

        if chinese_hours:
            embed.add_field(name="⏰ Lucky Hours", value=self._format_hours_24_to_12(chinese_hours), inline=False)

        # Lucky Info
        lucky_parts = []
        if chinese_lucky_nums:
            lucky_parts.append(f"🔢 **Numbers:** {', '.join(map(str, chinese_lucky_nums))}")
        if chinese_lucky_colors:
            lucky_parts.append(f"🎨 **Colors:** {', '.join(chinese_lucky_colors)}")
        if lucky_parts: embed.add_field(name="Lucky Info", value=" • ".join(lucky_parts), inline=False)

        if chinese_lucky_flowers:
            embed.add_field(name="🌸 Lucky Flowers", value=", ".join(chinese_lucky_flowers), inline=False)

        if chinese_traits:
            embed.add_field(name="✨ Traits", value=", ".join(chinese_traits), inline=False)

        if chinese_compat:
            embed.add_field(name="❤️ Compatibility", value=str(chinese_compat), inline=True)
        if chinese_incompat:
            embed.add_field(name="❌ Incompatible", value=str(chinese_incompat), inline=True)

        countdown = self._calculate_next_birthday_countdown(user_birthday)
        embed.set_footer(text=f"Birthday: {user_birthday.strftime('%B %d, %Y')} • Next: {countdown} • Page 2/3")
        return embed

    def _build_primal_embed(self, spirit_data: Optional[Dict[str, Any]], western_data: Dict[str, Any], 
                          chinese_data: Dict[str, Any], user_birthday: date, 
                          western_sign: str, chinese_animal: str) -> discord.Embed:
        """Build the Primal Astrology page embed."""
        spirit_name = spirit_data.get("Name", "Unknown") if spirit_data else "Unknown"
        embed = discord.Embed(
            title=f"🌀 Spirit Animal: {spirit_name}",
            color=discord.Color.from_rgb(138, 43, 226),  # Blue Violet
            timestamp=discord.utils.utcnow(),
        )

        western_emoji = western_data.get("emoji", "")
        chinese_emoji = chinese_data.get("Emoji", "🔮")
        combo_explanation = f"{western_emoji} {western_sign} + {chinese_emoji} {self._normalize_chinese_to_primal(chinese_animal)}"
        embed.add_field(name="Based on", value=combo_explanation, inline=False)

        if spirit_data:
            embed.description = spirit_data.get("Description", "No description available.")
            
            # Row 1: Traits
            traits = spirit_data.get("Traits", [])
            if traits:
                embed.add_field(name="✨ Traits", value=", ".join(traits), inline=False)
            
            # Row 2: Career & Relationships
            career = spirit_data.get("Career", "")
            if career:
                embed.add_field(name="💼 Career", value=career, inline=False)
            
            relationships = spirit_data.get("Relationships", "")
            if relationships:
                embed.add_field(name="❤️ Relationships", value=relationships, inline=False)

            compat = spirit_data.get("Compatibility", [])
            if compat:
                # Compatibility field might already exist as string or list, handle both
                compat_val = ", ".join(compat) if isinstance(compat, list) else str(compat)
                embed.add_field(name="🤝 Compatibility", value=compat_val, inline=False)
        else:
            embed.description = "No matching spirit animal found for this combination."

        countdown = self._calculate_next_birthday_countdown(user_birthday)
        embed.set_footer(text=f"Birthday: {user_birthday.strftime('%B %d, %Y')} • Next: {countdown} • Page 3/3")
        return embed

    @commands.hybrid_command(name="horoscope", description="Get the horoscope for a zodiac sign.")
    @app_commands.describe(sign="The zodiac sign to get the horoscope for.", day="The day of the horoscope (yesterday, today, tomorrow).")
    @app_commands.choices(
        sign=[app_commands.Choice(name=s, value=s) for s in _WESTERN_SIGNS],
        day=[
            app_commands.Choice(name="Yesterday", value="yesterday"),
            app_commands.Choice(name="Today", value="today"),
            app_commands.Choice(name="Tomorrow", value="tomorrow"),
        ]
    )
    async def horoscope(self, ctx: commands.Context, sign: str, day: Optional[app_commands.Choice[str]] = None):
        """Get the daily horoscope for a sign."""
        if ctx.interaction:
            await ctx.interaction.response.defer()
        else:
            await ctx.typing()
        
        day_str = day.value if day else "today"

        valid_signs = self._WESTERN_SIGNS
        match = next((s for s in valid_signs if s.lower() == sign.lower()), None)
        
        if not match:
            msg = f"❌ Invalid sign '{sign}'."
            if ctx.interaction:
                await ctx.interaction.followup.send(msg, ephemeral=True)
            else:
                await ctx.send(msg)
            return

        text, stats = await self._fetch_horoscope_data(match, day_str)
        sign_data = await self._find_sign_data(match)
        
        if not text:
            msg = f"❌ Could not fetch horoscope for {match} for {day_str}."
            if ctx.interaction:
                await ctx.interaction.followup.send(msg, ephemeral=True)
            else:
                await ctx.send(msg)
            return
        
        embed = self._build_horoscope_embed(match, text, stats, sign_data, day_str)

        if ctx.interaction:
            await ctx.interaction.followup.send(embed=embed)
        else:
            await ctx.send(embed=embed)

        # Task tracking — get_horoscope (only counts for "today")
        if day_str == "today":
            try:
                from Systems.Functions.tasks_db import tasks_db
                await tasks_db.update_progress(str(ctx.author.id), "get_horoscope")
            except Exception as _e:
                logger.warning(f"horoscope task tracking failed for {ctx.author.id}: {_e}")

    async def year_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[int]]:
        """Autocomplete for year input - shows suggestions after 3 digits are typed."""
        if len(current) < 3:
            return []
        
        try:
            current_year = datetime.now().year
            if current.isdigit():
                base = int(current)
                suggestions = []
                if len(current) == 3:
                    for i in range(10):
                        year = base * 10 + i
                        if 1900 <= year <= current_year + 10:
                            suggestions.append(app_commands.Choice(name=str(year), value=year))
                elif len(current) == 4:
                    if 1900 <= base <= current_year + 10:
                        suggestions.append(app_commands.Choice(name=str(base), value=base))
                else:
                    if 1900 <= base <= current_year:
                        suggestions.append(app_commands.Choice(name=str(base), value=base))
                
                return suggestions[:25] 
        except ValueError:
            pass
        
        return []

    async def day_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[int]]:
        """Autocomplete for day input - simple 1-31 range."""
        try:
            if current.isdigit():
                val = int(current)
                return [
                    app_commands.Choice(name=str(i), value=i)
                    for i in range(1, 32) if str(i).startswith(current)
                ][:25]
            return []
        except ValueError:
            return []

    @app_commands.command(name="astrology", description="Show your zodiac sign info based on your birthday")
    @app_commands.describe(
        month="Select your birth month",
        day="Select your birth day (autocomplete after first digit)",
        year="Enter your birth year (autocomplete after 3 digits)"
    )
    @app_commands.choices(month=[
        app_commands.Choice(name=datetime(2000, i, 1).strftime("%B"), value=i)
        for i in range(1, 13)
    ])
    @app_commands.autocomplete(day=day_autocomplete, year=year_autocomplete)
    async def astrology(self, interaction: discord.Interaction, month: app_commands.Choice[int], day: int, year: int):
        """Slash command to display a rich embed of zodiac info for the provided birthday using separate month/day/year inputs."""
        month_value = month.value
        day_value = day
        current_year = datetime.now().year
        if not (1900 <= year <= current_year):
            await interaction.response.send_message(
                f"❌ Invalid year! Please enter a year between 1900 and {current_year}.",
                ephemeral=True,
            )
            return
        try:
            user_birthday = date(year, month_value, day_value)
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid date. Please check the month/day combination (e.g., February 29 only on leap years).",
                ephemeral=True,
            )
            return
        if user_birthday > date.today():
            await interaction.response.send_message(
                "❌ Date cannot be in the future. Please select today or a past date.",
                ephemeral=True,
            )
            return

        sign_name = self._zodiac_for_date(user_birthday)
        sign_data = await self._find_sign_data(sign_name)
        if not sign_data:
            await interaction.response.send_message(
                f"❌ Could not find data for {sign_name}.", ephemeral=True
            )
            return

        chinese_data = await self._find_chinese_sign_by_birthday(user_birthday)
        
        if not chinese_data:
            await interaction.response.send_message(
                f"❌ Could not find Chinese zodiac data for year {year}.", ephemeral=True
            )
            return

        spirit_data = await self._find_primal_entry(sign_name, chinese_data.get("Name", ""))
        
        # Send initial Western page with buttons
        view = AstrologyView(
            self,
            sign_data,
            chinese_data,
            spirit_data,
            user_birthday,
            sign_name,
            chinese_data.get("Name", "")
        )
        initial_embed = view.get_embed()
        await interaction.response.send_message(embed=initial_embed, view=view)

async def setup(bot: commands.Bot) -> None:
    cog = AstrologyCog(bot)
    await bot.add_cog(cog)