# app.py
# Streamlit prototype: Connect users with physicians for epidemic-disease consulting
# Run: pip install streamlit pandas pytz
#      streamlit run app.py

import streamlit as st
import sqlite3
from datetime import datetime, timedelta, time
import pytz
import pandas as pd
import uuid
import os
import re

DB_PATH = "telehealth.db"

# --------------------------- DB HELPERS ---------------------------

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS physicians (
        id TEXT PRIMARY KEY,
        full_name TEXT NOT NULL,
        country TEXT NOT NULL,
        timezone TEXT NOT NULL,
        specialties TEXT NOT NULL,  -- comma-separated
        languages TEXT NOT NULL,    -- comma-separated
        about TEXT
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS availability (
        id TEXT PRIMARY KEY,
        physician_id TEXT NOT NULL,
        start_utc TEXT NOT NULL,   -- ISO8601
        end_utc TEXT NOT NULL,     -- ISO8601
        booked INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY(physician_id) REFERENCES physicians(id) ON DELETE CASCADE
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS appointments (
        id TEXT PRIMARY KEY,
        physician_id TEXT NOT NULL,
        physician_name TEXT NOT NULL,
        user_name TEXT NOT NULL,
        user_email TEXT NOT NULL,
        user_timezone TEXT NOT NULL,
        start_utc TEXT NOT NULL,
        end_utc TEXT NOT NULL,
        meeting_link TEXT NOT NULL,
        reason TEXT,
        created_at_utc TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'scheduled',
        FOREIGN KEY(physician_id) REFERENCES physicians(id) ON DELETE CASCADE
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        appointment_id TEXT NOT NULL,
        sender TEXT NOT NULL,       -- 'user' or 'physician'
        body TEXT NOT NULL,
        sent_at_utc TEXT NOT NULL,
        FOREIGN KEY(appointment_id) REFERENCES appointments(id) ON DELETE CASCADE
    );
    """)
    conn.commit()
    return conn

def seed_sample_data(conn):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM physicians;")
    if cur.fetchone()[0] > 0:
        return  # already seeded

    sample = [
        {
            "full_name": "Dr. Aisha Rahman",
            "country": "Pakistan",
            "timezone": "Asia/Karachi",
            "specialties": "Epidemiology,Infectious Diseases,COVID-19",
            "languages": "English,Urdu",
            "about": "10+ years in outbreak response and telemedicine."
        },
        {
            "full_name": "Dr. Mateo Alvarez",
            "country": "Spain",
            "timezone": "Europe/Madrid",
            "specialties": "Infectious Diseases,Travel Medicine,Dengue",
            "languages": "English,Spanish",
            "about": "Focus on vector-borne diseases and global health."
        },
        {
            "full_name": "Dr. Hana Sato",
            "country": "Japan",
            "timezone": "Asia/Tokyo",
            "specialties": "Public Health,Influenza,Respiratory Infections",
            "languages": "English,Japanese",
            "about": "Community surveillance and prevention specialist."
        },
    ]
    for doc in sample:
        pid = str(uuid.uuid4())
        cur.execute("""INSERT INTO physicians
            (id, full_name, country, timezone, specialties, languages, about)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (pid, doc["full_name"], doc["country"], doc["timezone"],
             doc["specialties"], doc["languages"], doc["about"]))
        # create 7 days of 3 daily slots each, 30-minute slots starting 14:00, 15:00, 16:00 local
        tz = pytz.timezone(doc["timezone"])
        today_local = datetime.now(tz).date()
        for d in range(0, 7):
            day = today_local + timedelta(days=d)
            for hour in [14, 15, 16]:
                start_local = tz.localize(datetime.combine(day, time(hour=hour, minute=0)))
                end_local = start_local + timedelta(minutes=30)
                start_utc = start_local.astimezone(pytz.utc).isoformat()
                end_utc = end_local.astimezone(pytz.utc).isoformat()
                cur.execute("""INSERT INTO availability (id, physician_id, start_utc, end_utc, booked)
                               VALUES (?, ?, ?, ?, 0)""",
                            (str(uuid.uuid4()), pid, start_utc, end_utc))
    conn.commit()

def list_physicians(conn, specialty=None, language=None, country=None, search=None):
    q = "SELECT id, full_name, country, timezone, specialties, languages, about FROM physicians"
    filters = []
    params = []
    def like_clause(field, value):
        filters.append(f"LOWER({field}) LIKE ?")
        params.append(f"%{value.lower()}%")

    if specialty:
        like_clause("specialties", specialty)
    if language:
        like_clause("languages", language)
    if country:
        like_clause("country", country)
    if search:
        filters.append("(LOWER(full_name) LIKE ? OR LOWER(about) LIKE ?)")
        params.extend([f"%{search.lower()}%", f"%{search.lower()}%"])

    if filters:
        q += " WHERE " + " AND ".join(filters)
    q += " ORDER BY full_name ASC;"
    return pd.read_sql_query(q, conn, params=params)

def list_slots_for_physician(conn, physician_id, only_future=True):
    q = "SELECT id, start_utc, end_utc, booked FROM availability WHERE physician_id = ?"
    params = [physician_id]
    if only_future:
        now = datetime.utcnow().isoformat()
        q += " AND end_utc >= ?"
        params.append(now)
    q += " ORDER BY start_utc ASC"
    return pd.read_sql_query(q, conn, params=params)

def get_physician(conn, pid):
    return pd.read_sql_query(
        "SELECT * FROM physicians WHERE id = ?",
        conn, params=[pid]
    ).iloc[0].to_dict()

def book_slot(conn, slot_id, user_name, user_email, user_tz, reason):
    cur = conn.cursor()
    # lock & check
    cur.execute("SELECT physician_id, start_utc, end_utc, booked FROM availability WHERE id = ?", (slot_id,))
    row = cur.fetchone()
    if not row:
        return None, "Slot not found."
    physician_id, start_utc, end_utc, booked = row
    if booked:
        return None, "Sorry, this slot was just booked."
    # get physician
    cur.execute("SELECT full_name FROM physicians WHERE id = ?", (physician_id,))
    prow = cur.fetchone()
    if not prow:
        return None, "Physician not found."
    physician_name = prow[0]
    appt_id = str(uuid.uuid4())
    meeting_link = f"https://example.test/meet/{appt_id}"  # placeholder
    cur.execute("""INSERT INTO appointments
        (id, physician_id, physician_name, user_name, user_email, user_timezone, start_utc, end_utc,
         meeting_link, reason, created_at_utc, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'scheduled')""",
        (appt_id, physician_id, physician_name, user_name, user_email, user_tz,
         start_utc, end_utc, meeting_link, reason, datetime.utcnow().isoformat()))
    cur.execute("UPDATE availability SET booked = 1 WHERE id = ?", (slot_id,))
    conn.commit()
    return appt_id, None

def list_user_appointments(conn, user_email):
    return pd.read_sql_query("""
        SELECT id, physician_name, start_utc, end_utc, meeting_link, status, reason
        FROM appointments WHERE user_email = ?
       appts_display["Start (local)"] = appts_display["start_utc"].apply(
    lambda x: to_user_local(x, user_tz).strftime("%a %d %b %Y, %I:%M %p") if to_user_local(x, user_tz) else ""
)
appts_display["End (local)"] = appts_display["end_utc"].apply(
    lambda x: to_user_local(x, user_tz).strftime("%I:%M %p") if to_user_local(x, user_tz) else ""
)
expected_cols = ["physician_name","Start (local)","End (local)","meeting_link","status","reason","id"]
cols_present = [c for c in expected_cols if c in appts_display.columns]
appts_display = appts_display[cols_present]
