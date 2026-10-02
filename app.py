import streamlit as st
import pandas as pd
import sqlite3
import os
import time
import re
import io
import requests
from werkzeug.security import generate_password_hash, check_password_hash

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="FocusGuard AI",
    page_icon="🛡️",
    layout="wide"
)


# =========================================================
# PATHS
# =========================================================

BASE_DIR = os.path.dirname(__file__)

DB_PATH = os.path.join(
    BASE_DIR,
    "focusguard_users.db"
)

MOBILE_USAGE_DB = os.path.join(
    BASE_DIR,
    "mobile_usage.db"
)

CSV_PATH = os.path.join(
    BASE_DIR,
    "focus_guard_data.csv"
)


# =========================================================
# DATABASE SETUP
# =========================================================

def initialize_database():

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT NOT NULL,
            role TEXT NOT NULL,
            profession TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            screen_time REAL,
            social_media_time REAL,
            productivity REAL,
            risk_level TEXT,
            risk_score INTEGER,
            date TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            activity TEXT,
            duration INTEGER,
            date TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            daily_limit REAL DEFAULT 5.0,
            updated_at TEXT
        )
    """)

    # Add profession if old database does not have it
    try:
        cursor.execute(
            "ALTER TABLE users ADD COLUMN profession TEXT"
        )
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()


initialize_database()


# =========================================================
# USER FUNCTIONS
# =========================================================

def create_user(
    username,
    password,
    email,
    role,
    profession
):

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    hashed_password = generate_password_hash(password)

    try:
        # Prevent duplicate usernames.
        cursor.execute(
            "SELECT 1 FROM users WHERE LOWER(username) = LOWER(?) LIMIT 1",
            (username.strip(),)
        )
        if cursor.fetchone():
            return "username_exists"

        # Prevent the same email from being registered again.
        cursor.execute(
            "SELECT 1 FROM users WHERE LOWER(email) = LOWER(?) LIMIT 1",
            (email.strip(),)
        )
        if cursor.fetchone():
            return "email_exists"

        cursor.execute("""
            INSERT INTO users
            (
                username,
                password,
                email,
                role,
                profession
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            username.strip(),
            hashed_password,
            email.strip(),
            role,
            profession
        ))

        conn.commit()
        return True

    except sqlite3.IntegrityError:
        return "username_exists"

    finally:
        conn.close()


def is_valid_email(email):
    """Validate the basic structure of an email address.

    This checks format only; it does not claim that the mailbox actually exists.
    """
    email = email.strip()
    pattern = r"^[A-Za-z0-9][A-Za-z0-9._%+-]*@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$"
    return re.fullmatch(pattern, email) is not None

def check_user(username, password):

    # Developer access is role-based and uses environment secrets.
    # The credentials are NOT shown in the normal user interface.
    developer_username = os.getenv("FOCUSGUARD_DEVELOPER_USERNAME", "")
    developer_password = os.getenv("FOCUSGUARD_DEVELOPER_PASSWORD", "")

    if (
        developer_username
        and developer_password
        and username.strip() == developer_username
        and password == developer_password
    ):
        return (
            0,
            developer_username,
            "",
            "",
            "Developer",
            "Developer"
        )

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            username,
            password,
            email,
            role,
            profession
        FROM users
        WHERE username = ?
    """, (
        username,
    ))

    user = cursor.fetchone()

    if not user:
        conn.close()
        return None

    stored_password = user[2]

    # New hashed password
    if stored_password.startswith("scrypt:") or stored_password.startswith("pbkdf2:"):

        if check_password_hash(
            stored_password,
            password
        ):
            conn.close()
            return user

    # Old plain-text password
    elif stored_password == password:

        # Convert old password to secure hash
        new_hash = generate_password_hash(password)

        cursor.execute("""
            UPDATE users
            SET password = ?
            WHERE id = ?
        """, (
            new_hash,
            user[0]
        ))

        conn.commit()
        conn.close()

        return user

    conn.close()
    return None

# =========================================================
# ANALYSIS FUNCTIONS
# =========================================================

def save_analysis(
    username,
    screen_time,
    social_media_time,
    productivity,
    risk_level,
    risk_score
):

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    

    cursor.execute("""
        INSERT INTO user_analysis
        (
            username,
            screen_time,
            social_media_time,
            productivity,
            risk_level,
            risk_score,
            date
        )
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
    """, (
        username,
        screen_time,
        social_media_time,
        productivity,
        risk_level,
        risk_score
    ))

    conn.commit()
    conn.close()


def get_user_analysis(username):

    conn = sqlite3.connect(DB_PATH)

    result = pd.read_sql_query(
        """
        SELECT
            screen_time,
            social_media_time,
            productivity,
            risk_level,
            risk_score,
            date
        FROM user_analysis
        WHERE username = ?
        ORDER BY id DESC
        """,
        conn,
        params=(username,)
    )

    conn.close()

    return result


def get_all_analysis():

    conn = sqlite3.connect(DB_PATH)

    result = pd.read_sql_query(
        """
        SELECT
            username,
            screen_time,
            social_media_time,
            productivity,
            risk_level,
            risk_score,
            date
        FROM user_analysis
        ORDER BY id DESC
        """,
        conn
    )

    conn.close()

    return result


# =========================================================
# PERSONAL GOALS / PROGRESS FUNCTIONS
# =========================================================

def save_user_goal(username, daily_limit):

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO user_goals
        (username, daily_limit, updated_at)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(username) DO UPDATE SET
            daily_limit = excluded.daily_limit,
            updated_at = excluded.updated_at
    """, (
        username,
        daily_limit
    ))

    conn.commit()
    conn.close()


def get_user_goal(username, default=5.0):

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT daily_limit
        FROM user_goals
        WHERE username = ?
    """, (username,))

    row = cursor.fetchone()
    conn.close()

    if row and row[0] is not None:
        return float(row[0])

    return float(default)


def get_latest_user_analysis(username):

    history = get_user_analysis(username)

    if history.empty:
        return None

    history["date"] = pd.to_datetime(
        history["date"],
        errors="coerce"
    )
    history = history.dropna(subset=["date"]).sort_values("date")

    if history.empty:
        return None

    return history.iloc[-1]


def get_focus_checkin_streak(username):
    history = get_user_analysis(username)

    if history.empty:
        return 0

    dates = pd.to_datetime(
        history["date"],
        errors="coerce"
    ).dropna().dt.date

    unique_dates = sorted(set(dates), reverse=True)

    if not unique_dates:
        return 0

    streak = 1

    for i in range(1, len(unique_dates)):
        difference = (
            unique_dates[i - 1] - unique_dates[i]
        ).days

        if difference == 1:
            streak += 1
        else:
            break

    return streak


def get_achievements(username):
    history = get_user_analysis(username)

    if history.empty:
        return []

    history["date"] = pd.to_datetime(
        history["date"],
        errors="coerce"
    )
    history = history.dropna(subset=["date"]).sort_values("date")

    achievements = []

    if len(history) >= 1:
        achievements.append("🥇 First Focus Check-in")

    if len(history) >= 3:
        achievements.append("🔥 3 Analysis Milestone")

    if len(history) >= 2:
        if float(history.iloc[-1]["screen_time"]) < float(history.iloc[0]["screen_time"]):
            achievements.append("📉 Screen Time Reduced")

        if float(history.iloc[-1]["social_media_time"]) < float(history.iloc[0]["social_media_time"]):
            achievements.append("📵 Social Media Reduced")

    if (history["productivity"] >= 4).any():
        achievements.append("🎯 High Productivity")

    if (history["risk_score"] <= 40).any():
        achievements.append("🟢 Low Risk Achieved")

    return achievements


def get_smart_reminder_recommendation(username, daily_limit):
    latest = get_latest_user_analysis(username)

    if latest is None:
        return {
            "activity": "📚 Focus Session",
            "duration": 25,
            "reason": "Complete your first analysis so FocusGuard can personalize your reminder.",
            "priority": "Getting Started"
        }

    screen = float(latest["screen_time"])
    social = float(latest["social_media_time"])
    productivity = float(latest["productivity"])
    risk = float(latest["risk_score"])

    if screen > daily_limit:
        return {
            "activity": "🚶 Take a Break",
            "duration": 15,
            "reason": f"Your latest screen time is {screen:.1f} hours, above your {daily_limit:.1f}-hour daily goal.",
            "priority": "High Priority"
        }

    if social >= 4:
        return {
            "activity": "📵 Stop Social Media",
            "duration": 20,
            "reason": f"Your latest social media usage is {social:.1f} hours, which is high.",
            "priority": "High Priority"
        }

    if screen >= 8:
        return {
            "activity": "🚶 Take a Break",
            "duration": 15,
            "reason": f"Your latest screen time is {screen:.1f} hours, so a break is recommended.",
            "priority": "High Priority"
        }

    if productivity <= 2:
        return {
            "activity": "📚 Focus Session",
            "duration": 25,
            "reason": "Your latest productivity level is low. A short focused session can help you restart productively.",
            "priority": "Focus Support"
        }

    if risk >= 70:
        return {
            "activity": "🧘 Relax / Meditation",
            "duration": 10,
            "reason": f"Your latest risk score is {risk:.0f}/100. A short reset is recommended.",
            "priority": "Risk Support"
        }

    if social >= 2 or screen >= 5 or productivity == 3:
        return {
            "activity": "🚶 Take a Break",
            "duration": 10,
            "reason": "Your latest analysis shows moderate digital usage. A short break can help maintain balance.",
            "priority": "Balance"
        }

    return {
        "activity": "📚 Focus Session",
        "duration": 25,
        "reason": "Your latest analysis looks balanced. A focused session can help you maintain your progress.",
        "priority": "Maintain Progress"
    }


# =========================================================
# REMINDER FUNCTIONS
# =========================================================

def save_reminder(
    username,
    activity,
    duration
):

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO reminders
        (
            username,
            activity,
            duration,
            date
        )
        VALUES (?, ?, ?, datetime('now'))
    """, (
        username,
        activity,
        duration
    ))

    conn.commit()
    conn.close()


def get_reminders(username):

    conn = sqlite3.connect(DB_PATH)

    result = pd.read_sql_query(
        """
        SELECT
            id,
            activity,
            duration,
            date
        FROM reminders
        WHERE username = ?
        ORDER BY id DESC
        """,
        conn,
        params=(username,)
    )

    conn.close()

    return result


# =========================================================
# AUTOMATIC DEVICE USAGE
# =========================================================

def get_automatic_device_usage():

    if not os.path.exists(MOBILE_USAGE_DB):

        return {
            "phone_screen": 0.0,
            "phone_social": 0.0,
            "phone_productivity_time": 0.0,
            "phone_productivity_level": "LOW",
            "laptop_screen": 0.0,
            "laptop_social": 0.0,
            "combined_screen": 0.0,
            "combined_social": 0.0
        }

    conn = sqlite3.connect(MOBILE_USAGE_DB)

    try:

                # PHONE DATA FROM PUBLIC RENDER API
        # -------------------------------------------------

        try:
            username = st.session_state.get("username", "default_user")
            response = requests.get(
                "https://focusguard-ai-9.onrender.com/latest_usage",
                params={"username": username},
                timeout=30
            )
            if response.status_code == 200:
                phone_data = response.json()
                phone_screen = float(phone_data.get("screen_time", 0))
                phone_social = float(phone_data.get("social_media_time", 0))
                phone_productivity = float(phone_data.get("productivity_time", 0))
                phone_productivity_level = phone_data.get("productivity_level", "LOW")
            else:
                phone_screen = phone_social = phone_productivity = 0.0
                phone_productivity_level = "LOW"
        except Exception:
            phone_screen = phone_social = phone_productivity = 0.0
            phone_productivity_level = "LOW"
        # -------------------------------------------------
        # LAPTOP DATA
        # -------------------------------------------------

        laptop_screen = 0.0
        laptop_social = 0.0

        try:

            laptop_df = pd.read_sql_query(
                """
                SELECT
                    COALESCE(
                        SUM(usage_minutes),
                        0
                    ) AS usage_minutes,

                    COALESCE(
                        SUM(social_minutes),
                        0
                    ) AS social_minutes

                FROM laptop_usage
                """,
                conn
            )

            laptop_screen = float(
                laptop_df.iloc[0]["usage_minutes"]
            )

            laptop_social = float(
                laptop_df.iloc[0]["social_minutes"]
            )

        except Exception:

            # Older laptop table may not have
            # social_minutes column.

            try:

                laptop_df = pd.read_sql_query(
                    """
                    SELECT
                        COALESCE(
                            SUM(usage_minutes),
                            0
                        ) AS usage_minutes
                    FROM laptop_usage
                    """,
                    conn
                )

                laptop_screen = float(
                    laptop_df.iloc[0]["usage_minutes"]
                )

            except Exception:

                laptop_screen = 0.0


        # -------------------------------------------------
        # CONVERT MINUTES TO HOURS
        # -------------------------------------------------

        phone_screen_hours = phone_screen / 60

        phone_social_hours = phone_social / 60

        laptop_screen_hours = laptop_screen / 60

        laptop_social_hours = laptop_social / 60


        combined_screen_hours = (
            phone_screen_hours
            + laptop_screen_hours
        )

        combined_social_hours = (
            phone_social_hours
            + laptop_social_hours
        )


        return {

            "phone_screen":
                phone_screen_hours,

            "phone_social":
                phone_social_hours,

            "phone_productivity_time":
                phone_productivity / 60,

            "phone_productivity_level":
                phone_productivity_level,

            "laptop_screen":
                laptop_screen_hours,

            "laptop_social":
                laptop_social_hours,

            "combined_screen":
                combined_screen_hours,

            "combined_social":
                combined_social_hours
        }


    except Exception:

        return {
            "phone_screen": 0.0,
            "phone_social": 0.0,
            "phone_productivity_time": 0.0,
            "phone_productivity_level": "LOW",
            "laptop_screen": 0.0,
            "laptop_social": 0.0,
            "combined_screen": 0.0,
            "combined_social": 0.0
        }

    finally:

        conn.close()


# =========================================================
# SESSION STATE
# =========================================================

if "logged_in" not in st.session_state:

    st.session_state["logged_in"] = False


if "username" not in st.session_state:

    st.session_state["username"] = ""


if "role" not in st.session_state:

    st.session_state["role"] = ""


if "profession" not in st.session_state:

    st.session_state["profession"] = ""


if "analysis_done" not in st.session_state:

    st.session_state["analysis_done"] = False


# =========================================================
# LOGIN / SIGNUP
# =========================================================

if not st.session_state["logged_in"]:

    st.markdown(
        """
        <div style="
            text-align:center;
            padding:30px;
        ">

        <h1>🛡️ FocusGuard AI</h1>

        <p style="font-size:20px;">
        Real-Time Digital Productivity Analysis System
        </p>

        </div>
        """,
        unsafe_allow_html=True
    )

    st.divider()

    login_option = st.radio(
        "Choose an option",
        [
            "🔐 Login",
            "📝 Sign Up"
        ],
        horizontal=True
    )


    # =====================================================
    # SIGN UP
    # =====================================================

    if login_option == "📝 Sign Up":
        st.subheader("📝 Create Your Account")
        username = st.text_input("👤 Username", key="signup_username")
        email = st.text_input("📧 Email", key="signup_email")
        password = st.text_input("🔐 Password", type="password", key="signup_password")
        confirm_password = st.text_input("🔑 Confirm Password", type="password", key="signup_confirm_password")
        role = st.selectbox("Choose your profile", ["🎓 Student", "💼 Employee"], key="signup_role")

        if role == "🎓 Student":
            profession = st.selectbox(
                "🎓 Choose your field of study",
                ["Select field", "💻 Information Technology", "📊 Data Science", "💻 Computer Science", "🎓 BCA", "⚙️ BTech / BE", "🖥️ Computer Applications", "📚 Other"],
                key="signup_field"
            )
        else:
            profession = st.selectbox(
                "💼 Choose your profession",
                ["Select profession", "👨‍💻 IT / Software", "📊 Data / Analytics", "👩‍🏫 Teacher / Education", "📈 Business / Marketing", "🎨 Design / Creative", "🩺 Healthcare", "⚖️ Law", "💰 Finance / Accounting", "🧑‍💼 Other"],
                key="signup_profession"
            )

        if st.button("🚀 Create Account", key="create_account_button"):
            if not username.strip():
                st.warning("⚠️ Please enter username.")
            elif not email.strip():
                st.warning("⚠️ Please enter email.")
            elif not is_valid_email(email):
                st.warning("⚠️ Please enter a valid email address, for example name@gmail.com.")
            elif not password:
                st.warning("⚠️ Please enter password.")
            elif password != confirm_password:
                st.error("❌ Passwords do not match.")
            elif role == "🎓 Student" and profession == "Select field":
                st.warning("⚠️ Please select your field of study.")
            elif role == "💼 Employee" and profession == "Select profession":
                st.warning("⚠️ Please select your profession.")
            else:
                selected_role = "Student" if role == "🎓 Student" else "Employee"
                success = create_user(username.strip(), password, email.strip(), selected_role, profession)
                if success is True:
                    st.success("✅ Account created successfully! Now login.")
                elif success == "email_exists":
                    st.error("❌ This email is already registered. Please use another email or login.")
                else:
                    st.error("❌ This username is already registered. Please choose another username.")

    # LOGIN
    # =====================================================
    else:
        st.subheader("Welcome Back 👋")
        st.write("Sign in to continue to your FocusGuard AI dashboard.")
        username = st.text_input("👤 Username", key="login_username")
        password = st.text_input("🔐 Password", type="password", key="login_password")

        if st.button("🔓 Login", key="login_button"):
            if not username.strip() or not password:
                st.warning("⚠️ Please enter username and password.")
            else:
                user = check_user(username.strip(), password)
                if user:
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = user[1]
                    st.session_state["role"] = user[4]
                    st.session_state["profession"] = user[5] if user[5] else ""
                    st.success("✅ Login successful!")
                    st.rerun()
                else:
                    st.error("❌ Invalid username or password.")

    st.stop()


# =========================================================
# LOAD DATASET
# =========================================================

try:

    df = pd.read_csv(CSV_PATH)

except Exception:

    df = pd.DataFrame()


# =========================================================
# CUSTOM CSS
# =========================================================

st.markdown(
    """
    <style>

    .main-title {
        text-align:center;
        font-size:42px;
        font-weight:bold;
    }

    .sub-title {
        text-align:center;
        font-size:20px;
    }

    div[data-testid="metric-container"] {

        background-color:white;

        border:1px solid #dfe7e1;

        padding:18px;

        border-radius:15px;

        box-shadow:
        0 3px 10px
        rgba(0,0,0,0.08);
    }

    .device-card {

        padding:18px;

        border-radius:15px;

        border:1px solid #dfe7e1;

        margin-bottom:10px;
    }

    </style>
    """,
    unsafe_allow_html=True
)

# =========================================================
# SIDEBAR
# =========================================================

st.sidebar.markdown(
    "## 🛡️ FocusGuard AI"
)

st.sidebar.success(
    f"👤 {st.session_state['username']}"
)

st.sidebar.write(
    f"Role: {st.session_state['role']}"
)

st.sidebar.write(
    f"Profession: {st.session_state['profession']}"
)

# Developer controls are intentionally NOT rendered here.
# Only the authenticated Developer role can open the
# Developer Panel.

st.sidebar.divider()

# =========================================================
# ROLE-BASED PAGE NAVIGATION
# =========================================================
#
# Normal Student/Employee accounts never see an Access Mode
# selector and can never switch themselves to Developer mode.
# Developer access is granted only when the authenticated
# account has role="Developer".
#
# =========================================================
# PAGE NAVIGATION STATE
# =========================================================

if "_nav_target" in st.session_state:
    st.session_state["page_selector"] = st.session_state.pop(
        "_nav_target"
    )

# User pages only
all_page_options = [
    "👤 My Data",
    "🏠 Dashboard",
    "📱 Device Analysis",
    "📊 Data Analysis",
    "🎓 Smart Learning",
    "🔔 Smart Reminders",
    "📜 History",
    "📥 Download"
]

if st.session_state.get("analysis_done", False):

    page_options = all_page_options

else:

    page_options = [
        "👤 My Data"
    ]

if (
    "page_selector" not in st.session_state
    or st.session_state["page_selector"] not in page_options
):

    st.session_state["page_selector"] = page_options[0]

# Developer access is based only on the authenticated role.
if st.session_state.get("role") == "Developer":

    page = "🔐 Developer"

else:

    page = st.session_state["page_selector"]

# =========================================================
# LOGOUT
# =========================================================

if st.sidebar.button(
    "🚪 Logout",
    use_container_width=True
):

    st.session_state.clear()

    st.rerun()


# =========================================================
# AUTOMATIC DEVICE DATA
# =========================================================

device_data = get_automatic_device_usage()


phone_screen_hours = device_data[
    "phone_screen"
]

phone_social_hours = device_data[
    "phone_social"
]

phone_productivity_hours = device_data[
    "phone_productivity_time"
]

phone_productivity_level = device_data[
    "phone_productivity_level"
]

laptop_screen_hours = device_data[
    "laptop_screen"
]

laptop_social_hours = device_data[
    "laptop_social"
]

combined_screen_hours = device_data[
    "combined_screen"
]

combined_social_hours = device_data[
    "combined_social"
]




def show_page_header():
    if st.session_state["role"] == "Student":
        dashboard_title = "🎓 Student Focus Dashboard"
        dashboard_subtitle = (
            "Improve your study focus and digital habits."
        )
    else:
        dashboard_title = "💼 Employee Productivity Dashboard"
        dashboard_subtitle = (
            "Improve your work productivity and digital balance."
        )

    st.markdown(
        """
        <div class="main-title">
            🛡️ FocusGuard AI
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown(
        f"""
        <div class="sub-title">
            {dashboard_title}
        </div>
        """,
        unsafe_allow_html=True
    )

    st.write(dashboard_subtitle)
    st.divider()


if page == "🏠 Dashboard":

    show_page_header()

    st.subheader("🏠 Dashboard")

    st.info(
        "Welcome to FocusGuard AI. Select a page from the sidebar "
        "to view a specific part of your productivity analysis."
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "📱 Phone Screen",
            f"{phone_screen_hours:.2f} hrs"
        )

    with col2:
        st.metric(
            "💻 Laptop Usage",
            f"{laptop_screen_hours:.2f} hrs"
        )

    with col3:
        st.metric(
            "📱 Social Media",
            f"{combined_social_hours:.2f} hrs"
        )

    with col4:
        st.metric(
            "📱💻 Combined",
            f"{combined_screen_hours:.2f} hrs"
        )

    st.subheader("🎯 Quick Overview")

    if phone_productivity_level == "HIGH":
        st.success("🟢 Automatic productivity level: HIGH")
    elif phone_productivity_level == "MODERATE":
        st.warning("🟡 Automatic productivity level: MODERATE")
    else:
        st.info("🔵 Automatic productivity level: LOW")

    st.caption(
        "Detailed device usage is available under Device Analysis. "
        "Dataset results are available under Data Analysis."
    )

    # =========================================================
    # PERSONAL ENGAGEMENT / GOALS
    # =========================================================

    latest = get_latest_user_analysis(
        st.session_state["username"]
    )

    if latest is not None:
        st.divider()
        st.subheader("🎯 Your Personal Progress")

        goal = get_user_goal(
            st.session_state["username"],
            5.0
        )
        current_screen = float(latest["screen_time"])
        goal_percent = min(100.0, (current_screen / goal) * 100) if goal > 0 else 0

        g1, g2, g3 = st.columns(3)
        with g1:
            st.metric("⏰ Screen-Time Goal", f"{goal:.1f} hrs")
        with g2:
            st.metric("📱 Latest Usage", f"{current_screen:.1f} hrs")
        with g3:
            streak = get_focus_checkin_streak(st.session_state["username"])
            st.metric("🔥 Focus Check-in Streak", f"{streak} day(s)")

        st.progress(goal_percent / 100)

        if current_screen <= goal:
            st.success("✅ You are within your latest screen-time goal. Keep going!")
        else:
            st.warning("⚠️ Your latest screen time is above your goal. Try the recommended reminder in Smart Reminders.")

        achievements = get_achievements(
            st.session_state["username"]
        )

        st.subheader("🏆 Achievements")
        if achievements:
            st.write(" •  ".join(achievements))
        else:
            st.info("Complete an analysis to start earning achievements.")

        st.subheader("💡 Today's Personal Tip")
        recommendation = get_smart_reminder_recommendation(
            st.session_state["username"],
            goal
        )
        st.info(
            f"{recommendation['reason']} Recommended: {recommendation['activity']} for {recommendation['duration']} minutes."
        )
    else:
        st.divider()
        st.info("📌 Complete your first analysis to unlock personal goals, achievements and smart recommendations.")

elif page == "📱 Device Analysis":
    show_page_header()

    # =========================================================
    # AUTOMATIC DEVICE DASHBOARD
    # =========================================================

    st.subheader(
        "📱💻 Automatic Device Usage"
    )

    st.caption(
        "Usage is collected automatically from Android and laptop tracking."
    )

    col1, col2, col3, col4 = st.columns(4)

    with col1:

        st.metric(
            "📱 Phone Screen",
            f"{phone_screen_hours:.2f} hrs"
        )

    with col2:

        st.metric(
            "📱 Phone Social",
            f"{phone_social_hours:.2f} hrs"
        )

    with col3:

        st.metric(
            "💻 Laptop Usage",
            f"{laptop_screen_hours:.2f} hrs"
        )

    with col4:

        st.metric(
            "📱💻 Combined",
            f"{combined_screen_hours:.2f} hrs"
        )


    # =========================================================
    # AUTOMATIC PRODUCTIVITY
    # =========================================================

    st.subheader(
        "🎯 Automatic Productivity"
    )

    col1, col2, col3 = st.columns(3)

    with col1:

        st.metric(
            "💼 Productivity App Time",
            f"{phone_productivity_hours:.2f} hrs"
        )

    with col2:

        st.metric(
            "🎯 Automatic Productivity",
            phone_productivity_level
        )

    with col3:

        if phone_productivity_level == "HIGH":

            st.success(
                "🟢 Good productive app usage"
            )

        elif phone_productivity_level == "MODERATE":

            st.warning(
                "🟡 Moderate productive app usage"
            )

        else:

            st.info(
                "🔵 Low productive app usage"
            )


    st.caption(
        "Productivity is calculated from detected productivity apps "
        "such as Gmail, Google Docs, Microsoft Word and Microsoft Teams."
    )

    st.divider()


elif page == "📊 Data Analysis":
    show_page_header()

    # =========================================================
    # DATASET ANALYSIS
    # =========================================================

    if not df.empty:

        st.subheader(
            "📊 Dataset Analysis"
        )

        if (
            "Screen_Time" in df.columns
            and
            "Social_Media_Time" in df.columns
        ):

            average_screen_time = df[
                "Screen_Time"
            ].mean()

            average_social_media = df[
                "Social_Media_Time"
            ].mean()

            col1, col2 = st.columns(2)

            with col1:

                st.metric(
                    "⏱️ Average Screen Time",
                    f"{average_screen_time:.2f} hrs"
                )

            with col2:

                st.metric(
                    "📱 Average Social Media",
                    f"{average_social_media:.2f} hrs"
                )


    # =========================================================
    # WASTE TIME DETECTION
    # =========================================================

    if not df.empty and "Social_Media_Time" in df.columns:

        st.subheader(
            "🚨 Waste Time Detection"
        )

        average_social_media = df[
            "Social_Media_Time"
        ].mean()

        if average_social_media >= 4:

            st.error(
                "🔴 High Waste Time Detected"
            )

        elif average_social_media >= 2:

            st.warning(
                "🟡 Moderate Waste Time Detected"
            )

        else:

            st.success(
                "🟢 Low Waste Time Detected"
            )


    st.info(
        "📌 This page shows dataset-level summary only. Your personal progress "
        "graphs are available under 📜 History and use only your own saved analyses."
    )


elif page == "👤 My Data":
    # =========================================================
    # MY DATA / PERSONAL ANALYSIS
    # =========================================================

    show_page_header()

    st.subheader("👤 My Data")

    st.info(
        "Enter your usage data below. After you click Analyze, "
        "your complete FocusGuard AI analysis will appear on this page."
    )

    # ---------------------------------------------------------
    # LOAD AUTOMATIC DEVICE DATA
    # ---------------------------------------------------------

    if st.button("📱💻 Use Automatic Device Data", key="auto_device_data_button"):

        st.session_state["screen_time_input"] = round(
            combined_screen_hours, 2
        )

        st.session_state["social_media_input"] = round(
            combined_social_hours, 2
        )

        if phone_productivity_level == "HIGH":
            automatic_productivity = 5
        elif phone_productivity_level == "MODERATE":
            automatic_productivity = 3
        else:
            automatic_productivity = 2

        st.session_state["productivity_input"] = automatic_productivity

        st.success("✅ Automatic phone + laptop data loaded!")
        st.rerun()

    # ---------------------------------------------------------
    # INPUTS
    # ---------------------------------------------------------

    user_screen_time = st.number_input(
        "⏱️ Your Screen Time (hours)",
        min_value=0.0,
        max_value=24.0,
        step=0.5,
        key="screen_time_input"
    )

    daily_limit = st.number_input(
        "⏰ Your Daily Screen Time Limit (hours)",
        min_value=1.0,
        max_value=24.0,
        value=5.0,
        step=0.5,
        key="daily_limit_input"
    )

    user_social_media = st.number_input(
        "📱 Your Social Media Time (hours)",
        min_value=0.0,
        max_value=24.0,
        step=0.5,
        key="social_media_input"
    )

    user_productivity = st.selectbox(
        "🎯 Your Productivity Level",
        [
            "Select Productivity Level",
            1,
            2,
            3,
            4,
            5
        ],
        key="productivity_input"
    )

    if st.button("🔍 Analyze My Usage"):

        if not isinstance(user_productivity, int):
            st.warning("⚠️ Please select your productivity level.")
        else:
            # Save the exact values used for this analysis.
            st.session_state["last_screen_time"] = user_screen_time
            st.session_state["last_daily_limit"] = daily_limit
            st.session_state["last_social_media"] = user_social_media
            st.session_state["last_productivity"] = user_productivity
                    # Send daily screen time limit to Flask API
        try:
            username = st.session_state.get("username", "default_user")

            requests.post(
                "https://focusguard-ai-9.onrender.com/set_limit",
                json={
                    "username": username,
                    "daily_limit": daily_limit
                },
                timeout=3
            )

        except Exception as e:
            print("Daily limit API connection error:", e)

        # Store the user's personal screen-time goal locally as well.
        save_user_goal(
            st.session_state["username"],
            daily_limit
        )

        st.session_state["analysis_done"] = True
        st.session_state["analysis_saved"] = False
        st.rerun()

    # ---------------------------------------------------------
    # ANALYSIS RESULT - SHOWN ONLY AFTER ANALYZE
    # ---------------------------------------------------------

    if st.session_state.get("analysis_done", False):

        screen_time = float(
            st.session_state.get("last_screen_time", 0)
        )
        social_media = float(
            st.session_state.get("last_social_media", 0)
        )
        productivity_value = int(
            st.session_state.get("last_productivity", 0)
        )
        saved_daily_limit = float(
            st.session_state.get("last_daily_limit", 5)
        )

        st.divider()
        st.subheader("📋 Your FocusGuard AI Result")

        # Waste time
        if social_media >= 4:
            st.error("🔴 High Waste Time")
        elif social_media >= 2:
            st.warning("🟡 Moderate Waste Time")
        else:
            st.success("🟢 Low Waste Time")

        # Screen time
        if screen_time >= 8:
            st.error("⚠️ High Screen Time")
        elif screen_time >= 5:
            st.warning("⚠️ Moderate Screen Time")
        else:
            st.success("✅ Healthy Screen Time")

        # Daily limit
        if screen_time > saved_daily_limit:
            exceeded = screen_time - saved_daily_limit
            st.error(
                f"🔴 Daily limit exceeded by {exceeded:.1f} hours."
            )
        else:
            st.success(
                "🟢 You are within your daily screen-time limit."
            )

        # Productivity
        if productivity_value <= 2:
            st.warning("📉 Your productivity level is low.")
        elif productivity_value == 3:
            st.info("📊 Your productivity level is average.")
        else:
            st.success("📈 Your productivity level is good.")

        # Usage dashboard
        st.subheader("📊 Your Usage Dashboard")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("⏱️ Screen Time", f"{screen_time:.1f} hrs")

        with col2:
            st.metric("📱 Social Media", f"{social_media:.1f} hrs")

        with col3:
            st.metric("🎯 Productivity", f"{productivity_value}/5")

        # Risk level
        st.subheader("🚦 FocusGuard AI Risk Level")

        if (
            social_media >= 4
            or screen_time >= 8
            or productivity_value <= 2
        ):
            risk_level = "🔴 HIGH RISK"
            st.error(
                "High risk detected. Your digital usage needs attention."
            )
        elif (
            social_media >= 2
            or screen_time >= 5
            or productivity_value == 3
        ):
            risk_level = "🟡 MODERATE RISK"
            st.warning(
                "Moderate risk detected. Try maintaining a better screen-time balance."
            )
        else:
            risk_level = "🟢 LOW RISK"
            st.success(
                "Low risk detected. Your digital habits are under control."
            )

        # Risk score
        st.subheader("🧠 FocusGuard AI Risk Score")

        risk_score = 0

        if screen_time >= 8:
            risk_score += 40
        elif screen_time >= 5:
            risk_score += 25
        else:
            risk_score += 10

        if social_media >= 4:
            risk_score += 40
        elif social_media >= 2:
            risk_score += 25
        else:
            risk_score += 10

        if productivity_value <= 2:
            risk_score += 20
        elif productivity_value == 3:
            risk_score += 10
        else:
            risk_score += 5

        st.metric("🧠 Risk Score", f"{risk_score}/100")
        st.progress(risk_score / 100)

        if risk_score >= 70:
            st.error("🔴 High Risk Score")
        elif risk_score >= 40:
            st.warning("🟡 Moderate Risk Score")
        else:
            st.success("🟢 Low Risk Score")

        # Save only once
        if not st.session_state.get("analysis_saved", False):
            save_analysis(
                st.session_state["username"],
                screen_time,
                social_media,
                productivity_value,
                risk_level,
                risk_score
            )
            st.session_state["analysis_saved"] = True

        st.session_state["last_risk_level"] = risk_level
        st.session_state["last_risk_score"] = risk_score

        # Recommendation
        st.subheader("💡 Personalized Recommendation")

        if social_media >= 4 or screen_time >= 8:
            st.write("🔴 Reduce unnecessary screen and social media usage.")
            st.write("• Set a daily screen-time limit.")
            st.write("• Take regular breaks.")
        elif social_media >= 2 or screen_time >= 5:
            st.write("🟡 Maintain a balanced screen-time routine.")
            st.write("• Reduce unnecessary scrolling.")
            st.write("• Keep focused study/work sessions.")
        else:
            st.write("🟢 Continue maintaining your healthy digital habits.")

elif page == "🎓 Smart Learning":
    show_page_header()

    # =========================================================
    # SMART LEARNING SUGGESTIONS
    # =========================================================

    st.divider()

    st.subheader(
        "💡 Smart Learning Suggestions"
    )

    user_profession = st.session_state.get(
        "profession",
        ""
    )


    suggestion_map = {

        "👨‍💻 IT / Software": [
            "🤖 Generative AI & Prompt Engineering",
            "☁️ Cloud Computing",
            "🔐 Cybersecurity",
            "🧠 Machine Learning",
            "⚙️ DevOps",
            "🌐 Advanced Web Development"
        ],

        "📊 Data / Analytics": [
            "🤖 Generative AI for Data Analysis",
            "🧠 Machine Learning",
            "🔬 Data Science",
            "☁️ Cloud Data Engineering",
            "🗄️ Advanced SQL",
            "📈 Advanced Power BI & Data Visualization"
        ],

        "👩‍🏫 Teacher / Education": [
            "🤖 AI in Education",
            "💻 Digital Teaching Tools",
            "📚 EdTech & Online Learning",
            "🧠 Learning Design",
            "🗣️ Public Speaking",
            "📊 Educational Data Analytics"
        ],

        "📈 Business / Marketing": [
            "🤖 AI for Business",
            "📊 Business Analytics",
            "📱 Advanced Digital Marketing",
            "🚀 Entrepreneurship",
            "🧠 Leadership & Management",
            "📈 Data-Driven Decision Making"
        ],

        "🎨 Design / Creative": [
            "🤖 AI for Creative Design",
            "🖥️ Advanced UI/UX Design",
            "🎬 Motion Graphics",
            "🎮 3D Design",
            "🎨 Design Thinking",
            "📱 Digital Content Creation"
        ],

        "🩺 Healthcare": [
            "🤖 AI in Healthcare",
            "💻 Health Informatics",
            "📊 Healthcare Data Analytics",
            "🏥 Digital Health Technology",
            "🧠 Healthcare Management",
            "🔐 Healthcare Data Security"
        ],

        "⚖️ Law": [
            "🤖 AI for Legal Research",
            "🔐 Cyber Law",
            "💻 Legal Technology",
            "📚 Advanced Legal Research",
            "🗣️ Legal Communication",
            "🔒 Data Privacy & Protection"
        ],

        "💰 Finance / Accounting": [
            "🤖 AI in Finance",
            "📊 Financial Analytics",
            "📈 Business Analytics",
            "💻 FinTech",
            "☁️ Cloud Accounting",
            "🔐 Financial Data Security"
        ],

        "🎓 Student": [
            "🤖 Generative AI",
            "📊 Data Analytics",
            "💻 Web Development",
            "🗣️ Communication & Public Speaking",
            "💼 Career & Interview Skills",
            "☁️ Cloud Computing"
        ]
    }


    field_suggestion_map = {
        "💻 Information Technology": [
            "🤖 Generative AI",
            "🐍 Python & Automation",
            "🌐 Advanced Web Development",
            "🔐 Cybersecurity",
            "☁️ Cloud Computing",
            "💼 Interview & Placement Skills"
        ],
        "📊 Data Science": [
            "🐍 Python for Data Science",
            "📈 Power BI & Data Visualization",
            "🧠 Machine Learning",
            "🗄️ SQL",
            "🤖 Generative AI for Data Analysis",
            "💼 Data Analyst Interview Skills"
        ],
        "💻 Computer Science": [
            "🐍 Python Programming",
            "🧠 Data Structures & Algorithms",
            "🌐 Web Development",
            "🗄️ Database Management",
            "🔐 Cybersecurity",
            "☁️ Cloud Computing"
        ],
        "🎓 BCA": [
            "🐍 Python",
            "🌐 Web Development",
            "🗄️ SQL & Databases",
            "📊 Data Analytics",
            "🤖 Generative AI",
            "💼 Career & Interview Skills"
        ],
        "⚙️ BTech / BE": [
            "🧠 Machine Learning",
            "☁️ Cloud Computing",
            "🔐 Cybersecurity",
            "💻 Software Development",
            "🤖 Generative AI",
            "💼 Technical Interview Skills"
        ],
        "🖥️ Computer Applications": [
            "🐍 Python",
            "🌐 Web Development",
            "🗄️ Database Management",
            "📊 Data Analytics",
            "☁️ Cloud Computing",
            "💼 Career Skills"
        ]
    }

    suggestions = suggestion_map.get(
        user_profession,
        field_suggestion_map.get(
            user_profession,
            [
                "🤖 Generative AI",
                "💻 Digital Skills",
                "📊 Data Analytics",
                "🗣️ Communication Skills",
                "☁️ Cloud Computing"
            ]
        )
    )


    for suggestion in suggestions:

        st.write(
            f"• {suggestion}"
        )


elif page == "🔔 Smart Reminders":
    show_page_header()

    # =========================================================
    # PERSONALIZED SMART REMINDER
    # =========================================================

    st.divider()
    st.subheader("🔔 Personalized Smart Reminder")
    st.caption(
        "FocusGuard chooses a useful reminder from your own latest analysis "
        "instead of giving every user the same reminder."
    )

    username = st.session_state["username"]
    personal_goal = get_user_goal(username, 5.0)
    recommendation = get_smart_reminder_recommendation(
        username,
        personal_goal
    )

    st.markdown("### ⭐ Recommended for You")

    r1, r2, r3 = st.columns(3)
    with r1:
        st.metric("🔔 Reminder", recommendation["activity"])
    with r2:
        st.metric("⏱️ Duration", f"{recommendation['duration']} min")
    with r3:
        st.metric("🎯 Priority", recommendation["priority"])

    st.info(
        f"💡 Why this reminder? {recommendation['reason']}"
    )

    if st.button("⭐ Set Recommended Reminder", use_container_width=True):
        save_reminder(
            username,
            recommendation["activity"],
            recommendation["duration"]
        )
        st.success(
            f"✅ Your personalized {recommendation['activity']} reminder was saved for {recommendation['duration']} minutes."
        )

    st.divider()
    st.subheader("⚙️ Choose Your Own Reminder")

    reminder_option = st.selectbox(
        "Choose an activity",
        [
            "No Reminder",
            "📚 Focus Session",
            "🚶 Take a Break",
            "💧 Drink Water",
            "🧘 Relax / Meditation",
            "🏃 Exercise",
            "📵 Stop Social Media",
            "😴 Sleep / Digital Detox"
        ],
        key="manual_reminder_option"
    )

    if reminder_option != "No Reminder":
        reminder_minutes = st.number_input(
            "Reminder duration (minutes)",
            min_value=1,
            max_value=120,
            value=5,
            step=1,
            key="manual_reminder_duration"
        )

        if st.button("🔔 Save Custom Reminder", key="save_custom_reminder"):
            save_reminder(
                username,
                reminder_option,
                reminder_minutes
            )
            st.success(
                f"✅ Custom reminder saved for {reminder_minutes} minutes."
            )

    saved_reminders = get_reminders(username)

    if not saved_reminders.empty:
        st.divider()
        st.subheader("📋 My Saved Reminders")

        reminder_table = saved_reminders.copy()
        reminder_table["date"] = pd.to_datetime(
            reminder_table["date"],
            errors="coerce"
        )
        reminder_table["date"] = reminder_table["date"].dt.strftime(
            "%d %b %Y, %I:%M %p"
        )
        reminder_table.columns = [
            "ID",
            "Reminder",
            "Duration (min)",
            "Saved On"
        ]

        st.dataframe(
            reminder_table,
            use_container_width=True,
            hide_index=True
        )


elif page == "📜 History":
    show_page_header()

    # =========================================================
    # MY USAGE HISTORY & PROGRESS
    # =========================================================

    st.divider()
    st.subheader("📈 My Usage Progress")
    st.caption(
        "Track your own saved analyses over time. This section uses only "
        "your FocusGuard AI results — not the survey dataset."
    )

    history = get_user_analysis(
        st.session_state["username"]
    )

    if history.empty:
        st.info(
            "📭 No previous analysis is available yet. "
            "Complete your first analysis from My Data to start tracking progress."
        )
    else:
        # Convert stored dates and show oldest analysis first for a timeline.
        history["date"] = pd.to_datetime(
            history["date"],
            errors="coerce"
        )
        history = history.dropna(subset=["date"]).sort_values("date")

        history_display = history.copy()
        history_display["Analysis"] = [
            f"Analysis {i + 1}"
            for i in range(len(history_display))
        ]

        st.subheader("📊 Screen Time & Social Media Trend")
        st.caption(
            "Higher line = more hours used. A downward line means your usage decreased "
            "compared with earlier analyses."
        )

        usage_chart = history_display.set_index("Analysis")[[
            "screen_time",
            "social_media_time"
        ]].rename(columns={
            "screen_time": "Screen Time (hours)",
            "social_media_time": "Social Media Time (hours)"
        })

        st.line_chart(usage_chart, use_container_width=True)

        st.subheader("🎯 Productivity Progress")
        st.caption(
            "Productivity is shown on your 1–5 scale. Higher values mean a higher "
            "self-reported productivity level."
        )

        productivity_chart = history_display.set_index("Analysis")[[
            "productivity"
        ]].rename(columns={
            "productivity": "Productivity Level (1–5)"
        })

        st.line_chart(
            productivity_chart,
            use_container_width=True
        )

        st.subheader("🧠 Risk Score Progress")
        st.caption(
            "Risk score is tracked from 0 to 100. A lower score means fewer risk points "
            "were detected by the FocusGuard rules."
        )

        risk_chart = history_display.set_index("Analysis")[[
            "risk_score"
        ]].rename(columns={
            "risk_score": "Risk Score (0–100)"
        })

        st.line_chart(
            risk_chart,
            use_container_width=True
        )

        # ---------------------------------------------------------
        # LATEST VS PREVIOUS ANALYSIS
        # ---------------------------------------------------------

        if len(history_display) >= 2:
            previous = history_display.iloc[-2]
            latest = history_display.iloc[-1]

            st.subheader("🔄 Latest vs Previous Analysis")
            st.caption(
                "This compares your most recent saved analysis with the analysis immediately before it."
            )

            def format_change(current, previous_value, unit=""):
                change = float(current) - float(previous_value)
                if change > 0:
                    return f"↑ {change:.1f}{unit} increase"
                if change < 0:
                    return f"↓ {abs(change):.1f}{unit} decrease"
                return "→ No change"

            c1, c2, c3, c4 = st.columns(4)

            with c1:
                screen_change = float(latest["screen_time"]) - float(previous["screen_time"])
                st.metric(
                    "⏱️ Screen Time",
                    f"{latest['screen_time']:.1f} hrs",
                    delta=f"{screen_change:+.1f} hrs"
                )

            with c2:
                social_change = float(latest["social_media_time"]) - float(previous["social_media_time"])
                st.metric(
                    "📱 Social Media",
                    f"{latest['social_media_time']:.1f} hrs",
                    delta=f"{social_change:+.1f} hrs"
                )

            with c3:
                productivity_change = float(latest["productivity"]) - float(previous["productivity"])
                st.metric(
                    "🎯 Productivity",
                    f"{int(latest['productivity'])}/5",
                    delta=f"{productivity_change:+.0f} level"
                )

            with c4:
                risk_change = float(latest["risk_score"]) - float(previous["risk_score"])
                st.metric(
                    "🧠 Risk Score",
                    f"{int(latest['risk_score'])}/100",
                    delta=f"{risk_change:+.0f} points"
                )

            st.markdown(
                f"**Previous:** {previous['date'].strftime('%d %b %Y, %I:%M %p')}  "
                f"  →  **Latest:** {latest['date'].strftime('%d %b %Y, %I:%M %p')}"
            )

            # Simple plain-language summary for quick understanding.
            if screen_change < 0:
                st.success(f"⏱️ Screen time decreased by {abs(screen_change):.1f} hours.")
            elif screen_change > 0:
                st.warning(f"⏱️ Screen time increased by {screen_change:.1f} hours.")
            else:
                st.info("⏱️ Screen time stayed the same.")

            if social_change < 0:
                st.success(f"📱 Social media time decreased by {abs(social_change):.1f} hours.")
            elif social_change > 0:
                st.warning(f"📱 Social media time increased by {social_change:.1f} hours.")
            else:
                st.info("📱 Social media time stayed the same.")

            if productivity_change > 0:
                st.success(f"🎯 Productivity increased by {productivity_change:.0f} level.")
            elif productivity_change < 0:
                st.warning(f"🎯 Productivity decreased by {abs(productivity_change):.0f} level.")
            else:
                st.info("🎯 Productivity stayed the same.")

        else:
            st.info(
                "ℹ️ You have one saved analysis. Complete another analysis later "
                "to see increase/decrease comparisons."
            )

        # ---------------------------------------------------------
        # SAVED ANALYSIS TABLE
        # ---------------------------------------------------------

        st.subheader("📋 My Saved Analysis Records")

        table = history_display[[
            "date",
            "screen_time",
            "social_media_time",
            "productivity",
            "risk_level",
            "risk_score"
        ]].copy()

        table.columns = [
            "Analysis Date",
            "Screen Time (hrs)",
            "Social Media (hrs)",
            "Productivity (1–5)",
            "Risk Level",
            "Risk Score"
        ]

        table["Analysis Date"] = table["Analysis Date"].dt.strftime(
            "%d %b %Y, %I:%M %p"
        )

        st.dataframe(
            table,
            use_container_width=True,
            hide_index=True
        )

elif page == "📥 Download":

    show_page_header()

    st.subheader("📥 Download Your Result")

    download_text = f"""
    FocusGuard AI
    Real-Time Digital Productivity Analysis System

    Username:
    {st.session_state["username"]}

    Role:
    {st.session_state["role"]}

    Profession:
    {st.session_state["profession"]}

    Automatic Phone Screen Time:
    {phone_screen_hours:.2f} hours

    Automatic Laptop Usage:
    {laptop_screen_hours:.2f} hours

    Combined Screen Time:
    {combined_screen_hours:.2f} hours

    Automatic Productivity App Time:
    {phone_productivity_hours:.2f} hours

    Automatic Productivity Level:
    {phone_productivity_level}
    """

    if st.session_state.get("analysis_done", False):

        download_text += f"""

    Personal Analysis

    Screen Time:
    {st.session_state.get("last_screen_time", 0):.1f} hours

    Social Media Time:
    {st.session_state.get("last_social_media", 0):.1f} hours

    Productivity:
    {st.session_state.get("last_productivity", 0)}/5

    Risk Level:
    {st.session_state.get("last_risk_level", "Not available")}

    Risk Score:
    {st.session_state.get("last_risk_score", 0)}/100
    """


    pdf_buffer = io.BytesIO()

    pdf = canvas.Canvas(pdf_buffer, pagesize=A4)

    width, height = A4
    y = height - 50

    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(50, y, "FocusGuard AI")
    y -= 25

    pdf.setFont("Helvetica", 11)
    pdf.drawString(
        50,
        y,
        "Real-Time Digital Productivity Analysis System"
    )
    y -= 35

    for line in download_text.strip().split("\n"):

        line = line.strip()

        if not line:
            y -= 10
            continue

        if y < 50:
            pdf.showPage()
            y = height - 50
            pdf.setFont("Helvetica", 11)

        pdf.drawString(50, y, line[:100])
        y -= 18

    pdf.save()

    pdf_buffer.seek(0)

    st.download_button(
        "📥 Download My Analysis PDF",
        data=pdf_buffer,
        file_name="FocusGuard_AI_Result.pdf",
        mime="application/pdf"
    )

elif page == "🔐 Developer":

    # =========================================================
    # DEVELOPER PANEL
    # =========================================================
    # This page is unreachable for Student/Employee sessions
    # because page is set to Developer only for role="Developer".

    if st.session_state.get("role") != "Developer":
        st.error("❌ Developer access denied.")
        st.stop()

    show_page_header()

    st.subheader("🔐 Developer Panel")

    st.success("✅ Developer access granted")

    if not df.empty:

        st.subheader("🔐 Developer Dataset View")

        st.dataframe(
            df,
            use_container_width=True
        )

    st.divider()

    st.subheader("🔐 All User Analysis")

    all_data = get_all_analysis()

    if not all_data.empty:

        st.dataframe(
            all_data,
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info("No analysis data available.")


# =========================================================
# NEXT / PREVIOUS PAGE NAVIGATION
# =========================================================

if page in all_page_options:

    current_index = all_page_options.index(page)

    st.divider()

    st.caption(
        f"Step {current_index + 1} of {len(all_page_options)}"
    )

    progress_value = (current_index + 1) / len(all_page_options)
    st.progress(progress_value)

    nav_col1, nav_col2 = st.columns(2)

    with nav_col1:
        if current_index > 0:
            if st.button(
                "← Previous",
                use_container_width=True,
                key=f"previous_page_{current_index}"
            ):
                st.session_state["_nav_target"] = all_page_options[
                    current_index - 1
                ]
                st.rerun()

    with nav_col2:
        next_allowed = (
            current_index < len(all_page_options) - 1
            and (
                page != "👤 My Data"
                or st.session_state.get("analysis_done", False)
            )
        )

        if next_allowed:
            if st.button(
                "Next →",
                use_container_width=True,
                key=f"next_page_{current_index}"
            ):
                st.session_state["_nav_target"] = all_page_options[
                    current_index + 1
                ]
                st.rerun()
        elif page == "👤 My Data":
            st.info(
                "Complete your analysis first, then click Next →"
            )
