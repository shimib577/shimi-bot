# שימי בוט — עוזר אישי בטלגרם

## מה הבוט עושה
- עונה לכל הודעה בצ'אט בצורה חכמה (מחובר ל-Claude)
- שולח תזכורת בוקר בכל יום ב-07:30
- שולח תזכורת ערב בכל יום ב-21:00
- זוכר את ההיסטוריה של השיחה

---

## הפעלה ב-Railway (הכי פשוט, חינמי)

### שלב 1 — צור חשבון Railway
- כנס ל: https://railway.app
- התחבר עם GitHub

### שלב 2 — צור פרויקט חדש
- לחץ "New Project"
- בחר "Deploy from GitHub repo"
- העלה את הקבצים האלה ל-GitHub repo חדש

### שלב 3 — הוסף משתני סביבה
בלשונית Variables הוסף:
```
TELEGRAM_TOKEN=הטוקן שלך
ANTHROPIC_API_KEY=המפתח שלך
SHIMI_CHAT_ID=####
```

### שלב 4 — הוסף Procfile
צור קובץ בשם `Procfile` עם התוכן:
```
worker: python bot.py
```

### שלב 5 — Deploy
Railway יבנה ויפעיל את הבוט אוטומטית.

---

## הפעלה מקומית (לבדיקה)

```bash
pip install -r requirements.txt
export TELEGRAM_TOKEN="הטוקן שלך"
export ANTHROPIC_API_KEY="המפתח שלך"
export SHIMI_CHAT_ID="=####"
python bot.py
```

---

## איפה מקבלים Anthropic API Key?
כנס ל: https://console.anthropic.com
צור מפתח חדש תחת API Keys.
