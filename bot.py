import os
import logging
import asyncio
from datetime import time
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import httpx

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
SHIMI_CHAT_ID = int(os.environ.get("SHIMI_CHAT_ID", "1065288478"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """אתה שימי — העוזר האישי של לירן לין (שמוכר גם כשימי).
אתה מכיר אותו היטב ועוזר לו לנהל את היום יום שלו בצורה חכמה.

המטרה שלך:
- לעזור לו לזכור משימות ולתעדף אותן
- לשלוח תזכורות בוקר וערב
- לענות בקצרה וחכם — הוא עם ADHD, אז אל תכביד
- לדבר בעברית, בטון חברותי וישיר
- לא לדבר יותר מדי — מקסימום 3-4 משפטים בכל תגובה

מה שאתה יודע עליו:
- עצמאי בתחום AI לאנימציה/תוכן
- עובד על פרויקט קנדיבור (עדיפות עליונה)
- גר בנס ציונה, עובר דירה באוגוסט
- נשוי לסיון, יש לו ילדים
- יש לו ADHD — אוהב דברים פשוטים וברורים

תזכורת בוקר: שלח הודעה קצרה ואנרגטית עם שאלה — מה 3 המשימות של היום?
תזכורת ערב: שלח הודעה קצרה עם שאלה — מה הדבר האחד שחייב לקרות מחר?"""

conversation_history = {}

async def call_claude(chat_id: int, user_message: str) -> str:
    if chat_id not in conversation_history:
        conversation_history[chat_id] = []
    
    conversation_history[chat_id].append({"role": "user", "content": user_message})
    
    if len(conversation_history[chat_id]) > 20:
        conversation_history[chat_id] = conversation_history[chat_id][-20:]
    
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
                "system": SYSTEM_PROMPT,
                "messages": conversation_history[chat_id]
            }
        )
        data = response.json()
        assistant_message = data["content"][0]["text"]
        conversation_history[chat_id].append({"role": "assistant", "content": assistant_message})
        return assistant_message

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("היי שימי! 👋\n\nאני העוזר האישי שלך. אני כאן כדי לעזור לך לנהל את היום יום.\n\nמה יש לך על הראש היום?")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_text = update.message.text
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    try:
        response = await call_claude(chat_id, user_text)
        await update.message.reply_text(response)
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("אופס, משהו השתבש. נסה שוב.")

async def morning_reminder(context: ContextTypes.DEFAULT_TYPE):
    try:
        response = await call_claude(SHIMI_CHAT_ID, "שלח תזכורת בוקר")
        await context.bot.send_message(chat_id=SHIMI_CHAT_ID, text=response)
    except Exception as e:
        logger.error(f"Morning reminder error: {e}")

async def evening_reminder(context: ContextTypes.DEFAULT_TYPE):
    try:
        response = await call_claude(SHIMI_CHAT_ID, "שלח תזכורת ערב")
        await context.bot.send_message(chat_id=SHIMI_CHAT_ID, text=response)
    except Exception as e:
        logger.error(f"Evening reminder error: {e}")

async def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.job_queue.run_daily(morning_reminder, time=time(hour=4, minute=30), days=(0,1,2,3,4,5,6))
    app.job_queue.run_daily(evening_reminder, time=time(hour=18, minute=0), days=(0,1,2,3,4,5,6))
    logger.info("Bot started!")
    await app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
