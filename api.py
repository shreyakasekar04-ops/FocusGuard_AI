from flask import Flask, request, jsonify
import sqlite3
from datetime import datetime, timezone, timedelta
import os
import time

app = Flask(__name__)

# =================================================
# CONFIGURATION
# =================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

DB_PATH = os.path.join(
    BASE_DIR,
    "mobile_usage.db"
)

# India Standard Time
IST = timezone(
    timedelta(hours=5, minutes=30)
)


# =================================================
# DATABASE CONNECTION
# =================================================

def get_connection():

    conn = sqlite3.connect(
        DB_PATH
    )

    return conn


# =================================================
# CURRENT INDIA TIME
# =================================================

def get_india_time():

    return datetime.now(
        timezone.utc
    ).astimezone(
        IST
    )


# =================================================
# DATABASE
# =================================================

def create_database():

    conn = get_connection()

    cursor = conn.cursor()

    # =================================================
    # MOBILE USAGE
    # =================================================

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

    # =================================================
    # SCREEN TIME LIMITS
    # =================================================

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
# HOME / API STATUS
# =================================================

@app.route("/")
def home():

    return "FocusGuard AI API is running!"


# =================================================
# SET DAILY SCREEN TIME LIMIT
# =================================================

@app.route(
    "/set_limit",
    methods=["POST"]
)
def set_limit():

    try:

        data = request.get_json()

        if data is None:

            return jsonify({
                "status": "error",
                "message": "No JSON data received"
            }), 400

        username = str(
            data.get(
                "username",
                ""
            )
        ).strip()

        daily_limit = float(
            data.get(
                "daily_limit",
                5
            )
        )

        if not username:

            return jsonify({
                "status": "error",
                "message": "Username is required"
            }), 400

        if daily_limit <= 0:

            return jsonify({
                "status": "error",
                "message": "Daily limit must be greater than 0"
            }), 400

        conn = get_connection()

        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO screen_time_limits
            (
                username,
                daily_limit
            )
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

        print(
            "SET LIMIT ERROR:",
            str(e)
        )

        return jsonify({

            "status": "error",

            "message": str(e)

        }), 500


# =================================================
# GET DAILY SCREEN TIME LIMIT
# =================================================

@app.route(
    "/get_limit",
    methods=["GET"]
)
def get_limit():

    try:

        username = request.args.get(
            "username",
            "default_user"
        )

        conn = get_connection()

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

        print(
            "GET LIMIT ERROR:",
            str(e)
        )

        return jsonify({

            "status": "error",

            "message": str(e)

        }), 500


# =================================================
# SAVE CUSTOM REMINDER
# =================================================

@app.route(
    "/save_reminder",
    methods=["POST"]
)
def save_reminder():

    try:

        data = request.get_json()

        if data is None:

            return jsonify({

                "status": "error",

                "message":
                    "No JSON data received"

            }), 400

        username = str(
            data.get(
                "username",
                "default_user"
            )
        ).strip()

        activity = str(
            data.get(
                "activity",
                "Focus Session"
            )
        ).strip()

        duration = int(
            data.get(
                "duration",
                5
            )
        )

        # -------------------------------------------------
        # VALIDATION
        # -------------------------------------------------

        if not username:

            return jsonify({

                "status": "error",

                "message":
                    "Username is required"

            }), 400

        if not activity:

            activity = "Focus Session"

        if duration < 1 or duration > 120:

            return jsonify({

                "status": "error",

                "message":
                    "Duration must be between 1 and 120 minutes"

            }), 400

        # -------------------------------------------------
        # EXACT FUTURE TIMESTAMP
        # -------------------------------------------------

        now_ms = int(
            time.time() * 1000
        )

        trigger_at_ms = (
            now_ms
            +
            (
                duration
                * 60
                * 1000
            )
        )

        # -------------------------------------------------
        # INDIA TIME
        # -------------------------------------------------

        created_at = get_india_time().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        # -------------------------------------------------
        # SAVE REMINDER
        # -------------------------------------------------

        conn = get_connection()

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
            "\n=============================="
        )

        print(
            "REMINDER SAVED"
        )

        print(
            "ID:",
            reminder_id
        )

        print(
            "Username:",
            username
        )

        print(
            "Activity:",
            activity
        )

        print(
            "Duration:",
            duration,
            "minutes"
        )

        print(
            "Created IST:",
            created_at
        )

        print(
            "Trigger:",
            trigger_at_ms
        )

        print(
            "==============================\n"
        )

        return jsonify({

            "status": "success",

            "message":
                "Reminder saved successfully",

            "id":
                reminder_id,

            "username":
                username,

            "activity":
                activity,

            "duration":
                duration,

            "created_at":
                created_at,

            "trigger_at_ms":
                trigger_at_ms

        }), 200

    except Exception as e:

        print(
            "SAVE REMINDER ERROR:",
            str(e)
        )

        return jsonify({

            "status": "error",

            "message": str(e)

        }), 500


# =================================================
# GET PENDING REMINDERS
# =================================================

@app.route(
    "/pending_reminders",
    methods=["GET"]
)
def pending_reminders():

    try:

        username = request.args.get(
            "username",
            "default_user"
        )

        current_time_ms = int(
            time.time() * 1000
        )

        conn = get_connection()

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
            current_time_ms
        ))

        rows = cursor.fetchall()

        conn.close()

        reminders = []

        for row in rows:

            reminders.append({

                "id":
                    row[0],

                "activity":
                    row[1],

                "duration":
                    row[2],

                "created_at":
                    row[3],

                "trigger_at_ms":
                    row[4]

            })

        return jsonify({

            "status":
                "success",

            "username":
                username,

            "reminders":
                reminders

        }), 200

    except Exception as e:

        print(
            "PENDING REMINDER ERROR:",
            str(e)
        )

        return jsonify({

            "status":
                "error",

            "message":
                str(e)

        }), 500


# =================================================
# GET ALL USER REMINDERS
# =================================================

@app.route(
    "/user_reminders",
    methods=["GET"]
)
def user_reminders():

    try:

        username = request.args.get(
            "username",
            "default_user"
        )

        conn = get_connection()

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

                "id":
                    row[0],

                "activity":
                    row[1],

                "duration":
                    row[2],

                "created_at":
                    row[3],

                "trigger_at_ms":
                    row[4],

                "delivered":
                    row[5]

            })

        return jsonify({

            "status":
                "success",

            "username":
                username,

            "reminders":
                reminders

        }), 200

    except Exception as e:

        print(
            "USER REMINDERS ERROR:",
            str(e)
        )

        return jsonify({

            "status":
                "error",

            "message":
                str(e)

        }), 500


# =================================================
# COMPLETE REMINDER
# =================================================

@app.route(
    "/complete_reminder/<int:reminder_id>",
    methods=["POST"]
)
def complete_reminder(reminder_id):

    try:

        conn = get_connection()

        cursor = conn.cursor()

        cursor.execute("""
            UPDATE reminders

            SET delivered = 1

            WHERE id = ?
        """, (
            reminder_id,
        ))

        updated = cursor.rowcount

        conn.commit()

        conn.close()

        if updated == 0:

            return jsonify({

                "status":
                    "error",

                "message":
                    "Reminder not found",

                "updated":
                    0

            }), 404

        return jsonify({

            "status":
                "success",

            "message":
                "Reminder completed successfully",

            "updated":
                updated

        }), 200

    except Exception as e:

        print(
            "COMPLETE REMINDER ERROR:",
            str(e)
        )

        return jsonify({

            "status":
                "error",

            "message":
                str(e)

        }), 500


# =================================================
# RECEIVE AND SAVE ANDROID USAGE
# =================================================

@app.route(
    "/usage",
    methods=["POST"]
)
def receive_usage():

    try:

        data = request.get_json()

        if data is None:

            return jsonify({

                "status":
                    "error",

                "message":
                    "No JSON data received"

            }), 400

        # -------------------------------------------------
        # USERNAME
        # -------------------------------------------------

        username = str(
            data.get(
                "username",
                "default_user"
            )
        ).strip()

        # -------------------------------------------------
        # SCREEN TIME
        # -------------------------------------------------

        screen_time = float(
            data.get(
                "screen_time",
                0
            )
        )

        # -------------------------------------------------
        # SOCIAL MEDIA TIME
        # -------------------------------------------------

        social_media_time = float(
            data.get(
                "social_media_time",
                0
            )
        )

        # -------------------------------------------------
        # PRODUCTIVITY TIME
        #
        # Accept both:
        # productivity_time
        # productivity
        # -------------------------------------------------

        productivity_time = float(
            data.get(
                "productivity_time",
                data.get(
                    "productivity",
                    0
                )
            )
        )

        # -------------------------------------------------
        # PRODUCTIVITY LEVEL
        #
        # Accept:
        # productivity_level
        #
        # If Android sends only productivity number,
        # automatically calculate level.
        # -------------------------------------------------

        productivity_level = str(
            data.get(
                "productivity_level",
                ""
            )
        ).upper().strip()

        if productivity_level not in [
            "LOW",
            "MODERATE",
            "HIGH"
        ]:

            if productivity_time >= 2:

                productivity_level = "HIGH"

            elif productivity_time >= 1:

                productivity_level = "MODERATE"

            else:

                productivity_level = "LOW"

        # -------------------------------------------------
        # OPTIONAL APP USAGE
        # -------------------------------------------------

        app_usage = data.get(
            "app_usage",
            []
        )

        # -------------------------------------------------
        # PRINT RECEIVED DATA
        # -------------------------------------------------

        print(
            "\n=============================="
        )

        print(
            "ANDROID USAGE RECEIVED"
        )

        print(
            "Username:",
            username
        )

        print(
            "Screen Time:",
            screen_time
        )

        print(
            "Social Media:",
            social_media_time
        )

        print(
            "Productivity Time:",
            productivity_time
        )

        print(
            "Productivity Level:",
            productivity_level
        )

        print(
            "App Usage:",
            app_usage
        )

        print(
            "==============================\n"
        )

        # -------------------------------------------------
        # SAVE TO DATABASE
        # -------------------------------------------------

        conn = get_connection()

        cursor = conn.cursor()

        date = get_india_time().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

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
            date
        ))

        usage_id = cursor.lastrowid

        conn.commit()

        conn.close()

        return jsonify({

            "status":
                "success",

            "message":
                "Usage data saved successfully",

            "id":
                usage_id,

            "username":
                username,

            "screen_time":
                screen_time,

            "social_media_time":
                social_media_time,

            "productivity_time":
                productivity_time,

            "productivity_level":
                productivity_level,

            "date":
                date

        }), 200

    except Exception as e:

        print(
            "USAGE API ERROR:",
            str(e)
        )

        return jsonify({

            "status":
                "error",

            "message":
                str(e)

        }), 500


# =================================================
# GET LATEST ANDROID USAGE
# =================================================

@app.route(
    "/latest_usage",
    methods=["GET"]
)
def latest_usage():

    try:

        username = request.args.get(
            "username",
            "default_user"
        )

        conn = get_connection()

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

                "status":
                    "success",

                "username":
                    username,

                "screen_time":
                    result[0],

                "social_media_time":
                    result[1],

                "productivity_time":
                    result[2],

                "productivity_level":
                    result[3],

                "date":
                    result[4]

            }), 200

        # -------------------------------------------------
        # NO DATA YET
        # -------------------------------------------------

        return jsonify({

            "status":
                "success",

            "username":
                username,

            "screen_time":
                0,

            "social_media_time":
                0,

            "productivity_time":
                0,

            "productivity_level":
                "LOW",

            "date":
                None

        }), 200

    except Exception as e:

        print(
            "LATEST USAGE ERROR:",
            str(e)
        )

        return jsonify({

            "status":
                "error",

            "message":
                str(e)

        }), 500


# =================================================
# RUN SERVER
# =================================================

if __name__ == "__main__":

    print(
        "================================"
    )

    print(
        "FocusGuard AI API started"
    )

    print(
        "Database:",
        DB_PATH
    )

    print(
        "================================"
    )

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
