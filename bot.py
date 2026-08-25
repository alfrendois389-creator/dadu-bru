# bot.py
# BOT DADU DUEL — FULL FITUR
# AUTO ROLL GACOR, DEPOSIT ADMIN, QRIS, WITHDRAW, LAST WIN

import random
import sqlite3
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ==================== KONFIGURASI ====================
BOT_TOKEN = "8986690043:AAFhRUhCU6acJQ3LtTroQ7z7DjBmg4V1kFQ"
ADMIN_IDS = [8502398484]
MIN_BET = 0.2
MAX_BET = 100
WD_MIN = 10
KOIN_RATE = 1000
AUTO_ROLL_THRESHOLD = 0.2
MIN_TOTAL_BET = 0.4
FEE = 0.1
QRIS_IMAGE_PATH = "qris.png"

# ==================== DATABASE ====================
DB_NAME = "dadu.db"

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            saldo REAL DEFAULT 0,
            dana TEXT DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            amount REAL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS withdraw_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            dana TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS last_win (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            amount REAL,
            side TEXT,
            score TEXT,
            game INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS deposit_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            amount REAL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# ==================== HELPER ====================
def get_user(user_id, username):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    if not user:
        c.execute("INSERT INTO users (id, username) VALUES (?, ?)", (user_id, username))
        conn.commit()
        c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = c.fetchone()
    conn.close()
    return user

def update_saldo(user_id, amount):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET saldo = saldo + ? WHERE id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def add_history(user_id, typ, amount, desc=""):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO history (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
        (user_id, typ, amount, desc),
    )
    conn.commit()
    conn.close()

def save_last_win(user_id, username, amount, side, score):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as total FROM last_win")
    total = c.fetchone()
    game_num = total["total"] + 1
    c.execute(
        "INSERT INTO last_win (user_id, username, amount, side, score, game) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, username, amount, side, score, game_num),
    )
    conn.commit()
    conn.close()

def get_last_win():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM last_win ORDER BY created_at DESC LIMIT 1")
    res = c.fetchone()
    conn.close()
    return res

def get_all_last_win():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM last_win ORDER BY created_at DESC LIMIT 10")
    res = c.fetchall()
    conn.close()
    return res

def add_withdraw_request(user_id, amount, dana):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO withdraw_requests (user_id, amount, dana) VALUES (?, ?, ?)",
        (user_id, amount, dana),
    )
    conn.commit()
    conn.close()

def get_pending_wd():
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        SELECT w.*, u.username FROM withdraw_requests w
        JOIN users u ON w.user_id = u.id
        WHERE w.status = 'pending'
    ''')
    res = c.fetchall()
    conn.close()
    return res

# ==================== DATA TARUHAN ====================
bets = {"K": [], "B": []}
auto_roll_enabled = True
user_states = {}

# ==================== COMMANDS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_user(user.id, user.username)
    last = get_last_win()
    all_last = get_all_last_win()
    msg = f"🎲 SELAMAT DATANG {user.first_name.upper()}!\n"
    if last:
        msg += "\n𝗟𝗔𝗦𝗧 𝗪𝗜𝗡\n─────────────────\n"
        for l in all_last:
            msg += f"𝗚{l['game']} : {l['side']} {l['score']} [ {l['amount']:.1f} ]\n"
        msg += "─────────────────\n"
    msg += (
        "\n📋 PERINTAH:\n"
        "/balance - Cek saldo\n"
        "/bet K/B [jumlah] - Pasang taruhan\n"
        "/rekap - Lihat total taruhan\n"
        "/deposit [jumlah] - Minta deposit QRIS\n"
        "/withdraw [jumlah] - Request WD\n"
        "/setdana [nomor] - Simpan nomor DANA\n"
        "/lastwin - Last win terakhir\n"
        "/autoon - Nyalakan auto roll\n"
        "/autooff - Matikan auto roll\n"
        "/help - Bantuan\n\n"
        "🎯 ADMIN ONLY:\n"
        "/roll - Roll manual\n"
        "/cekwd - Lihat WD pending\n"
        "/confirm @user [jumlah] - Konfirmasi WD\n"
        "/reject @user - Tolak WD\n"
        "/confirmdeposit @user [jumlah] - Konfirmasi deposit"
    )
    await update.message.reply_text(msg)

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = get_user(user.id, user.username)
    await update.message.reply_text(
        f"💰 SALDO : {data['saldo']:.2f} KOIN\n"
        f"💵 1 KOIN = Rp {KOIN_RATE:,}\n"
        f"📌 MIN BET {MIN_BET} • WITHDRAW {WD_MIN}"
    )

async def setdana(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("❌ CONTOH: /setdana 08123456789")
        return
    dana = context.args[0]
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET dana = ? WHERE id = ?", (dana, user.id))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ NOMOR DANA: {dana}")

async def lastwin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    all_last = get_all_last_win()
    if not all_last:
        await update.message.reply_text("📭 BELUM ADA KEMENANGAN.")
        return
    msg = "𝗟𝗔𝗦𝗧 𝗪𝗜𝗡\n"
    msg += "─────────────────\n"
    for l in all_last:
        msg += f"𝗚{l['game']} : {l['side']} {l['score']} [ {l['amount']:.1f} ]\n"
    msg += "─────────────────"
    await update.message.reply_text(msg)

# ==================== BET ====================
async def bet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if len(context.args) < 2:
        await update.message.reply_text("❌ CONTOH: /bet K 0.5")
        return
    side = context.args[0].upper()
    if side not in ["K", "B"]:
        await update.message.reply_text("❌ PILIH K ATAU B!")
        return
    try:
        amount = float(context.args[1].replace(",", "."))
    except:
        await update.message.reply_text("❌ JUMLAH HARUS ANGKA!")
        return
    if amount < MIN_BET or amount > MAX_BET:
        await update.message.reply_text(f"❌ MIN {MIN_BET} / MAX {MAX_BET} KOIN!")
        return
    user_data = get_user(user.id, user.username)
    if user_data["saldo"] < amount:
        await update.message.reply_text(f"❌ SALDO: {user_data['saldo']:.2f} KOIN")
        return
    update_saldo(user.id, -amount)
    add_history(user.id, "bet", -amount, f"{side} {amount}")
    bets[side].append({"user_id": user.id, "username": user.username, "amount": amount})
    await update.message.reply_text(f"✅ TARUHAN {side} {amount:.2f} KOIN")
    total_k = sum(b["amount"] for b in bets["K"])
    total_b = sum(b["amount"] for b in bets["B"])
    total_all = total_k + total_b
    if auto_roll_enabled and total_all >= MIN_TOTAL_BET:
        selisih = abs(total_k - total_b)
        if selisih <= AUTO_ROLL_THRESHOLD:
            await update.message.reply_text(f"⚡ K {total_k:.2f} VS B {total_b:.2f} → ROLL 3 DETIK...")
            await asyncio.sleep(3)
            await auto_roll(update, context)
        else:
            await update.message.reply_text(f"📊 K {total_k:.2f} VS B {total_b:.2f} (SELISIH {selisih:.2f})")
    else:
        await update.message.reply_text(f"📊 TOTAL: {total_all:.2f} KOIN")

# ==================== AUTO ROLL ====================
async def auto_roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not bets["K"] and not bets["B"]:
        return
    total_k = sum(b["amount"] for b in bets["K"])
    total_b = sum(b["amount"] for b in bets["B"])
    
    await update.message.reply_text("🎲 M1 123")
    await asyncio.sleep(1)
    d1 = random.randint(1, 6)
    d2 = random.randint(1, 6)
    total1 = d1 + d2
    if total1 <= 3:
        hasil1 = "K"
        side1 = "KECIL"
    else:
        hasil1 = "B"
        side1 = "BESAR"
    await update.message.reply_text(f"🎲 {d1} - {d2} (TOTAL {total1}) → {side1}")
    
    await update.message.reply_text("🎲 M2 123")
    await asyncio.sleep(1)
    d3 = random.randint(1, 6)
    d4 = random.randint(1, 6)
    total2 = d3 + d4
    if total2 <= 3:
        hasil2 = "K"
        side2 = "KECIL"
    else:
        hasil2 = "B"
        side2 = "BESAR"
    await update.message.reply_text(f"🎲 {d3} - {d4} (TOTAL {total2}) → {side2}")
    
    skor = {"K": 0, "B": 0}
    if hasil1 == "K":
        skor["K"] += 1
    else:
        skor["B"] += 1
    if hasil2 == "K":
        skor["K"] += 1
    else:
        skor["B"] += 1
    
    if skor["K"] == 2:
        winner_side = "KECIL"
        result = "K"
        score = "0-2"
        d_win, d_lose = d1, d2
    elif skor["B"] == 2:
        winner_side = "BESAR"
        result = "B"
        score = "0-2"
        d_win, d_lose = d1, d2
    else:
        await update.message.reply_text("🎲 M3 123")
        await asyncio.sleep(1)
        d5 = random.randint(1, 6)
        d6 = random.randint(1, 6)
        total3 = d5 + d6
        if total3 <= 3:
            hasil3 = "K"
            side3 = "KECIL"
        else:
            hasil3 = "B"
            side3 = "BESAR"
        await update.message.reply_text(f"🎲 {d5} - {d6} (TOTAL {total3}) → {side3}")
        if hasil3 == "K":
            skor["K"] += 1
        else:
            skor["B"] += 1
        if skor["K"] > skor["B"]:
            winner_side = "KECIL"
            result = "K"
            score = "1-2"
            d_win, d_lose = d5, d6
        else:
            winner_side = "BESAR"
            result = "B"
            score = "1-2"
            d_win, d_lose = d5, d6
    
    winner_amount = total_k if result == "K" else total_b
    winner_bets = bets["K"] if result == "K" else bets["B"]
    pot = winner_amount * (1 - FEE)
    
    msg = f"DUEL KB DADUX    ALL ROLE\n"
    msg += f"HASIL BO3: {winner_side} ({result}) {score}\n"
    msg += f"DADU: {d_win} - {d_lose}\n"
    msg += f"{winner_side} {score}!\n\n"
    msg += f"💰 POT: {winner_amount:.2f} KOIN\n"
    msg += f"🏆 {len(winner_bets)} PEMENANG\n\n"
    
    for b in winner_bets:
        share = (b["amount"] / winner_amount) * pot
        update_saldo(b["user_id"], share)
        add_history(b["user_id"], "win", share, f"Win {winner_side} {score}")
        msg += f"  @{b['username']} +{share:.2f} KOIN\n"
    
    await update.message.reply_text(msg)
    
    if winner_bets:
        w = winner_bets[0]
        save_last_win(w["user_id"], w["username"], w["amount"], winner_side, score)
    
    bets["K"].clear()
    bets["B"].clear()

async def roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ HANYA ADMIN!")
        return
    await auto_roll(update, context)

# ==================== DEPOSIT ====================
async def deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_admin = user.id in ADMIN_IDS

    # ============ ADMIN DEPOSIT KE USER ============
    if is_admin and len(context.args) >= 2:
        username = context.args[0].replace("@", "")
        try:
            amount = float(context.args[1].replace(",", "."))
        except:
            await update.message.reply_text("❌ JUMLAH HARUS ANGKA!")
            return

        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username = ?", (username,))
        target = c.fetchone()
        conn.close()

        if not target:
            await update.message.reply_text(f"❌ @{username} TIDAK DITEMUKAN!")
            return

        update_saldo(target['id'], amount)
        add_history(target['id'], "deposit", amount, f"Admin deposit {amount}")

        await update.message.reply_text(f"✅ DEPOSIT @{username} +{amount:.2f} KOIN BERHASIL!")

        try:
            await context.bot.send_message(
                target['id'],
                f"✅ DEPOSIT BERHASIL!\n"
                f"👤 @{username}\n"
                f"💰 +{amount:.2f} KOIN (Rp {amount*KOIN_RATE:,.0f})"
            )
        except:
            pass
        return

    # ============ USER DEPOSIT QRIS ============
    if len(context.args) < 1:
        await update.message.reply_text("❌ CONTOH: /deposit 0.5")
        return

    try:
        amount = float(context.args[0].replace(",", "."))
    except:
        await update.message.reply_text("❌ JUMLAH HARUS ANGKA!")
        return

    if amount < MIN_BET:
        await update.message.reply_text(f"❌ MIN DEPOSIT {MIN_BET} KOIN!")
        return

    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO deposit_requests (user_id, username, amount, status) VALUES (?, ?, ?, 'pending')",
        (user.id, user.username, amount)
    )
    dep_id = c.lastrowid
    conn.commit()
    conn.close()

    user_states[user.id] = {"deposit_id": dep_id, "amount": amount}

    keyboard = [[InlineKeyboardButton("📤 KIRIM BUKTI TRANSFER", callback_data=f"kirim_bukti_{dep_id}")]]
    msg = f"💳 BAYAR KE QRIS\n💰 {amount} KOIN (Rp {amount*KOIN_RATE:,.0f})\n📌 KLIK TOMBOL SETELAH TRANSFER!"
    try:
        with open(QRIS_IMAGE_PATH, "rb") as f:
            await update.message.reply_photo(f, caption=msg, reply_markup=InlineKeyboardMarkup(keyboard))
    except:
        await update.message.reply_text(msg + "\n\n⚠️ QRIS TIDAK DITEMUKAN!")

async def kirim_bukti_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        dep_id = int(query.data.split("_")[2])
    except:
        await query.edit_message_text("❌ DATA TIDAK VALID!")
        return

    user = query.from_user

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM deposit_requests WHERE id = ? AND status = 'pending'", (dep_id,))
    dep = c.fetchone()
    conn.close()

    if not dep:
        await query.edit_message_text("❌ TIDAK ADA DEPOSIT PENDING!")
        return

    await query.edit_message_text(
        f"📤 KIRIM FOTO BUKTI TRANSFER\n"
        f"👤 @{user.username}\n"
        f"💰 {dep['amount']} KOIN (Rp {dep['amount'] * KOIN_RATE:,.0f})"
    )

    user_states[user.id] = {"deposit_id": dep['id'], "amount": dep['amount']}

async def handle_bukti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    state = user_states.get(user.id, {})
    dep_id = state.get("deposit_id")

    if not dep_id:
        await update.message.reply_text("❌ /DEPOSIT DULU!")
        return

    if not update.message.photo:
        await update.message.reply_text("❌ KIRIM FOTO!")
        return

    photo = update.message.photo[-1].file_id

    for admin_id in ADMIN_IDS:
        await context.bot.send_photo(
            admin_id,
            photo,
            caption=(
                f"📥 BUKTI TRANSFER\n"
                f"👤 USERNAME: @{user.username}\n"
                f"🆔 ID: {user.id}\n"
                f"💰 NOMINAL: {state['amount']} KOIN (Rp {state['amount']*KOIN_RATE:,.0f})\n"
                f"📌 KONFIRMASI: /confirmdeposit @{user.username} {state['amount']}"
            )
        )

    await update.message.reply_text(
        f"✅ BUKTI TERKIRIM KE ADMIN!\n"
        f"👤 @{user.username}\n"
        f"💰 {state['amount']} KOIN\n"
        f"⏳ TUNGGU KONFIRMASI ADMIN."
    )

    conn = get_db()
    c = conn.cursor()
    c.execute(
        "UPDATE deposit_requests SET status = 'waiting_confirmation' WHERE id = ?",
        (dep_id,)
    )
    conn.commit()
    conn.close()

    user_states[user.id] = {}

async def confirmdeposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ HANYA ADMIN!")
        return

    if len(context.args) < 2:
        await update.message.reply_text("❌ /CONFIRMDEPOSIT @USERNAME 0.5")
        return

    username = context.args[0].replace("@", "")
    try:
        amount = float(context.args[1].replace(",", "."))
    except:
        try:
            amount = int(context.args[1])
        except:
            await update.message.reply_text("❌ JUMLAH HARUS ANGKA!")
            return

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = c.fetchone()

    if not user:
        await update.message.reply_text(f"❌ @{username} TIDAK DITEMUKAN!")
        conn.close()
        return

    c.execute(
        "UPDATE deposit_requests SET status = 'done' WHERE user_id = ? AND status = 'waiting_confirmation'",
        (user['id'],)
    )
    conn.commit()
    conn.close()

    update_saldo(user['id'], amount)
    add_history(user['id'], "deposit", amount, f"Deposit {amount}")

    await update.message.reply_text(f"✅ DEPOSIT @{username} +{amount:.2f} KOIN BERHASIL!")

    try:
        await context.bot.send_message(
            user['id'],
            f"✅ DEPOSIT BERHASIL!\n"
            f"👤 @{username}\n"
            f"💰 +{amount:.2f} KOIN (Rp {amount*KOIN_RATE:,.0f})"
        )
    except:
        pass

# ==================== WITHDRAW ====================
async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if len(context.args) < 1:
        await update.message.reply_text("❌ /withdraw 0.5")
        return
    try:
        amount = float(context.args[0].replace(",", "."))
    except:
        await update.message.reply_text("❌ JUMLAH HARUS ANGKA!")
        return
    if amount < WD_MIN:
        await update.message.reply_text(f"❌ MIN WD {WD_MIN} KOIN!")
        return
    user_data = get_user(user.id, user.username)
    if user_data["saldo"] < amount:
        await update.message.reply_text(f"❌ SALDO: {user_data['saldo']:.2f}")
        return
    if not user_data["dana"]:
        await update.message.reply_text("❌ /setdana DULU!")
        return
    add_withdraw_request(user.id, amount, user_data["dana"])
    await update.message.reply_text(f"✅ WD {amount:.2f} KOIN → ADMIN!")

async def cekwd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ HANYA ADMIN!")
        return
    pending = get_pending_wd()
    if not pending:
        await update.message.reply_text("✅ TIDAK ADA WD PENDING.")
        return
    msg = "📤 LIST WD PENDING\n\n"
    for w in pending:
        msg += f"@{w['username']} - {w['amount']:.2f} KOIN\nDANA: {w['dana']}\nID: {w['id']}\n---\n"
    await update.message.reply_text(msg)

async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ HANYA ADMIN!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /confirm @user 0.5")
        return
    username = context.args[0].replace("@", "")
    try:
        amount = float(context.args[1].replace(",", "."))
    except:
        try:
            amount = int(context.args[1])
        except:
            await update.message.reply_text("❌ JUMLAH HARUS ANGKA!")
            return
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    if not user:
        await update.message.reply_text(f"❌ @{username} TIDAK DITEMUKAN!")
        conn.close()
        return
    c.execute("SELECT * FROM withdraw_requests WHERE user_id = ? AND status = 'pending'", (user["id"],))
    wd = c.fetchone()
    if not wd:
        await update.message.reply_text(f"❌ TIDAK ADA WD PENDING UNTUK @{username}")
        conn.close()
        return
    c.execute("UPDATE withdraw_requests SET status = 'done' WHERE id = ?", (wd["id"],))
    conn.commit()
    conn.close()
    update_saldo(user["id"], -wd["amount"])
    add_history(user["id"], "withdraw", -wd["amount"], f"WD {wd['amount']}")
    await update.message.reply_text(f"✅ WD @{username} {wd['amount']:.2f} KOIN SELESAI!")

async def reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ HANYA ADMIN!")
        return
    if len(context.args) < 1:
        await update.message.reply_text("❌ /reject @user")
        return
    username = context.args[0].replace("@", "")
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    if not user:
        await update.message.reply_text(f"❌ @{username} TIDAK DITEMUKAN!")
        conn.close()
        return
    c.execute("SELECT * FROM withdraw_requests WHERE user_id = ? AND status = 'pending'", (user["id"],))
    wd = c.fetchone()
    if not wd:
        await update.message.reply_text(f"❌ TIDAK ADA WD PENDING UNTUK @{username}")
        conn.close()
        return
    c.execute("UPDATE withdraw_requests SET status = 'rejected' WHERE id = ?", (wd["id"],))
    conn.commit()
    conn.close()
    update_saldo(user["id"], wd["amount"])
    add_history(user["id"], "reject", wd["amount"], f"WD ditolak {wd['amount']}")
    await update.message.reply_text(f"❌ WD @{username} {wd['amount']:.2f} KOIN DITOLAK!")

# ==================== REKAP ====================
async def rekap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_k = sum(b["amount"] for b in bets["K"])
    total_b = sum(b["amount"] for b in bets["B"])
    msg = "📊 REKAP TARUHAN\n\n🔵 KECIL (K):\n"
    if bets["K"]:
        for b in bets["K"]:
            msg += f"  @{b['username']} {b['amount']:.2f}\n"
        msg += f"  TOTAL: {total_k:.2f}\n\n"
    else:
        msg += "  (KOSONG)\n\n"
    msg += "🔴 BESAR (B):\n"
    if bets["B"]:
        for b in bets["B"]:
            msg += f"  @{b['username']} {b['amount']:.2f}\n"
        msg += f"  TOTAL: {total_b:.2f}\n\n"
    else:
        msg += "  (KOSONG)\n\n"
    msg += f"TOTAL SEMUA: {total_k + total_b:.2f} KOIN"
    await update.message.reply_text(msg)

# ==================== AUTO ROLL ON/OFF ====================
async def autoon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global auto_roll_enabled
    auto_roll_enabled = True
    await update.message.reply_text("✅ AUTO ROLL DIAKTIFKAN!")

async def autooff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global auto_roll_enabled
    auto_roll_enabled = False
    await update.message.reply_text("❌ AUTO ROLL DIMATIKAN!")

# ==================== MAIN ====================
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("setdana", setdana))
    app.add_handler(CommandHandler("lastwin", lastwin))
    app.add_handler(CommandHandler("bet", bet))
    app.add_handler(CommandHandler("rekap", rekap))
    app.add_handler(CommandHandler("roll", roll))
    app.add_handler(CommandHandler("deposit", deposit))
    app.add_handler(CommandHandler("withdraw", withdraw))
    app.add_handler(CommandHandler("cekwd", cekwd))
    app.add_handler(CommandHandler("confirm", confirm))
    app.add_handler(CommandHandler("reject", reject))
    app.add_handler(CommandHandler("confirmdeposit", confirmdeposit))
    app.add_handler(CommandHandler("autoon", autoon))
    app.add_handler(CommandHandler("autooff", autooff))
    app.add_handler(CallbackQueryHandler(kirim_bukti_callback, pattern="kirim_bukti_"))
    app.add_handler(MessageHandler(filters.PHOTO, handle_bukti))

    print("🤖 BOT DADU BERJALAN...")
    app.run_polling()

if __name__ == "__main__":
    main()
def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            saldo REAL DEFAULT 0,
            dana TEXT DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            amount REAL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS withdraw_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            dana TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS last_win (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            amount REAL,
            side TEXT,
            score TEXT,
            game INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS deposit_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            amount REAL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# ==================== HELPER ====================
def get_user(user_id, username):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    if not user:
        c.execute("INSERT INTO users (id, username) VALUES (?, ?)", (user_id, username))
        conn.commit()
        c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = c.fetchone()
    conn.close()
    return user

def update_saldo(user_id, amount):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET saldo = saldo + ? WHERE id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def add_history(user_id, typ, amount, desc=""):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO history (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
        (user_id, typ, amount, desc),
    )
    conn.commit()
    conn.close()

def save_last_win(user_id, username, amount, side, score):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as total FROM last_win")
    total = c.fetchone()
    game_num = total["total"] + 1
    c.execute(
        "INSERT INTO last_win (user_id, username, amount, side, score, game) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, username, amount, side, score, game_num),
    )
    conn.commit()
    conn.close()

def get_last_win():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM last_win ORDER BY created_at DESC LIMIT 1")
    res = c.fetchone()
    conn.close()
    return res

def get_all_last_win():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM last_win ORDER BY created_at DESC LIMIT 10")
    res = c.fetchall()
    conn.close()
    return res

def add_withdraw_request(user_id, amount, dana):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO withdraw_requests (user_id, amount, dana) VALUES (?, ?, ?)",
        (user_id, amount, dana),
    )
    conn.commit()
    conn.close()

def get_pending_wd():
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        SELECT w.*, u.username FROM withdraw_requests w
        JOIN users u ON w.user_id = u.id
        WHERE w.status = 'pending'
    ''')
    res = c.fetchall()
    conn.close()
    return res

# ==================== DATA TARUHAN ====================
bets = {"K": [], "B": []}
auto_roll_enabled = True
user_states = {}

# ==================== COMMANDS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_user(user.id, user.username)
    last = get_last_win()
    all_last = get_all_last_win()
    msg = f"🎲 SELAMAT DATANG {user.first_name.upper()}!\n"
    if last:
        msg += "\n𝗟𝗔𝗦𝗧 𝗪𝗜𝗡\n─────────────────\n"
        for l in all_last:
            msg += f"𝗚{l['game']} : {l['side']} {l['score']} [ {l['amount']:.1f} ]\n"
        msg += "─────────────────\n"
    msg += (
        "\n📋 PERINTAH:\n"
        "/balance - Cek saldo\n"
        "/bet K/B [jumlah] - Pasang taruhan\n"
        "/rekap - Lihat total taruhan\n"
        "/deposit [jumlah] - Minta deposit QRIS\n"
        "/withdraw [jumlah] - Request WD\n"
        "/setdana [nomor] - Simpan nomor DANA\n"
        "/lastwin - Last win terakhir\n"
        "/autoon - Nyalakan auto roll\n"
        "/autooff - Matikan auto roll\n"
        "/help - Bantuan\n\n"
        "🎯 ADMIN ONLY:\n"
        "/roll - Roll manual\n"
        "/cekwd - Lihat WD pending\n"
        "/confirm @user [jumlah] - Konfirmasi WD\n"
        "/reject @user - Tolak WD\n"
        "/confirmdeposit @user [jumlah] - Konfirmasi deposit"
    )
    await update.message.reply_text(msg)

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = get_user(user.id, user.username)
    await update.message.reply_text(
        f"💰 SALDO : {data['saldo']:.2f} KOIN\n"
        f"💵 1 KOIN = Rp {KOIN_RATE:,}\n"
        f"📌 MIN BET {MIN_BET} • WITHDRAW {WD_MIN}"
    )

async def setdana(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("❌ CONTOH: /setdana 08123456789")
        return
    dana = context.args[0]
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET dana = ? WHERE id = ?", (dana, user.id))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ NOMOR DANA: {dana}")

async def lastwin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    all_last = get_all_last_win()
    if not all_last:
        await update.message.reply_text("📭 BELUM ADA KEMENANGAN.")
        return
    msg = "𝗟𝗔𝗦𝗧 𝗪𝗜𝗡\n"
    msg += "─────────────────\n"
    for l in all_last:
        msg += f"𝗚{l['game']} : {l['side']} {l['score']} [ {l['amount']:.1f} ]\n"
    msg += "─────────────────"
    await update.message.reply_text(msg)

# ==================== BET ====================
async def bet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if len(context.args) < 2:
        await update.message.reply_text("❌ CONTOH: /bet K 0.5")
        return
    side = context.args[0].upper()
    if side not in ["K", "B"]:
        await update.message.reply_text("❌ PILIH K ATAU B!")
        return
    try:
        amount = float(context.args[1].replace(",", "."))
    except:
        await update.message.reply_text("❌ JUMLAH HARUS ANGKA!")
        return
    if amount < MIN_BET or amount > MAX_BET:
        await update.message.reply_text(f"❌ MIN {MIN_BET} / MAX {MAX_BET} KOIN!")
        return
    user_data = get_user(user.id, user.username)
    if user_data["saldo"] < amount:
        await update.message.reply_text(f"❌ SALDO: {user_data['saldo']:.2f} KOIN")
        return
    update_saldo(user.id, -amount)
    add_history(user.id, "bet", -amount, f"{side} {amount}")
    bets[side].append({"user_id": user.id, "username": user.username, "amount": amount})
    await update.message.reply_text(f"✅ TARUHAN {side} {amount:.2f} KOIN")
    total_k = sum(b["amount"] for b in bets["K"])
    total_b = sum(b["amount"] for b in bets["B"])
    total_all = total_k + total_b
    if auto_roll_enabled and total_all >= MIN_TOTAL_BET:
        selisih = abs(total_k - total_b)
        if selisih <= AUTO_ROLL_THRESHOLD:
            await update.message.reply_text(f"⚡ K {total_k:.2f} VS B {total_b:.2f} → ROLL 3 DETIK...")
            await asyncio.sleep(3)
            await auto_roll(update, context)
        else:
            await update.message.reply_text(f"📊 K {total_k:.2f} VS B {total_b:.2f} (SELISIH {selisih:.2f})")
    else:
        await update.message.reply_text(f"📊 TOTAL: {total_all:.2f} KOIN")

# ==================== AUTO ROLL ====================
async def auto_roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not bets["K"] and not bets["B"]:
        return
    total_k = sum(b["amount"] for b in bets["K"])
    total_b = sum(b["amount"] for b in bets["B"])
    
    await update.message.reply_text("🎲 M1 123")
    await asyncio.sleep(1)
    d1 = random.randint(1, 6)
    d2 = random.randint(1, 6)
    total1 = d1 + d2
    if total1 <= 3:
        hasil1 = "K"
        side1 = "KECIL"
    else:
        hasil1 = "B"
        side1 = "BESAR"
    await update.message.reply_text(f"🎲 {d1} - {d2} (TOTAL {total1}) → {side1}")
    
    await update.message.reply_text("🎲 M2 123")
    await asyncio.sleep(1)
    d3 = random.randint(1, 6)
    d4 = random.randint(1, 6)
    total2 = d3 + d4
    if total2 <= 3:
        hasil2 = "K"
        side2 = "KECIL"
    else:
        hasil2 = "B"
        side2 = "BESAR"
    await update.message.reply_text(f"🎲 {d3} - {d4} (TOTAL {total2}) → {side2}")
    
    skor = {"K": 0, "B": 0}
    if hasil1 == "K":
        skor["K"] += 1
    else:
        skor["B"] += 1
    if hasil2 == "K":
        skor["K"] += 1
    else:
        skor["B"] += 1
    
    if skor["K"] == 2:
        winner_side = "KECIL"
        result = "K"
        score = "0-2"
        d_win, d_lose = d1, d2
    elif skor["B"] == 2:
        winner_side = "BESAR"
        result = "B"
        score = "0-2"
        d_win, d_lose = d1, d2
    else:
        await update.message.reply_text("🎲 M3 123")
        await asyncio.sleep(1)
        d5 = random.randint(1, 6)
        d6 = random.randint(1, 6)
        total3 = d5 + d6
        if total3 <= 3:
            hasil3 = "K"
            side3 = "KECIL"
        else:
            hasil3 = "B"
            side3 = "BESAR"
        await update.message.reply_text(f"🎲 {d5} - {d6} (TOTAL {total3}) → {side3}")
        if hasil3 == "K":
            skor["K"] += 1
        else:
            skor["B"] += 1
        if skor["K"] > skor["B"]:
            winner_side = "KECIL"
            result = "K"
            score = "1-2"
            d_win, d_lose = d5, d6
        else:
            winner_side = "BESAR"
            result = "B"
            score = "1-2"
            d_win, d_lose = d5, d6
    
    winner_amount = total_k if result == "K" else total_b
    winner_bets = bets["K"] if result == "K" else bets["B"]
    pot = winner_amount * (1 - FEE)
    
    msg = f"DUEL KB DADUX    ALL ROLE\n"
    msg += f"HASIL BO3: {winner_side} ({result}) {score}\n"
    msg += f"DADU: {d_win} - {d_lose}\n"
    msg += f"{winner_side} {score}!\n\n"
    msg += f"💰 POT: {winner_amount:.2f} KOIN\n"
    msg += f"🏆 {len(winner_bets)} PEMENANG\n\n"
    
    for b in winner_bets:
        share = (b["amount"] / winner_amount) * pot
        update_saldo(b["user_id"], share)
        add_history(b["user_id"], "win", share, f"Win {winner_side} {score}")
        msg += f"  @{b['username']} +{share:.2f} KOIN\n"
    
    await update.message.reply_text(msg)
    
    if winner_bets:
        w = winner_bets[0]
        save_last_win(w["user_id"], w["username"], w["amount"], winner_side, score)
    
    bets["K"].clear()
    bets["B"].clear()

async def roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ HANYA ADMIN!")
        return
    await auto_roll(update, context)

# ==================== DEPOSIT ====================
async def deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_admin = user.id in ADMIN_IDS
    
    # ============ ADMIN DEPOSIT KE USER ============
    if is_admin and len(context.args) >= 2:
        username = context.args[0].replace("@", "")
        try:
            amount = float(context.args[1].replace(",", "."))
        except:
            await update.message.reply_text("❌ JUMLAH HARUS ANGKA!")
            return
        
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username = ?", (username,))
        target = c.fetchone()
        conn.close()
        
        if not target:
            await update.message.reply_text(f"❌ @{username} TIDAK DITEMUKAN!")
            return
        
        update_saldo(target['id'], amount)
        add_history(target['id'], "deposit", amount, f"Admin deposit {amount}")
        
        await update.message.reply_text(f"✅ DEPOSIT @{username} +{amount:.2f} KOIN BERHASIL!")
        
        try:
            await context.bot.send_message(
                target['id'],
                f"✅ DEPOSIT BERHASIL!\n"
                f"👤 @{username}\n"
                f"💰 +{amount:.2f} KOIN (Rp {amount*KOIN_RATE:,.0f})"
            )
        except:
            pass
        return
    
    # ============ USER DEPOSIT QRIS ============
    if len(context.args) < 1:
        await update.message.reply_text("❌ CONTOH: /deposit 0.5")
        return
    
    try:
        amount = float(context.args[0].replace(",", "."))
    except:
        await update.message.reply_text("❌ JUMLAH HARUS ANGKA!")
        return
    
    if amount < MIN_BET:
        await update.message.reply_text(f"❌ MIN DEPOSIT {MIN_BET} KOIN!")
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO deposit_requests (user_id, username, amount) VALUES (?, ?, ?)",
        (user.id, user.username, amount)
    )
    conn.commit()
    conn.close()
    
    keyboard = [[InlineKeyboardButton("📤 KIRIM BUKTI TRANSFER", callback_data=f"kirim_bukti_{user.id}")]]
    msg = f"💳 BAYAR KE QRIS\n💰 {amount} KOIN (Rp {amount*KOIN_RATE:,.0f})\n📌 KLIK TOMBOL SETELAH TRANSFER!"
    try:
        with open(QRIS_IMAGE_PATH, "rb") as f:
            await update.message.reply_photo(f, caption=msg, reply_markup=InlineKeyboardMarkup(keyboard))
    except:
        await update.message.reply_text(msg + "\n\n⚠️ QRIS TIDAK DITEMUKAN!")

async def kirim_bukti_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        user_id = int(query.data.split("_")[2])
    except:
        await query.edit_message_text("❌ DATA TIDAK VALID!")
        return

    user = query.from_user

    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM deposit_requests WHERE user_id = ? AND status = 'pending' ORDER BY created_at DESC LIMIT 1",
        (user_id,)
    )
    dep = c.fetchone()
    conn.close()

    if not dep:
        await query.edit_message_text("❌ TIDAK ADA DEPOSIT PENDING!")
        return

    await query.edit_message_text(
        f"📤 KIRIM FOTO BUKTI TRANSFER\n"
        f"👤 @{user.username}\n"
        f"💰 {dep['amount']} KOIN (Rp {dep['amount'] * KOIN_RATE:,.0f})"
    )

    user_states[user.id] = {"deposit_id": dep['id'], "amount": dep['amount']}
    
async def handle_bukti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    state = user_states.get(user.id, {})
    
    if not state.get("deposit_id"):
        await update.message.reply_text("❌ /DEPOSIT DULU!")
        return
    
    if not update.message.photo:
        await update.message.reply_text("❌ KIRIM FOTO!")
        return
    
    photo = update.message.photo[-1].file_id
    
    for admin_id in ADMIN_IDS:
        await context.bot.send_photo(
            admin_id,
            photo,
            caption=(
                f"📥 BUKTI TRANSFER\n"
                f"👤 USERNAME: @{user.username}\n"
                f"🆔 ID: {user.id}\n"
                f"💰 NOMINAL: {state['amount']} KOIN (Rp {state['amount']*KOIN_RATE:,.0f})\n"
                f"📌 KONFIRMASI: /confirmdeposit @{user.username} {state['amount']}"
            )
        )
    
    await update.message.reply_text(
        f"✅ BUKTI TERKIRIM KE ADMIN!\n"
        f"👤 @{user.username}\n"
        f"💰 {state['amount']} KOIN\n"
        f"⏳ TUNGGU KONFIRMASI ADMIN."
    )
    
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "UPDATE deposit_requests SET status = 'waiting_confirmation' WHERE id = ?",
        (state['deposit_id'],)
    )
    conn.commit()
    conn.close()
    
    user_states[user.id] = {}

async def confirmdeposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ HANYA ADMIN!")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ /CONFIRMDEPOSIT @USERNAME 0.5")
        return
    
    username = context.args[0].replace("@", "")
    try:
        amount = float(context.args[1].replace(",", "."))
    except:
        try:
            amount = int(context.args[1])
        except:
            await update.message.reply_text("❌ JUMLAH HARUS ANGKA!")
            return
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    
    if not user:
        await update.message.reply_text(f"❌ @{username} TIDAK DITEMUKAN!")
        conn.close()
        return
    
    c.execute(
        "UPDATE deposit_requests SET status = 'done' WHERE user_id = ? AND status = 'waiting_confirmation'",
        (user['id'],)
    )
    conn.commit()
    conn.close()
    
    update_saldo(user['id'], amount)
    add_history(user['id'], "deposit", amount, f"Deposit {amount}")
    
    await update.message.reply_text(f"✅ DEPOSIT @{username} +{amount:.2f} KOIN BERHASIL!")
    
    try:
        await context.bot.send_message(
            user['id'],
            f"✅ DEPOSIT BERHASIL!\n"
            f"👤 @{username}\n"
            f"💰 +{amount:.2f} KOIN (Rp {amount*KOIN_RATE:,.0f})"
        )
    except:
        pass

# ==================== WITHDRAW ====================
async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if len(context.args) < 1:
        await update.message.reply_text("❌ /withdraw 0.5")
        return
    try:
        amount = float(context.args[0].replace(",", "."))
    except:
        await update.message.reply_text("❌ JUMLAH HARUS ANGKA!")
        return
    if amount < WD_MIN:
        await update.message.reply_text(f"❌ MIN WD {WD_MIN} KOIN!")
        return
    user_data = get_user(user.id, user.username)
    if user_data["saldo"] < amount:
        await update.message.reply_text(f"❌ SALDO: {user_data['saldo']:.2f}")
        return
    if not user_data["dana"]:
        await update.message.reply_text("❌ /setdana DULU!")
        return
    add_withdraw_request(user.id, amount, user_data["dana"])
    await update.message.reply_text(f"✅ WD {amount:.2f} KOIN → ADMIN!")

async def cekwd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ HANYA ADMIN!")
        return
    pending = get_pending_wd()
    if not pending:
        await update.message.reply_text("✅ TIDAK ADA WD PENDING.")
        return
    msg = "📤 LIST WD PENDING\n\n"
    for w in pending:
        msg += f"@{w['username']} - {w['amount']:.2f} KOIN\nDANA: {w['dana']}\nID: {w['id']}\n---\n"
    await update.message.reply_text(msg)

async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ HANYA ADMIN!")
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ /confirm @user 0.5")
        return
    username = context.args[0].replace("@", "")
    try:
        amount = float(context.args[1].replace(",", "."))
    except:
        try:
            amount = int(context.args[1])
        except:
            await update.message.reply_text("❌ JUMLAH HARUS ANGKA!")
            return
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    if not user:
        await update.message.reply_text(f"❌ @{username} TIDAK DITEMUKAN!")
        conn.close()
        return
    c.execute("SELECT * FROM withdraw_requests WHERE user_id = ? AND status = 'pending'", (user["id"],))
    wd = c.fetchone()
    if not wd:
        await update.message.reply_text(f"❌ TIDAK ADA WD PENDING UNTUK @{username}")
        conn.close()
        return
    c.execute("UPDATE withdraw_requests SET status = 'done' WHERE id = ?", (wd["id"],))
    conn.commit()
    conn.close()
    update_saldo(user["id"], -wd["amount"])
    add_history(user["id"], "withdraw", -wd["amount"], f"WD {wd['amount']}")
    await update.message.reply_text(f"✅ WD @{username} {wd['amount']:.2f} KOIN SELESAI!")

async def reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ HANYA ADMIN!")
        return
    if len(context.args) < 1:
        await update.message.reply_text("❌ /reject @user")
        return
    username = context.args[0].replace("@", "")
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    if not user:
        await update.message.reply_text(f"❌ @{username} TIDAK DITEMUKAN!")
        conn.close()
        return
    c.execute("SELECT * FROM withdraw_requests WHERE user_id = ? AND status = 'pending'", (user["id"],))
    wd = c.fetchone()
    if not wd:
        await update.message.reply_text(f"❌ TIDAK ADA WD PENDING UNTUK @{username}")
        conn.close()
        return
    c.execute("UPDATE withdraw_requests SET status = 'rejected' WHERE id = ?", (wd["id"],))
    conn.commit()
    conn.close()
    update_saldo(user["id"], wd["amount"])
    add_history(user["id"], "reject", wd["amount"], f"WD ditolak {wd['amount']}")
    await update.message.reply_text(f"❌ WD @{username} {wd['amount']:.2f} KOIN DITOLAK!")

# ==================== REKAP ====================
async def rekap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_k = sum(b["amount"] for b in bets["K"])
    total_b = sum(b["amount"] for b in bets["B"])
    msg = "📊 REKAP TARUHAN\n\n🔵 KECIL (K):\n"
    if bets["K"]:
        for b in bets["K"]:
            msg += f"  @{b['username']} {b['amount']:.2f}\n"
        msg += f"  TOTAL: {total_k:.2f}\n\n"
    else:
        msg += "  (KOSONG)\n\n"
    msg += "🔴 BESAR (B):\n"
    if bets["B"]:
        for b in bets["B"]:
            msg += f"  @{b['username']} {b['amount']:.2f}\n"
        msg += f"  TOTAL: {total_b:.2f}\n\n"
    else:
        msg += "  (KOSONG)\n\n"
    msg += f"TOTAL SEMUA: {total_k + total_b:.2f} KOIN"
    await update.message.reply_text(msg)

# ==================== AUTO ROLL ON/OFF ====================
async def autoon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global auto_roll_enabled
    auto_roll_enabled = True
    await update.message.reply_text("✅ AUTO ROLL DIAKTIFKAN!")

async def autooff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global auto_roll_enabled
    auto_roll_enabled = False
    await update.message.reply_text("❌ AUTO ROLL DIMATIKAN!")

# ==================== MAIN ====================
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("setdana", setdana))
    app.add_handler(CommandHandler("lastwin", lastwin))
    app.add_handler(CommandHandler("bet", bet))
    app.add_handler(CommandHandler("rekap", rekap))
    app.add_handler(CommandHandler("roll", roll))
    app.add_handler(CommandHandler("deposit", deposit))
    app.add_handler(CommandHandler("withdraw", withdraw))
    app.add_handler(CommandHandler("cekwd", cekwd))
    app.add_handler(CommandHandler("confirm", confirm))
    app.add_handler(CommandHandler("reject", reject))
    app.add_handler(CommandHandler("confirmdeposit", confirmdeposit))
    app.add_handler(CommandHandler("autoon", autoon))
    app.add_handler(CommandHandler("autooff", autooff))
    app.add_handler(CallbackQueryHandler(kirim_bukti_callback, pattern="kirim_bukti_"))
    app.add_handler(MessageHandler(filters.PHOTO, handle_bukti))
    
    print("🤖 BOT DADU BERJALAN...")
    app.run_polling()

if __name__ == "__main__":
    main()
