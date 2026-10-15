import os
import threading
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI
import uvicorn
from fpdf import FPDF
from geopy.distance import geodesic
from supabase import create_client, Client
from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

# --- FASTAPI WEB SERVER FOR RENDER PORT BINDING ---
app_web = FastAPI()


@app_web.get("/")
def home():
  return {"status": "Bot is running live!"}


def run_fastapi():
  port = int(os.environ.get("PORT", 10000))
  uvicorn.run(app_web, host="0.0.0.0", port=port)


# --- CONFIGURATION ---
BOT_TOKEN = "8742119027:AAHURXCQ9yC0cBZ4xIqBKkTIlrPMcKMC3dA"
COORDINATOR_ID = "7609626589"

# Supabase መረጃዎች
SUPABASE_URL = "https://qeqyphocgcbjntfqeqyp.supabase.co"
SUPABASE_KEY = "sb_publishable_6o_ZagLjQhLdwStKdV_VXQ_hZ74Iw5l"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# አስተማሪው የሚገኝበት ቦታ Coordinate እና የሚፈቀደው ርቀት (በሜትር)
TEACHER_LOCATION = (9.1590690, 39.0281169)
ALLOWED_DISTANCE = 100

NAME, STUDENT_ID, LOCATION, REASON = range(4)
START_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton("🔄 አዲስ ምዝገባ ጀምር")]], resize_keyboard=True
)


def get_eth_now():
  # የኢትዮጵያ ሰዓት (UTC+3)
  return datetime.now(timezone(timedelta(hours=3)))


def is_already_registered(telegram_id, session, date_str):
  response = (
      supabase.table("attendance_records")
      .select("*")
      .eq("telegram_id", str(telegram_id))
      .eq("attendance_date", date_str)
      .eq("session", session)
      .execute()
  )
  return len(response.data) > 0


# --- PDF GENERATOR ---
async def generate_pdf_report(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
  user_id = str(update.message.from_user.id)
  if user_id != COORDINATOR_ID:
    await update.message.reply_text("ይቅርታ፣ ይህ ትዕዛዝ ለCoordinator ብቻ ነው!")
    return

  try:
    await update.message.reply_text("📊 ሪፖርቱ ከዳታቤዝ እየተዘጋጀ ነው...")

    att_res = supabase.table("attendance_records").select("*").execute()
    students_res = supabase.table("students").select("*").execute()

    students_map = {s["telegram_id"]: s for s in students_res.data}

    pdf = FPDF()
    pdf.add_page()

    pdf.set_font("Arial", "B", 16)
    pdf.cell(
        190, 15, txt="Weekly Student Attendance Report", ln=True, align="C"
    )
    pdf.set_font("Arial", size=10)
    pdf.cell(
        190,
        10,
        txt=f"Generated Date: {get_eth_now().strftime('%Y-%m-%d %I:%M %p')}",
        ln=True,
        align="C",
    )
    pdf.ln(5)

    pdf.set_font("Arial", "B", 10)
    pdf.set_fill_color(230, 230, 230)
    headers = ["Student ID", "Full Name", "Session", "Status", "Date"]
    col_widths = [30, 55, 45, 30, 30]

    for i, h in enumerate(headers):
      pdf.cell(col_widths[i], 10, h, border=1, align="C", fill=True)
    pdf.ln()

    pdf.set_font("Arial", size=9)
    for record in att_res.data:
      t_id = record["telegram_id"]
      student = students_map.get(t_id, {})
      s_id = str(student.get("student_id", "N/A"))
      f_name = str(student.get("full_name", "Unknown"))[:25]
      sess = str(record["session"])
      stat = str(record["status"])
      r_date = str(record["attendance_date"])

      pdf.cell(col_widths[0], 10, s_id, border=1, align="C")
      pdf.cell(col_widths[1], 10, f_name, border=1)
      pdf.cell(col_widths[2], 10, sess, border=1, align="C")
      pdf.cell(col_widths[3], 10, stat, border=1, align="C")
      pdf.cell(col_widths[4], 10, r_date, border=1, align="C")
      pdf.ln()

    pdf_file = "Weekly_Attendance.pdf"
    pdf.output(pdf_file)
    with open(pdf_file, "rb") as f:
      await context.bot.send_document(
          chat_id=COORDINATOR_ID,
          document=f,
          caption="📊 የሳምንቱ ሪፖርት ተዘጋጅቷል።",
      )
    os.remove(pdf_file)
  except Exception as e:
    await update.message.reply_text(f"ስህተት፦ {e}")


# --- BOT CONVERSATION LOGIC ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
  user_id = str(update.message.from_user.id)
  now = get_eth_now()
  today_date = now.strftime("%Y-%m-%d")

  current_minutes = now.hour * 60 + now.minute

  if 510 <= current_minutes <= 600:
    session = "Morning"
  elif 820 <= current_minutes <= 900:
    session = "Afternoon"
  else:
    session = "Late/Off-time"

  context.user_data["session"] = session
  if is_already_registered(user_id, session, today_date):
    await update.message.reply_text(
        f"⚠️ ለ{session} ክፍለ ጊዜ ቀድመህ ተመዝግበሃል።",
        reply_markup=START_KEYBOARD,
    )
    return ConversationHandler.END

  student_res = (
      supabase.table("students")
      .select("*")
      .eq("telegram_id", user_id)
      .execute()
  )

  if student_res.data and len(student_res.data) > 0:
    student = student_res.data[0]
    context.user_data["full_name"], context.user_data["student_id"] = (
        student["full_name"],
        student["student_id"],
    )
    await update.message.reply_text(
        f"ሰላም {context.user_data['full_name']}! እባክህ መገኘቴን አረጋግጥ የሚለውን ተጫን።",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("📍 መገኘቴን አረጋግጥ", request_location=True)]],
            resize_keyboard=True,
        ),
    )
    return LOCATION
  else:
    await update.message.reply_text(
        "አዲስ ተማሪ ነህ። ሙሉ ስምህን አስገባ፦", reply_markup=ReplyKeyboardRemove()
    )
    return NAME


async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
  context.user_data["full_name"] = update.message.text
  await update.message.reply_text("የተማሪ ID ቁጥርህን አስገባ፦")
  return STUDENT_ID


async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
  context.user_data["student_id"] = update.message.text.upper()
  await update.message.reply_text(
      "አሁን ሎኬሽን ላክ፦",
      reply_markup=ReplyKeyboardMarkup(
          [[KeyboardButton("📍 ሎኬሽን ላክ", request_location=True)]],
          resize_keyboard=True,
      ),
  )
  return LOCATION


async def get_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
  user_loc = (update.message.location.latitude, update.message.location.longitude)
  distance = geodesic(TEACHER_LOCATION, user_loc).meters
  now, session = get_eth_now(), context.user_data["session"]
  context.user_data["now"] = now

  if distance > ALLOWED_DISTANCE or session == "Late/Off-time":
    await update.message.reply_text(
        f"❌ ርቀት፡ {int(distance)}m ወይም ሰዓት አልፏል። ምክንያት ጻፍ፦"
    )
    return REASON
  return await finalize_attendance(update, context, "Present")


async def get_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
  return await finalize_attendance(
      update, context, f"Late ({update.message.text})"
  )


async def finalize_attendance(update, context, status):
  now, session = context.user_data["now"], context.user_data["session"]
  user_id = str(update.message.from_user.id)

  student_check = (
      supabase.table("students").select("*").eq("telegram_id", user_id).execute()
  )
  if not student_check.data:
    supabase.table("students").insert({
        "telegram_id": user_id,
        "full_name": context.user_data["full_name"],
        "student_id": context.user_data["student_id"],
    }).execute()

  supabase.table("attendance_records").insert({
      "telegram_id": user_id,
      "session": f"{now.strftime('%I:%M %p')} ({session})",
      "status": status,
      "attendance_date": now.strftime("%Y-%m-%d"),
  }).execute()

  await update.message.reply_text(
      f"✅ ተመዝግቧል። ሰዓት፡ {now.strftime('%I:%M %p')}",
      reply_markup=START_KEYBOARD,
  )
  return ConversationHandler.END


def main():
  # FastAPI ሰርቨሩን በሌላ ሬድ (Thread) ማስጀመር
  t = threading.Thread(target=run_fastapi, daemon=True)
  t.start()

  app = (
      Application.builder()
      .token(BOT_TOKEN)
      .connect_timeout(30.0)
      .read_timeout(30.0)
      .write_timeout(30.0)
      .build()
  )

  app.add_handler(CommandHandler("report", generate_pdf_report))
  app.add_handler(
      MessageHandler(filters.Regex("^Report$"), generate_pdf_report)
  )

  conv = ConversationHandler(
      entry_points=[
          CommandHandler("start", start),
          MessageHandler(filters.Regex("^🔄 አዲስ ምዝገባ ጀምር$"), start),
      ],
      states={
          NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
          STUDENT_ID: [
              MessageHandler(filters.TEXT & ~filters.COMMAND, get_id)
          ],
          LOCATION: [MessageHandler(filters.LOCATION, get_location)],
          REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_reason)],
      },
      fallbacks=[CommandHandler("start", start)],
  )
  app.add_handler(conv)
  print("Attendance Bot with Supabase is Live...")
  app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
  main()
