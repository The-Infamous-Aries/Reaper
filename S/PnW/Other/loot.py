import discord
from discord.ext import commands
import re
import asyncio
from typing import Dict, List, Optional, Any
from Systems.Functions import emoji as emoji_mod

class Loot(commands.Cog):
    """Loot processing system for P&W war messages."""
    
    def __init__(self, bot):
        self.bot = bot
        # Resource mapping for standardization
        self.resource_mapping = {
            'food': 'FOOD',
            'coal': 'COAL', 
            'oil': 'OIL',
            'uranium': 'URANIUM',
            'lead': 'LEAD',
            'iron': 'IRON',
            'bauxite': 'BAUXITE',
            'gasoline': 'GASOLINE',
            'munitions': 'MUNITIONS',
            'steel': 'STEEL',
            'aluminum': 'ALUMINUM',
            'credit': 'CREDIT'
        }
        
        # Policy multipliers
        self.policy_multipliers = {
            'base': 0.10,           # 10% base loot
            'pirate': 1.4,         # 40% increase from Pirate policy
            'ape': 1.1,            # 10% increase from Advanced Pirate Economics
            'moneybags': 0.6         # 40% reduction from Moneybags policy
        }

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user:
            return

        if self.bot.user.mentioned_in(message):
            content = message.content.lower()
            
            # Handle intelligence messages (projected loot)
            if 'gathered intelligence' in content or 'spies discovered' in content:
                await self.process_intelligence(message)
            
            # Handle actual loot messages
            elif 'looted' in content and ('defeated' in content or 'crushed' in content or 'surrender' in content):
                await self.process_loot(message)

    async def process_intelligence(self, message):
        """Process intelligence messages and show projected loot calculations."""
        try:
            # Extract resource data from intelligence message
            intel_data = self._extract_intelligence_data(message.content)
            if not intel_data:
                return

            # Get trade values for calculations
            trade_data = await self._get_trade_values()
            if not trade_data:
                await message.channel.send("❌ Could not fetch trade values.")
                return

            # Calculate projected loot scenarios
            projected_scenarios = self._calculate_projected_loot(intel_data, trade_data)
            
            # Create and send embed
            embed = self._create_projected_embed(projected_scenarios, intel_data, message.author)
            await message.channel.send(embed=embed)

        except Exception as e:
            print(f"Error processing intelligence: {e}")
            await message.channel.send(f"❌ Error processing intelligence: {str(e)}")

    async def process_loot(self, message):
        """Process loot messages and create embed with values."""
        try:
            # Extract loot data from message
            loot_data = self._extract_loot_data(message.content)
            if not loot_data:
                return

            # Get trade values
            trade_data = await self._get_trade_values()
            if not trade_data:
                await message.channel.send("❌ Could not fetch trade values.")
                return

            # Calculate total values
            loot_summary = self._calculate_loot_values(loot_data, trade_data)
            
            # Create and send embed
            embed = self._create_loot_embed(loot_summary, message.author)
            await message.channel.send(embed=embed)

        except Exception as e:
            print(f"Error processing loot: {e}")
            await message.channel.send(f"❌ Error processing loot: {str(e)}")

    def _extract_intelligence_data(self, content: str) -> Optional[Dict[str, float]]:
        """Extract resource and money data from intelligence message."""
        try:
            intel_data = {}
            
            # Extract money value
            money_pattern = r'\$([0-9,]+(?:\.[0-9]{2})?)'
            money_match = re.search(money_pattern, content)
            if money_match:
                intel_data['money'] = float(money_match.group(1).replace(',', ''))
            else:
                intel_data['money'] = 0

            # Extract resources
            for resource_key, resource_name in self.resource_mapping.items():
                if resource_key == 'credit':
                    continue
                
                # Pattern to match resource amounts in intelligence format
                resource_pattern = r'([0-9,]+(?:\.[0-9]{2})?)\s+' + re.escape(resource_key)
                matches = re.findall(resource_pattern, content, re.IGNORECASE)
                
                total_amount = 0
                for match in matches:
                    amount = float(match.replace(',', ''))
                    total_amount += amount
                
                if total_amount > 0:
                    intel_data[resource_name] = total_amount

            return intel_data if (intel_data['money'] > 0 or len(intel_data) > 1) else None

        except Exception as e:
            print(f"Error extracting intelligence data: {e}")
            return None

    def _extract_loot_data(self, content: str) -> Optional[Dict[str, float]]:
        """Extract looted resources and money from message content."""
        try:
            loot_data = {}
            
            # Extract money values
            money_pattern = r'\$([0-9,]+(?:\.[0-9]{2})?)'
            money_matches = re.findall(money_pattern, content)
            total_money = 0
            for money_str in money_matches:
                money_val = float(money_str.replace(',', ''))
                total_money += money_val
            loot_data['money'] = total_money

            # Extract resources
            for resource_key, resource_name in self.resource_mapping.items():
                if resource_key == 'credit':
                    continue  # Skip credit for now
                
                # Pattern to match resource amounts (handles both "32.00 coal" and "1,950.00 bauxite")
                resource_pattern = r'([0-9,]+(?:\.[0-9]{2})?)\s+' + re.escape(resource_key)
                matches = re.findall(resource_pattern, content, re.IGNORECASE)
                
                total_amount = 0
                for match in matches:
                    amount = float(match.replace(',', ''))
                    total_amount += amount
                
                if total_amount > 0:
                    loot_data[resource_name] = total_amount

            return loot_data if (loot_data.get('money', 0) > 0 or len(loot_data) > 1) else None

        except Exception as e:
            print(f"Error extracting loot data: {e}")
            return None

    def _calculate_projected_loot(self, intel_data: Dict[str, float], trade_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate projected loot amounts for different policy combinations."""
        try:
            # Create price mapping from trade data (using best sell offer)
            price_map = {}
            for item in trade_data:
                resource_name = item.get('resource', '').upper()
                best_sell_price = item.get('best_sell_offer', {}).get('price', 0)
                if resource_name and best_sell_price > 0:
                    price_map[resource_name] = best_sell_price

            scenarios = {}
            
            # Calculate for each scenario
            scenarios_config = [
                {'name': 'Total Possible w/out Pirate or APE', 'multipliers': ['base']},
                {'name': 'Total Possible w/out Pirate or APE but with Moneybags', 'multipliers': ['base', 'moneybags']},
                {'name': 'Total Possible w/Pirate but not APE or Moneybags', 'multipliers': ['base', 'pirate']},
                {'name': 'Total Possible w/Pirate & Moneybags but not APE', 'multipliers': ['base', 'pirate', 'moneybags']},
                {'name': 'Total Possible w/Pirate & APE but not Moneybags', 'multipliers': ['base', 'pirate', 'ape']},
                {'name': 'Total Possible w/Pirate, APE & Moneybags', 'multipliers': ['base', 'pirate', 'ape', 'moneybags']}
            ]
            
            for scenario in scenarios_config:
                total_multiplier = 1.0
                for multiplier_key in scenario['multipliers']:
                    total_multiplier *= self.policy_multipliers[multiplier_key]
                
                # Calculate projected values
                projected_money = intel_data.get('money', 0) * total_multiplier
                projected_resources = {}
                total_resource_value = 0
                
                for resource_name, amount in intel_data.items():
                    if resource_name == 'money':
                        continue
                    
                    if resource_name in price_map:
                        projected_amount = amount * total_multiplier
                        unit_price = price_map[resource_name]
                        projected_value = projected_amount * unit_price
                        total_resource_value += projected_value
                        
                        projected_resources[resource_name] = {
                            'original_amount': amount,
                            'projected_amount': projected_amount,
                            'unit_price': unit_price,
                            'projected_value': projected_value
                        }
                
                scenarios[scenario['name']] = {
                    'multiplier': total_multiplier,
                    'projected_money': projected_money,
                    'projected_resources': projected_resources,
                    'total_resource_value': total_resource_value,
                    'grand_total': projected_money + total_resource_value
                }

            return scenarios

        except Exception as e:
            print(f"Error calculating projected loot: {e}")
            return {}

    async def _get_trade_values(self) -> Optional[List[Dict[str, Any]]]:
        """Get current trade values from the API."""
        try:
            # Try to get the query system from existing cogs
            for cog_name in ['SnipeGuide', 'Alliance']:
                cog = self.bot.get_cog(cog_name)
                if cog and hasattr(cog, 'query'):
                    return await cog.query.get_trade_resource_values()
            
            # Fallback: try to import and create query instance
            try:
                from Systems.PnW.Util.query import create_v3_query_instance
                from Systems.Functions.config import PANDW_API_KEY
                
                query = create_v3_query_instance(api_key=PANDW_API_KEY)
                return await query.get_trade_resource_values()
            except Exception as e:
                print(f"Could not create query instance: {e}")
                return None

        except Exception as e:
            print(f"Error getting trade values: {e}")
            return None

    def _calculate_loot_values(self, loot_data: Dict[str, float], trade_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate the total value of looted resources."""
        try:
            # Create price mapping from trade data (using best sell offer)
            price_map = {}
            for item in trade_data:
                resource_name = item.get('resource', '').upper()
                best_sell_price = item.get('best_sell_offer', {}).get('price', 0)
                if resource_name and best_sell_price > 0:
                    price_map[resource_name] = best_sell_price

            # Calculate resource values
            resource_breakdown = {}
            total_resource_value = 0

            for resource_name, amount in loot_data.items():
                if resource_name == 'money':
                    continue
                
                if resource_name in price_map:
                    unit_price = price_map[resource_name]
                    total_value = amount * unit_price
                    total_resource_value += total_value
                    
                    resource_breakdown[resource_name] = {
                        'amount': amount,
                        'unit_price': unit_price,
                        'total_value': total_value
                    }

            # Calculate totals
            total_money = loot_data.get('money', 0)
            grand_total = total_money + total_resource_value

            return {
                'money': total_money,
                'resources': resource_breakdown,
                'total_resource_value': total_resource_value,
                'grand_total': grand_total,
                'price_map': price_map
            }

        except Exception as e:
            print(f"Error calculating loot values: {e}")
            return {'money': loot_data.get('money', 0), 'resources': {}, 'total_resource_value': 0, 'grand_total': loot_data.get('money', 0)}

    def _create_projected_embed(self, scenarios: Dict[str, Any], intel_data: Dict[str, float], author: discord.Member) -> discord.Embed:
        """Create a rich embed showing projected loot calculations."""
        try:
            embed = discord.Embed(
                title="🔮 Projected Loot Summary",
                description="Potential loot based on different policy combinations",
                color=discord.Color.purple()
            )

            # --- Current Resources Section ---
            current_resources = []
            emoji_map = emoji_mod.resource_codes()
            for resource_name, amount in intel_data.items():
                if resource_name == 'money':
                    continue
                emoji = emoji_map.get(resource_name.upper()) or ''
                current_resources.append(f"{emoji} {amount:,.0f} {resource_name.title()}")
            
            money_emoji = '💲'
            current_info = f"{money_emoji} Money: ${intel_data.get('money', 0):,.2f}"
            if current_resources:
                current_info += f"\n" + ' '.join(current_resources)
            
            embed.add_field(
                name="Current Target Resources",
                value=current_info,
                inline=False
            )

            # --- Projected Resource Amounts Section ---
            embed.add_field(name="--- Projected Lootable Resources ---", value="\u200b", inline=False)

            no_ape_scenario_name = 'Total Possible w/Pirate but not APE or Moneybags'
            with_ape_scenario_name = 'Total Possible w/Pirate & APE but not Moneybags'

            no_ape_data = scenarios.get(no_ape_scenario_name)
            with_ape_data = scenarios.get(with_ape_scenario_name)

            if not no_ape_data or not with_ape_data:
                embed.add_field(name="Error", value="Could not calculate all required scenarios.", inline=False)
            else:
                if no_ape_data['projected_resources']:
                    for resource_name, _ in no_ape_data['projected_resources'].items():
                        emoji = emoji_map.get(resource_name.upper()) or '📦'
                        no_ape_amount = no_ape_data['projected_resources'][resource_name]['projected_amount']
                        with_ape_amount = with_ape_data['projected_resources'][resource_name]['projected_amount']

                        embed.add_field(
                            name=f"{emoji} {resource_name.title()}",
                            value=f"Without APE: {no_ape_amount:,.2f}\nWith APE: {with_ape_amount:,.2f}",
                            inline=False
                        )
                else:
                    embed.add_field(name="No Resources", value="Target has no resources to loot.", inline=False)
            
            # --- Total Value Section ---
            if no_ape_data and with_ape_data:
                embed.add_field(name='--- Projected Total Values ---', value='\u200b', inline=False)
                embed.add_field(
                    name="Max Loot Value (w/out APE)",
                    value=f"**${no_ape_data['grand_total']:,.2f}**",
                    inline=False
                )
                embed.add_field(
                    name="Max Loot Value (w/ APE)",
                    value=f"**${with_ape_data['grand_total']:,.2f}**",
                    inline=False
                )

            embed.set_footer(
                text=f"Requested by {author.display_name}",
                icon_url=author.display_avatar.url if author.display_avatar else None
            )
            embed.timestamp = discord.utils.utcnow()

            return embed

        except Exception as e:
            print(f"Error creating projected embed: {e}")
            return discord.Embed(
                title="🔮 Projected Loot Summary",
                description="Error calculating projections",
                color=discord.Color.red()
            )

    def _create_loot_embed(self, loot_summary: Dict[str, Any], author: discord.Member) -> discord.Embed:
        """Create a rich embed showing looted resource values."""
        try:
            embed = discord.Embed(
                title="💰 War Loot Summary",
                description="Looted resource values calculated using best sell offers",
                color=discord.Color.gold()
            )

            # Add money field
            if loot_summary['money'] > 0:
                money_emoji = '💲'
                embed.add_field(
                    name=f"{money_emoji} Money Looted",
                    value=f"${loot_summary['money']:,.2f}",
                    inline=False
                )

            # Add resource fields
            resources = loot_summary['resources']
            if resources:
                emoji_map = emoji_mod.resource_codes()
                for resource_name, data in resources.items():
                    emoji = emoji_map.get(resource_name.upper()) or '📦'
                    embed.add_field(
                        name=f"{emoji} {resource_name.title()}",
                        value=f"({data['amount']:,.2f}) - (${data['total_value']:,.2f})",
                        inline=False
                    )

            # Add total fields
            embed.add_field(
                name="📊 Totals",
                value=f"Resource Value: ${loot_summary['total_resource_value']:,.2f}\n"
                      f"**Grand Total: ${loot_summary['grand_total']:,.2f}**",
                inline=False
            )

            embed.set_footer(
                text=f"Requested by {author.display_name}",
                icon_url=author.display_avatar.url if author.display_avatar else None
            )
            embed.timestamp = discord.utils.utcnow()

            return embed

        except Exception as e:
            print(f"Error creating embed: {e}")
            # Fallback embed
            return discord.Embed(
                title="💰 War Loot Summary",
                description=f"Total Value: ${loot_summary.get('grand_total', 0):,.2f}",
                color=discord.Color.gold()
            )

async def setup(bot):
    await bot.add_cog(Loot(bot))