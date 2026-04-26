import os
import json
import logging
import asyncio
from datetime import datetime, time
import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GMAIL_TOKEN = os.environ.get("GMAIL_TOKEN", "")

MEMORY_FILE = "memory.json"
TASKS_FILE = "tasks.json"

# ─── זיכרון ומשימות ────────────────────────────────────────────

def load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_memory():
    return load_json(MEMORY_FILE, {"facts": [], "conversation": []})

def save_memory(mem):
    save_json(MEMORY_FILE, mem)

def get_tasks():
    return load_json(TASKS_FILE, [])

def save_tasks(tasks):
    save_json(TASKS_FILE, tasks)

# ─── System Prompt ──────────────────────────────────────────────

def build_system_prompt():
    mem = get_memory()
    tasks = get_tasks()
    now = datetime.now().strftime("%A, %d/%m/%Y %H:%M")

    facts_text = "\n".join(f"- {f}" for f in mem["facts"]) if mem["facts"] else "אין עדיין"
    open_tasks = [t for t in tasks if not t.get("done")]
    tasks_text = "\n".join(f"- [{t['priority']}] {t['text']}" for t in open_tasks) if open_tasks else "אין משימות פתוחות"

    return f"""אתה שימי-בוט — העוזר האישי החכם של שימי (לירן לין).
התאריך והשעה עכשיו: {now}

═══ מה שאתה יודע על שימי ═══
- עצמאי בתחום AI קריאייטיב (וידאו, אנימציה, תוכן)
- גר בנס ציונה, עובר דירה באוגוסט
- נשוי לסיון, יש לו ילדים
- יש לו ADHD — אוהב קצר, ברור, ישיר
- עובד עם: Sora, Kling, ComfyUI, Claude, Midjourney

═══ זיכרון אישי ═══
{facts_text}

═══ משימות פתוחות ═══
{tasks_text}

═══ כללים ═══
- דבר תמיד בעברית
- תגובות קצרות (3-4 משפטים מקסימום)
- טון חברי, ישיר, לא פורמלי
- אם מישהו אומר לך לזכור משהו — ענה עם [REMEMBER: הטקסט]
- אם מישהו מוסיף משימה — ענה עם [TASK: הטקסט | עדיפות: גבוהה/בינונית/נמוכה]
- אם מישהו מסמן משימה כבוצעת — ענה עם [DONE: מספר המשימה]
- אם מישהו מבקש סיכום מיילים — ענה עם [GMAIL]"""

# ─── Claude API ─────────────────────────────────────────────────

conversation_history = {}

async def call_claude(user_id: int, user_message: str) -> str:
    if user_id not in conversation_history:
        conversation_history[user_id] = []

    conversation_history[user_id].append({"role": "user", "content": user_message})
    if len(conversation_history[user_id]) > 20:
        conversation_history[user_id] = conversation_history[user_id][-20:]

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 500,
                "system": build_system_prompt(),
                "messages": conversation_history[user_id]
            }
        )
        response.raise_for_status()
        data = response.json()
        assistant_message = data["content"][0]["text"]

    conversation_history[user_id].append({"role": "assistant", "content": assistant_message})
    return assistant_message

# ─── עיבוד תגובות חכמות ─────────────────────────────────────────

def process_response(response: str) -> str:
    """מעבד תגי action מהתגובה ומבצע אותם"""

    # זיכרון
    if "[REMEMBER:" in response:
        start = response.index("[REMEMBER:") + 10
        end = response.index("]", start)
        fact = response[start:end].strip()
        mem = get_memory()
        mem["facts"].append(fact)
        save_memory(mem)
        response = response.replace(f"[REMEMBER:{fact}]", "✅ זכרתי!")
        response = response.replace(f"[REMEMBER: {fact}]", "✅ זכרתי!")

    # הוספת משימה
    if "[TASK:" in response:
        start = response.index("[TASK:") + 6
        end = response.index("]", start)
        task_raw = response[start:end].strip()
        parts = task_raw.split("|")
        task_text = parts[0].strip()
        priority = "בינונית"
        if len(parts) > 1 and "עדיפות:" in parts[1]:
            priority = parts[1].split("עדיפות:")[1].strip()
        tasks = get_tasks()
        tasks.append({"id": len(tasks) + 1, "text": task_text, "priority": priority, "done": False})
        save_tasks(tasks)
        response = response.replace(f"[TASK:{task_raw}]", f"📋 נוספה משימה: {task_text}")

    # סיום משימה
    if "[DONE:" in response:
        start = response.index("[DONE:") + 6
        end = response.index("]", start)
        task_id = int(response[start:end].strip())
        tasks = get_tasks()
        for t in tasks:
            if t["id"] == task_id:
                t["done"] = True
        save_tasks(tasks)
        response = response.replace(f"[DONE:{task_id}]", f"✅ משימה {task_id} בוצעה!")

    return response

# ─── פקודות ─────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "היי שימי! 👋\n\n"
        "אני העוזר האישי שלך. הנה מה שאני יכול:\n"
        "📋 /tasks — רשימת משימות\n"
        "🧠 /memory — מה שאני זוכר עליך\n"
        "🗑 /clear — איפוס שיחה\n\n"
        "פשוט תכתוב לי כל מה שצריך!"
    )

async def cmd_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tasks = get_tasks()
    open_tasks = [t for t in tasks if not t.get("done")]
    done_tasks = [t for t in tasks if t.get("done")]

    if not tasks:
        await update.message.reply_text("אין משימות עדיין. תגיד לי מה יש לעשות!")
        return

    priority_icon = {"גבוהה": "🔴", "בינונית": "🟡", "נמוכה": "🟢"}
    msg = "📋 *משימות פתוחות:*\n"
    for t in open_tasks:
        icon = priority_icon.get(t["priority"], "⚪")
        msg += f"{icon} [{t['id']}] {t['text']}\n"

    if done_tasks:
        msg += f"\n✅ בוצעו: {len(done_tasks)} משימות"

    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mem = get_memory()
    if not mem["facts"]:
        await update.message.reply_text("עדיין לא זכרתי כלום. תגיד לי מה לזכור!")
        return
    msg = "🧠 *מה שאני זוכר:*\n"
    for f in mem["facts"]:
        msg += f"• {f}\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    await update.message.reply_text("🗑 השיחה אופסה!")

# ─── הודעות רגילות ──────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        reply = await call_claude(user_id, user_message)
        reply = process_response(reply)
        await update.message.reply_text(reply)
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("משהו השתבש, נסה שוב 🙏")

# ─── תזכורות אוטומטיות ──────────────────────────────────────────

async def send_morning_reminder(app: Application, chat_id: int):
    tasks = get_tasks()
    open_count = len([t for t in tasks if not t.get("done")])
    msg = (
        f"☀️ *בוקר טוב שימי!*\n\n"
        f"יש לך {open_count} משימות פתוחות.\n\n"
        f"מה 3 הדברים החשובים ביותר להיום?"
    )
    await app.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")

async def send_evening_reminder(app: Application, chat_id: int):
    msg = (
        "🌙 *ערב טוב שימי!*\n\n"
        "מה הדבר האחד שחייב לקרות מחר?"
    )
    await app.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")

async def scheduler(app: Application):
    chat_id = int(os.environ.get("SHIMI_CHAT_ID", "0"))
    if not chat_id:
        logger.warning("SHIMI_CHAT_ID לא הוגדר — תזכורות לא יישלחו")
        return

    while True:
        now = datetime.now()
        hour = now.hour
        minute = now.minute

        if hour == 8 and minute == 0:
            await send_morning_reminder(app, chat_id)
            await asyncio.sleep(61)
        elif hour == 21 and minute == 0:
            await send_evening_reminder(app, chat_id)
            await asyncio.sleep(61)
        else:
            await asyncio.sleep(30)

# ─── הפעלה ──────────────────────────────────────────────────────

async def post_init(app: Application):
    asyncio.create_task(scheduler(app))

def main():
    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(post_init)
        .build()
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("tasks", cmd_tasks))
    app.add_handler(CommandHandler("memory", cmd_memory))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("🤖 שימי-בוט עלה!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
