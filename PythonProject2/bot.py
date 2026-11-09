import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import aiohttp
from curl_cffi.requests import AsyncSession
import yt_dlp
import asyncio
import random
import io
import os
import re
import time
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv

# ==================== BẢO MẬT TOKEN TỪ FILE .ENV ====================
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# ==================== CẤU HÌNH ID & LINK GIF ====================
WELCOME_CHANNEL_ID = 1568825661106167959
LEVEL_UP_CHANNEL_ID = 1568826726451126362
OWNER_ROLE_ID = 1568822855922098237       # Role Oh-ner
BOOST_ROLE_ID = 1568838300377022474       # Role Boost

# Link GIF chuẩn (đã bỏ /vi để Discord tự ẩn link và chỉ hiện GIF)
WELCOME_GIF = "https://tenor.com/view/welcome-to-bp-brother-gif-1959277352795273333"
TROLL_GIF = "https://tenor.com/view/troll-face-gif-338291142027446223"

# ==================== CƠ SỞ DỮ LIỆU SQLITE ====================
conn = sqlite3.connect("nam_bot_data.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    exp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS reaction_roles (
    message_id INTEGER,
    emoji TEXT,
    role_id INTEGER,
    PRIMARY KEY (message_id, emoji)
)
""")
conn.commit()

# ==================== KHỞI TẠO BOT ====================
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

def get_exp_needed(level: int) -> int:
    """Level 0 -> 1 cần 25 EXP. Càng lên level cao càng cần nhiều EXP hơn."""
    return (level + 1) * 25

def create_level_card(username: str, level: int, exp: int, exp_needed: int, avatar_bytes: bytes = None) -> io.BytesIO:
    """Hàm vẽ giao diện (UI) thẻ Level bằng Pillow"""
    width, height = 700, 220
    img = Image.new("RGB", (width, height), color=(30, 31, 34))
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle([(10, 10), (width - 10, height - 10)], radius=20, fill=(43, 45, 49), outline=(88, 101, 242), width=3)

    if avatar_bytes:
        try:
            avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA").resize((140, 140))
            mask = Image.new("L", (140, 140), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse((0, 0, 140, 140), fill=255)
            img.paste(avatar, (35, 40), mask)
        except Exception:
            draw.ellipse((35, 40, 175, 180), fill=(88, 101, 242))
    else:
        draw.ellipse((35, 40, 175, 180), fill=(88, 101, 242))

    try:
        font_large = ImageFont.truetype("arial.ttf", 32)
        font_med = ImageFont.truetype("arial.ttf", 24)
        font_small = ImageFont.truetype("arial.ttf", 20)
    except Exception:
        font_large = ImageFont.load_default()
        font_med = ImageFont.load_default()
        font_small = ImageFont.load_default()

    draw.text((200, 45), f"{username}", fill=(255, 255, 255), font=font_large)
    draw.text((200, 90), f"Level: {level}", fill=(88, 101, 242), font=font_med)
    draw.text((480, 95), f"EXP: {exp} / {exp_needed}", fill=(181, 186, 193), font=font_small)

    bar_x, bar_y, bar_w, bar_h = 200, 135, 450, 32
    draw.rounded_rectangle([(bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h)], radius=15, fill=(20, 20, 22))

    progress = min(max(exp / exp_needed, 0), 1)
    fill_w = int(bar_w * progress)
    if fill_w > 0:
        draw.rounded_rectangle([(bar_x, bar_y), (bar_x + max(fill_w, 25), bar_y + bar_h)], radius=15, fill=(87, 242, 135))

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

def download_tiktok_direct(target_url: str, temp_filename: str):
    """Hàm dùng yt-dlp lấy thông tin và tải video trực tiếp từ TikTok"""
    ydl_opts = {
        "format": "best[vcodec^=avc]/best[ext=mp4]/best",
        "outtmpl": temp_filename,
        "quiet": True,
        "no_warnings": True,
        "playlistend": 1,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(target_url, download=True)
        if "entries" in info:
            entries = list(info["entries"])
            if not entries:
                return None
            info = entries[0]
        return info

# ==================== SỰ KIỆN (EVENTS) ====================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Đã đăng nhập thành công: {bot.user} (ID: {bot.user.id})")

# 1. WELCOME SYSTEM
@bot.event
async def on_member_join(member: discord.Member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        await channel.send(f"Welcum tu NamDepchai Brathar {member.mention}")
        await channel.send(WELCOME_GIF)

# 2. BOOST SYSTEM
@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    if before.premium_since is None and after.premium_since is not None:
        boost_role = after.guild.get_role(BOOST_ROLE_ID)
        if boost_role:
            try:
                await after.add_roles(boost_role, reason="Server Booster")
            except discord.Forbidden:
                print("Bot không đủ quyền để cấp role Boost.")

        target_channel = after.guild.system_channel or bot.get_channel(WELCOME_CHANNEL_ID)
        if target_channel:
            await target_channel.send(f"{after.mention} đã boost cho server")

# 3. MENTION BOT, LEVEL SYSTEM & BOOST MESSAGE
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    # Phản hồi khi có người tag (mention) bot
    if bot.user in message.mentions and not message.mention_everyone:
        await message.channel.send("sao?")
        await message.channel.send(TROLL_GIF)

    # Phát hiện thông báo Boost nhiều lần (Tier 1, 2, 3)
    if message.type in (
        discord.MessageType.premium_guild_subscription,
        discord.MessageType.premium_guild_tier_1,
        discord.MessageType.premium_guild_tier_2,
        discord.MessageType.premium_guild_tier_3,
    ):
        boost_role = message.guild.get_role(BOOST_ROLE_ID)
        if boost_role and boost_role not in message.author.roles:
            try:
                await message.author.add_roles(boost_role, reason="Server Booster")
            except discord.Forbidden:
                pass
        await message.channel.send(f"{message.author.mention} đã boost cho server")

    # Cộng 5 EXP mỗi tin nhắn
    user_id = message.author.id
    cursor.execute("SELECT exp, level FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()

    if not row:
        exp, level = 0, 0
        cursor.execute("INSERT INTO users (user_id, exp, level) VALUES (?, 0, 0)", (user_id,))
    else:
        exp, level = row

    exp += 5
    exp_needed = get_exp_needed(level)

    if exp >= exp_needed:
        exp -= exp_needed
        level += 1
        cursor.execute("UPDATE users SET exp = ?, level = ? WHERE user_id = ?", (exp, level, user_id))
        conn.commit()

        lv_channel = bot.get_channel(LEVEL_UP_CHANNEL_ID) or message.channel
        embed = discord.Embed(
            title="🎉 LÊN CẤP (LEVEL UP)!",
            description=f"Chúc mừng {message.author.mention} đã đạt **Level {level}**!\nCần **{get_exp_needed(level)} EXP** nữa để lên Level {level + 1}.",
            color=discord.Color.gold()
        )
        await lv_channel.send(embed=embed)
    else:
        cursor.execute("UPDATE users SET exp = ? WHERE user_id = ?", (exp, user_id))
        conn.commit()

    await bot.process_commands(message)

# 4. XỬ LÝ REACTION ROLE (THÊM & BỎ REACTION)
@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.member is None or payload.member.bot:
        return

    emoji_str = str(payload.emoji)
    cursor.execute("SELECT role_id FROM reaction_roles WHERE message_id = ? AND emoji = ?", (payload.message_id, emoji_str))
    row = cursor.fetchone()

    if row:
        guild = bot.get_guild(payload.guild_id)
        role = guild.get_role(row[0])
        if role:
            try:
                await payload.member.add_roles(role, reason="Reaction Role")
            except discord.Forbidden:
                pass

@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return

    member = guild.get_member(payload.user_id)
    if not member or member.bot:
        return

    emoji_str = str(payload.emoji)
    cursor.execute("SELECT role_id FROM reaction_roles WHERE message_id = ? AND emoji = ?", (payload.message_id, emoji_str))
    row = cursor.fetchone()

    if row:
        role = guild.get_role(row[0])
        if role:
            try:
                await member.remove_roles(role, reason="Reaction Role Removed")
            except discord.Forbidden:
                pass

# ==================== CÁC LỆNH SLASH COMMANDS ====================

# LỆNH: /ping
@bot.tree.command(name="ping", description="Kiểm tra độ trễ (ping) của bot")
async def ping_cmd(interaction: discord.Interaction):
    latency_ms = round(bot.latency * 1000)
    await interaction.response.send_message(f"🏓 Pong! (`{latency_ms}ms`)")

# LỆNH: /memeviet
@bot.tree.command(name="memeviet", description="Lấy 1 hình meme Việt Nam ngẫu nhiên từ trên web")
async def memeviet(interaction: discord.Interaction):
    await interaction.response.defer()
    subreddits = ["VietNam", "vozforums"]
    chosen_sub = random.choice(subreddits)
    url = f"https://meme-api.com/gimme/{chosen_sub}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                embed = discord.Embed(title=data.get("title", "Meme Việt"), color=discord.Color.red())
                embed.set_image(url=data.get("url"))
                embed.set_footer(text=f"Nguồn: r/{chosen_sub} | 👍 {data.get('ups', 0)}")
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send("Không thể tải meme lúc này, vui lòng thử lại sau!")

# LỆNH: /memeglobal
@bot.tree.command(name="memeglobal", description="Lấy 1 hình meme quốc tế ngẫu nhiên từ trên web")
async def memeglobal(interaction: discord.Interaction):
    await interaction.response.defer()
    url = "https://meme-api.com/gimme"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                embed = discord.Embed(title=data.get("title", "Global Meme"), color=discord.Color.blue())
                embed.set_image(url=data.get("url"))
                embed.set_footer(text=f"Nguồn: r/{data.get('subreddit')} | 👍 {data.get('ups', 0)}")
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send("Không thể tải meme lúc này, vui lòng thử lại sau!")

# LỆNH: /random
@bot.tree.command(name="random", description="Nói một từ hoặc một câu ngẫu nhiên (Tiếng Anh / Tiếng Việt văn minh)")
async def random_cmd(interaction: discord.Interaction):
    phrases = [
        "Hôm nay trời đẹp thật đấy, nhớ uống đủ nước nhé!",
        "Bất ngờ chưa bà già!",
        "Keep going, you are doing great!",
        "Đừng bao giờ từ bỏ ước mơ của bạn, hãy tắt báo thức và ngủ tiếp.",
        "The only way to do great work is to love what you do.",
        "Cà phê sữa đá không đường nhưng nhiều sữa đặc.",
        "Serendipity (Sự tình cờ may mắn).",
        "Code chạy không lỗi ngay lần đầu tiên? Chắc chắn có gì đó sai sai.",
        "Stay hungry, stay foolish.",
        "Một nụ cười bằng mười thang thuốc bổ.",
        "Believe you can and you're halfway there.",
        "Bánh mì Sài Gòn, đặc ruột thơm bơ!"
    ]
    await interaction.response.send_message(f"🎲 **Random:** {random.choice(phrases)}")

# LỆNH: /gaytest
@bot.tree.command(name="gaytest", description="Máy đo độ gay từ 1-100% (chỉ mang tính chất giải trí)")
@app_commands.describe(member="Chọn người muốn đo (bỏ trống để tự đo chính mình)")
async def gaytest_cmd(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    percent = random.randint(1, 100)
    filled = percent // 10
    bar = "🏳️‍🌈" * filled + "⬛" * (10 - filled)

    embed = discord.Embed(
        title="🏳️‍🌈 MÁY ĐO ĐỘ GAY",
        description=(
            f"🎯 Đối tượng: {target.mention}\n"
            f"📊 Độ gay của bạn là: **{percent}%**\n"
            f"{bar}\n\n"
            f"*Lưu ý: Kết quả chỉ mang tính chất giải trí 🤣*"
        ),
        color=discord.Color.from_rgb(255, 105, 180)
    )
    await interaction.response.send_message(embed=embed)

# LỆNH: /femboytest
@bot.tree.command(name="femboytest", description="Máy đo độ femboy từ 1-100% (chỉ mang tính chất giải trí)")
@app_commands.describe(member="Chọn người muốn đo (bỏ trống để tự đo chính mình)")
async def femboytest_cmd(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    percent = random.randint(1, 100)
    filled = percent // 10
    bar = "🌸" * filled + "⬛" * (10 - filled)

    embed = discord.Embed(
        title="🌸 MÁY ĐO ĐỘ FEMBOY",
        description=(
            f"🎯 Đối tượng: {target.mention}\n"
            f"📊 Độ femboy của bạn là: **{percent}%**\n"
            f"{bar}\n\n"
            f"*Lưu ý: Kết quả chỉ mang tính chất giải trí 🤣*"
        ),
        color=discord.Color.from_rgb(255, 182, 193)
    )
    await interaction.response.send_message(embed=embed)

# LỆNH: /ship
@bot.tree.command(name="ship", description="Máy ghép đôi (ship) hai người với tỷ lệ ngẫu nhiên")
@app_commands.describe(nguoi_1="Chọn người thứ nhất", nguoi_2="Chọn người thứ hai")
async def ship_cmd(interaction: discord.Interaction, nguoi_1: discord.Member, nguoi_2: discord.Member):
    percent = random.randint(1, 100)
    filled = percent // 10
    bar = "💖" * filled + "🖤" * (10 - filled)

    if percent >= 80:
        status = "💘 Trời sinh một cặp, cưới luôn đi chờ chi!"
    elif percent >= 50:
        status = "💕 Khá hợp nhau đấy, bật đèn xanh thử xem!"
    elif percent >= 25:
        status = "💔 Hơi lệch sóng một chút, cần cố gắng thêm!"
    else:
        status = "🧊 Như nước với lửa, làm bạn tốt hơn nhé!"

    embed = discord.Embed(
        title="💘 MÁY ĐẨY THUYỀN (SHIP)",
        description=(
            f"💞 {nguoi_1.mention} ❤️ {nguoi_2.mention}\n"
            f"📊 Độ hợp nhau: **{percent}%**\n"
            f"{bar}\n"
            f"💬 **Đánh giá:** {status}\n\n"
            f"*Lưu ý: Kết quả chỉ mang tính chất giải trí 🤣*"
        ),
        color=discord.Color.red()
    )
    await interaction.response.send_message(embed=embed)

# LỆNH: /level
@bot.tree.command(name="level", description="Xem Level hiện tại của bạn kèm giao diện UI")
async def level_cmd(interaction: discord.Interaction, member: discord.Member = None):
    await interaction.response.defer()
    target = member or interaction.user

    cursor.execute("SELECT exp, level FROM users WHERE user_id = ?", (target.id,))
    row = cursor.fetchone()
    exp, level = row if row else (0, 0)
    exp_needed = get_exp_needed(level)

    avatar_bytes = None
    if target.display_avatar:
        async with aiohttp.ClientSession() as session:
            async with session.get(target.display_avatar.url) as resp:
                if resp.status == 200:
                    avatar_bytes = await resp.read()

    card_buffer = create_level_card(target.display_name, level, exp, exp_needed, avatar_bytes)
    file = discord.File(fp=card_buffer, filename="level_card.png")

    filled = int((exp / exp_needed) * 10)
    bar_text = "🟩" * filled + "⬛" * (10 - filled)

    embed = discord.Embed(
        title=f"📊 Thông tin cấp độ của {target.display_name}",
        description=f"**Level:** `{level}`\n**Tiến trình:** `{exp}/{exp_needed} EXP`\n{bar_text}",
        color=discord.Color.green()
    )
    embed.set_image(url="attachment://level_card.png")
    await interaction.followup.send(embed=embed, file=file)

# LỆNH: /exp
@bot.tree.command(name="exp", description="Xem số EXP hiện tại của bạn")
async def exp_cmd(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    cursor.execute("SELECT exp, level FROM users WHERE user_id = ?", (target.id,))
    row = cursor.fetchone()
    exp, level = row if row else (0, 0)
    exp_needed = get_exp_needed(level)

    await interaction.response.send_message(
        f"✨ **{target.display_name}** hiện đang ở **Level {level}** với **{exp}/{exp_needed} EXP** (Cần thêm `{exp_needed - exp} EXP` để lên cấp tiếp theo)."
    )

# LỆNH: /leaderboard
@bot.tree.command(name="leaderboard", description="Xem bảng xếp hạng Level trong server")
async def leaderboard_cmd(interaction: discord.Interaction):
    cursor.execute("SELECT user_id, level, exp FROM users ORDER BY level DESC, exp DESC LIMIT 10")
    rows = cursor.fetchall()

    if not rows:
        return await interaction.response.send_message("Chưa có dữ liệu bảng xếp hạng!")

    desc = ""
    medals = ["🥇", "🥈", "🥉"]
    for idx, (u_id, lvl, xp) in enumerate(rows, start=1):
        rank_icon = medals[idx - 1] if idx <= 3 else f"`#{idx}`"
        desc += f"{rank_icon} <@{u_id}> — **Level {lvl}** (`{xp}/{get_exp_needed(lvl)} EXP`)\n"

    embed = discord.Embed(
        title="🏆 BẢNG XẾP HẠNG LEVEL",
        description=desc,
        color=discord.Color.gold()
    )
    await interaction.response.send_message(embed=embed)

# LỆNH: /newvideo (Kết nối trực tiếp TikTok qua Embed + yt-dlp)
@bot.tree.command(name="newvideo", description="Lấy video TikTok mới nhất không logo kèm kiểm tra shadowban")
@app_commands.describe(username="Nhập username TikTok (VD: tiktok) hoặc dán trực tiếp link video TikTok")
async def newvideo_cmd(interaction: discord.Interaction, username: str):
    await interaction.response.defer()
    raw_input = username.strip()

    temp_file = f"temp_tiktok_{interaction.id}.mp4"
    target_url = None
    clean_user = raw_input.lstrip("@")

    try:
        if raw_input.startswith("http://") or raw_input.startswith("https://"):
            target_url = raw_input
        else:
            embed_url = f"https://www.tiktok.com/embed/@{clean_user}"
            async with AsyncSession(impersonate="chrome") as session:
                resp = await session.get(embed_url, timeout=15)
                if resp.status_code == 200:
                    vid_ids = re.findall(r"video/(\d{18,20})", resp.text)
                    if not vid_ids:
                        vid_ids = re.findall(r'"(?:id|videoId)"\s*:\s*"(\d{18,20})"', resp.text)
                    if vid_ids:
                        latest_id = max(vid_ids, key=int)
                        target_url = f"https://www.tiktok.com/@{clean_user}/video/{latest_id}"

            if not target_url:
                target_url = f"https://www.tiktok.com/@{clean_user}"

        info = await asyncio.to_thread(download_tiktok_direct, target_url, temp_file)
        if not info:
            return await interaction.followup.send(f"❌ Không tìm thấy video nào từ `@{clean_user}`.")

        views = info.get("view_count") or 0
        likes = info.get("like_count") or 0
        shares = info.get("repost_count") or 0
        comments = info.get("comment_count") or 0
        title = info.get("description") or info.get("title") or "Không có tiêu đề"
        uploader = info.get("uploader") or clean_user
        create_time = info.get("timestamp") or 0

        age_hours = (time.time() - create_time) / 3600 if create_time else 0
        engagement_rate = ((likes + shares + comments) / views * 100) if views > 0 else 0

        if views == 0 and age_hours > 0.5:
            shadowban_status = "🔴 **Có dấu hiệu Shadowban cao** (0 lượt xem sau hơn 30 phút đăng)"
        elif views < 50 and age_hours > 3:
            shadowban_status = "🟠 **Nghi ngờ bị bóp tương tác / Shadowban nhẹ** (Lượt xem rất thấp sau nhiều giờ)"
        elif views < 200 and engagement_rate > 30 and age_hours > 2:
            shadowban_status = "🟡 **Có thể bị hạn chế lên xu hướng (FYP)** (Tỷ lệ tương tác cao nhưng view thấp)"
        else:
            shadowban_status = "🟢 **Bình thường (Không bị Shadowban)**"

        embed = discord.Embed(
            title=f"🎬 Video mới nhất của @{uploader}",
            description=title[:250],
            color=discord.Color.purple()
        )
        embed.add_field(name="👁️ Lượt xem", value=f"`{views:,}`", inline=True)
        embed.add_field(name="❤️ Lượt thích", value=f"`{likes:,}`", inline=True)
        embed.add_field(name="🔁 Lượt chia sẻ", value=f"`{shares:,}`", inline=True)
        embed.add_field(name="🛡️ Kiểm tra Shadowban", value=shadowban_status, inline=False)

        if os.path.exists(temp_file):
            file_size = os.path.getsize(temp_file)
            if file_size <= 24 * 1024 * 1024:
                vid_file = discord.File(temp_file, filename=f"{uploader}_latest.mp4")
                await interaction.followup.send(embed=embed, file=vid_file)
            else:
                embed.add_field(name="⚠️ Dung lượng lớn", value=f"Video nặng hơn 25MB nên không thể đính kèm trực tiếp. [Xem trên TikTok]({info.get('webpage_url', target_url)})", inline=False)
                await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(embed=embed)

    except Exception as e:
        await interaction.followup.send(
            f"❌ Không thể lấy video của `{raw_input}`. Hãy kiểm tra lại tên người dùng hoặc dán trực tiếp link video TikTok vào lệnh!\n**Chi tiết:** `{str(e)[:180]}`"
        )
    finally:
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception:
                pass

# LỆNH: /taorole
@bot.tree.command(name="taorole", description="Tạo một Role mới với tên và màu tùy chọn")
@app_commands.describe(
    ten_role="Nhập tên Role muốn tạo",
    mau_role="Nhập màu Role (VD: blue, màu xanh, màu vàng, xanh lá, đỏ, tím, hồng, cam hoặc mã #HEX)"
)
async def taorole_cmd(interaction: discord.Interaction, ten_role: str, mau_role: str):
    has_owner_role = any(r.id == OWNER_ROLE_ID for r in interaction.user.roles)
    if not (has_owner_role or interaction.user.guild_permissions.manage_roles):
        return await interaction.response.send_message(
            "⛔ Chỉ **Oh-ner** hoặc quản trị viên mới được dùng lệnh này!",
            ephemeral=True
        )

    color_map = {
        "blue": discord.Color.blue(),
        "màu xanh": discord.Color.blue(),
        "xanh": discord.Color.blue(),
        "xanh dương": discord.Color.blue(),
        "màu xanh dương": discord.Color.blue(),
        "yellow": discord.Color.gold(),
        "màu vàng": discord.Color.gold(),
        "vàng": discord.Color.gold(),
        "green": discord.Color.green(),
        "xanh lá": discord.Color.green(),
        "màu xanh lá": discord.Color.green(),
        "red": discord.Color.red(),
        "đỏ": discord.Color.red(),
        "màu đỏ": discord.Color.red(),
        "purple": discord.Color.purple(),
        "tím": discord.Color.purple(),
        "màu tím": discord.Color.purple(),
        "orange": discord.Color.orange(),
        "cam": discord.Color.orange(),
        "màu cam": discord.Color.orange(),
        "pink": discord.Color.from_rgb(255, 105, 180),
        "hồng": discord.Color.from_rgb(255, 105, 180),
        "màu hồng": discord.Color.from_rgb(255, 105, 180),
        "white": discord.Color.from_rgb(255, 255, 255),
        "trắng": discord.Color.from_rgb(255, 255, 255),
        "màu trắng": discord.Color.from_rgb(255, 255, 255),
    }

    clean_color = mau_role.strip().lower()
    role_color = color_map.get(clean_color)

    if role_color is None:
        if clean_color.startswith("#"):
            try:
                role_color = discord.Color(int(clean_color[1:], 16))
            except ValueError:
                role_color = discord.Color.default()
        else:
            role_color = discord.Color.default()

    try:
        new_role = await interaction.guild.create_role(
            name=ten_role,
            color=role_color,
            reason=f"Tạo bởi {interaction.user}"
        )
        await interaction.response.send_message(
            f"✅ Đã tạo role **{new_role.name}** ({new_role.mention})\n"
            f"🆔 **ID Role:** `{new_role.id}`"
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ Bot không đủ quyền! Hãy cấp quyền `Manage Roles` (Quản lý Vai trò) cho Bot.",
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(f"⚠️ Đã xảy ra lỗi khi tạo role: `{e}`", ephemeral=True)

# LỆNH: /role (Reaction Role - Chỉ Oh-ner mới dùng được)
@bot.tree.command(name="role", description="Tạo bảng Reaction Role (Chỉ dành cho role Oh-ner)")
@app_commands.describe(
    role_ids="Nhập ID của Role (Nếu nhiều role thì ngăn cách bằng dấu phẩy, VD: 12345, 67890)",
    emojis="Nhập Emoji tương ứng (Ngăn cách bằng dấu phẩy nếu nhiều role, VD: 🔥, ⭐)",
    noi_dung="Nội dung tin nhắn bảng nhận Role"
)
async def role_cmd(interaction: discord.Interaction, role_ids: str, emojis: str, noi_dung: str = "Hãy thả cảm xúc (reaction) bên dưới để nhận Role tương ứng!"):
    has_owner_role = any(r.id == OWNER_ROLE_ID for r in interaction.user.roles)
    if not has_owner_role:
        return await interaction.response.send_message(
            "⛔ **Truy cập bị từ chối!** Chỉ những người sở hữu role <@&1568822855922098237> (**Oh-ner**) mới được phép dùng lệnh này!",
            ephemeral=True
        )

    r_list = [r.strip() for r in role_ids.split(",") if r.strip()]
    e_list = [e.strip() for e in emojis.split(",") if e.strip()]

    if len(r_list) != len(e_list):
        return await interaction.response.send_message("⚠️ Số lượng **ID Role** và **Emoji** phải bằng nhau!", ephemeral=True)

    desc_lines = [noi_dung, ""]
    valid_pairs = []

    for r_str, emoji_str in zip(r_list, e_list):
        if not r_str.isdigit():
            return await interaction.response.send_message(f"⚠️ ID Role không hợp lệ: `{r_str}`", ephemeral=True)
        role_obj = interaction.guild.get_role(int(r_str))
        if not role_obj:
            return await interaction.response.send_message(f"⚠️ Không tìm thấy Role với ID `{r_str}` trong server!", ephemeral=True)

        desc_lines.append(f"{emoji_str} : {role_obj.mention}")
        valid_pairs.append((emoji_str, role_obj.id))

    embed = discord.Embed(
        title="🎭 NHẬN ROLE TỰ ĐỘNG (REACTION ROLE)",
        description="\n".join(desc_lines),
        color=discord.Color.blurple()
    )

    await interaction.response.send_message("✅ Đã tạo bảng Reaction Role!", ephemeral=True)
    msg = await interaction.channel.send(embed=embed)

    for emoji_str, r_id in valid_pairs:
        try:
            await msg.add_reaction(emoji_str)
            cursor.execute("INSERT OR REPLACE INTO reaction_roles (message_id, emoji, role_id) VALUES (?, ?, ?)", (msg.id, emoji_str, r_id))
        except discord.HTTPException:
            await interaction.followup.send(f"⚠️ Không thể gắn emoji `{emoji_str}`, hãy kiểm tra lại emoji.", ephemeral=True)

    conn.commit()

# LỆNH: /info
@bot.tree.command(name="info", description="Giới thiệu về Bot của Nam và các chức năng")
async def info_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🤖 GIỚI THIỆU: BOT CỦA NAM",
        description="Xin chào! Mình là **Bot của Nam**, trợ lý đa năng phục vụ cho server với các vai trò chính:",
        color=discord.Color.teal()
    )
    embed.add_field(
        name="1. 👋 Chào mừng thành viên mới (Welcome)",
        value="Tự động gửi lời chào `Welcum tu NamDepchai Brathar` kèm GIF tới thành viên mới.",
        inline=False
    )
    embed.add_field(
        name="2. 😂 Kho Meme (`/memeviet` & `/memeglobal`)",
        value="Tìm và gửi meme ngẫu nhiên từ Việt Nam và Quốc tế trực tiếp từ trên web.",
        inline=False
    )
    embed.add_field(
        name="3. 🎲 Giải trí (`/random`, `/gaytest`, `/femboytest`, `/ship`) & 🏓 Mạng (`/ping`)",
        value="Nói câu ngẫu nhiên, đo độ gay/femboy, đẩy thuyền cặp đôi và kiểm tra độ trễ của Bot.",
        inline=False
    )
    embed.add_field(
        name="4. 📈 Hệ thống Cấp độ (`/level`, `/exp`, `/leaderboard`)",
        value="Tích lũy 5 EXP mỗi tin nhắn, tự động tăng độ khó theo cấp độ kèm thẻ giao diện Level UI.",
        inline=False
    )
    embed.add_field(
        name="5. 🎵 TikTok Downloader (`/newvideo`)",
        value="Tải trực tiếp video TikTok mới nhất không logo, thống kê lượt xem/thích/chia sẻ và kiểm tra Shadowban.",
        inline=False
    )
    embed.add_field(
        name="6. 🎭 Quản lý Role (`/taorole`, `/role`) & 💎 Nhận diện Boost",
        value="Tạo role mới theo màu, lập bảng nhận role tự động (dành riêng cho **Oh-ner**) và tự động thông báo + tặng role khi có người Boost server.",
        inline=False
    )
    embed.set_footer(text="Phát triển dành riêng cho Server của NamDepchai")
    await interaction.response.send_message(embed=embed)

if not TOKEN:
    print("❌ LỖI: Không tìm thấy DISCORD_TOKEN! Hãy kiểm tra lại file .env của bạn.")
else:
    bot.run(TOKEN)
