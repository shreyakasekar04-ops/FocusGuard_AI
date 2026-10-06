from flask import Flask, request, jsonify
import sqlite3
from datetime import datetime, timezone
import os
import time

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "mobile_usage.db")


# =================================================
# DATABASE
# =================================================

def create_database():

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mobile_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            screen_time REAL NOT NULL,
            social_media_time REAL NOT NULL,
            productivity_time REAL DEFAULT 0,
            productivity_level TEXT DEFAULT 'LOW',
            date TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS screen_time_limits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            daily_limit REAL NOT NULL
        )
    """)

    # =================================================
    # REMINDERS
    # =================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            activity TEXT NOT NULL,
            duration INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            trigger_at_ms INTEGER NOT NULL,
            delivered INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()


create_database()


# =================================================
# HOME
# =================================================

@app.route("/")
def home():

    return "FocusGuard AI API is running!"


# =================================================
# SAVE DAILY SCREEN TIME LIMIT
# =================================================

@app.route("/set_limit", methods=["POST"])
def set_limit():

    try:

        data = request.get_json()

        username = data.get("username")
        daily_limit = float(
            data.get("daily_limit", 5)
        )

        if not username:

            return jsonify({
                "status": "error",
                "message": "Username is required"
            }), 400

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO screen_time_limits
            (username, daily_limit)
            VALUES (?, ?)

            ON CONFLICT(username)
            DO UPDATE SET
            daily_limit = excluded.daily_limit
        """, (
            username,
            daily_limit
        ))

        conn.commit()
        conn.close()

        return jsonify({
            "status": "success",
            "username": username,
            "daily_limit": daily_limit
        }), 200

    except Exception as e:

        print("LIMIT API ERROR:", str(e))

        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


# =================================================
# GET DAILY SCREEN TIME LIMIT
# =================================================

@app.route("/get_limit", methods=["GET"])
def get_limit():

    try:

        username = request.args.get(
            "username",
            "default_user"
        )

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT daily_limit
            FROM screen_time_limits
            WHERE username = ?
        """, (
            username,
        ))

        result = cursor.fetchone()

        conn.close()

        if result:

            return jsonify({
                "status": "success",
                "username": username,
                "daily_limit": result[0]
            }), 200

        return jsonify({
            "status": "success",
            "username": username,
            "daily_limit": 5
        }), 200

    except Exception as e:

        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


# =================================================
# SAVE CUSTOM REMINDER
# =================================================

@app.route("/save_reminder", methods=["POST"])
def save_reminder():

    try:

        data = request.get_json()

        if data is None:
            return jsonify({
                "status": "error",
                "message": "No JSON data received"
            }), 400

        username = str(
            data.get("username", "default_user")
        ).strip()

        activity = str(
            data.get("activity", "Focus Session")
        ).strip()

        duration = int(
            data.get("duration", 5)
        )

        if not username:
            return jsonify({
                "status": "error",
                "message": "Username is required"
            }), 400

        if duration < 1 or duration > 120:
            return jsonify({
                "status": "error",
                "message": "Duration must be between 1 and 120 minutes"
            }), 400

        # UTC timestamp for Android scheduling.
        # Android converts this automatically to local phone time.
        trigger_at_ms = int(
            time.time() * 1000
        ) + (duration * 60 * 1000)

        # Human-readable IST timestamp.
        created_at = datetime.now(
            timezone.utc
        ).astimezone().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO reminders
            (
                username,
                activity,
                duration,
                created_at,
                trigger_at_ms,
                delivered
            )
            VALUES (?, ?, ?, ?, ?, 0)
        """, (
            username,
            activity,
            duration,
            created_at,
            trigger_at_ms
        ))

        reminder_id = cursor.lastrowid

        conn.commit()
        conn.close()

        print(
            f"Reminder saved: "
            f"{username} | "
            f"{activity} | "
            f"{duration} min"
        )

        return jsonify({
            "status": "success",
            "id": reminder_id,
            "username": username,
            "activity": activity,
            "duration": duration,
            "created_at": created_at,
            "trigger_at_ms": trigger_at_ms
        }), 200

    except Exception as e:

        print(
            "REMINDER SAVE ERROR:",
            str(e)
        )

        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


# =================================================
# GET PENDING REMINDERS
# =================================================

@app.route("/pending_reminders", methods=["GET"])
def pending_reminders():

    try:

        username = request.args.get(
            "username",
            "default_user"
        )

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                id,
                activity,
                duration,
                created_at,
                trigger_at_ms
            FROM reminders
            WHERE username = ?
              AND delivered = 0
              AND trigger_at_ms > ?
            ORDER BY trigger_at_ms ASC
        """, (
            username,
            int(time.time() * 1000)
        ))

        rows = cursor.fetchall()

        conn.close()

        reminders = []

        for row in rows:

            reminders.append({

                "id": row[0],

                "activity": row[1],

                "duration": row[2],

                "created_at": row[3],

                "trigger_at_ms": row[4]

            })

        return jsonify({

            "status": "success",

            "username": username,

            "reminders": reminders

        }), 200

    except Exception as e:

        print(
            "PENDING REMINDER ERROR:",
            str(e)
        )

        return jsonify({

            "status": "error",

            "message": str(e)

        }), 500

    # =================================================
# GET ALL USER REMINDERS
# =================================================

@app.route("/user_reminders", methods=["GET"])
def user_reminders():

    try:

        username = request.args.get(
            "username",
            "default_user"
        )

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                id,
                activity,
                duration,
                created_at,
                trigger_at_ms,
                delivered
            FROM reminders
            WHERE username = ?
            ORDER BY id DESC
        """, (
            username,
        ))

        rows = cursor.fetchall()

        conn.close()

        reminders = []

        for row in rows:

            reminders.append({

                "id": row[0],

                "activity": row[1],

                "duration": row[2],

                "created_at": row[3],

                "trigger_at_ms": row[4],

                "delivered": row[5]

            })

        return jsonify({

            "status": "success",

            "username": username,

            "reminders": reminders

        }), 200

    except Exception as e:

        print(
            "USER REMINDERS ERROR:",
            str(e)
        )

        return jsonify({

            "status": "error",

            "message": str(e)

        }), 500


# =================================================
# MARK REMINDER DELIVERED
# =================================================

@app.route("/complete_reminder/<int:reminder_id>", methods=["POST"])
def complete_reminder(reminder_id):

    try:

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE reminders
            SET delivered = 1
            WHERE id = ?
        """, (
            reminder_id,
        ))

        conn.commit()

        updated = cursor.rowcount

        conn.close()

        return jsonify({

            "status": "success",

            "updated": updated

        }), 200

    except Exception as e:

        return jsonify({

            "status": "error",

            "message": str(e)

        }), 500


# =================================================
# RECEIVE AND SAVE ANDROID USAGE
# =================================================

@app.route("/usage", methods=["POST"])
def receive_usage():

    try:

        data = request.get_json()

        if data is None:

            return jsonify({
                "status": "error",
                "message": "No JSON data received"
            }), 400

        username = data.get(
            "username",
            "default_user"
        )

        screen_time = float(
            data.get("screen_time", 0)
        )

        social_media_time = float(
            data.get("social_media_time", 0)
        )

        productivity_time = float(
            data.get("productivity_time", 0)
        )

        productivity_level = data.get(
            "productivity_level",
            "LOW"
        )

        app_usage = data.get(
            "app_usage",
            []
        )

        print("\n==============================")
        print("ANDROID USAGE RECEIVED")
        print("Username:", username)
        print("Screen Time:", screen_time)
        print("Social Media:", social_media_time)
        print("Productivity:", productivity_time)
        print("Productivity Level:", productivity_level)
        print("App Usage:", app_usage)

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO mobile_usage
            (
                username,
                screen_time,
                social_media_time,
                productivity_time,
                productivity_level,
                date
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            username,
            screen_time,
            social_media_time,
            productivity_time,
            productivity_level,
            datetime.now(
                timezone.utc
            ).astimezone().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        ))

        conn.commit()
        conn.close()

        return jsonify({

            "status": "success",

            "message":
                "Usage data saved successfully",

            "screen_time":
                screen_time,

            "social_media_time":
                social_media_time,

            "productivity_time":
                productivity_time,

            "productivity_level":
                productivity_level

        }), 200

    except Exception as e:

        print(
            "API ERROR:",
            str(e)
        )

        return jsonify({

            "status": "error",

            "message":
                str(e)

        }), 500


# =================================================
# GET LATEST ANDROID USAGE
# =================================================

@app.route("/latest_usage", methods=["GET"])
def latest_usage():

    try:

        username = request.args.get(
            "username",
            "default_user"
        )

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                screen_time,
                social_media_time,
                productivity_time,
                productivity_level,
                date
            FROM mobile_usage
            WHERE username = ?
            ORDER BY id DESC
            LIMIT 1
        """, (
            username,
        ))

        result = cursor.fetchone()

        conn.close()

        if result:

            return jsonify({

                "status": "success",

                "username": username,

                "screen_time": result[0],

                "social_media_time": result[1],

                "productivity_time": result[2],

                "productivity_level": result[3],

                "date": result[4]

            }), 200

        return jsonify({

            "status": "success",

            "username": username,

            "screen_time": 0,

            "social_media_time": 0,

            "productivity_time": 0,

            "productivity_level": "LOW",

            "date": None

        }), 200

    except Exception as e:

        return jsonify({

            "status": "error",

            "message": str(e)

        }), 500


# =================================================
# RUN SERVER
# =================================================

if __name__ == "__main__":

    print(
        "FocusGuard AI API started"
    )

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
