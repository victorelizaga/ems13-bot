import discord
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
from pytz import timezone
import os, sys, random
from dotenv import load_dotenv

# ===================== ENV =====================
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    sys.exit("DISCORD_TOKEN missing")

# ===================== CHANNEL IDS =====================
LOGBOOK_CHANNEL_ID = 1435553972202246286
REPORTS_CHANNEL_ID = 1435554028145741834
ADMIN_CHANNEL_ID   = 1456045677862846638

# ===================== ROLES =====================
ADMIN_ROLE_NAME = "admin"
HIGHERUPS_ROLE_NAME = "higherups"

# ===================== BOT =====================
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ===================== TIMEZONE =====================
PH_TZ = timezone("Asia/Manila")

# ===================== DATA =====================
clocked_in = {}   # user_id -> datetime
duties = {}       # user_id -> list[{id,start,end}]

# ===================== HELPERS =====================
def display_name(m):
    return m.nick if m and m.nick else m.name

def duty_id():
    return str(random.randint(1000, 9999))

def time12(dt):
    return dt.astimezone(PH_TZ).strftime("%I:%M:%S %p")

def get_role(guild, name):
    return discord.utils.get(guild.roles, name=name)

def has_role(m, role):
    return any(r.name == role for r in m.roles)

def is_admin(m):
    return has_role(m, ADMIN_ROLE_NAME)

def is_higherups(m):
    return has_role(m, HIGHERUPS_ROLE_NAME)

def admin_only():
    async def p(ctx): return is_admin(ctx.author)
    return commands.check(p)

def override_allowed():
    async def p(ctx): return is_admin(ctx.author) or is_higherups(ctx.author)
    return commands.check(p)

def channel_only(cid):
    async def p(ctx): return ctx.channel.id == cid
    return commands.check(p)

def week_minutes(uid):
    start = datetime.now(PH_TZ) - timedelta(days=7)
    return sum(
        int((d["end"] - d["start"]).total_seconds() // 60)
        for d in duties.get(uid, []) if d["end"] >= start
    )

# ===================== EVENTS =====================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    scheduler.start()

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, (commands.CommandNotFound, commands.CheckFailure)):
        return
    raise error

# ===================== HELP =====================
@bot.command()
async def help(ctx):
    await ctx.send(
        "```EMS13 HR MANAGEMENT\n\n"
        "GENERAL\n"
        "!help\n!id\n!setnickname NAME\n\n"
        "LOGBOOK\n"
        "!clockin\n!clockout\n!status\n"
        "!override clockin|clockout ID\n\n"
        "REPORTS (ADMIN)\n"
        "!report\n!singlereport ID\n!void ID DUTYID\n\n"
        "ADMIN CHANNEL\n"
        "!admin\n!addadmin ID\n!removeadmin ID\n"
        "!employee delete ID\n```"
    )

# ===================== GENERAL =====================
@bot.command()
async def id(ctx):
    await ctx.send(f"`{ctx.author.id}`")

@bot.command()
async def setnickname(ctx, *, name):
    try:
        await ctx.author.edit(nick=name)
        await ctx.send(f"```Nickname set to {name}```")
    except discord.Forbidden:
        await ctx.send("```Bot lacks permission to change nicknames```")

# ===================== STATUS =====================
@bot.command()
@channel_only(LOGBOOK_CHANNEL_ID)
async def status(ctx):
    total = week_minutes(ctx.author.id)
    h, m = divmod(total, 60)

    if ctx.author.id not in clocked_in:
        await ctx.send(
            f"```> YOU ARE CURRENTLY NOT WORKING OR CLOCKED-IN.\n"
            f"+ YOUR WEEK TOTAL: {h} HOURS {m} MINUTES```"
        )
    else:
        mins = int((datetime.now(PH_TZ) - clocked_in[ctx.author.id]).total_seconds() // 60)
        await ctx.send(
            f"```> YOU ARE CURRENTLY CLOCKED-IN.\n"
            f"+ CURRENT DUTY: {mins} minutes\n"
            f"+ YOUR WEEK TOTAL: {h} HOURS {m} MINUTES```"
        )

# ===================== CLOCK =====================
@bot.command()
@channel_only(LOGBOOK_CHANNEL_ID)
async def clockin(ctx):
    if ctx.author.id in clocked_in:
        return await ctx.send("```Already clocked in```")

    clocked_in[ctx.author.id] = datetime.now(PH_TZ)
    await ctx.send(
        f"```{display_name(ctx.author)} CLOCKED IN\n{time12(datetime.now(PH_TZ))}```"
    )

@bot.command()
@channel_only(LOGBOOK_CHANNEL_ID)
async def clockout(ctx):
    uid = ctx.author.id
    if uid not in clocked_in:
        return await ctx.send("```Not clocked in```")

    start = clocked_in.pop(uid)
    end = datetime.now(PH_TZ)
    did = duty_id()

    total_minutes = int((end - start).total_seconds() // 60)
    h, m = divmod(total_minutes, 60)

    duties.setdefault(uid, []).append({"id": did, "start": start, "end": end})

    await ctx.send(
        f"```{display_name(ctx.author)} CLOCKED OUT\n"
        f"DUTY ID: {did}\nTOTAL: {h} HOURS {m} MINUTES```"
    )

# ===================== OVERRIDE =====================
@bot.group()
@channel_only(LOGBOOK_CHANNEL_ID)
@override_allowed()
async def override(ctx):
    if ctx.invoked_subcommand is None:
        await ctx.send("```!override clockin|clockout ID```")

@override.command()
async def clockin(ctx, user_id: int):
    m = ctx.guild.get_member(user_id)
    clocked_in[user_id] = datetime.now(PH_TZ)

    await ctx.send(
        f"```{display_name(m)} FORCE CLOCKED IN\n"
        f"By {display_name(ctx.author)}\n"
        f"{time12(datetime.now(PH_TZ))}```"
    )

@override.command()
async def clockout(ctx, user_id: int):
    if user_id not in clocked_in:
        return await ctx.send("```User not clocked in```")

    m = ctx.guild.get_member(user_id)
    start = clocked_in.pop(user_id)
    end = datetime.now(PH_TZ)
    did = duty_id()

    total_minutes = int((end - start).total_seconds() // 60)
    h, mnts = divmod(total_minutes, 60)

    duties.setdefault(user_id, []).append({"id": did, "start": start, "end": end})

    await ctx.send(
        f"```{display_name(m)} FORCE CLOCKED OUT\n"
        f"By {display_name(ctx.author)}\n"
        f"DUTY ID: {did}\nTOTAL: {h} HOURS {mnts} MINUTES```"
    )

# ===================== REPORTS =====================
@bot.command()
@channel_only(REPORTS_CHANNEL_ID)
@admin_only()
async def report(ctx):
    sent = False
    for uid, logs in duties.items():
        weekly = [d for d in logs if d["end"] >= datetime.now(PH_TZ) - timedelta(days=7)]
        if not weekly:
            continue

        total = sum(int((d["end"] - d["start"]).total_seconds() // 60) for d in weekly)
        h, m = divmod(total, 60)
        member = ctx.guild.get_member(uid)

        lines = [
            f"- Duty ID {d['id']} : "
            f"{int((d['end'] - d['start']).total_seconds() // 60)} mins "
            f"Date: {d['end'].strftime('%m/%d/%Y')}"
            for d in weekly
        ]

        await ctx.send(
            f"```{display_name(member)} ({uid})\n"
            f"> TOTAL TIME (WEEK): {h:02d} HOURS {m:02d} MINUTES\n"
            f"DUTIES:\n" + "\n".join(lines) + "```"
        )
        sent = True

    if not sent:
        await ctx.send("```No duties or reports```")

@bot.command()
@channel_only(REPORTS_CHANNEL_ID)
@override_allowed()
async def singlereport(ctx, user_id: int):
    logs = duties.get(user_id)
    if not logs:
        return await ctx.send("```No duties found```")

    member = ctx.guild.get_member(user_id)
    blocks = []

    for d in logs:
        mins = int((d["end"] - d["start"]).total_seconds() // 60)
        blocks.append(
            f"DUTY ID: {d['id']}\n"
            f"TOTAL: {mins} minutes\n"
            f"DATE: {d['end'].strftime('%m/%d/%Y')}"
        )

    await ctx.send(
        f"```{display_name(member)} ({user_id})\n\n" + "\n\n".join(blocks) + "```"
    )

@bot.command()
@channel_only(REPORTS_CHANNEL_ID)
@override_allowed()
async def void(ctx, user_id: int, duty_id: str):
    logs = duties.get(user_id)
    if not logs:
        return await ctx.send("```User has no duties```")

    for d in logs:
        if d["id"] == duty_id:
            logs.remove(d)
            return await ctx.send("```Duty voided```")

    await ctx.send("```Duty ID not found```")

# ===================== ADMIN =====================
@bot.command()
@channel_only(ADMIN_CHANNEL_ID)
@admin_only()
async def admin(ctx):
    role = get_role(ctx.guild, ADMIN_ROLE_NAME)
    members = role.members if role else []
    await ctx.send(
        "```Admins:\n" + ("\n".join(display_name(m) for m in members) or "None") + "```"
    )

@bot.command()
@channel_only(ADMIN_CHANNEL_ID)
@admin_only()
async def addadmin(ctx, user_id: int):
    m = ctx.guild.get_member(user_id)
    role = get_role(ctx.guild, ADMIN_ROLE_NAME)
    await m.add_roles(role)
    await ctx.send(f"```Added admin role to {display_name(m)}```")

@bot.command()
@channel_only(ADMIN_CHANNEL_ID)
@admin_only()
async def removeadmin(ctx, user_id: int):
    m = ctx.guild.get_member(user_id)
    role = get_role(ctx.guild, ADMIN_ROLE_NAME)
    await m.remove_roles(role)
    await ctx.send(f"```Removed admin role from {display_name(m)}```")

@bot.command()
@channel_only(ADMIN_CHANNEL_ID)
@admin_only()
async def employee(ctx, action: str, user_id: int):
    if action != "delete":
        return
    clocked_in.pop(user_id, None)
    duties.pop(user_id, None)
    await ctx.send(f"```Employee {user_id} removed```")

# ===================== REMINDERS =====================
async def morning_reminder():
    await bot.get_channel(LOGBOOK_CHANNEL_ID).send(
        "***🔔 MORNING TSUNAMI IS COMING!***\nAutoclockout in **2 minutes**."
    )

async def evening_reminder():
    await bot.get_channel(LOGBOOK_CHANNEL_ID).send(
        "***🔔 EVENING TSUNAMI IS COMING!***\nAutoclockout in **2 minutes**."
    )

# ===================== AUTO CLOCKOUT =====================
async def auto_clockout():
    ch = bot.get_channel(LOGBOOK_CHANNEL_ID)
    for uid, start in list(clocked_in.items()):
        m = ch.guild.get_member(uid)
        end = datetime.now(PH_TZ)
        did = duty_id()

        total_minutes = int((end - start).total_seconds() // 60)
        h, mnts = divmod(total_minutes, 60)

        duties.setdefault(uid, []).append({"id": did, "start": start, "end": end})

        await ch.send(
            f"```{display_name(m)} CLOCKED OUT\n"
            f"DUTY ID: {did}\nTOTAL: {h} HOURS {mnts} MINUTES```"
        )

        clocked_in.pop(uid)

# ===================== SCHEDULER =====================
scheduler = AsyncIOScheduler(timezone=PH_TZ)

scheduler.add_job(morning_reminder, CronTrigger(hour=5, minute=58))
scheduler.add_job(evening_reminder, CronTrigger(hour=17, minute=58))
scheduler.add_job(auto_clockout, CronTrigger(hour=6, minute=0))
scheduler.add_job(auto_clockout, CronTrigger(hour=18, minute=0))

# ===================== RUN =====================
bot.run(TOKEN)
