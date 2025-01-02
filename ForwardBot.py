import discord
from discord.ext import commands
import re
import aiosqlite
import os  # To check for database existence
import asyncio  # Import asyncio to manage the event loop
from dotenv import load_dotenv

load_dotenv()

# Define the database path (ensure it is a permanent location)
DB_PATH = "forwarding.db"  # This will store the database in the current directory

# Database setup function
async def init_db():
    # Check if the database file exists, if not, create it
    if not os.path.exists(DB_PATH):
        async with aiosqlite.connect(DB_PATH) as db:
            # Create the sources table if it doesn't exist
            await db.execute('''CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_channel TEXT,
                target_channel TEXT
            )''')
            await db.commit()

# Initialize bot
intents = discord.Intents.default()
intents.message_content = True  # Ensure the bot can read message content
bot = commands.Bot(command_prefix="!", intents=intents)

# Event to initialize the database when bot is ready
@bot.event
async def on_ready():
    print(f"Bot is logged in as {bot.user}")

# Command to add a source channel to the database using mention
@bot.command()
async def source(ctx, channel: discord.TextChannel):
    """Add a source channel to the database using mention."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Check if the source channel is already in the database
        async with db.execute("SELECT * FROM sources WHERE source_channel = ?", (str(channel.id),)) as cursor:
            existing = await cursor.fetchone()
            if existing:
                await ctx.send(f"Source channel {channel.mention} is already added.")
                return
        
        # Add the source channel to the database
        await db.execute("INSERT INTO sources (source_channel) VALUES (?)", (str(channel.id),))
        await db.commit()
    await ctx.send(f"Source channel {channel.mention} added.")

# Command to list all source channels
@bot.command()
async def listsources(ctx):
    """List all source channels."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM sources") as cursor:
            sources = await cursor.fetchall()
    if sources:
        sources_list = "\n".join([f"Source Channel: <#{source[1]}>" for source in sources])
        await ctx.send(f"Source channels:\n{sources_list}")
    else:
        await ctx.send("No source channels found.")

# Command to pair source and target channels or threads using mentions
@bot.command()
async def target(ctx, source_channel, target_channel):
    """Pair a source channel with a target channel or thread using mentions."""
    source_channel = discord.utils.get(ctx.guild.text_channels, mention=source_channel) or discord.utils.get(ctx.guild.threads, mention=source_channel)
    target_channel = discord.utils.get(ctx.guild.text_channels, mention=target_channel) or discord.utils.get(ctx.guild.threads, mention=target_channel)
    
    if not source_channel or not target_channel:
        await ctx.send("Invalid source or target. Please mention valid channels or threads.")
        return

    # Update the database with the source-target pairing
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE sources SET target_channel = ? WHERE source_channel = ?",
                         (str(target_channel.id), str(source_channel.id)))
        await db.commit()

    await ctx.send(f"Source {source_channel.mention} paired with target {target_channel.mention}.")

# Command to list source-target pairs
@bot.command()
async def sourcepair(ctx):
    """List source-target pairs."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM sources WHERE target_channel IS NOT NULL") as cursor:
            pairs = await cursor.fetchall()
    if pairs:
        pairs_list = "\n".join([f"Source: <#{pair[1]}> -> Target: <#{pair[2]}>" for pair in pairs])
        await ctx.send(f"Source-Target pairs:\n{pairs_list}")
    else:
        await ctx.send("No source-target pairs found.")

# Command to show help for all commands
@bot.command()
async def forwardhelp(ctx):
    """Show help for the commands."""
    help_text = """
    **Commands:**
    !source [#Channel Name] - Add a source channel by mentioning it.
    !listsources - List all source channels.
    !target [#Source Channel or #Source Thread] [#Target Channel or #Target Thread] - Pair source with target.
    !sourcepair - List source-target pairs.
    !removesource [#Channel Name] - Remove a source channel by mentioning it.
    !forwardhelp - Show this help message.
    """
    await ctx.send(help_text)

# Event to forward messages from source to target channels
@bot.event
async def on_message(message):
    # Skip processing if the message is a command
    if message.content.startswith("!"):
        await bot.process_commands(message)
        return

    # Only forward messages if they are in a source channel
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM sources WHERE source_channel = ?", (str(message.channel.id),)) as cursor:
            source = await cursor.fetchone()

    # If a source is found, check if it has a target channel
    if source:
        target_channel_id = source[2]  # The target_channel field
        if target_channel_id is None:
            # If there's no target channel set, skip forwarding this message
            return

        # Try to get the target channel
        target_channel = bot.get_channel(int(target_channel_id))

        if target_channel:
            # Check if the message contains custom emojis that may not be available in the target server
            content = message.content
            emoji_pattern = r"<a?:([a-zA-Z0-9_]+):([0-9]+)>"
            matches = re.findall(emoji_pattern, content)

            # For each custom emoji found in the message content
            for emoji_name, emoji_id in matches:
                # Try to find the emoji in the source server
                emoji = discord.utils.get(message.guild.emojis, name=emoji_name)
                if emoji:
                    # If the emoji exists in the source server, use it as is
                    continue
                else:
                    # If the emoji doesn't exist in the source server, try to find it in any of the bot's servers
                    target_emoji = None
                    for guild in bot.guilds:
                        target_emoji = discord.utils.get(guild.emojis, name=emoji_name)
                        if target_emoji:
                            break

                    # If we found the emoji in any of the bot's servers, replace it
                    if target_emoji:
                        content = content.replace(f"<:{emoji_name}:{emoji_id}>", f"<:{target_emoji.name}:{target_emoji.id}>")
                    else:
                        # If no matching emoji is found in any server, replace with a fallback
                        content = content.replace(f"<:{emoji_name}:{emoji_id}>", f":{emoji_name}:")
            
            # Process the embed content for custom emojis
            if message.embeds:
                for embed in message.embeds:
                    # Check title, description, fields, and footer for emojis
                    if embed.title:
                        embed.title = re.sub(emoji_pattern, lambda m: f"<:{m.group(1)}:{m.group(2)}>", embed.title)
                    if embed.description:
                        embed.description = re.sub(emoji_pattern, lambda m: f"<:{m.group(1)}:{m.group(2)}>", embed.description)
                    for field in embed.fields:
                        if field.name:
                            field.name = re.sub(emoji_pattern, lambda m: f"<:{m.group(1)}:{m.group(2)}>", field.name)
                        if field.value:
                            field.value = re.sub(emoji_pattern, lambda m: f"<:{m.group(1)}:{m.group(2)}>", field.value)
                    if embed.footer.text:
                        embed.footer.text = re.sub(emoji_pattern, lambda m: f"<:{m.group(1)}:{m.group(2)}>", embed.footer.text)

            # Forward the message to the target channel
            if isinstance(target_channel, discord.TextChannel):
                await target_channel.send(
                    content=content,
                    embed=message.embeds[0] if message.embeds else None,
                    files=message.attachments,
                    allowed_mentions=discord.AllowedMentions(everyone=False, users=False, roles=False)
                )
            elif isinstance(target_channel, discord.Thread):
                await target_channel.send(
                    content=content,
                    embed=message.embeds[0] if message.embeds else None,
                    files=message.attachments,
                    allowed_mentions=discord.AllowedMentions(everyone=False, users=False, roles=False)
                )

            # Forward stickers if present
            if message.stickers:
                for sticker in message.stickers:
                    await target_channel.send(sticker=sticker)

            # Forward all embeds
            if message.embeds:
                for embed in message.embeds:
                    await target_channel.send(embed=embed)

        else:
            print(f"Error: Target channel with ID {target_channel_id} not found.")
    else:
        # No source found, so we don't need to forward this message
        pass

    await bot.process_commands(message)

# Command to remove a source channel from the database using mention
@bot.command()
async def removesource(ctx, channel: discord.TextChannel):
    """Remove a source channel from the database using mention."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Check if the source channel exists in the database
        async with db.execute("SELECT * FROM sources WHERE source_channel = ?", (str(channel.id),)) as cursor:
            existing = await cursor.fetchone()
            if not existing:
                await ctx.send(f"Source channel {channel.mention} not found.")
                return
        
        # Remove the source channel from the database
        await db.execute("DELETE FROM sources WHERE source_channel = ?", (str(channel.id),))
        await db.commit()

    await ctx.send(f"Source channel {channel.mention} has been removed.")

# Initialize the database before starting the bot
async def start_bot():
    await init_db()
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise ValueError("No DISCORD_BOT_TOKEN found in environment variables")
    await bot.start(token)

# Run the bot (now awaiting the start_bot coroutine)
asyncio.run(start_bot())
