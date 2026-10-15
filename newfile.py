from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from geopy.distance import geodesic
from pydantic import BaseModel
from supabase import Client, create_client
import uvicorn
import os

app = FastAPI()

# --- SUPABASE CONFIGURATION ---
SUPABASE_URL = "https://qeqyphocgcbjntfqeqyp.supabase.co"
SUPABASE_KEY = "sb_publishable_6o_ZagLjQhLdwStKdV_VXQ_hZ74Iw5l"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# የአስተማሪው ቦታ Coordinate እና የሚፈቀደው ርቀት (በሜትር)
TEACHER_LOCATION = (9.1590690, 39.0281169)
ALLOWED_DISTANCE = 100


class AttendanceRequest(BaseModel):
  full_name: str
  student_id: str
  latitude: float
  longitude: float


def get_eth_now():
  # የኢትዮጵያ ሰዓት (UTC+3)
  return datetime.now(timezone(timedelta(hours=3)))


@app.get("/", response_class=HTMLResponse)
def read_root():
  try:
    with open("index.html", "r", encoding="utf-8") as f:
      return f.read()
  except FileNotFoundError:
    return "<h3>index.html ፋይል አልተገኘም!</h3>"


@app.post("/submit-attendance")
def submit_attendance(data: AttendanceRequest):
  now = get_eth_now()
  today_date = now.strftime("%Y-%m-%d")
  current_minutes = now.hour * 60 + now.minute

  # የክፍለ ጊዜ (Session) ውሳኔ
  if 510 <= current_minutes <= 600:
    session = "Morning"
  elif 820 <= current_minutes <= 900:
    session = "Afternoon"
  else:
    session = "Late/Off-time"

  if session == "Late/Off-time":
    raise HTTPException(
        status_code=400, detail="የመመዝገቢያ ሰዓት አልፏል ወይም የክፍለ ጊዜ ውጭ ነው!"
    )

  # ሎኬሽን ማረጋገጥ (Distance Calculation)
  user_loc = (data.latitude, data.longitude)
  distance = geodesic(TEACHER_LOCATION, user_loc).meters

  if distance > ALLOWED_DISTANCE:
    raise HTTPException(
        status_code=400,
        detail=(
            f"ከተፈቀደው ቦታ ውጭ ነዎት (ርቀት፡ {int(distance)} ሜትር)። እባክዎ ወደ ክፍሉ"
            " ይጠጋሉ።"
        ),
    )

  # ዛሬ መመዝገቡን ማረጋገጥ
  existing = (
      supabase.table("attendance_records")
      .select("*")
      .eq("student_id", data.student_id)
      .eq("attendance_date", today_date)
      .eq("session", session)
      .execute()
  )

  if existing.data and len(existing.data) > 0:
    raise HTTPException(
        status_code=400, detail=f"ለ{session} ክፍለ ጊዜ ቀድመው ተመዝግበዋል!"
    )

  # 1. ተማሪው በ students ሠንጠረዥ ውስጥ መኖሩን ማረጋገጥ
  student_check = (
      supabase.table("students")
      .select("*")
      .eq("student_id", data.student_id)
      .execute()
  )
  if not student_check.data:
    supabase.table("students").insert({
        "full_name": data.full_name,
        "student_id": data.student_id,
    }).execute()

  # 2. የመገኘት መዝገብ ማስገባት
  supabase.table("attendance_records").insert({
      "student_id": data.student_id,
      "full_name": data.full_name,
      "session": session,
      "status": "Present",
      "attendance_date": today_date,
      "time": now.strftime("%I:%M %p"),
  }).execute()

  return {
      "message": (
          f"በሰላም ተመዝግበዋል! (ሰዓት፡ {now.strftime('%I:%M %p')} - {session})"
      )
  }


if __name__ == "__main__":
  port = int(os.environ.get("PORT", 10000))
  uvicorn.run(app, host="0.0.0.0", port=port)
