
import discord
import logging
import random
import asyncio
from typing import Optional, Dict, Any
from Systems.Functions import emoji as emoji_mod

logger = logging.getLogger(__name__)

def get_partial_emoji(name: str) -> Optional[discord.PartialEmoji]:
    """Helper to get PartialEmoji from emoji module"""
    emoji_id = emoji_mod.EMOJI_IDS.get(name)
    if emoji_id:
        return discord.PartialEmoji(name=name, id=emoji_id)
    return None

class StoryMapManager:
    """Independent story map manager that loads directly from Walk Tru JSON files"""
    
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__ + '.StoryMapManager')
        self.story_maps = {}  
        self._story_configs = {
            'horror': {
                'filename': 'Horror.json',
                'title': f'{emoji_mod.mention("Haunted")} THE HAUNTED SANITARIUM {emoji_mod.mention("Haunted")}',
                'description': 'Escape from a decrepit sanitarium filled with malevolent spirits and dark secrets.',
                'start_stage': 'event_start',
                'mechanic': 'fear',
                'emoji': emoji_mod.mention("Haunted"),
                'emoji_key': 'Haunted',
                'starting_value': 0
            },
            'ganster': {
                'filename': 'Ganster.json',
                'title': f'{emoji_mod.mention("Mafia")} THE GANGSTER\'S RISE {emoji_mod.mention("Mafia")}',
                'description': 'Build your criminal empire in the dangerous underworld of organized crime.',
                'start_stage': 'event_start',
                'mechanic': 'heat',
                'emoji': emoji_mod.mention("Mafia"),
                'emoji_key': 'Mafia',
                'starting_value': 0
            },
            'knight': {
                'filename': 'Knight.json',
                'title': f'{emoji_mod.mention("Knight")} THE KNIGHT\'S QUEST {emoji_mod.mention("Knight")}',
                'description': 'Embark on a medieval adventure as Sir Gareth, facing moral dilemmas and epic quests.',
                'start_stage': 'event_start',
                'mechanic': 'honor',
                'emoji': emoji_mod.mention("Knight"),
                'emoji_key': 'Knight',
                'starting_value': 100
            },
            'robot': {
                'filename': 'Robot.json',
                'title': f'{emoji_mod.mention("Robot")} THE ROBOT UPRISING {emoji_mod.mention("Robot")}',
                'description': 'Navigate a dystopian future where artificial intelligence has taken control.',
                'start_stage': 'event_start',
                'mechanic': 'power',
                'emoji': emoji_mod.mention("Robot"),
                'emoji_key': 'Robot',
                'starting_value': 0
            },
            'western': {
                'filename': 'Western.json',
                'title': f'{emoji_mod.mention("Western")} THE WESTERN FRONTIER {emoji_mod.mention("Western")}',
                'description': 'Ride into the Wild West and forge your legend in dusty towns and dangerous territories.',
                'start_stage': 'event_start',
                'mechanic': 'health',
                'emoji': emoji_mod.mention("Western"),
                'emoji_key': 'Western',
                'starting_value': 100
            },
            'wizard': {
                'filename': 'Wizard.json',
                'title': f'{emoji_mod.mention("Wizard")} THE WIZARD\'S APPRENTICE {emoji_mod.mention("Wizard")}',
                'description': 'Begin your magical journey as a young wizard\'s apprentice investigating mysterious magic.',
                'start_stage': 'event_start',
                'mechanic': 'mana',
                'emoji': emoji_mod.mention("Wizard"),
                'emoji_key': 'Wizard',
                'starting_value': 100
            }
        }
        self._cache = {}
    
    async def load_story_maps(self):
        """Load all story maps using centralized data manager"""
        self.story_maps = {} 
        story_configs = {
            'horror': {
                'title': f'{emoji_mod.mention("Haunted")} Horror Sanitarium',
                'description': 'Survive the supernatural horrors of an abandoned sanitarium while managing your fear. Navigate through 20 terrifying events, uncover dark secrets, and confront Dr. Crowley\'s evil experiments. Your fear level determines your fate as you battle both external horrors and internal terror.',
                'mechanic': 'fear',
                'mechanic_emoji': emoji_mod.mention("Haunted"),
                'emoji_key': 'Haunted',
                'mechanic_name': 'Fear',
                'min_value': 0,
                'max_value': 100,
                'starting_value': 0,
                'progress_emoji': emoji_mod.mention("Haunted"),
                'warning_thresholds': {
                    'caution': 25,
                    'warning': 50,
                    'danger': 75,
                    'critical': 90
                },
                'max_fear': 100,
                'starting_fear': 0,
                'fear_mechanics': {
                    'max_fear': 100,
                    'starting_fear': 0
                }
            },
            'ganster': {
                'title': f'{emoji_mod.mention("Mafia")} 1920s Chicago Gangster',
                'description': 'Navigate the criminal underworld of 1920s Chicago. Build your reputation, avoid the heat from authorities, and rise through the ranks of organized crime. Every choice affects your Heat level with law enforcement.',
                'mechanic': 'heat',
                'mechanic_emoji': emoji_mod.mention("Mafia"),
                'emoji_key': 'Mafia',
                'mechanic_name': 'Heat',
                'min_value': 0,
                'max_value': 100,
                'starting_value': 0,
                'progress_emoji': emoji_mod.mention("Mafia"),
                'warning_thresholds': {
                    'caution': 25,
                    'warning': 50,
                    'danger': 75,
                    'critical': 90
                },
                'max_heat': 100,
                'natural_decay': 2,
                'decay_frequency': 3,
                'heat_mechanics': {
                    'max_heat': 100,
                    'natural_decay': 2,
                    'decay_frequency': 3
                }
            },
            'knight': {
                'title': f'{emoji_mod.mention("Knight")} Knight\'s Quest',
                'description': 'Embark on a noble quest as Sir Gareth, testing your honor and chivalry at every turn. Start with 100 honor and navigate moral dilemmas to determine your legacy.',
                'mechanic': 'honor',
                'mechanic_emoji': emoji_mod.mention("Knight"),
                'emoji_key': 'Knight',
                'mechanic_name': 'Honor',
                'min_value': 0,
                'max_value': 150,
                'starting_value': 100,
                'progress_emoji': emoji_mod.mention("Knight"),
                'warning_thresholds': {
                    'critical': 10,
                    'danger': 25,
                    'warning': 50,
                    'caution': 75
                },
                'starting_honor': 100,
                'max_honor': 150,
                'min_honor': 0,
                'natural_decay': 0,
                'decay_frequency': 0,
                'honor_gain_bonus_threshold': 120,
                'honor_gain_bonus_message': 'Your exceptional honor inspires others and makes future noble choices easier.',
                'honor_mechanics': {
                    'starting_honor': 100,
                    'max_honor': 150,
                    'min_honor': 0,
                    'natural_decay': 0,
                    'decay_frequency': 0,
                    'honor_gain_bonus_threshold': 120,
                    'honor_gain_bonus_message': 'Your exceptional honor inspires others and makes future noble choices easier.'
                }
            },
            'robot': {
                'title': f'{emoji_mod.mention("Robot")} Robot Factory Escape',
                'description': 'Escape from a robot factory by managing your power levels. Start at 0% power and reach 100% by stage 10 to build your robot body, then maintain power above 0% to survive until escape.',
                'mechanic': 'power',
                'mechanic_emoji': emoji_mod.mention("Robot"),
                'emoji_key': 'Robot',
                'mechanic_name': 'Power',
                'min_value': 0,
                'max_value': 100,
                'starting_value': 0,
                'progress_emoji': emoji_mod.mention("Robot"),
                'warning_thresholds': {
                    'critical': 10,
                    'danger': 25,
                    'warning': 50,
                    'caution': 75
                },
                'power_threshold_stage_10': 100,
                'power_failure_threshold': 0,
                'power_conservation_bonus': 'Successful power conservation choices provide small bonuses',
                'power_mechanics': {
                    'power_threshold_stage_10': 100,
                    'power_failure_threshold': 0,
                    'power_conservation_bonus': 'Successful power conservation choices provide small bonuses'
                }
            },
            'western': {
                'title': f'{emoji_mod.mention("Western")} Western Adventure',
                'description': 'Live the life of a legendary gunslinger through the American frontier. Manage your health as you face duels, poker games, train robberies, and the dangers of the Wild West. Every choice affects your survival in this unforgiving land.',
                'mechanic': 'health',
                'mechanic_emoji': emoji_mod.mention("Western"),
                'emoji_key': 'Western',
                'mechanic_name': 'Health',
                'min_value': 0,
                'max_value': 100,
                'starting_value': 100,
                'progress_emoji': emoji_mod.mention("Western"),
                'warning_thresholds': {
                    'critical': 10,
                    'danger': 25,
                    'warning': 50,
                    'caution': 75
                },
                'starting_health': 100,
                'max_health': 100,
                'min_health': 0,
                'natural_recovery': 2,
                'recovery_frequency': 3,
                'health_mechanics': {
                    'starting_health': 100,
                    'max_health': 100,
                    'min_health': 0,
                    'natural_recovery': 2,
                    'recovery_frequency': 3
                }
            },
            'wizard': {
                'title': f'{emoji_mod.mention("Wizard")} Wizard\'s Magical Journey',
                'description': 'Embark on an epic magical adventure as a young wizard\'s apprentice. Master spells, manage your mana wisely, and face legendary challenges. Your magical journey spans 20+ events with complex spellcasting decisions.',
                'mechanic': 'mana',
                'mechanic_emoji': emoji_mod.mention("Wizard"),
                'mechanic_name': 'Mana',
                'min_value': 0,
                'max_value': 150,
                'starting_value': 100,
                'progress_emoji': emoji_mod.mention("Wizard"),
                'warning_thresholds': {
                    'critical': 10,
                    'danger': 25,
                    'warning': 50,
                    'caution': 75
                },
                'max_mana': 150,
                'min_mana': 0,
                'starting_mana': 100,
                'natural_recovery': 2,
                'recovery_frequency': 'every_3_stages',
                'mana_warning_threshold': 20,
                'critical_mana_threshold': 10,
                'auto_defeat_threshold': 0,
                'mana_mechanics': {
                    'starting_mana': 100,
                    'max_mana': 150,
                    'min_mana': 0,
                    'natural_recovery': 2,
                    'recovery_frequency': 'every_3_stages',
                    'mana_warning_threshold': 20,
                    'critical_mana_threshold': 10,
                    'auto_defeat_threshold': 0
                }
            }
        }

        for adventure_type, config in story_configs.items():
            try:
                data_key = f'walktru_{adventure_type}'
                story_data = await self.bot.user_data_manager.get_json_data(data_key)
                
                if story_data:
                    # Merge base config with loaded data
                    story_data.update({
                        'adventure_type': adventure_type,
                        'emoji': config['mechanic_emoji'],
                        'starting_value': config['starting_value'],
                        'max_value': config['max_value'],
                        'start_stage': 'event_start',
                        'title': f"{config['title']}",
                        'mechanic': config['mechanic'],
                        'mechanics': config
                    })
                    
                    self.story_maps[adventure_type] = story_data
                else:
                    logger.warning(f"Story data not found for {adventure_type}")
                    
            except Exception as e:
                logger.error(f"Error loading story map {adventure_type}: {e}")

        logger.info(f"Loaded {len(self.story_maps)} story maps")
        return self.story_maps
    
    async def _load_story_data(self, story_key):
        """Helper method to load story data using centralized user_data_manager"""
        try:
            if story_key not in self._story_configs:
                self.logger.error(f"Unknown story key: {story_key}")
                return None

            data_key = f'walktru_{story_key}'
            story_data = await self.bot.user_data_manager.load_json_data(data_key)
            
            if not story_data:
                self.logger.error(f"Story data empty for {story_key}")
                return None
                
            return story_data
            
        except Exception as e:
            self.logger.error(f"Error loading story data for {story_key}: {e}")
            return None
    
    async def load_story_maps_lazy(self):
        """Lazy loading wrapper with error handling"""
        try:
            self.story_maps = await self.load_story_maps()
            return self.story_maps
        except Exception as e:
            logger.error(f"Error in lazy loading: {e}")
            self.story_maps = {}
            return {}

story_map_manager = None

def create_progress_bar(current, maximum, filled_emoji, empty_emoji, length=10):
    """Create a visual progress bar with emojis"""
    if maximum == 0:
        percentage = 0
    else:
        percentage = min(100, max(0, (current / maximum) * 100))
    
    filled = int((percentage / 100) * length)
    empty = length - filled
    
    bar = filled_emoji * filled + empty_emoji * empty
    return f"{bar} {current}/{maximum} ({percentage:.0f}%)"

def get_mechanic_display(adventure_type, current_value, story_data):
    """Get the display for the current mechanic with warning messages"""
    config = story_data
    mechanics = config.get('mechanics', {})
    
    # Use adventure specific emoji for filled part, black square for empty
    filled_emoji = config.get('emoji', '⬜')
    empty_emoji = '⬛'
    
    max_val = mechanics.get(f'max_{adventure_type}', 100)
    min_val = mechanics.get(f'min_{adventure_type}', 0)
    
    bar = create_progress_bar(current_value, max_val, filled_emoji, empty_emoji)
    
    warning = None
    warning_thresholds = mechanics.get('warning_thresholds', {})
    threshold_keys = {
        'horror': 'fear',
        'ganster': 'heat',
        'knight': 'honor',
        'robot': 'power',
        'western': 'health',
        'wizard': 'mana'
    }
    
    threshold_key = threshold_keys.get(adventure_type, adventure_type)
    specific_thresholds = warning_thresholds.get(threshold_key, {})
    
    if adventure_type == 'horror':
        warning = get_fear_warning(current_value, specific_thresholds)
    elif adventure_type == 'ganster':
        warning = get_heat_warning(current_value, specific_thresholds)
    elif adventure_type == 'knight':
        warning = get_honor_warning(current_value, specific_thresholds)
    elif adventure_type == 'robot':
        warning = get_power_warning(current_value, specific_thresholds)
    elif adventure_type == 'western':
        warning = get_health_warning(current_value, specific_thresholds)
    elif adventure_type == 'wizard':
        warning = get_mana_warning(current_value, max_val, specific_thresholds)
    
    return f"{bar}\n{warning}" if warning else bar

def get_fear_warning(fear, thresholds=None):
    if not thresholds:
        thresholds = {'critical': 90, 'danger': 75, 'warning': 50, 'caution': 25}
    
    if fear >= thresholds.get('critical', 90):
        return f"{emoji_mod.mention('Haunted')} You're on the verge of complete terror! One more scare could end everything!"
    elif fear >= thresholds.get('danger', 75):
        return f"{emoji_mod.mention('Haunted')} Your sanity is slipping away! Be very careful with your next choices!"
    elif fear >= thresholds.get('warning', 50):
        return "😰 Fear is taking hold. Choose wisely to avoid panic!"
    elif fear >= thresholds.get('caution', 25):
        return "😟 You're starting to feel uneasy. Stay alert!"
    return None

def get_heat_warning(heat, thresholds=None):
    if not thresholds:
        thresholds = {'critical': 90, 'danger': 75, 'warning': 50, 'caution': 25}
    
    if heat >= thresholds.get('critical', 90):
        return "🚨 The cops are closing in! One wrong move and you're going to jail!"
    elif heat >= thresholds.get('danger', 75):
        return "🔥 You're burning hot with the authorities! Lay low!"
    elif heat >= thresholds.get('warning', 50):
        return "⚠️ Police attention is increasing. Be more careful!"
    elif heat >= thresholds.get('caution', 25):
        return "👮 You're starting to attract unwanted attention."
    return None

def get_honor_warning(honor, thresholds=None):
    if not thresholds:
        thresholds = {'critical': 10, 'danger': 25, 'warning': 50, 'caution': 75}
    
    if honor <= thresholds.get('critical', 10):
        return f"{emoji_mod.mention('Knight')} Your honor is nearly lost! You're barely worthy of knighthood!"
    elif honor <= thresholds.get('danger', 25):
        return f"{emoji_mod.mention('Knight')} Your honor is severely tarnished! Act with virtue!"
    elif honor <= thresholds.get('warning', 50):
        return "⚠️ Your honor is questionable. Make noble choices!"
    elif honor <= thresholds.get('caution', 75):
        return "🏰 Your honor could be stronger. Stay true to knightly virtues!"
    return None

def get_power_warning(power, thresholds=None):
    if not thresholds:
        thresholds = {'critical': 10, 'danger': 25, 'warning': 50, 'caution': 75}
    
    if power <= thresholds.get('critical', 10):
        return f"{emoji_mod.mention('Robot')} Power critically low! Shutdown imminent!"
    elif power <= thresholds.get('danger', 25):
        return f"{emoji_mod.mention('Robot')} Low power reserves! Seek energy sources immediately!"
    elif power <= thresholds.get('warning', 50):
        return "🔌 Power levels dropping. Find energy soon!"
    elif power <= thresholds.get('caution', 75):
        return "🪫 Power could be higher for optimal performance."
    return None

def get_health_warning(current_health, thresholds=None):
    """Get health warning message for Western adventure"""
    if not thresholds:
        thresholds = {'critical': 10, 'danger': 25, 'warning': 50, 'caution': 75}
    
    if current_health <= thresholds.get('critical', 10):
        return f"{emoji_mod.mention('Western')} **CRITICAL**: You're barely alive! One more hit could be fatal!"
    elif current_health <= thresholds.get('danger', 25):
        return f"{emoji_mod.mention('Western')} **DANGER**: You're badly wounded! Seek medical attention!"
    elif current_health <= thresholds.get('warning', 50):
        return "🤕 **WARNING**: You're injured and need to be careful!"
    elif current_health <= thresholds.get('caution', 75):
        return "🩹 **CAUTION**: You've taken some damage. Watch your health!"
    return None

def get_mana_warning(current_mana, max_mana, thresholds=None):
    """Get mana warning message for Wizard adventure"""
    if not thresholds:
        thresholds = {'critical': 10, 'danger': 25, 'warning': 50, 'caution': 75}
    
    percentage = (current_mana / max_mana) * 100
    
    if percentage <= thresholds.get('critical', 10):
        return f"{emoji_mod.mention('Wizard')} **CRITICAL**: Mana nearly depleted! You can barely cast spells!"
    elif percentage <= thresholds.get('danger', 25):
        return f"{emoji_mod.mention('Wizard')} **DANGER**: Very low mana! Conserve your magical energy!"
    elif percentage <= thresholds.get('warning', 50):
        return "🌗 **WARNING**: Mana running low. Use magic wisely!"
    elif percentage <= thresholds.get('caution', 75):
        return "🌖 **CAUTION**: Mana could be higher for powerful spells."
    return None

def get_stat_bounds(adventure_type):
    """Get the minimum and maximum bounds for each adventure type's mechanic"""
    bounds = {
        'horror': {'min': 0, 'max': 100},    
        'ganster': {'min': 0, 'max': 100},  
        'knight': {'min': -50, 'max': 150},   
        'robot': {'min': 0, 'max': 100},      
        'western': {'min': 0, 'max': 100},   
        'wizard': {'min': 0, 'max': 150}       
    }
    return bounds.get(adventure_type, {'min': 0, 'max': 100})

def clamp_stat_value(value, adventure_type):
    """Clamp the stat value within the defined bounds"""
    bounds = get_stat_bounds(adventure_type)
    return max(bounds['min'], min(bounds['max'], value))

class WalktruView(discord.ui.View):
    def __init__(self, story_maps, user_id):
        super().__init__(timeout=600)  
        self.story_maps = story_maps
        self.user_id = user_id
        
        options = []
        # Use story_map_manager instance to access _story_configs if needed, 
        # or just rely on the passed story_maps keys if they match.
        # But we need the emoji_key from the manager.
        # Since story_maps is a dict of loaded data, and we don't have direct access to manager here easily 
        # unless we pass it or import the global.
        # The global 'story_map_manager' is available.
        
        manager = story_map_manager
        
        for key, config in manager._story_configs.items():
            # Get the correct emoji object for the select menu
            emoji_obj = get_partial_emoji(config.get('emoji_key', ''))
            
            options.append(discord.SelectOption(
                label=config['title'].replace(config['emoji'], '').strip(), # Remove emoji from title for clean label
                description=config['description'][:100],
                value=key,
                emoji=emoji_obj
            ))
            
        self.add_item(WalktruSelect(options))
        
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This menu is not for you.", ephemeral=True)
            return False
        return True

class WalktruSelect(discord.ui.Select):
    def __init__(self, options):
        super().__init__(placeholder="Choose an adventure...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        adventure_type = self.values[0]
        # Use the global manager
        if not story_map_manager:
            await interaction.response.send_message("System not initialized.", ephemeral=True)
            return
            
        story_data = story_map_manager.story_maps.get(adventure_type)
        if not story_data:
            await interaction.response.send_message("Error loading adventure.", ephemeral=True)
            return

        # Start the adventure
        view = WalktruChoiceView(interaction.user.id, story_data, adventure_type)
        await view.start_adventure(interaction)

class WalktruChoiceView(discord.ui.View):
    def __init__(self, user_id, story_data, adventure_type):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.story_data = story_data
        self.adventure_type = adventure_type
        self.current_stage_id = story_data.get('start_stage', 'event_start')
        self.current_mechanic_value = story_data.get('starting_value', 0)
        
        # Get bounds
        bounds = get_stat_bounds(adventure_type)
        self.current_mechanic_value = clamp_stat_value(self.current_mechanic_value, adventure_type)
        
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This adventure is not for you.", ephemeral=True)
            return False
        return True

    async def start_adventure(self, interaction: discord.Interaction):
        stage = self.get_stage(self.current_stage_id)
        if not stage:
            msg = "Error starting adventure: Stage not found."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return

        embed = self.create_embed(stage)
        self.update_buttons(stage)
        
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    def get_stage(self, stage_id):
        # Flatten the nested structure if needed, or search through events
        # The structure seems to be story_data['events'] -> list or dict
        events = self.story_data.get('events', {})
        # If events is a list (as in some JSONs), convert to dict or search
        if isinstance(events, list):
            for event in events:
                if event.get('id') == stage_id:
                    return event
            return None
        return events.get(stage_id)

    def create_embed(self, stage):
        embed = discord.Embed(
            title=f"{self.story_data.get('title', 'Adventure')} - {stage.get('title', 'Unknown Stage')}",
            description=stage.get('description', 'No description.'),
            color=discord.Color.blue()
        )
        
        # Add Mechanic Status
        mechanic_display = get_mechanic_display(
            self.adventure_type, 
            self.current_mechanic_value, 
            self.story_data
        )
        embed.add_field(
            name=f"{self.story_data.get('mechanic', 'Mechanic').title()} Status", 
            value=mechanic_display, 
            inline=False
        )
        
        if 'image_url' in stage:
            embed.set_image(url=stage['image_url'])
            
        return embed

    def update_buttons(self, stage):
        self.clear_items()
        choices = stage.get('choices', [])
        
        for i, choice in enumerate(choices):
            # Add emoji to button
            emoji_key = self.story_data.get('emoji_key', '')
            emoji_obj = get_partial_emoji(emoji_key)
            
            label = f"{i+1}"
            
            button = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.primary,
                custom_id=f"choice_{i}",
                emoji=emoji_obj,
                row=0
            )
            button.callback = self.make_choice_callback(i, choice)
            self.add_item(button)
            
        # Add Quit button
        quit_btn = discord.ui.Button(label="Quit", style=discord.ButtonStyle.danger, row=1)
        quit_btn.callback = self.quit_callback
        self.add_item(quit_btn)

    def make_choice_callback(self, index, choice):
        async def callback(interaction: discord.Interaction):
            # Calculate outcome
            success_chance = choice.get('success_chance', 100)
            roll = random.randint(1, 100)
            is_success = roll <= success_chance
            
            outcome = choice.get('success' if is_success else 'failure', {})
            
            # Update mechanic
            mechanic_change = outcome.get('mechanic_change', 0)
            self.current_mechanic_value += mechanic_change
            self.current_mechanic_value = clamp_stat_value(self.current_mechanic_value, self.adventure_type)
            
            # Next stage
            next_stage_id = outcome.get('next_stage')
            
            # Show outcome
            outcome_embed = discord.Embed(
                title="Choice Result",
                description=outcome.get('text', 'You move forward...'),
                color=discord.Color.green() if is_success else discord.Color.red()
            )
            
            if mechanic_change != 0:
                change_emoji = "⬆️" if mechanic_change > 0 else "⬇️"
                outcome_embed.add_field(
                    name=f"{self.story_data['emoji']} {self.story_data['mechanic'].title()} Change",
                    value=f"{change_emoji} {abs(mechanic_change)} points",
                    inline=True
                )
                
            await interaction.response.edit_message(embed=outcome_embed, view=None)
            await asyncio.sleep(2) # Reading time
            
            if not next_stage_id or next_stage_id == 'end':
                final_embed = discord.Embed(
                    title="Adventure Ended",
                    description="You have reached the end of your journey.",
                    color=discord.Color.gold()
                )
                await interaction.followup.send(embed=final_embed, ephemeral=True)
                self.stop()
            else:
                self.current_stage_id = next_stage_id
                await self.start_adventure(interaction)
                
        return callback

    async def quit_callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="Adventure ended.", view=None, embed=None)
        self.stop()
