import time
import sqlite3
import pygetwindow as gw
from datetime import datetime

DB_PATH = "mobile_usage.db"

SOCIAL_KEYWORDS = [
    "instagram",
    "youtube",
    "facebook",
    "whatsapp",
    "twitter",
    "x.com",
    "snapchat"
]


def create_table():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS laptop_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            app_name TEXT,
            usage_minutes REAL,
            date TEXT
        )
    """)

    conn.commit()
    conn.close()


def save_usage(app_name, minutes):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO laptop_usage
        (app_name, usage_minutes, date)
        VALUES (?, ?, ?)
    """, (
        app_name,
        minutes,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()


def get_active_window():
    try:
        window = gw.getActiveWindow()

        if window is None:
            return "Unknown"

        title = window.title.strip()

        if title == "":
            return "Unknown"

        return title

    except Exception:
        return "Unknown"


def is_social_media(window_title):
    title = window_title.lower()

    for keyword in SOCIAL_KEYWORDS:
        if keyword in title:
            return True

    return False


def main():

    create_table()

    print("======================================")
    print("💻 FocusGuard AI Laptop Tracker")
    print("======================================")
    print("Active application detection started...")
    print("Press CTRL+C to stop.")
    print()

    usage_data = {}

    try:

        while True:

            active_window = get_active_window()

            usage_data[active_window] = (
                usage_data.get(active_window, 0) + 10
            )

            print(
                f"\rActive Window: {active_window[:70]}",
                end=""
            )

            time.sleep(10)

    except KeyboardInterrupt:

        print("\n\n======================================")
        print("📊 Usage Summary")
        print("======================================")

        total_usage = 0
        social_usage = 0

        for app_name, seconds in usage_data.items():

            minutes = seconds / 60

            if minutes <= 0:
                continue

            save_usage(app_name, minutes)

            total_usage += minutes

            if is_social_media(app_name):
                social_usage += minutes

            print(
                f"{app_name[:50]} : {minutes:.2f} minutes"
            )

        print("--------------------------------------")
        print(f"💻 Total Laptop Usage: {total_usage:.2f} minutes")
        print(f"📱 Social Media Usage: {social_usage:.2f} minutes")
        print("--------------------------------------")
        print("✅ Laptop usage saved successfully")
        print("======================================")


if __name__ == "__main__":
    main()