# pip install pyTelegramBotAPI
# UzBiznesBot v4.1

import telebot
import json, os, threading, uuid, re
from datetime import datetime, timedelta
from collections import Counter
from telebot.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)

# ═══════════════════════════════════════════════
# Tokenlar environment variable dan o'qiladi
# Railway da: Settings → Variables ga qo'shasiz
# Local da: .env fayl yoki to'g'ridan yozing
# ═══════════════════════════════════════════════
MAIN_TOKEN     = os.environ.get("MAIN_TOKEN", "")
SUPER_ADMIN_ID = int(os.environ.get("SUPER_ADMIN_ID", "0"))

if not MAIN_TOKEN:
    raise ValueError("MAIN_TOKEN environment variable topilmadi!")

FREE_BOT_LIMIT     = 1
FREE_PROD_LIMIT    = 30
PREMIUM_BOT_LIMIT  = 10
PREMIUM_PROD_LIMIT = 500

bot       = telebot.TeleBot(MAIN_TOKEN)
DB_FILE   = "businesses.json"
USER_FILE = "users.json"

# ──────────────────────────────────────────────
# TOKEN ↔ SHORT KEY
# ──────────────────────────────────────────────
token_map = {}
rev_map   = {}

def get_short(token):
    if token not in rev_map:
        key = str(len(token_map))
        token_map[key] = token
        rev_map[token] = key
    return rev_map[token]

def get_token(short):
    return token_map.get(str(short))

# ──────────────────────────────────────────────
# YORDAMCHI FUNKSIYALAR
# ──────────────────────────────────────────────
def validate_phone(phone):
    cleaned = re.sub(r"[\s\-\(\)]", "", phone.strip())
    digits  = cleaned.lstrip("+")
    if not digits.isdigit():
        return False, "❌ Faqat raqamlar bo'lishi kerak!"
    if len(digits) < 10 or len(digits) > 15:
        return False, "❌ Noto'g'ri uzunlik!\nFormat: <code>+998901234567</code>"
    if not cleaned.startswith("+"):
        cleaned = "+" + cleaned
    return True, cleaned

def format_contact_phone(contact):
    phone = contact.phone_number or ""
    return "+" + phone if phone and not phone.startswith("+") else phone

def make_product(name, price, desc="", photo_id=None):
    return {
        "id":       str(uuid.uuid4())[:8],
        "name":     name,
        "price":    price,
        "desc":     desc,
        "photo_id": photo_id,
        "reviews":  [],
        "sale_price": None,
        "sale_until": None,
    }

def get_active_price(p):
    """Aksiya narxini tekshirish"""
    if p.get("sale_price") and p.get("sale_until"):
        if datetime.now().strftime("%Y-%m-%d %H:%M") <= p["sale_until"]:
            return p["sale_price"], True
    return p["price"], False

def stars(n):
    return "⭐" * n + "☆" * (5 - n)

def avg_rating(reviews):
    if not reviews: return 0
    return sum(r["stars"] for r in reviews) / len(reviews)

# ──────────────────────────────────────────────
# DB
# ──────────────────────────────────────────────
def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_users():
    if os.path.exists(USER_FILE):
        with open(USER_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_users(data):
    with open(USER_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user(uid):
    users = load_users()
    uid   = str(uid)
    if uid not in users:
        users[uid] = {"plan": "free", "premium_until": None}
        save_users(users)
    return users[uid]

def is_premium(uid):
    u = get_user(uid)
    if u["plan"] == "premium":
        if not u["premium_until"]: return True
        if datetime.now().strftime("%Y-%m-%d") <= u["premium_until"]: return True
        users = load_users()
        users[str(uid)]["plan"] = "free"
        save_users(users)
    return False

def set_premium(uid, days=30):
    users = load_users()
    uid   = str(uid)
    if uid not in users: users[uid] = {}
    users[uid]["plan"]          = "premium"
    users[uid]["premium_until"] = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    save_users(users)
    return users[uid]["premium_until"]

def get_user_bots(uid):
    db = load_db()
    return {k: v for k, v in db.items() if v.get("owner") == str(uid)}

# ──────────────────────────────────────────────
# REFERAL TIZIMI
# ──────────────────────────────────────────────
REFERAL_FILE    = "referals.json"
REFERAL_PREMIUM = 5   # nechta do'st uchun premium
REFERAL_DAYS    = 7   # necha kun premium

def load_refs():
    if os.path.exists(REFERAL_FILE):
        with open(REFERAL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_refs(data):
    with open(REFERAL_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_ref_stats(uid):
    """Foydalanuvchining referal statistikasi"""
    refs = load_refs()
    uid  = str(uid)
    if uid not in refs:
        refs[uid] = {"invited": [], "rewarded": 0}
        save_refs(refs)
    return refs[uid]

def register_referal(new_uid, inviter_uid):
    """Yangi foydalanuvchi referal orqali keldi"""
    refs      = load_refs()
    new_uid   = str(new_uid)
    inviter   = str(inviter_uid)

    # O'zini o'zi taklif qila olmaydi
    if new_uid == inviter: return

    # Allaqachon ro'yxatdan o'tganmi
    for uid, data in refs.items():
        if new_uid in data.get("invited", []):
            return

    if inviter not in refs:
        refs[inviter] = {"invited": [], "rewarded": 0}

    if new_uid not in refs[inviter]["invited"]:
        refs[inviter]["invited"].append(new_uid)
        save_refs(refs)

        total    = len(refs[inviter]["invited"])
        rewarded = refs[inviter]["rewarded"]

        # Har REFERAL_PREMIUM ta do'st uchun premium
        new_rewards = total // REFERAL_PREMIUM
        if new_rewards > rewarded:
            refs[inviter]["rewarded"] = new_rewards
            save_refs(refs)
            until = set_premium(inviter, REFERAL_DAYS)
            # Inviterga xabar
            try:
                bot.send_message(int(inviter),
                    f"🎉 <b>Tabriklaymiz!</b>\n\n"
                    f"Siz {REFERAL_PREMIUM} ta do'stni taklif qildingiz!\n"
                    f"⭐ <b>{REFERAL_DAYS} kunlik Premium</b> faollashdi!\n"
                    f"Muddat: {until}",
                    parse_mode="HTML")
            except: pass
        else:
            # Oddiy bildirishnoma
            remaining = REFERAL_PREMIUM - (total % REFERAL_PREMIUM)
            try:
                bot.send_message(int(inviter),
                    f"👥 Do'stingiz botga qo'shildi! (Jami: {total})\n"
                    f"⭐ Premiumga {remaining} ta qoldi!",
                    parse_mode="HTML")
            except: pass

# ──────────────────────────────────────────────
# HOLAT
# ──────────────────────────────────────────────
user_state   = {}
running_bots = {}
biz_orders   = {}

# ══════════════════════════════════════════════
# BOSH BOT
# ══════════════════════════════════════════════

def main_kb(uid=0):
    m = ReplyKeyboardMarkup(resize_keyboard=True)
    m.add(KeyboardButton("🏪 Bot yaratish"), KeyboardButton("📋 Botlarim"))
    m.add(KeyboardButton("💎 Tarif"),        KeyboardButton("🔗 Referal"))
    m.add(KeyboardButton("❓ Yordam"))
    if uid == SUPER_ADMIN_ID:
        m.add(KeyboardButton("🔐 Admin panel"))
    return m

@bot.message_handler(commands=["start"])
def start(message):
    uid  = message.from_user.id
    name = message.from_user.first_name
    get_user(uid)

    # Referal tekshirish: /start ref_12345678
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            inviter_uid = int(args[1].replace("ref_", ""))
            register_referal(uid, inviter_uid)
        except: pass

    plan = "⭐ Premium" if is_premium(uid) else "🆓 Bepul"
    bot.send_message(message.chat.id,
        f"👋 Salom, <b>{name}</b>! [{plan}]\n\n"
        "🤖 <b>UzBiznesBot v4.1</b>\n\n"
        f"🆓 Bepul: {FREE_BOT_LIMIT} bot · {FREE_PROD_LIMIT} mahsulot\n"
        f"⭐ Premium: {PREMIUM_BOT_LIMIT} bot · {PREMIUM_PROD_LIMIT} mahsulot\n"
        "  + 🖼️ Rasm · 📢 Broadcast · ⏰ Aksiya · 📊 Statistika · 🎟️ Promo\n\n"
        f"👥 Do'stlarni taklif qiling → {REFERAL_PREMIUM} ta = {REFERAL_DAYS} kun Premium!",
        reply_markup=main_kb(uid), parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "🏪 Bot yaratish")
def create_bot_cmd(message):
    uid  = message.from_user.id
    bots = get_user_bots(uid)
    lim  = PREMIUM_BOT_LIMIT if is_premium(uid) else FREE_BOT_LIMIT
    if len(bots) >= lim:
        bot.send_message(message.chat.id,
            f"❌ Limit: <b>{lim} ta bot</b>. 💎 /tarif", parse_mode="HTML"); return
    user_state[uid] = {"step": "ask_token"}
    bot.send_message(message.chat.id,
        "🔑 <b>1-qadam: Token</b>\n\n"
        "1. @BotFather → /newbot\n"
        "2. Nom va username bering\n"
        "3. Tokenni yuboring\n\n<i>Misol: 123456789:ABCdef...</i>",
        parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "📋 Botlarim")
def my_bots_cmd(message):
    uid  = message.from_user.id
    bots = get_user_bots(uid)
    if not bots:
        bot.send_message(message.chat.id, "📭 Hali bot yo'q.\n🏪 «Bot yaratish» tugmasini bosing!"); return
    markup = InlineKeyboardMarkup()
    for token, data in bots.items():
        s      = get_short(token)
        status = "🟢" if token in running_bots else "🔴"
        markup.add(InlineKeyboardButton(f"{status} {data['name']}", callback_data=f"BE:{s}"))
    bot.send_message(message.chat.id, "📋 <b>Botlaringiz:</b>",
        reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data.startswith("BE:"))
def bot_edit_menu(call):
    s     = call.data[3:]
    token = get_token(s)
    if not token: bot.answer_callback_query(call.id, "Topilmadi!"); return
    db   = load_db()
    data = db.get(token)
    if not data: bot.answer_callback_query(call.id, "Topilmadi!"); return
    prods  = len(data.get("products", []))
    ords   = len(data.get("orders",   []))
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("✏️ Nom",    callback_data=f"EN:{s}"),
        InlineKeyboardButton("📝 Tavsif", callback_data=f"ED:{s}"),
        InlineKeyboardButton("📞 Tel",    callback_data=f"EP:{s}"),
        InlineKeyboardButton("📦 Mahsulotlar", callback_data=f"PL:{s}"),
    )
    if is_premium(call.from_user.id):
        markup.add(
            InlineKeyboardButton("🎟️ Promo",     callback_data=f"PR:{s}"),
            InlineKeyboardButton("📊 Statistika", callback_data=f"ST:{s}"),
            InlineKeyboardButton("📢 Broadcast",  callback_data=f"BC:{s}"),
        )
    markup.add(InlineKeyboardButton("◀️ Orqaga", callback_data="MYBOTS"))
    bot.edit_message_text(
        chat_id=call.message.chat.id, message_id=call.message.message_id,
        text=(f"⚙️ <b>{data['name']}</b>\n\n"
              f"📝 {data['desc']}\n📞 {data['phone']}\n"
              f"📦 {prods} mahsulot · 🛒 {ords} buyurtma"),
        reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data == "MYBOTS")
def back_mybots(call):
    uid  = call.from_user.id
    bots = get_user_bots(uid)
    markup = InlineKeyboardMarkup()
    for token, data in bots.items():
        s      = get_short(token)
        status = "🟢" if token in running_bots else "🔴"
        markup.add(InlineKeyboardButton(f"{status} {data['name']}", callback_data=f"BE:{s}"))
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
        text="📋 <b>Botlaringiz:</b>", reply_markup=markup, parse_mode="HTML")

# ── Info tahrirlash ───────────────────────────
@bot.callback_query_handler(func=lambda c: c.data[:3] in ("EN:","ED:","EP:") and len(c.data) > 3)
def edit_info_cb(call):
    code = call.data[:2]; s = call.data[3:]
    token = get_token(s)
    if not token: bot.answer_callback_query(call.id, "Xato!"); return
    sm = {"EN":"ei_name","ED":"ei_desc","EP":"ei_phone"}
    lm = {"EN":"yangi nomni","ED":"yangi tavsifni","EP":"yangi telefon raqamni"}
    user_state[call.from_user.id] = {"step": sm[code], "token": token, "short": s}
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
        text=f"✏️ {lm[code].capitalize()} yozing:")

# ── Mahsulotlar ro'yxati ──────────────────────
@bot.callback_query_handler(func=lambda c: c.data.startswith("PL:"))
def prod_list(call):
    s     = call.data[3:]
    token = get_token(s)
    if not token: bot.answer_callback_query(call.id, "Xato!"); return
    db       = load_db()
    products = db.get(token, {}).get("products", [])
    uid      = call.from_user.id
    limit    = PREMIUM_PROD_LIMIT if is_premium(uid) else FREE_PROD_LIMIT
    markup   = InlineKeyboardMarkup()
    for p in products:
        price, on_sale = get_active_price(p)
        sale_mark = "🔥" if on_sale else ""
        rating    = avg_rating(p.get("reviews", []))
        r_str     = f" ⭐{rating:.1f}" if rating else ""
        markup.add(InlineKeyboardButton(
            f"{sale_mark}[{p['id']}] {p['name']} — {price}{r_str}",
            callback_data=f"PM:{s}:{p['id']}"))
    markup.add(InlineKeyboardButton(f"➕ Qo'shish ({len(products)}/{limit})", callback_data=f"PA:{s}"))
    markup.add(InlineKeyboardButton("◀️ Orqaga", callback_data=f"BE:{s}"))
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
        text=f"📦 <b>Mahsulotlar</b> — {len(products)} ta:",
        reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data.startswith("PM:"))
def prod_menu_cb(call):
    parts   = call.data.split(":")
    s, pid  = parts[1], parts[2]
    token   = get_token(s)
    if not token: return
    db = load_db()
    p  = next((x for x in db.get(token,{}).get("products",[]) if x["id"]==pid), None)
    if not p: return
    price, on_sale = get_active_price(p)
    sale_tx = f"\n🔥 Aksiya narxi: <b>{price}</b>" if on_sale else ""
    rating  = avg_rating(p.get("reviews",[]))
    r_str   = f"\n⭐ Reyting: {rating:.1f}/5 ({len(p.get('reviews',[]))} ta sharh)" if p.get("reviews") else ""
    markup  = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("✏️ Nom",    callback_data=f"PN:{s}:{pid}"),
        InlineKeyboardButton("💰 Narx",   callback_data=f"PP:{s}:{pid}"),
        InlineKeyboardButton("📝 Tavsif", callback_data=f"PD:{s}:{pid}"),
        InlineKeyboardButton("🗑️ O'chir", callback_data=f"PX:{s}:{pid}"),
    )
    if is_premium(call.from_user.id):
        markup.add(
            InlineKeyboardButton("🖼️ Rasm",   callback_data=f"PH:{s}:{pid}"),
            InlineKeyboardButton("⏰ Aksiya",  callback_data=f"PS:{s}:{pid}"),
        )
    markup.add(InlineKeyboardButton("◀️ Orqaga", callback_data=f"PL:{s}"))
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
        text=(f"📦 <b>{p['name']}</b>\n"
              f"💰 {p['price']}{sale_tx}\n"
              f"📝 {p.get('desc','—')}\n"
              f"🆔 <code>{p['id']}</code>{r_str}"),
        reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data.startswith("PX:"))
def prod_delete(call):
    parts  = call.data.split(":")
    s, pid = parts[1], parts[2]
    token  = get_token(s)
    if not token: return
    db = load_db()
    if token in db:
        db[token]["products"] = [p for p in db[token]["products"] if p["id"] != pid]
        save_db(db)
        reload_biz_bot(token, db[token])
    bot.answer_callback_query(call.id, "🗑️ O'chirildi!")
    call.data = f"PL:{s}"; prod_list(call)

@bot.callback_query_handler(func=lambda c: c.data[:3] in ("PN:","PP:","PD:","PH:","PS:"))
def prod_edit_cb(call):
    code   = call.data[:2]
    parts  = call.data.split(":")
    s, pid = parts[1], parts[2]
    token  = get_token(s)
    if not token: return
    if code in ("PH","PS") and not is_premium(call.from_user.id):
        bot.answer_callback_query(call.id, "⭐ Faqat Premium!", show_alert=True); return
    sm = {"PN":"pe_name","PP":"pe_price","PD":"pe_desc","PH":"pe_photo","PS":"pe_sale"}
    lm = {"PN":"Mahsulot nomini","PP":"Mahsulot narxini","PD":"Mahsulot tavsifini",
          "PH":"Mahsulot rasmini (rasm yuboring)","PS":"Aksiya narxini"}
    user_state[call.from_user.id] = {"step":sm[code],"token":token,"short":s,"prod_id":pid}
    if code == "PS":
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
            text="⏰ <b>Aksiya sozlash</b>\n\nFormatda yozing:\n"
                 "<code>Aksiya narxi | KUN</code>\n\n"
                 "Misol: <code>9 900 000 | 3</code>\n"
                 "(3 kun davomida aksiya narxi ko'rinadi)",
            parse_mode="HTML")
    elif code == "PH":
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
            text="🖼️ Mahsulot rasmini yuboring:")
    else:
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
            text=f"✏️ {lm[code]} yozing:")

@bot.callback_query_handler(func=lambda c: c.data.startswith("PA:"))
def prod_add_cb(call):
    s     = call.data[3:]
    token = get_token(s)
    if not token: return
    db    = load_db()
    uid   = call.from_user.id
    limit = PREMIUM_PROD_LIMIT if is_premium(uid) else FREE_PROD_LIMIT
    count = len(db.get(token,{}).get("products",[]))
    if count >= limit:
        bot.answer_callback_query(call.id, f"❌ Limit {limit} ta!", show_alert=True); return
    user_state[uid] = {"step":"prod_add","token":token,"short":s}
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
        text="📦 Yangi mahsulot:\n\n<code>Nomi | Narxi | Tavsifi</code>", parse_mode="HTML")

# ── Promo ─────────────────────────────────────
@bot.callback_query_handler(func=lambda c: c.data.startswith("PR:"))
def promo_list(call):
    if not is_premium(call.from_user.id):
        bot.answer_callback_query(call.id,"⭐ Faqat Premium!",show_alert=True); return
    s     = call.data[3:]
    token = get_token(s)
    if not token: return
    db     = load_db()
    promos = db.get(token,{}).get("promos",{})
    markup = InlineKeyboardMarkup()
    for code,disc in promos.items():
        markup.add(InlineKeyboardButton(f"🎟️ {code} — {disc}%", callback_data=f"PRC:{s}:{code}"))
    markup.add(InlineKeyboardButton("➕ Yangi promo", callback_data=f"PRA:{s}"))
    markup.add(InlineKeyboardButton("◀️ Orqaga",      callback_data=f"BE:{s}"))
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
        text=f"🎟️ <b>Promo kodlar</b> — {len(promos)} ta:",
        reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data.startswith("PRC:"))
def promo_del(call):
    parts   = call.data.split(":")
    s, code = parts[1], parts[2]
    token   = get_token(s)
    if not token: return
    db = load_db()
    if token in db and code in db[token].get("promos",{}):
        del db[token]["promos"][code]; save_db(db); reload_biz_bot(token,db[token])
    bot.answer_callback_query(call.id, f"🗑️ {code} o'chirildi!")
    call.data = f"PR:{s}"; promo_list(call)

@bot.callback_query_handler(func=lambda c: c.data.startswith("PRA:"))
def promo_add_cb(call):
    s = call.data[4:]; token = get_token(s)
    if not token: return
    user_state[call.from_user.id] = {"step":"promo_add","token":token,"short":s}
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
        text="🎟️ Promo kodni yozing:\n\n<code>KOD | Chegirma%</code>\n\nMisol: <code>SALE20 | 20</code>",
        parse_mode="HTML")

# ── Statistika ────────────────────────────────
@bot.callback_query_handler(func=lambda c: c.data.startswith("ST:"))
def stats_cb(call):
    if not is_premium(call.from_user.id):
        bot.answer_callback_query(call.id,"⭐ Faqat Premium!",show_alert=True); return
    s     = call.data[3:]
    token = get_token(s)
    if not token: return
    db    = load_db()
    data  = db.get(token,{})
    ords  = data.get("orders",[])
    top   = Counter(o.get("product_name") for o in ords).most_common(3)
    top_t = "\n".join(f"  {i+1}. {n} — {c}x" for i,(n,c) in enumerate(top)) or "  Hali yo'q"
    clients = len(set(o.get("uid") for o in ords if o.get("uid")))
    pending = len([o for o in ords if o.get("status") == "pending_payment"])
    confirmed = len([o for o in ords if o.get("status") == "confirmed"])
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("◀️ Orqaga", callback_data=f"BE:{s}"))
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
        text=(f"📊 <b>{data['name']} — Statistika</b>\n\n"
              f"🛒 Jami buyurtmalar: <b>{len(ords)}</b>\n"
              f"✅ Tasdiqlangan: <b>{confirmed}</b>\n"
              f"⏳ To'lov kutilmoqda: <b>{pending}</b>\n"
              f"👥 Mijozlar: <b>{clients}</b>\n\n"
              f"🏆 Top mahsulotlar:\n{top_t}"),
        reply_markup=markup, parse_mode="HTML")

# ── Broadcast ─────────────────────────────────
@bot.callback_query_handler(func=lambda c: c.data.startswith("BC:"))
def broadcast_cb(call):
    if not is_premium(call.from_user.id):
        bot.answer_callback_query(call.id,"⭐ Faqat Premium!",show_alert=True); return
    s = call.data[3:]; token = get_token(s)
    if not token: return
    user_state[call.from_user.id] = {"step":"broadcast","token":token,"short":s}
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
        text="📢 <b>Broadcast</b>\n\nBarcha mijozlarga yuboriladigan xabarni yozing:\n\n"
             "<i>Matn, rasm yoki video yuborishingiz mumkin</i>",
        parse_mode="HTML")

# ── Referal ───────────────────────────────────
@bot.message_handler(func=lambda m: m.text in ["🔗 Referal", "/referal"])
def referal_cmd(message):
    uid   = message.from_user.id
    stats = get_ref_stats(uid)
    total = len(stats["invited"])
    next_reward = REFERAL_PREMIUM - (total % REFERAL_PREMIUM)
    if total % REFERAL_PREMIUM == 0 and total > 0:
        next_reward = REFERAL_PREMIUM

    # Bot username olish
    try:
        me = bot.get_me()
        link = f"https://t.me/{me.username}?start=ref_{uid}"
    except:
        link = f"https://t.me/yourbot?start=ref_{uid}"

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔗 Ulashish", url=f"https://t.me/share/url?url={link}&text=UzBiznesBot%20orqali%20biznes%20bot%20yarating!"))

    bot.send_message(message.chat.id,
        f"🔗 <b>Referal tizimi</b>\n\n"
        f"Do'stlarni taklif qiling va <b>bepul Premium</b> qozonin!\n\n"
        f"👥 Taklif qilganlar: <b>{total}</b>\n"
        f"🏆 Mukofotlar: <b>{stats['rewarded']}</b> marta\n"
        f"⭐ Keyingi premiumga: <b>{next_reward}</b> ta qoldi\n\n"
        f"📋 Sizning havolangiz:\n<code>{link}</code>\n\n"
        f"💡 Har <b>{REFERAL_PREMIUM}</b> ta do'st = <b>{REFERAL_DAYS}</b> kun Premium!",
        reply_markup=markup, parse_mode="HTML")

# ── Tarif ─────────────────────────────────────
@bot.message_handler(func=lambda m: m.text in ["💎 Tarif","/tarif"])
def tarif_cmd(message):
    uid  = message.from_user.id
    plan = "⭐ Premium" if is_premium(uid) else "🆓 Bepul"
    markup = InlineKeyboardMarkup()
    if not is_premium(uid):
        markup.add(InlineKeyboardButton("💎 Premium olish", callback_data="BUY"))
    bot.send_message(message.chat.id,
        f"💎 <b>Tariflar</b>\n\nHozirgi: <b>{plan}</b>\n\n"
        f"🆓 <b>Bepul</b>\n• {FREE_BOT_LIMIT} ta bot · {FREE_PROD_LIMIT} ta mahsulot\n"
        "• Katalog, buyurtma, sharh\n\n"
        f"⭐ <b>Premium</b>\n• {PREMIUM_BOT_LIMIT} ta bot · {PREMIUM_PROD_LIMIT} ta mahsulot\n"
        "• 🖼️ Mahsulot rasmlari\n"
        "• ⏰ Vaqtinchalik aksiya\n"
        "• 📢 Broadcast xabar\n"
        "• 🎟️ Promo kodlar\n"
        "• 📊 Kengaytirilgan statistika",
        reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data == "BUY")
def buy_premium(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id,
        "💎 Premium uchun admin bilan bog'laning:\n@your_admin_username")

@bot.message_handler(func=lambda m: m.text == "❓ Yordam")
def help_cmd(message):
    bot.send_message(message.chat.id,
        "📚 <b>Yordam</b>\n\n"
        "1. @BotFather → /newbot → token\n"
        "2. «Bot yaratish» → token yuboring\n"
        "3. Ma'lumotlar + mahsulotlar\n"
        "4. ✅ Bot ishga tushadi!\n\n"
        "«📋 Botlarim» orqali tahrirlang.", parse_mode="HTML")

# ── Admin buyruqlar ───────────────────────────
@bot.message_handler(commands=["admin"])
def admin_panel(message):
    if message.from_user.id != SUPER_ADMIN_ID:
        bot.send_message(message.chat.id, "❌ Ruxsat yo'q!"); return
    _show_admin_panel(message.chat.id)

def _show_admin_panel(chat_id):
    db    = load_db()
    users = load_users()
    premium_count = len([u for u in users.values() if u.get("plan") == "premium"])
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton(f"👥 Foydalanuvchilar ({len(users)})", callback_data="SA_USERS"),
        InlineKeyboardButton(f"🤖 Botlar ({len(db)})",              callback_data="SA_BOTS"),
        InlineKeyboardButton(f"⭐ Premiumlar ({premium_count})",     callback_data="SA_PREMIUMS"),
        InlineKeyboardButton("💎 Premium berish",                    callback_data="SA_GIVEPREM"),
        InlineKeyboardButton("📢 Global broadcast",                  callback_data="SA_BROADCAST"),
        InlineKeyboardButton("🗑️ Bot o'chirish",                     callback_data="SA_DELBOT"),
    )
    bot.send_message(chat_id,
        f"🔐 <b>Super Admin Panel</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{len(users)}</b>\n"
        f"🤖 Jami botlar: <b>{len(db)}</b>\n"
        f"⭐ Premium: <b>{premium_count}</b>\n"
        f"🟢 Ishlamoqda: <b>{len(running_bots)}</b>",
        reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data == "SA_USERS")
def sa_users(call):
    if call.from_user.id != SUPER_ADMIN_ID: return
    users = load_users(); db = load_db()
    text  = f"👥 <b>Foydalanuvchilar: {len(users)}</b>\n\n"
    for uid, u in list(users.items())[:30]:
        bots = len([b for b in db.values() if b.get("owner") == uid])
        plan = "⭐" if u.get("plan") == "premium" else "🆓"
        exp  = u.get("premium_until","") or ""
        text += f"{plan} <code>{uid}</code> | {bots} bot {exp}\n"
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("◀️ Orqaga", callback_data="SA_BACK"))
    bot.edit_message_text(chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text, reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data == "SA_BOTS")
def sa_bots(call):
    if call.from_user.id != SUPER_ADMIN_ID: return
    db   = load_db()
    text = f"🤖 <b>Jami botlar: {len(db)}</b>\n\n"
    for token, d in list(db.items())[:20]:
        status = "🟢" if token in running_bots else "🔴"
        prods  = len(d.get("products", []))
        ords   = len(d.get("orders", []))
        text  += f"{status} <b>{d['name']}</b> | {prods} mahsulot | {ords} buyurtma\n"
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("◀️ Orqaga", callback_data="SA_BACK"))
    bot.edit_message_text(chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text, reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data == "SA_PREMIUMS")
def sa_premiums(call):
    if call.from_user.id != SUPER_ADMIN_ID: return
    users = load_users()
    prems = {uid: u for uid, u in users.items() if u.get("plan") == "premium"}
    text  = f"⭐ <b>Premium foydalanuvchilar: {len(prems)}</b>\n\n"
    for uid, u in prems.items():
        exp   = u.get("premium_until","∞") or "∞"
        text += f"<code>{uid}</code> — {exp} gacha\n"
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("◀️ Orqaga", callback_data="SA_BACK"))
    bot.edit_message_text(chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text or "Hali premium foydalanuvchi yo'q.",
        reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data == "SA_GIVEPREM")
def sa_giveprem(call):
    if call.from_user.id != SUPER_ADMIN_ID: return
    user_state[call.from_user.id] = {"step": "sa_giveprem"}
    bot.edit_message_text(chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="💎 <b>Premium berish</b>\n\n"
             "Formatda yozing:\n<code>USER_ID | KUN</code>\n\n"
             "Misol: <code>123456789 | 30</code>",
        parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data == "SA_BROADCAST")
def sa_broadcast(call):
    if call.from_user.id != SUPER_ADMIN_ID: return
    user_state[call.from_user.id] = {"step": "sa_broadcast"}
    bot.edit_message_text(chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="📢 <b>Global Broadcast</b>\n\n"
             "Barcha foydalanuvchilarga yuboriladigan xabarni yozing:",
        parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data == "SA_DELBOT")
def sa_delbot(call):
    if call.from_user.id != SUPER_ADMIN_ID: return
    db     = load_db()
    markup = InlineKeyboardMarkup()
    for token, d in db.items():
        s = get_short(token)
        markup.add(InlineKeyboardButton(
            f"🗑️ {d['name']}", callback_data=f"SA_DEL:{s}"))
    markup.add(InlineKeyboardButton("◀️ Orqaga", callback_data="SA_BACK"))
    bot.edit_message_text(chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="🗑️ <b>Qaysi botni o'chirish?</b>",
        reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data.startswith("SA_DEL:"))
def sa_del_confirm(call):
    if call.from_user.id != SUPER_ADMIN_ID: return
    s     = call.data[7:]
    token = get_token(s)
    if not token: return
    db    = load_db()
    name  = db.get(token, {}).get("name", "?")
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("✅ Ha, o'chir", callback_data=f"SA_DELOK:{s}"),
        InlineKeyboardButton("❌ Bekor",      callback_data="SA_DELBOT"),
    )
    bot.edit_message_text(chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"⚠️ <b>{name}</b> botini o'chirishni tasdiqlaysizmi?",
        reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data.startswith("SA_DELOK:"))
def sa_del_ok(call):
    if call.from_user.id != SUPER_ADMIN_ID: return
    s     = call.data[9:]
    token = get_token(s)
    if not token: return
    db   = load_db()
    name = db.get(token, {}).get("name", "?")
    if token in running_bots:
        try: running_bots[token].stop_polling()
        except: pass
        running_bots.pop(token, None)
    db.pop(token, None); save_db(db)
    bot.edit_message_text(chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"✅ <b>{name}</b> o'chirildi!", parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data == "SA_REFS")
def sa_refs(call):
    if call.from_user.id != SUPER_ADMIN_ID: return
    refs  = load_refs()
    total = sum(len(v["invited"]) for v in refs.values())
    text  = f"🔗 <b>Referal statistika</b>\n\n"
    text += f"Jami taklif: <b>{total}</b>\n\n"
    top   = sorted(refs.items(), key=lambda x: len(x[1]["invited"]), reverse=True)[:10]
    for uid, r in top:
        text += f"<code>{uid}</code> — {len(r['invited'])} ta · {r['rewarded']} mukofot\n"
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("◀️ Orqaga", callback_data="SA_BACK"))
    bot.edit_message_text(chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text, reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data == "SA_BACK")
def sa_back(call):
    if call.from_user.id != SUPER_ADMIN_ID: return
    db    = load_db()
    users = load_users()
    premium_count = len([u for u in users.values() if u.get("plan") == "premium"])
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton(f"👥 Foydalanuvchilar ({len(users)})", callback_data="SA_USERS"),
        InlineKeyboardButton(f"🤖 Botlar ({len(db)})",              callback_data="SA_BOTS"),
        InlineKeyboardButton(f"⭐ Premiumlar ({premium_count})",     callback_data="SA_PREMIUMS"),
        InlineKeyboardButton("💎 Premium berish",                    callback_data="SA_GIVEPREM"),
        InlineKeyboardButton("📢 Global broadcast",                  callback_data="SA_BROADCAST"),
        InlineKeyboardButton("🗑️ Bot o'chirish",                     callback_data="SA_DELBOT"),
        InlineKeyboardButton("🔗 Referal statistika",                callback_data="SA_REFS"),
    )
    bot.edit_message_text(chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"🔐 <b>Super Admin Panel</b>\n\n"
             f"👥 {len(users)} · 🤖 {len(db)} · ⭐ {premium_count} · 🟢 {len(running_bots)}",
        reply_markup=markup, parse_mode="HTML")

@bot.message_handler(commands=["givepremium"])
def give_premium(message):
    if message.from_user.id != SUPER_ADMIN_ID: return
    parts = message.text.split()
    if len(parts) < 2:
        bot.send_message(message.chat.id, "Ishlatish: /givepremium <uid> [kun]"); return
    days  = int(parts[2]) if len(parts) > 2 else 30
    until = set_premium(parts[1], days)
    bot.send_message(message.chat.id, f"✅ {parts[1]} ga {days} kun Premium. Muddat: {until}")
    try:
        bot.send_message(int(parts[1]),
            f"🎉 <b>Premium faollashdi!</b>\nMuddat: {until}", parse_mode="HTML")
    except: pass

@bot.message_handler(commands=["users"])
def admin_users(message):
    if message.from_user.id != SUPER_ADMIN_ID: return
    users = load_users(); db = load_db()
    text  = f"👥 Foydalanuvchilar: {len(users)}\n\n"
    for uid, u in list(users.items())[:20]:
        bots = len([b for b in db.values() if b.get("owner") == uid])
        plan = "⭐" if u.get("plan") == "premium" else "🆓"
        text += f"{plan} {uid} | {bots} bot\n"
    bot.send_message(message.chat.id, text)

# ══════════════════════════════════════════════
# BOSH BOT — HOLAT XABARLAR
# ══════════════════════════════════════════════

@bot.message_handler(content_types=["text","photo"],
    func=lambda m: m.from_user.id in user_state)
def handle_steps(message):
    uid   = message.from_user.id
    state = user_state.get(uid, {})
    step  = state.get("step","")
    text  = message.text.strip() if message.text else ""

    if step == "ask_token":
        if len(text) < 30 or ":" not in text:
            bot.send_message(message.chat.id, "❌ Token noto'g'ri!"); return
        db = load_db()
        if text in db:
            bot.send_message(message.chat.id, "⚠️ Bu token allaqachon ulangan!")
            user_state.pop(uid,None); return
        state["token"] = text; state["step"] = "ask_name"
        bot.send_message(message.chat.id,
            "✅ Token qabul!\n\n🏪 <b>Biznes nomini yozing:</b>", parse_mode="HTML")

    elif step == "ask_name":
        state["name"] = text; state["step"] = "ask_desc"
        bot.send_message(message.chat.id,
            f"✅ Nom: <b>{text}</b>\n\n📝 <b>Tavsif yozing:</b>", parse_mode="HTML")

    elif step == "ask_desc":
        state["desc"] = text; state["step"] = "ask_phone"
        bot.send_message(message.chat.id,
            "✅ Tavsif saqlandi!\n\n📞 <b>Telefon raqam:</b>\n"
            "<i>Misol: +998901234567</i>", parse_mode="HTML")

    elif step == "ask_phone":
        ok, result = validate_phone(text)
        if not ok:
            bot.send_message(message.chat.id,
                f"{result}\n\nMisol: <code>+998901234567</code>", parse_mode="HTML"); return
        state["phone"] = result; state["step"] = "ask_admin"
        bot.send_message(message.chat.id,
            f"✅ Raqam: <b>{result}</b>\n\n👤 <b>Admin Telegram ID:</b>\n"
            "ID bilish: @userinfobot → /start", parse_mode="HTML")

    elif step == "ask_admin":
        try: state["admin_id"] = int(text)
        except:
            bot.send_message(message.chat.id, "❌ ID faqat raqam!"); return
        state["step"] = "ask_product"; state["products"] = []
        bot.send_message(message.chat.id,
            "✅ Admin sozlandi!\n\n📦 <b>Birinchi mahsulot:</b>\n\n"
            "<code>Nomi | Narxi | Tavsifi</code>", parse_mode="HTML")

    elif step == "ask_product":
        parts = text.split("|")
        if len(parts) < 2:
            bot.send_message(message.chat.id,
                "❌ Format: <code>Nomi | Narxi | Tavsifi</code>", parse_mode="HTML"); return
        p = make_product(parts[0].strip(), parts[1].strip(),
                         parts[2].strip() if len(parts)>2 else "")
        state["products"].append(p)
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("➕ Yana", callback_data=f"MORE:{uid}"),
            InlineKeyboardButton("✅ Tugatish", callback_data=f"DONE:{uid}"),
        )
        bot.send_message(message.chat.id,
            f"✅ <b>{p['name']}</b> qo'shildi! 🆔 <code>{p['id']}</code>\n"
            f"Jami: {len(state['products'])} ta\n\nYana?",
            reply_markup=markup, parse_mode="HTML")

    elif step in ("ei_name","ei_desc","ei_phone"):
        token = state.get("token"); s = state.get("short")
        db = load_db()
        if not token or token not in db:
            bot.send_message(message.chat.id,"❌ Bot topilmadi!"); user_state.pop(uid,None); return
        field = {"ei_name":"name","ei_desc":"desc","ei_phone":"phone"}[step]
        if step == "ei_phone":
            ok, result = validate_phone(text)
            if not ok:
                bot.send_message(message.chat.id,
                    f"{result}\n\nMisol: <code>+998901234567</code>", parse_mode="HTML"); return
            text = result
        db[token][field] = text; save_db(db); reload_biz_bot(token,db[token])
        user_state.pop(uid,None)
        bot.send_message(message.chat.id, f"✅ Yangilandi: <b>{text}</b>", parse_mode="HTML")

    elif step in ("pe_name","pe_price","pe_desc"):
        token = state.get("token"); pid = state.get("prod_id")
        db = load_db()
        if not token or token not in db:
            bot.send_message(message.chat.id,"❌ Bot topilmadi!"); user_state.pop(uid,None); return
        field = {"pe_name":"name","pe_price":"price","pe_desc":"desc"}[step]
        for p in db[token]["products"]:
            if p["id"] == pid: p[field] = text; break
        save_db(db); reload_biz_bot(token,db[token])
        user_state.pop(uid,None)
        bot.send_message(message.chat.id, f"✅ Yangilandi: <b>{text}</b>", parse_mode="HTML")

    elif step == "pe_photo":
        token = state.get("token"); pid = state.get("prod_id")
        if not message.photo:
            bot.send_message(message.chat.id, "❌ Rasm yuboring!"); return
        db = load_db()
        if not token or token not in db:
            bot.send_message(message.chat.id,"❌ Bot topilmadi!"); user_state.pop(uid,None); return
        photo_id = message.photo[-1].file_id
        for p in db[token]["products"]:
            if p["id"] == pid: p["photo_id"] = photo_id; break
        save_db(db); reload_biz_bot(token,db[token])
        user_state.pop(uid,None)
        bot.send_message(message.chat.id, "✅ Rasm yuklandi!")

    elif step == "pe_sale":
        token = state.get("token"); pid = state.get("prod_id")
        parts = text.split("|")
        if len(parts) < 2:
            bot.send_message(message.chat.id,
                "❌ Format: <code>Narxi | KUN</code>", parse_mode="HTML"); return
        try: days = int(parts[1].strip())
        except:
            bot.send_message(message.chat.id, "❌ Kun raqam bo'lishi kerak!"); return
        until = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M")
        db = load_db()
        if not token or token not in db:
            bot.send_message(message.chat.id,"❌ Bot topilmadi!"); user_state.pop(uid,None); return
        for p in db[token]["products"]:
            if p["id"] == pid:
                p["sale_price"] = parts[0].strip()
                p["sale_until"] = until; break
        save_db(db); reload_biz_bot(token,db[token])
        user_state.pop(uid,None)
        bot.send_message(message.chat.id,
            f"✅ Aksiya o'rnatildi!\n💰 {parts[0].strip()}\n⏰ {until} gacha", parse_mode="HTML")

    elif step == "prod_add":
        token = state.get("token"); s = state.get("short")
        parts = text.split("|")
        if len(parts) < 2:
            bot.send_message(message.chat.id,
                "❌ Format: <code>Nomi | Narxi | Tavsifi</code>", parse_mode="HTML"); return
        p  = make_product(parts[0].strip(), parts[1].strip(),
                          parts[2].strip() if len(parts)>2 else "")
        db = load_db()
        if not token or token not in db:
            bot.send_message(message.chat.id,"❌ Bot topilmadi!"); user_state.pop(uid,None); return
        db[token].setdefault("products",[]).append(p)
        save_db(db); reload_biz_bot(token,db[token])
        user_state.pop(uid,None)
        bot.send_message(message.chat.id,
            f"✅ <b>{p['name']}</b> qo'shildi! 🆔 <code>{p['id']}</code>", parse_mode="HTML")

    elif step == "promo_add":
        token = state.get("token")
        parts = text.split("|")
        if len(parts) < 2:
            bot.send_message(message.chat.id,
                "❌ Format: <code>KOD | Foiz</code>", parse_mode="HTML"); return
        code = parts[0].strip().upper()
        try: disc = int(parts[1].strip())
        except:
            bot.send_message(message.chat.id, "❌ Foiz raqam!"); return
        db = load_db()
        if not token or token not in db:
            bot.send_message(message.chat.id,"❌ Bot topilmadi!"); user_state.pop(uid,None); return
        db[token].setdefault("promos",{})[code] = disc
        save_db(db); reload_biz_bot(token,db[token])
        user_state.pop(uid,None)
        bot.send_message(message.chat.id,
            f"✅ Promo: <code>{code}</code> — <b>{disc}%</b>", parse_mode="HTML")

    elif step == "broadcast":
        token = state.get("token")
        db    = load_db()
        if not token or token not in db:
            bot.send_message(message.chat.id,"❌ Bot topilmadi!"); user_state.pop(uid,None); return
        orders_list = db[token].get("orders", [])
        client_ids  = list(set(o["uid"] for o in orders_list if o.get("uid")))
        biz_bot_obj = running_bots.get(token)
        if not biz_bot_obj:
            bot.send_message(message.chat.id,"❌ Bot ishlamayapti!"); user_state.pop(uid,None); return
        sent = 0
        for cid in client_ids:
            try:
                if message.photo:
                    biz_bot_obj.send_photo(cid, message.photo[-1].file_id,
                        caption=message.caption or "")
                else:
                    biz_bot_obj.send_message(cid, message.text)
                sent += 1
            except: pass
        user_state.pop(uid, None)
        bot.send_message(message.chat.id,
            f"📢 Broadcast yuborildi!\n✅ {sent}/{len(client_ids)} mijozga yetdi.")

    elif step == "sa_giveprem":
        parts = text.split("|")
        if len(parts) < 2:
            bot.send_message(message.chat.id,
                "❌ Format: <code>USER_ID | KUN</code>", parse_mode="HTML"); return
        try:
            target_uid = parts[0].strip()
            days       = int(parts[1].strip())
        except:
            bot.send_message(message.chat.id, "❌ Noto'g'ri format!"); return
        until = set_premium(target_uid, days)
        user_state.pop(uid, None)
        bot.send_message(message.chat.id,
            f"✅ <code>{target_uid}</code> ga <b>{days}</b> kun Premium!\nMuddat: {until}",
            parse_mode="HTML")
        try:
            bot.send_message(int(target_uid),
                f"🎉 <b>Premium faollashdi!</b>\nMuddat: <b>{until}</b>", parse_mode="HTML")
        except: pass

    elif step == "sa_broadcast":
        users    = load_users()
        all_uids = list(users.keys())
        sent     = 0
        for cid in all_uids:
            try:
                if message.photo:
                    bot.send_photo(int(cid), message.photo[-1].file_id,
                        caption=message.caption or "")
                else:
                    bot.send_message(int(cid), message.text)
                sent += 1
            except: pass
        user_state.pop(uid, None)
        bot.send_message(message.chat.id,
            f"📢 <b>Global Broadcast!</b>\n✅ {sent}/{len(all_uids)} foydalanuvchiga yetdi.",
            parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data.startswith("MORE:"))
def more_cb(call):
    uid = int(call.data.split(":")[1])
    if uid in user_state: user_state[uid]["step"] = "ask_product"
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
        text="📦 Keyingi mahsulot:\n\n<code>Nomi | Narxi | Tavsifi</code>", parse_mode="HTML")

@bot.callback_query_handler(func=lambda c: c.data.startswith("DONE:"))
def done_cb(call):
    uid   = int(call.data.split(":")[1])
    state = user_state.get(uid)
    if not state: bot.answer_callback_query(call.id,"Xato! Qaytadan boshlang."); return
    token    = state.get("token")
    biz_data = {
        "owner": str(uid), "name": state.get("name",""),
        "desc":  state.get("desc",""), "phone": state.get("phone",""),
        "admin_id": state.get("admin_id", uid),
        "products": state.get("products",[]),
        "promos": {}, "orders": [],
    }
    db = load_db(); db[token] = biz_data; save_db(db)
    try:
        start_biz_bot(token, biz_data)
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
            text=(f"🎉 <b>Bot yaratildi!</b>\n\n"
                  f"🏪 <b>{biz_data['name']}</b>\n"
                  f"📦 {len(biz_data['products'])} ta mahsulot\n\n"
                  "✅ Bot ishlamoqda! 🚀"),
            parse_mode="HTML")
    except Exception as e:
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
            text=f"❌ Xatolik: <code>{e}</code>", parse_mode="HTML")
    user_state.pop(uid, None)

# ══════════════════════════════════════════════
# BIZNES BOT MOTORI
# ══════════════════════════════════════════════

def start_biz_bot(token, data):
    if token in running_bots:
        try: running_bots[token].stop_polling()
        except: pass

    bb     = telebot.TeleBot(token)
    if token not in biz_orders: biz_orders[token] = {}
    orders = biz_orders[token]

    def send_main_kb(chat_id, user_id):
        m = ReplyKeyboardMarkup(resize_keyboard=True)
        m.add(KeyboardButton("🛍️ Katalog"),  KeyboardButton("💰 Narxlar"))
        m.add(KeyboardButton("📦 Buyurtma"), KeyboardButton("📞 Aloqa"))
        m.add(KeyboardButton("⭐ Sharhlar"))
        if int(user_id) == int(data.get("admin_id", -1)):
            m.add(KeyboardButton("⚙️ Admin panel"))
        bb.send_message(chat_id, "👇 Bo'limni tanlang:", reply_markup=m)

    def check_subscription(uid):
        """Foydalanuvchi kanalga obuna bo'lganmi tekshirish"""
        channel = data.get("required_channel")
        if not channel: return True
        try:
            member = bb.get_chat_member(channel, uid)
            return member.status in ("member","administrator","creator")
        except: return True  # Kanal topilmasa o'tkazib yuboramiz

    def ask_subscribe(chat_id, channel):
        """Obuna bo'lishni so'rash"""
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("📣 Kanalga o'tish", url=f"https://t.me/{channel.lstrip('@')}"))
        markup.add(InlineKeyboardButton("✅ Obuna bo'ldim", callback_data="CHECK_SUB"))
        bb.send_message(chat_id,
            f"⚠️ <b>Davom etish uchun kanalga obuna bo'ling:</b>\n\n"
            f"📣 {channel}\n\n"
            "Obuna bo'lgach «✅ Obuna bo'ldim» tugmasini bosing.",
            reply_markup=markup, parse_mode="HTML")

    @bb.callback_query_handler(func=lambda c: c.data == "CHECK_SUB")
    def check_sub_cb(call):
        if check_subscription(call.from_user.id):
            bb.answer_callback_query(call.id, "✅ Tasdiqlandi!")
            bb.delete_message(call.message.chat.id, call.message.message_id)
            send_main_kb(call.message.chat.id, call.from_user.id)
        else:
            bb.answer_callback_query(call.id,
                "❌ Siz hali obuna bo'lmadingiz!", show_alert=True)

    # ── /start ────────────────────────────────
    @bb.message_handler(commands=["start"])
    def biz_start(msg):
        if not check_subscription(msg.from_user.id):
            channel = data.get("required_channel","")
            bb.send_message(msg.chat.id,
                f"👋 Xush kelibsiz!\n\n🏪 <b>{data['name']}</b>\n📝 {data['desc']}",
                parse_mode="HTML")
            ask_subscribe(msg.chat.id, channel); return
        bb.send_message(msg.chat.id,
            f"👋 Xush kelibsiz!\n\n🏪 <b>{data['name']}</b>\n📝 {data['desc']}",
            parse_mode="HTML")
        send_main_kb(msg.chat.id, msg.from_user.id)

    # ── Katalog ───────────────────────────────
    @bb.message_handler(func=lambda m: m.text == "🛍️ Katalog")
    def biz_catalog(msg):
        products = data.get("products",[])
        if not products: bb.send_message(msg.chat.id,"📭 Hozircha mahsulot yo'q."); return
        markup = InlineKeyboardMarkup()
        for p in products:
            price, on_sale = get_active_price(p)
            rating = avg_rating(p.get("reviews",[]))
            r_str  = f" ⭐{rating:.1f}" if rating else ""
            sale_m = "🔥" if on_sale else ""
            markup.add(InlineKeyboardButton(
                f"{sale_m}{p['name']} — {price}{r_str}",
                callback_data=f"BP:{p['id']}"))
        bb.send_message(msg.chat.id,
            f"🛍️ <b>Katalog</b> — {len(products)} ta:",
            reply_markup=markup, parse_mode="HTML")

    @bb.callback_query_handler(func=lambda c: c.data.startswith("BP:"))
    def biz_prod_cb(call):
        pid = call.data[3:]
        p   = next((x for x in data["products"] if x["id"]==pid), None)
        if not p: return
        price, on_sale = get_active_price(p)
        sale_tx = f"\n🔥 <b>Aksiya: {price}</b>" if on_sale else ""
        reviews = p.get("reviews",[])
        rating  = avg_rating(reviews)
        r_str   = f"\n⭐ {rating:.1f}/5 ({len(reviews)} sharh)" if reviews else ""
        markup  = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("🛒 Buyurtma",  callback_data=f"BO:{pid}"),
            InlineKeyboardButton("⭐ Sharhlar",  callback_data=f"RV:{pid}"),
            InlineKeyboardButton("◀️ Orqaga",    callback_data="BCAT"),
        )
        if p.get("photo_id"):
            try:
                bb.delete_message(call.message.chat.id, call.message.message_id)
                bb.send_photo(call.message.chat.id, p["photo_id"],
                    caption=(f"📦 <b>{p['name']}</b>\n"
                             f"💰 {p['price']}{sale_tx}\n"
                             f"📝 {p.get('desc','—')}{r_str}"),
                    reply_markup=markup, parse_mode="HTML")
            except:
                bb.edit_message_text(chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=(f"📦 <b>{p['name']}</b>\n💰 {p['price']}{sale_tx}\n"
                          f"📝 {p.get('desc','—')}{r_str}"),
                    reply_markup=markup, parse_mode="HTML")
        else:
            bb.edit_message_text(chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=(f"📦 <b>{p['name']}</b>\n💰 {p['price']}{sale_tx}\n"
                      f"📝 {p.get('desc','—')}{r_str}"),
                reply_markup=markup, parse_mode="HTML")

    @bb.callback_query_handler(func=lambda c: c.data == "BCAT")
    def biz_back(call):
        products = data.get("products",[])
        markup   = InlineKeyboardMarkup()
        for p in products:
            price, on_sale = get_active_price(p)
            markup.add(InlineKeyboardButton(
                f"{'🔥' if on_sale else ''}{p['name']} — {price}",
                callback_data=f"BP:{p['id']}"))
        bb.edit_message_text(chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"🛍️ <b>Katalog</b> — {len(products)} ta:",
            reply_markup=markup, parse_mode="HTML")

    # ── Narxlar ───────────────────────────────
    @bb.message_handler(func=lambda m: m.text == "💰 Narxlar")
    def biz_prices(msg):
        products = data.get("products",[])
        text = f"💰 <b>{data['name']} — Narxlar</b>\n\n"
        for i, p in enumerate(products,1):
            price, on_sale = get_active_price(p)
            sale_m = " 🔥" if on_sale else ""
            text  += f"{i}. {p['name']} — <b>{price}</b>{sale_m}\n"
        text += f"\n📞 {data['phone']}"
        bb.send_message(msg.chat.id, text, parse_mode="HTML")

    # ── Sharhlar ──────────────────────────────
    @bb.message_handler(func=lambda m: m.text == "⭐ Sharhlar")
    def biz_reviews(msg):
        products = data.get("products",[])
        markup   = InlineKeyboardMarkup()
        for p in products:
            rating = avg_rating(p.get("reviews",[]))
            r_str  = f"⭐{rating:.1f}" if p.get("reviews") else "—"
            markup.add(InlineKeyboardButton(
                f"{p['name']} {r_str}", callback_data=f"RV:{p['id']}"))
        bb.send_message(msg.chat.id,
            "⭐ <b>Sharhlar</b>\n\nMahsulotni tanlang:",
            reply_markup=markup, parse_mode="HTML")

    @bb.callback_query_handler(func=lambda c: c.data.startswith("RV:"))
    def show_reviews(call):
        pid      = call.data[3:]
        p        = next((x for x in data["products"] if x["id"]==pid), None)
        if not p: return
        reviews  = p.get("reviews",[])
        markup   = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("✍️ Sharh qoldirish", callback_data=f"WR:{pid}"))
        markup.add(InlineKeyboardButton("◀️ Orqaga", callback_data=f"BP:{pid}"))
        if not reviews:
            text = f"⭐ <b>{p['name']}</b>\n\nHali sharh yo'q. Birinchi bo'ling!"
        else:
            rating = avg_rating(reviews)
            text   = f"⭐ <b>{p['name']}</b> — {rating:.1f}/5\n\n"
            for r in reviews[-5:]:
                text += f"{stars(r['stars'])} <b>{r['name']}</b>\n{r['text']}\n\n"
        bb.edit_message_text(chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=text, reply_markup=markup, parse_mode="HTML")

    @bb.callback_query_handler(func=lambda c: c.data.startswith("WR:"))
    def write_review(call):
        pid = call.data[3:]
        orders[call.from_user.id] = {"step":"review_stars","prod_id":pid}
        markup = InlineKeyboardMarkup(row_width=5)
        markup.add(*[InlineKeyboardButton(f"{i}⭐", callback_data=f"RS:{pid}:{i}") for i in range(1,6)])
        bb.edit_message_text(chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="⭐ Necha yulduz berasiz?",
            reply_markup=markup)

    @bb.callback_query_handler(func=lambda c: c.data.startswith("RS:"))
    def review_stars(call):
        parts  = call.data.split(":")
        pid, n = parts[1], int(parts[2])
        orders[call.from_user.id] = {
            "step": "review_text", "prod_id": pid,
            "stars": n, "name": call.from_user.first_name
        }
        bb.edit_message_text(chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"{stars(n)} {n} yulduz!\n\n✍️ Izoh yozing:")

    # ── Buyurtma ──────────────────────────────
    @bb.message_handler(func=lambda m: m.text == "📦 Buyurtma")
    def biz_order(msg):
        products = data.get("products",[])
        markup   = InlineKeyboardMarkup()
        for p in products:
            price, _ = get_active_price(p)
            markup.add(InlineKeyboardButton(f"{p['name']} — {price}", callback_data=f"BO:{p['id']}"))
        bb.send_message(msg.chat.id,
            "📦 <b>Buyurtma</b>\n\nMahsulot tanlang:",
            reply_markup=markup, parse_mode="HTML")

    @bb.callback_query_handler(func=lambda c: c.data.startswith("BO:"))
    def biz_order_start(call):
        if not check_subscription(call.from_user.id):
            bb.answer_callback_query(call.id)
            ask_subscribe(call.message.chat.id, data.get("required_channel","")); return
        pid = call.data[3:]
        p   = next((x for x in data["products"] if x["id"]==pid), None)
        if not p: return
        orders[call.from_user.id] = {"product":p,"step":"ask_name"}
        bb.edit_message_text(chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"🛒 <b>{p['name']}</b> tanlandi!\n\n👤 Ismingizni yozing:",
            parse_mode="HTML")

    # ── Buyurtma jarayoni ─────────────────────
    @bb.message_handler(func=lambda m: m.from_user.id in orders and
        orders[m.from_user.id].get("step") == "ask_name")
    def order_name(msg):
        name = msg.text.strip() if msg.text else ""
        if len(name) < 2: bb.send_message(msg.chat.id,"❌ Ism kamida 2 harf!"); return
        orders[msg.from_user.id]["name"] = name
        orders[msg.from_user.id]["step"] = "ask_phone"
        markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add(KeyboardButton("📱 Raqamimni ulashish", request_contact=True))
        bb.send_message(msg.chat.id,
            "📞 <b>Telefon raqamingiz</b>\n\n"
            "Tugma orqali ulashing <b>yoki</b> qo'lda kiriting:\n"
            "<i>+998901234567</i>",
            reply_markup=markup, parse_mode="HTML")

    @bb.message_handler(content_types=["contact"],
        func=lambda m: m.from_user.id in orders and
        orders[m.from_user.id].get("step") == "ask_phone")
    def order_contact(msg):
        phone = format_contact_phone(msg.contact)
        if not phone: bb.send_message(msg.chat.id,"❌ Raqam olib bo'lmadi. Qo'lda kiriting:"); return
        _after_phone(msg, phone)

    @bb.message_handler(func=lambda m: m.from_user.id in orders and
        orders[m.from_user.id].get("step") == "ask_phone")
    def order_phone_text(msg):
        ok, result = validate_phone(msg.text.strip() if msg.text else "")
        if not ok:
            bb.send_message(msg.chat.id,
                f"{result}\n\nYoki tugma orqali ulashing.", parse_mode="HTML"); return
        _after_phone(msg, result)

    def _after_phone(msg, phone):
        orders[msg.from_user.id]["phone"] = phone
        main_m = ReplyKeyboardMarkup(resize_keyboard=True)
        main_m.add(KeyboardButton("🛍️ Katalog"), KeyboardButton("💰 Narxlar"))
        main_m.add(KeyboardButton("📦 Buyurtma"), KeyboardButton("📞 Aloqa"))
        main_m.add(KeyboardButton("⭐ Sharhlar"))
        if msg.from_user.id == int(data.get("admin_id", -1)): main_m.add(KeyboardButton("⚙️ Admin panel"))
        if data.get("promos"):
            orders[msg.from_user.id]["step"] = "ask_promo"
            bb.send_message(msg.chat.id,
                f"✅ Raqam: <b>{phone}</b>\n\n"
                "🎟️ Promo kodingiz bormi? Yo'q bo'lsa «Yo'q» yozing:",
                reply_markup=main_m, parse_mode="HTML")
        else:
            orders[msg.from_user.id]["step"] = "ask_addr"
            bb.send_message(msg.chat.id,
                f"✅ Raqam: <b>{phone}</b>\n\n📍 Manzilingizni yozing:",
                reply_markup=main_m, parse_mode="HTML")

    @bb.message_handler(func=lambda m: m.from_user.id in orders and
        orders[m.from_user.id].get("step") == "ask_promo")
    def order_promo(msg):
        code   = msg.text.strip().upper() if msg.text else ""
        promos = data.get("promos",{})
        if code in promos:
            orders[msg.from_user.id]["discount"] = promos[code]
            bb.send_message(msg.chat.id, f"✅ <b>{promos[code]}%</b> chegirma!", parse_mode="HTML")
        else:
            orders[msg.from_user.id]["discount"] = 0
        orders[msg.from_user.id]["step"] = "ask_addr"
        bb.send_message(msg.chat.id, "📍 Manzilingizni yozing:")

    @bb.message_handler(func=lambda m: m.from_user.id in orders and
        orders[m.from_user.id].get("step") == "ask_addr")
    def order_addr(msg):
        addr = msg.text.strip() if msg.text else ""
        if len(addr) < 5: bb.send_message(msg.chat.id,"❌ Manzil kamida 5 belgi!"); return
        orders[msg.from_user.id]["addr"] = addr
        orders[msg.from_user.id]["step"] = "ask_payment"
        # To'lov screenshoti so'rash
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("💳 To'lovni o'tkazdim", callback_data="PAY_SENT"))
        markup.add(InlineKeyboardButton("🚚 Yetkazilganda to'layman", callback_data="PAY_COD"))
        bb.send_message(msg.chat.id,
            "💳 <b>To'lov usulini tanlang:</b>",
            reply_markup=markup, parse_mode="HTML")

    @bb.callback_query_handler(func=lambda c: c.data == "PAY_SENT" and
        c.from_user.id in orders)
    def pay_sent(call):
        orders[call.from_user.id]["step"]    = "ask_screenshot"
        orders[call.from_user.id]["payment"] = "transfer"
        bb.edit_message_text(chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="📸 <b>To'lov screenshotini yuboring:</b>\n\n"
                 "To'lov amalga oshirilgandan keyin screenshot olib yuboring.",
            parse_mode="HTML")

    @bb.callback_query_handler(func=lambda c: c.data == "PAY_COD" and
        c.from_user.id in orders)
    def pay_cod(call):
        orders[call.from_user.id]["payment"] = "cod"
        _finalize_order(call.message, call.from_user.id, call.from_user.first_name)

    @bb.message_handler(content_types=["photo"],
        func=lambda m: m.from_user.id in orders and
        orders[m.from_user.id].get("step") == "ask_screenshot")
    def order_screenshot(msg):
        orders[msg.from_user.id]["screenshot_id"] = msg.photo[-1].file_id
        orders[msg.from_user.id]["step"]          = "pending_confirmation"
        _finalize_order(msg, msg.from_user.id, msg.from_user.first_name, with_screenshot=True)

    def _finalize_order(msg, uid, fname, with_screenshot=False):
        order = orders.get(uid, {})
        p     = order.get("product",{})
        disc  = order.get("discount",0)
        d_tx  = f"\n🎟️ Chegirma: <b>{disc}%</b>" if disc else ""
        pay   = "💳 Bank o'tkazmasi" if order.get("payment") == "transfer" else "🚚 Naqd (yetkazilganda)"
        s_tx  = "\n📸 Screenshot yuborildi" if with_screenshot else ""

        # Buyurtma ID
        order_id = str(uuid.uuid4())[:6].upper()
        orders[uid]["order_id"] = order_id

        bb.send_message(msg.chat.id,
            f"✅ <b>Buyurtma qabul qilindi!</b>\n"
            f"🆔 Buyurtma: <code>{order_id}</code>\n\n"
            f"📦 {p.get('name','')}\n💰 {p.get('price','')}{d_tx}\n"
            f"👤 {order.get('name','')}\n📞 {order.get('phone','')}\n"
            f"📍 {order.get('addr','')}\n"
            f"💳 {pay}{s_tx}\n\n"
            f"⏳ Admin tasdiqlashini kuting.",
            parse_mode="HTML")

        # Adminga
        try:
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"OC:{uid}:{order_id}"),
                InlineKeyboardButton("❌ Bekor qilish", callback_data=f"OR:{uid}:{order_id}"),
            )
            adm_text = (
                f"🔔 <b>YANGI BUYURTMA!</b> 🆔 <code>{order_id}</code>\n\n"
                f"📦 <b>{p.get('name','')}</b> — {p.get('price','')}{d_tx}\n"
                f"💳 {pay}\n\n"
                f"👤 {order.get('name','')}\n"
                f"📞 {order.get('phone','')}\n"
                f"📍 {order.get('addr','')}\n"
                f"🆔 TG ID: <code>{uid}</code>"
            )
            if with_screenshot and order.get("screenshot_id"):
                bb.send_photo(data["admin_id"], order["screenshot_id"],
                    caption=adm_text, reply_markup=markup, parse_mode="HTML")
            else:
                bb.send_message(data["admin_id"], adm_text,
                    reply_markup=markup, parse_mode="HTML")
        except: pass

        # DB ga saqlash
        db_live = load_db()
        if token in db_live:
            db_live[token].setdefault("orders",[]).append({
                "uid": uid, "order_id": order_id,
                "product_name": p.get("name",""),
                "status": "pending_payment" if with_screenshot else "pending",
                "date": datetime.now().strftime("%Y-%m-%d %H:%M")
            })
            save_db(db_live)
            data["orders"] = db_live[token]["orders"]
        orders.pop(uid, None)

    # ── Buyurtma tasdiqlash/rad (admin) ────────
    @bb.callback_query_handler(func=lambda c: c.data.startswith("OC:") or c.data.startswith("OR:"))
    def order_confirm(call):
        if call.from_user.id != int(data.get("admin_id", -1)): return
        parts    = call.data.split(":")
        action   = parts[0]
        cuid     = int(parts[1])
        order_id = parts[2]

        if action == "OC":
            try:
                bb.send_message(cuid,
                    f"✅ <b>Buyurtmangiz tasdiqlandi!</b>\n"
                    f"🆔 <code>{order_id}</code>\n\n"
                    f"Tez orada yetkazib beramiz. 🚚",
                    parse_mode="HTML")
            except: pass
            status_text = "✅ Tasdiqlandi"
        else:
            try:
                bb.send_message(cuid,
                    f"❌ <b>Buyurtmangiz bekor qilindi.</b>\n"
                    f"🆔 <code>{order_id}</code>\n\n"
                    f"Savollar uchun: {data['phone']}",
                    parse_mode="HTML")
            except: pass
            status_text = "❌ Bekor qilindi"

        # DB yangilash
        db_live = load_db()
        if token in db_live:
            for o in db_live[token].get("orders",[]):
                if o.get("order_id") == order_id:
                    o["status"] = "confirmed" if action=="OC" else "rejected"; break
            save_db(db_live)
            data["orders"] = db_live[token]["orders"]

        bb.edit_message_caption(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            caption=call.message.caption + f"\n\n{status_text}",
            parse_mode="HTML") if call.message.caption else bb.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=call.message.text + f"\n\n{status_text}",
            parse_mode="HTML")

    # ── Sharh yozish ──────────────────────────
    @bb.message_handler(func=lambda m: m.from_user.id in orders and
        orders[m.from_user.id].get("step") == "review_text")
    def review_text(msg):
        uid_   = msg.from_user.id
        order  = orders[uid_]
        pid    = order["prod_id"]
        review = {
            "name":  order["name"],
            "stars": order["stars"],
            "text":  msg.text.strip() if msg.text else "—",
            "date":  datetime.now().strftime("%Y-%m-%d")
        }
        db_live = load_db()
        if token in db_live:
            for p in db_live[token]["products"]:
                if p["id"] == pid:
                    p.setdefault("reviews",[]).append(review)
                    break
            save_db(db_live)
            data["products"] = db_live[token]["products"]
        orders.pop(uid_, None)
        bb.send_message(msg.chat.id,
            f"✅ Rahmat! {stars(review['stars'])} sharh qabul qilindi!", parse_mode="HTML")

    # ── Aloqa ─────────────────────────────────
    @bb.message_handler(func=lambda m: m.text == "📞 Aloqa")
    def biz_contact(msg):
        bb.send_message(msg.chat.id,
            f"📞 <b>Aloqa</b>\n\n🏪 {data['name']}\n📱 {data['phone']}",
            parse_mode="HTML")

    # ══════════════════════════════════════════
    # BIZNES BOT ADMIN PANEL
    # ══════════════════════════════════════════
    @bb.message_handler(func=lambda m: m.text == "⚙️ Admin panel" and
        m.from_user.id == int(data.get("admin_id", -1)))
    def adm_panel(msg):
        products = data.get("products",[]); ords = data.get("orders",[])
        channel  = data.get("required_channel","Yo'q")
        markup   = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(f"📦 Mahsulotlar ({len(products)})", callback_data="ADM_PRODS"))
        markup.add(InlineKeyboardButton("✏️ Ma'lumotlar",                    callback_data="ADM_INFO"))
        markup.add(InlineKeyboardButton(f"🛒 Buyurtmalar ({len(ords)})",    callback_data="ADM_ORDERS"))
        markup.add(InlineKeyboardButton("🎟️ Promo kodlar",                  callback_data="ADM_PROMOS"))
        markup.add(InlineKeyboardButton(f"📣 Kanal ({channel})",            callback_data="ADM_CHANNEL"))
        bb.send_message(msg.chat.id,
            f"⚙️ <b>Admin panel</b>\n🏪 {data['name']}",
            reply_markup=markup, parse_mode="HTML")

    @bb.callback_query_handler(func=lambda c: c.data == "ADM_PRODS")
    def adm_prods(call):
        if call.from_user.id != int(data.get("admin_id", -1)): return
        products = data.get("products",[])
        markup   = InlineKeyboardMarkup()
        for p in products:
            price, on_sale = get_active_price(p)
            markup.add(InlineKeyboardButton(
                f"{'🔥' if on_sale else ''}[{p['id']}] {p['name']} — {price}",
                callback_data=f"ADMP:{p['id']}"))
        markup.add(InlineKeyboardButton("➕ Qo'shish", callback_data="ADM_ADDP"))
        markup.add(InlineKeyboardButton("◀️ Orqaga",   callback_data="ADM_BACK"))
        bb.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
            text=f"📦 <b>Mahsulotlar</b> — {len(products)} ta:",
            reply_markup=markup, parse_mode="HTML")

    @bb.callback_query_handler(func=lambda c: c.data.startswith("ADMP:"))
    def adm_prod_menu(call):
        if call.from_user.id != int(data.get("admin_id", -1)): return
        pid = call.data[5:]
        p   = next((x for x in data["products"] if x["id"]==pid), None)
        if not p: return
        price, on_sale = get_active_price(p)
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("✏️ Nom",    callback_data=f"AEN:{pid}"),
            InlineKeyboardButton("💰 Narx",   callback_data=f"AEP:{pid}"),
            InlineKeyboardButton("📝 Tavsif", callback_data=f"AED:{pid}"),
            InlineKeyboardButton("🗑️ O'chir", callback_data=f"ADL:{pid}"),
        )
        markup.add(InlineKeyboardButton("◀️ Orqaga", callback_data="ADM_PRODS"))
        bb.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
            text=(f"📦 <b>{p['name']}</b>\n💰 {price}\n"
                  f"📝 {p.get('desc','—')}\n🆔 <code>{p['id']}</code>"),
            reply_markup=markup, parse_mode="HTML")

    @bb.callback_query_handler(func=lambda c: c.data.startswith("ADL:"))
    def adm_del(call):
        if call.from_user.id != int(data.get("admin_id", -1)): return
        pid     = call.data[4:]
        db_live = load_db()
        if token in db_live:
            db_live[token]["products"] = [p for p in db_live[token]["products"] if p["id"]!=pid]
            save_db(db_live); data["products"] = db_live[token]["products"]
        bb.answer_callback_query(call.id,"🗑️ O'chirildi!")
        call.data = "ADM_PRODS"; adm_prods(call)

    @bb.callback_query_handler(func=lambda c: c.data[:4] in ("AEN:","AEP:","AED:"))
    def adm_edit_prod(call):
        if call.from_user.id != int(data.get("admin_id", -1)): return
        code = call.data[:3]; pid = call.data[4:]
        sm = {"AEN":"adm_pname","AEP":"adm_pprice","AED":"adm_pdesc"}
        lm = {"AEN":"nomini","AEP":"narxini","AED":"tavsifini"}
        orders[call.from_user.id] = {"step":sm[code],"prod_id":pid}
        bb.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
            text=f"✏️ Mahsulotning yangi {lm[code]}ni yozing:")

    @bb.callback_query_handler(func=lambda c: c.data == "ADM_ADDP")
    def adm_addp(call):
        if call.from_user.id != int(data.get("admin_id", -1)): return
        orders[call.from_user.id] = {"step":"adm_addprod"}
        bb.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
            text="📦 Yangi mahsulot:\n\n<code>Nomi | Narxi | Tavsifi</code>", parse_mode="HTML")

    @bb.callback_query_handler(func=lambda c: c.data == "ADM_INFO")
    def adm_info(call):
        if call.from_user.id != int(data.get("admin_id", -1)): return
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("✏️ Nom",     callback_data="ACN"))
        markup.add(InlineKeyboardButton("📝 Tavsif",  callback_data="ACD"))
        markup.add(InlineKeyboardButton("📞 Telefon", callback_data="ACP"))
        markup.add(InlineKeyboardButton("◀️ Orqaga",  callback_data="ADM_BACK"))
        bb.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
            text=(f"✏️ <b>Ma'lumotlar</b>\n\n"
                  f"Nom: {data['name']}\nTavsif: {data['desc']}\nTel: {data['phone']}"),
            reply_markup=markup, parse_mode="HTML")

    @bb.callback_query_handler(func=lambda c: c.data in ("ACN","ACD","ACP"))
    def adm_change(call):
        if call.from_user.id != int(data.get("admin_id", -1)): return
        sm = {"ACN":"adm_chname","ACD":"adm_chdesc","ACP":"adm_chphone"}
        lm = {"ACN":"nomini","ACD":"tavsifini","ACP":"telefonini"}
        orders[call.from_user.id] = {"step":sm[call.data]}
        bb.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
            text=f"✏️ Biznesning yangi {lm[call.data]}ni yozing:")

    @bb.callback_query_handler(func=lambda c: c.data == "ADM_ORDERS")
    def adm_orders_list(call):
        if call.from_user.id != int(data.get("admin_id", -1)): return
        ords  = data.get("orders",[])[-10:]
        text  = "🛒 <b>Oxirgi 10 ta buyurtma</b>\n\n"
        for o in reversed(ords):
            st = {"confirmed":"✅","rejected":"❌","pending":"⏳","pending_payment":"💳"}.get(o.get("status",""),"⏳")
            text += f"{st} [{o.get('order_id','?')}] {o.get('product_name','?')} | {o.get('date','')}\n"
        if not ords: text += "Hali buyurtma yo'q."
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("◀️ Orqaga", callback_data="ADM_BACK"))
        bb.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
            text=text, reply_markup=markup, parse_mode="HTML")

    @bb.callback_query_handler(func=lambda c: c.data == "ADM_PROMOS")
    def adm_promos(call):
        if call.from_user.id != int(data.get("admin_id", -1)): return
        promos = data.get("promos",{})
        markup = InlineKeyboardMarkup()
        for code,disc in promos.items():
            markup.add(InlineKeyboardButton(f"🎟️ {code} — {disc}%", callback_data=f"APRD:{code}"))
        markup.add(InlineKeyboardButton("➕ Yangi promo", callback_data="APRA"))
        markup.add(InlineKeyboardButton("◀️ Orqaga",      callback_data="ADM_BACK"))
        bb.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
            text=f"🎟️ <b>Promo kodlar</b> — {len(promos)} ta:",
            reply_markup=markup, parse_mode="HTML")

    @bb.callback_query_handler(func=lambda c: c.data.startswith("APRD:"))
    def adm_promo_del(call):
        if call.from_user.id != int(data.get("admin_id", -1)): return
        code    = call.data[5:]
        db_live = load_db()
        if token in db_live and code in db_live[token].get("promos",{}):
            del db_live[token]["promos"][code]; save_db(db_live)
            data["promos"] = db_live[token]["promos"]
        bb.answer_callback_query(call.id,f"🗑️ {code} o'chirildi!")
        call.data = "ADM_PROMOS"; adm_promos(call)

    @bb.callback_query_handler(func=lambda c: c.data == "APRA")
    def adm_promo_add(call):
        if call.from_user.id != int(data.get("admin_id", -1)): return
        orders[call.from_user.id] = {"step":"adm_promo"}
        bb.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
            text="🎟️ Promo kodni yozing:\n\n<code>KOD | Chegirma%</code>", parse_mode="HTML")

    @bb.callback_query_handler(func=lambda c: c.data == "ADM_BACK")
    def adm_back_cb(call):
        if call.from_user.id != int(data.get("admin_id", -1)): return
        products = data.get("products",[]); ords = data.get("orders",[])
        markup   = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(f"📦 Mahsulotlar ({len(products)})", callback_data="ADM_PRODS"))
        markup.add(InlineKeyboardButton("✏️ Ma'lumotlar",                    callback_data="ADM_INFO"))
        markup.add(InlineKeyboardButton(f"🛒 Buyurtmalar ({len(ords)})",    callback_data="ADM_ORDERS"))
        markup.add(InlineKeyboardButton("🎟️ Promo kodlar",                  callback_data="ADM_PROMOS"))
        markup.add(InlineKeyboardButton(f"📣 Kanal",                        callback_data="ADM_CHANNEL"))
        bb.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
            text=f"⚙️ <b>Admin panel</b>\n🏪 {data['name']}",
            reply_markup=markup, parse_mode="HTML")

    # ── Admin matn handleri ───────────────────
    @bb.message_handler(content_types=["text","photo"],
        func=lambda m: m.from_user.id in orders and
        orders[m.from_user.id].get("step","").startswith("adm"))
    def adm_text(msg):
        if msg.from_user.id != int(data.get("admin_id", -1)): return
        uid_  = msg.from_user.id
        order = orders[uid_]
        step  = order["step"]
        txt   = msg.text.strip() if msg.text else ""
        db_live = load_db()

        if step == "adm_addprod":
            parts = txt.split("|")
            if len(parts) < 2:
                bb.send_message(msg.chat.id,
                    "❌ Format: <code>Nomi | Narxi | Tavsifi</code>", parse_mode="HTML"); return
            p = make_product(parts[0].strip(), parts[1].strip(),
                             parts[2].strip() if len(parts)>2 else "")
            if token in db_live:
                db_live[token].setdefault("products",[]).append(p)
                save_db(db_live); data["products"] = db_live[token]["products"]
            orders.pop(uid_,None)
            bb.send_message(msg.chat.id,
                f"✅ <b>{p['name']}</b> qo'shildi! 🆔 <code>{p['id']}</code>", parse_mode="HTML")

        elif step in ("adm_pname","adm_pprice","adm_pdesc"):
            pid   = order["prod_id"]
            field = {"adm_pname":"name","adm_pprice":"price","adm_pdesc":"desc"}[step]
            if token in db_live:
                for p in db_live[token]["products"]:
                    if p["id"]==pid: p[field]=txt; break
                save_db(db_live); data["products"]=db_live[token]["products"]
            orders.pop(uid_,None)
            bb.send_message(msg.chat.id, f"✅ Yangilandi: <b>{txt}</b>", parse_mode="HTML")

        elif step in ("adm_chname","adm_chdesc","adm_chphone"):
            field = {"adm_chname":"name","adm_chdesc":"desc","adm_chphone":"phone"}[step]
            if step == "adm_chphone":
                ok, result = validate_phone(txt)
                if not ok:
                    bb.send_message(msg.chat.id,
                        f"{result}\n\nMisol: <code>+998901234567</code>", parse_mode="HTML"); return
                txt = result
            if token in db_live:
                db_live[token][field]=txt; save_db(db_live); data[field]=txt
            orders.pop(uid_,None)
            bb.send_message(msg.chat.id, f"✅ Yangilandi: <b>{txt}</b>", parse_mode="HTML")

        elif step == "adm_promo":
            parts = txt.split("|")
            if len(parts) < 2:
                bb.send_message(msg.chat.id,
                    "❌ Format: <code>KOD | Foiz</code>", parse_mode="HTML"); return
            code = parts[0].strip().upper()
            try: disc = int(parts[1].strip())
            except: bb.send_message(msg.chat.id,"❌ Foiz raqam!"); return
            if token in db_live:
                db_live[token].setdefault("promos",{})[code]=disc
                save_db(db_live); data["promos"]=db_live[token]["promos"]
            orders.pop(uid_,None)
            bb.send_message(msg.chat.id,
                f"✅ Promo: <code>{code}</code> — <b>{disc}%</b>", parse_mode="HTML")

        elif step == "adm_channel":
            channel = txt.strip()
            if not channel.startswith("@"):
                channel = "@" + channel
            if token in db_live:
                db_live[token]["required_channel"] = channel
                save_db(db_live); data["required_channel"] = channel
            orders.pop(uid_,None)
            bb.send_message(msg.chat.id,
                f"✅ Kanal sozlandi: <b>{channel}</b>\n\n"
                f"Endi buyurtma berishdan oldin kanalga obuna bo'lish majburiy!",
                parse_mode="HTML")

    @bb.callback_query_handler(func=lambda c: c.data == "ADM_CHANNEL")
    def adm_channel(call):
        if call.from_user.id != int(data.get("admin_id", -1)): return
        current = data.get("required_channel", "Yo'q")
        markup  = InlineKeyboardMarkup()
        if current != "Yo'q":
            markup.add(InlineKeyboardButton("🗑️ Kanalni o'chirish", callback_data="ADM_CHANNEL_DEL"))
        markup.add(InlineKeyboardButton("◀️ Orqaga", callback_data="ADM_BACK"))
        orders[call.from_user.id] = {"step": "adm_channel"}
        bb.edit_message_text(chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"📣 <b>Kanal obuna tekshiruvi</b>\n\n"
                 f"Hozirgi kanal: <b>{current}</b>\n\n"
                 "Yangi kanal username yozing:\n"
                 "<i>Misol: @mening_kanalim</i>\n\n"
                 "O'chirish uchun tugmani bosing:",
            reply_markup=markup, parse_mode="HTML")

    @bb.callback_query_handler(func=lambda c: c.data == "ADM_CHANNEL_DEL")
    def adm_channel_del(call):
        if call.from_user.id != int(data.get("admin_id", -1)): return
        db_live = load_db()
        if token in db_live:
            db_live[token]["required_channel"] = None
            save_db(db_live); data["required_channel"] = None
        orders.pop(call.from_user.id, None)
        bb.answer_callback_query(call.id, "✅ Kanal o'chirildi!")
        bb.edit_message_text(chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="✅ Kanal tekshiruvi o'chirildi. Endi hamma buyurtma bera oladi.")

    @bb.callback_query_handler(func=lambda c: c.data == "ADM_BACK")
    def adm_back_cb(call):
        if call.from_user.id != int(data.get("admin_id", -1)): return
        products = data.get("products",[]); ords = data.get("orders",[])
        channel  = data.get("required_channel","Yo'q") or "Yo'q"
        markup   = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(f"📦 Mahsulotlar ({len(products)})", callback_data="ADM_PRODS"))
        markup.add(InlineKeyboardButton("✏️ Ma'lumotlar",                    callback_data="ADM_INFO"))
        markup.add(InlineKeyboardButton(f"🛒 Buyurtmalar ({len(ords)})",    callback_data="ADM_ORDERS"))
        markup.add(InlineKeyboardButton("🎟️ Promo kodlar",                  callback_data="ADM_PROMOS"))
        markup.add(InlineKeyboardButton(f"📣 Kanal ({channel})",            callback_data="ADM_CHANNEL"))
        bb.edit_message_text(chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"⚙️ <b>Admin panel</b>\n🏪 {data['name']}",
            reply_markup=markup, parse_mode="HTML")

    @bb.message_handler(func=lambda m: True)
    def biz_unknown(msg):
        send_main_kb(msg.chat.id, msg.from_user.id)

    running_bots[token] = bb
    t = threading.Thread(target=bb.infinity_polling, daemon=True)
    t.start()
    print(f"🟢 {data['name']} ishga tushdi")

def reload_biz_bot(token, data):
    start_biz_bot(token, data)

def migrate_db():
    """Eski mahsulotlarga yangi maydonlarni qo'shish"""
    db      = load_db()
    changed = False
    for token, biz in db.items():
        # admin_id ni int ga o'girish
        if "admin_id" in biz and not isinstance(biz["admin_id"], int):
            try: biz["admin_id"] = int(biz["admin_id"]); changed = True
            except: pass
        for p in biz.get("products", []):
            if "id" not in p:
                p["id"] = str(uuid.uuid4())[:8]; changed = True
            if "reviews" not in p:
                p["reviews"] = []; changed = True
            if "sale_price" not in p:
                p["sale_price"] = None; changed = True
            if "sale_until" not in p:
                p["sale_until"] = None; changed = True
            if "photo_id" not in p:
                p["photo_id"] = None; changed = True
        if "promos" not in biz:
            biz["promos"] = {}; changed = True
        if "orders" not in biz:
            biz["orders"] = []; changed = True
    if changed:
        save_db(db)
        print("✅ Migratsiya bajarildi — eski ma'lumotlar yangilandi")

def load_existing_bots():
    migrate_db()
    db = load_db()
    for token, data in db.items():
        try:
            get_short(token)
            start_biz_bot(token, data)
        except Exception as e:
            print(f"❌ {data.get('name','?')}: {e}")

# ══════════════════════════════════════════════
if __name__ == "__main__":
    print("🚀 UzBiznesBot v4.1 ishga tushdi!")
    load_existing_bots()
    bot.infinity_polling()
