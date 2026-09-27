from flask import Flask, request, jsonify
import sqlite3
from datetime import datetime
import os



app = Flask(__name__)


# -------------------------------------------------
# DATABASE PATH
# -------------------------------------------------

DB_PATH = os.path.join(
    os.path.dirname(__file__),
    "mobile_usage.db"
)


# -------------------------------------------------
# HOME
# -------------------------------------------------

@app.route("/")
def home():
    return "FocusGuard AI API is running!"
# -------------------------------------------------
# SAVE DAILY SCREEN TIME LIMIT
# -------------------------------------------------

@app.route("/set_limit", methods=["POST"])
def set_limit():

    try:
        data = request.get_json()

        username = data.get("username")
        daily_limit = float(data.get("daily_limit", 5))

        if not username:
            return jsonify({
                "status": "error",
                "message": "Username is required"
            }), 400

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS screen_time_limits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                daily_limit REAL NOT NULL
            )
        """)

        cursor.execute("""
            INSERT INTO screen_time_limits
            (username, daily_limit)
            VALUES (?, ?)
            ON CONFLICT(username)
            DO UPDATE SET daily_limit = excluded.daily_limit
        """, (
            username,
            daily_limit
        ))

        conn.commit()
        conn.close()

        print(
            f"⏰ Daily Limit Saved: {username} = {daily_limit} hours"
        )

        return jsonify({
            "status": "success",
            "username": username,
            "daily_limit": daily_limit
        }), 200

    except Exception as e:

        print("❌ LIMIT API ERROR:", str(e))

        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
    
    # -------------------------------------------------
# GET DAILY SCREEN TIME LIMIT
# -------------------------------------------------

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
            CREATE TABLE IF NOT EXISTS screen_time_limits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                daily_limit REAL NOT NULL
            )
        """)

        cursor.execute("""
            SELECT daily_limit
            FROM screen_time_limits
            WHERE username = ?
        """, (username,))

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


# -------------------------------------------------
# RECEIVE AND SAVE ANDROID USAGE
# -------------------------------------------------

@app.route("/usage", methods=["POST"])
def receive_usage():

    try:

        # Get JSON data from Android
        data = request.get_json()

        if data is None:
            return jsonify({
                "status": "error",
                "message": "No JSON data received"
            }), 400


        # -------------------------------------------------
        # GET DATA FROM ANDROID
        # -------------------------------------------------

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


        # -------------------------------------------------
        # DISPLAY RECEIVED DATA
        # -------------------------------------------------

        print("\n================================")
        print("📱 Android Usage Received")

        print(
            "Screen Time:",
            screen_time,
            "minutes"
        )

        print(
            "Social Media Time:",
            social_media_time,
            "minutes"
        )

        print(
            "Productivity App Time:",
            productivity_time,
            "minutes"
        )

        print(
            "Automatic Productivity Level:",
            productivity_level
        )

        print(
            "App Usage Data:",
            app_usage
        )


        # -------------------------------------------------
        # CONNECT DATABASE
        # -------------------------------------------------

        conn = sqlite3.connect(DB_PATH)

        cursor = conn.cursor()


        # -------------------------------------------------
        # CREATE MOBILE USAGE TABLE
        # -------------------------------------------------

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mobile_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                screen_time REAL NOT NULL,
                social_media_time REAL NOT NULL,
                productivity_time REAL DEFAULT 0,
                productivity_level TEXT DEFAULT 'LOW',
                date TEXT NOT NULL
            )
        """)


        # -------------------------------------------------
        # SAVE USAGE DATA
        # -------------------------------------------------

        cursor.execute("""
            INSERT INTO mobile_usage
            (
                screen_time,
                social_media_time,
                productivity_time,
                productivity_level,
                date
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            screen_time,
            social_media_time,
            productivity_time,
            productivity_level,
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        ))


        # -------------------------------------------------
        # SAVE DATABASE
        # -------------------------------------------------

        conn.commit()
        conn.close()


        print("✅ Usage data saved successfully")
        print("================================\n")


        # -------------------------------------------------
        # SEND RESPONSE TO ANDROID
        # -------------------------------------------------

        return jsonify({
            "status": "success",
            "message": "Usage data saved successfully",
            "screen_time": screen_time,
            "social_media_time": social_media_time,
            "productivity_time": productivity_time,
            "productivity_level": productivity_level
        }), 200


    except Exception as e:

        print("❌ API ERROR:", str(e))

        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

        # -------------------------------------------------
        # GET LATEST ANDROID USAGE FOR STREAMLIT
        # -------------------------------------------------
        
        @app.route("/latest_usage", methods=["GET"])
        def latest_usage():
        
            try:
        
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
        
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS mobile_usage (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        screen_time REAL NOT NULL,
                        social_media_time REAL NOT NULL,
                        productivity_time REAL DEFAULT 0,
                        productivity_level TEXT DEFAULT 'LOW',
                        date TEXT NOT NULL
                    )
                """)
        
                cursor.execute("""
                    SELECT
                        screen_time,
                        social_media_time,
                        productivity_time,
                        productivity_level,
                        date
                    FROM mobile_usage
                    ORDER BY id DESC
                    LIMIT 1
                """)
        
                result = cursor.fetchone()
        
                conn.close()
        
                if result:
        
                    return jsonify({
                        "status": "success",
                        "screen_time": result[0],
                        "social_media_time": result[1],
                        "productivity_time": result[2],
                        "productivity_level": result[3],
                        "date": result[4]
                    }), 200
        
                return jsonify({
                    "status": "success",
                    "screen_time": 0,
                    "social_media_time": 0,
                    "productivity_time": 0,
                    "productivity_level": "LOW",
                    "date": None
                }), 200
        
            except Exception as e:
        
                print("❌ LATEST USAGE ERROR:", str(e))
        
                return jsonify({
                    "status": "error",
                    "message": str(e)
                }), 500
        
        
        # -------------------------------------------------
        # RUN FLASK SERVER
        # -------------------------------------------------
        
        if __name__ == "__main__":
        
            print("======================================")
            print("🛡️ FocusGuard AI API")
            print("======================================")
        
            print("Starting Flask server...")
        
            print("Android Emulator URL:")
            print("http://10.0.2.2:5000")
        
            print("======================================")
        
        
            app.run(
                host="0.0.0.0",
                port=5000,
                debug=True
    )
    
