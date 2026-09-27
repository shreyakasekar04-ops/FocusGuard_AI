import sqlite3
import os

DB_PATH = os.path.join(
    os.path.dirname(__file__),
    "focusguard_users.db"
)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# ==============================
# USERS TABLE
# ==============================

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT,
    email TEXT,
    role TEXT
)
""")

# Check existing columns
cursor.execute("PRAGMA table_info(users)")
columns = [row[1] for row in cursor.fetchall()]

# Add profession column if missing
if "profession" not in columns:
    cursor.execute(
        "ALTER TABLE users ADD COLUMN profession TEXT"
    )

# Add known_skills column if missing
if "known_skills" not in columns:
    cursor.execute(
        "ALTER TABLE users ADD COLUMN known_skills TEXT"
    )


# ==============================
# USER ANALYSIS TABLE
# ==============================

cursor.execute("""
CREATE TABLE IF NOT EXISTS user_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    screen_time REAL,
    social_media_time REAL,
    productivity INTEGER,
    risk_level TEXT,
    risk_score INTEGER,
    date TEXT
)
""")


# ==============================
# REMINDERS TABLE
# ==============================

cursor.execute("""
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    activity TEXT,
    duration INTEGER,
    date TEXT
)
""")


conn.commit()
conn.close()

print("Database updated successfully!")