import streamlit as st
import pandas as pd
import sqlite3
import os
import time
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
            username,
            hashed_password,
            email,
            role,
            profession
        ))

        conn.commit()

        return True

    except sqlite3.IntegrityError:

        return False

    finally:

        conn.close()

def check_user(username, password):

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

        # -------------------------------------------------
        # PHONE DATA
        # -------------------------------------------------

        phone_df = pd.read_sql_query(
            """
            SELECT
                COALESCE(SUM(screen_time), 0)
                    AS screen_time,

                COALESCE(SUM(social_media_time), 0)
                    AS social_media_time,

                COALESCE(SUM(productivity_time), 0)
                    AS productivity_time

            FROM mobile_usage
            """,
            conn
        )

        phone_screen = float(
            phone_df.iloc[0]["screen_time"]
        )

        phone_social = float(
            phone_df.iloc[0]["social_media_time"]
        )

        phone_productivity = float(
            phone_df.iloc[0]["productivity_time"]
        )


        # -------------------------------------------------
        # PHONE PRODUCTIVITY LEVEL
        # -------------------------------------------------

        if phone_productivity >= 120:

            phone_productivity_level = "HIGH"

        elif phone_productivity >= 60:

            phone_productivity_level = "MODERATE"

        else:

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

        username = st.text_input(
            "👤 Username"
        )

        email = st.text_input(
            "📧 Email"
        )

        password = st.text_input(
            "🔐 Password",
            type="password"
        )

        confirm_password = st.text_input(
            "🔑 Confirm Password",
            type="password"
        )

        role = st.selectbox(
            "Choose your profile",
            [
                "🎓 Student",
                "💼 Employee"
            ]
        )

        profession = st.selectbox(
            "💼 Choose your profession",
            [
                "Select profession",
                "👨‍💻 IT / Software",
                "📊 Data / Analytics",
                "👩‍🏫 Teacher / Education",
                "📈 Business / Marketing",
                "🎨 Design / Creative",
                "🩺 Healthcare",
                "⚖️ Law",
                "💰 Finance / Accounting",
                "🎓 Student",
                "🧑‍💼 Other"
            ]
        )


        if st.button(
            "🚀 Create Account"
        ):

            if not username.strip():

                st.warning(
                    "⚠️ Please enter username."
                )

            elif not email.strip():

                st.warning(
                    "⚠️ Please enter email."
                )

            elif "@" not in email:

                st.warning(
                    "⚠️ Please enter a valid email."
                )

            elif not password:

                st.warning(
                    "⚠️ Please enter password."
                )

            elif password != confirm_password:

                st.error(
                    "❌ Passwords do not match."
                )

            elif profession == "Select profession":

                st.warning(
                    "⚠️ Please select your profession."
                )

            else:

                selected_role = (
                    "Student"
                    if role == "🎓 Student"
                    else "Employee"
                )

                success = create_user(
                    username.strip(),
                    password,
                    email.strip(),
                    selected_role,
                    profession
                )

                if success:

                    st.success(
                        "✅ Account created successfully! "
                        "Now login."
                    )

                else:

                    st.error(
                        "❌ Username already exists."
                    )


    # =====================================================
    # LOGIN
    # =====================================================

    else:

        st.subheader(
            "Welcome Back 👋"
        )

        st.write(
            "Sign in to continue to your FocusGuard AI dashboard."
        )

        username = st.text_input(
            "👤 Username"
        )

        password = st.text_input(
            "🔐 Password",
            type="password"
        )


        if st.button(
            "🔓 Login"
        ):

            if not username.strip() or not password:

                st.warning(
                    "⚠️ Please enter username and password."
                )

            else:

                user = check_user(
                    username.strip(),
                    password
                )

                if user:

                    st.session_state["logged_in"] = True

                    st.session_state["username"] = user[1]

                    st.session_state["role"] = user[4]

                    st.session_state["profession"] = (
                        user[5]
                        if user[5]
                        else ""
                    )

                    st.success(
                        "✅ Login successful!"
                    )

                    st.rerun()

                else:

                    st.error(
                        "❌ Invalid username or password."
                    )

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

st.sidebar.divider()

# =========================================================
# ACCESS MODE
# =========================================================

access_mode = st.sidebar.radio(
    "🔐 Access Mode",
    [
        "👤 User",
        "🔐 Developer"
    ]
)

st.sidebar.divider()

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

# Developer mode
if access_mode == "🔐 Developer":

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


    # =========================================================
    # PRODUCTIVITY DATASET ANALYSIS
    # =========================================================

    if (
        not df.empty
        and
        "Productivity_Level" in df.columns
    ):

        st.subheader(
            "🎯 Productivity Level Analysis"
        )

        productivity_counts = (
            df["Productivity_Level"]
            .value_counts()
        )

        st.bar_chart(
            productivity_counts
        )

        most_common_productivity = (
            productivity_counts.idxmax()
        )

        st.success(
            f"🎯 Most common productivity level: "
            f"{most_common_productivity}"
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

    if st.button("📱💻 Use Automatic Device Data"):

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
                "http://127.0.0.1:5000/set_limit",
                json={
                    "username": username,
                    "daily_limit": daily_limit
                },
                timeout=3
            )

        except Exception as e:
            print("Daily limit API connection error:", e)
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


    suggestions = suggestion_map.get(
        user_profession,
        [
            "🤖 Generative AI",
            "💻 Digital Skills",
            "📊 Data Analytics",
            "🗣️ Communication Skills",
            "☁️ Cloud Computing"
        ]
    )


    for suggestion in suggestions:

        st.write(
            f"• {suggestion}"
        )


elif page == "🔔 Smart Reminders":
    show_page_header()

    # =========================================================
    # SMART REMINDER
    # =========================================================

    st.divider()

    st.subheader(
        "🔔 Smart Reminder"
    )

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
        ]
    )


    if reminder_option != "No Reminder":

        reminder_minutes = st.number_input(
            "Reminder duration (minutes)",
            min_value=1,
            max_value=120,
            value=5,
            step=1
        )


        if st.button(
            "🔔 Set Reminder"
        ):

            save_reminder(
                st.session_state["username"],
                reminder_option,
                reminder_minutes
            )

            st.success(
                f"✅ Reminder saved for "
                f"{reminder_minutes} minutes."
            )


elif page == "📜 History":
    show_page_header()

    # =========================================================
    # MY PREVIOUS ANALYSIS
    # =========================================================

    st.divider()

    st.subheader(
        "📊 My Previous Analysis"
    )

    previous_data = get_user_analysis(
        st.session_state["username"]
    )


    if not previous_data.empty:

        st.dataframe(
            previous_data,
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info(
            "No saved analysis yet."
        )


    # =========================================================

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

    show_page_header()

    st.subheader("🔐 Developer Panel")

    developer_password = st.text_input(
        "Developer Password",
        type="password"
    )

    if developer_password == "FocusGuard@123":

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

    elif developer_password:
        st.error("❌ Incorrect password")


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
