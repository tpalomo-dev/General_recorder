import datetime
import zoneinfo
import asyncpg
import aiohttp
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
import logging
import os

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI()

# Environment variables
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# Map shorthands and full names to table columns
COLUMN_MAPPING = {
    "sueño": "Suenho",
    "s": "Suenho",
    "sueño prof": "Suenho_profundo",
    "sp": "Suenho_profundo",
    "peso": "Peso",
    "p": "Peso",
    "kcal": "KCal",
    "km": "KM_Nad",
    "cerve": "Cerve",
    "copete": "Copete"
}

async def handle_message(message, text: str):
    """
    Handles a Telegram message updating daily stats.
    Message can contain multiple fields: "s 1, sp 2, p 70"
    """
    # 1. Parse message into updates
    updates = {}
    parts = [p.strip() for p in text.split(",")]

    for part in parts:
        if not part:
            continue
        tokens = part.lower().split()
        if len(tokens) < 2:
            continue
        field_input = " ".join(tokens[:-1])
        try:
            value = float(tokens[-1])
        except ValueError:
            continue

        # Match field to column (supports shorthands)
        column_to_update = None
        for key in COLUMN_MAPPING:
            if field_input.startswith(key):
                column_to_update = COLUMN_MAPPING[key]
                break
        if column_to_update:
            updates[column_to_update] = value

    if not updates:
        return JSONResponse({"status": "error", "message": "No valid fields found in message."})

    # 2. Prepare timestamp and day
    tz = zoneinfo.ZoneInfo("America/Santiago")
    now = datetime.datetime.now(tz).replace(tzinfo=None)
    today = now.date()
    
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        # 3. Build upsert query dynamically
        columns = ["day", "timestamp"] + list(updates.keys())
        values_list = [today, now] + list(updates.values())
        placeholders = ", ".join([f"${i+1}" for i in range(len(values_list))])
        update_clause = ", ".join([f"{col} = EXCLUDED.{col}" for col in updates.keys()])

        query = f"""
            INSERT INTO General_track ({', '.join(columns)})
            VALUES ({placeholders})
            ON CONFLICT(day)
            DO UPDATE SET {update_clause}
        """

        await conn.execute(query, *values_list)

        # 4. Send confirmation via Telegram
        update_str = ", ".join([f"{k}={v}" for k, v in updates.items()])
        async with aiohttp.ClientSession() as session:
            await session.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={
                    "chat_id": message["chat"]["id"],
                    "text": f"Updated today: {update_str}"
                }
            )

        return JSONResponse({"status": "success", "message": f"Updated today: {update_str}"})
    finally:
        await conn.close()

@app.post("/telegram_webhook")
async def telegram_webhook(req: Request):
    try:
        data = await req.json()
        logger.info(f"Received webhook data: {data}")
        message = data.get("message")
        if not message:
            return JSONResponse({"status": "no_message"})

        if message.get("text"):

            return await handle_message(message, message["text"])

        else:
            logger.warning(f"Unknown message type: {message.keys()}")
            return JSONResponse({"status": "unknown_message_type"})

    except Exception as e:
        logger.error(f"Unhandled error in webhook: {str(e)}")

        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)


@app.get("/favicon.ico")
async def faviconico():
    return Response(status_code=204)


@app.get("/favicon.png")
async def faviconpng():
    return Response(status_code=204)


@app.get("/")
def read_root():
    return {"message": "Hello World from FastAPI on Vercel!"}


@app.get("/api/health")
def health_check():
    return {"status": "healthy"}
