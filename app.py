# Library standar
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta

# Library pihak ketiga
import pytz
from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

# Library lokal
from helpers import apology, login_required, clear_unmatched_shift_ins, calculate_shift_hours, calculate_total_shift_hours, check_weekly_attendance, calculate_current_streak

# Hot Reload
os.environ['FLASK_DEBUG'] = '1'

# Konfigurasi nama aplikasi
app = Flask(__name__)

# Keperluan hosting
application = app

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Password admin
load_dotenv() 
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

# Konfigurasi Library CS50 untuk akses database SQLite
db = SQL("sqlite:///bmhg.db")


# Fungsi after_request ini mencegah caching dari respon HTTP oleh browser atau proxy
@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    clear_unmatched_shift_ins()

    activities_shown = db.execute(
        "SELECT activity, timestamp FROM activities WHERE user_id = ? ORDER BY timestamp DESC LIMIT 5",
        session["user_id"]
    )

    activities = db.execute(
        "SELECT activity, timestamp FROM activities WHERE user_id = ? ORDER BY timestamp DESC",
        session["user_id"]
    )

    users_shift_in = db.execute(
        """
        SELECT u.username FROM users u
        JOIN activities a1 ON u.id = a1.user_id
        LEFT JOIN activities a2 ON u.id = a2.user_id 
                                AND a2.activity = 'Shift-Out' 
                                AND a2.timestamp > a1.timestamp
        WHERE a1.activity = 'Shift-In' 
        AND a2.id IS NULL
        """
    )

    usernames_shift_in = [user["username"] for user in users_shift_in]

    today = datetime.now()
    start_of_this_week = (today - timedelta(days=today.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_this_week = (start_of_this_week + timedelta(days=4)).replace(hour=23, minute=59, second=59, microsecond=999999)
    start_of_last_week = start_of_this_week - timedelta(days=7)
    end_of_last_week = end_of_this_week - timedelta(days=7)

    shift_hours_this_week = calculate_shift_hours(activities, start_of_this_week, end_of_this_week)
    shift_hours_last_week = calculate_shift_hours(activities, start_of_last_week, end_of_last_week)

    if shift_hours_last_week < 5 or not check_weekly_attendance(activities, start_of_last_week, end_of_last_week):
        badge_class = "badge rounded-pill text-bg-warning"
    else:
        badge_class = "badge rounded-pill text-bg-success"

    if shift_hours_this_week < 5 or not check_weekly_attendance(activities, start_of_this_week, end_of_this_week):
        if shift_hours_last_week < 5 or not check_weekly_attendance(activities, start_of_last_week, end_of_last_week):
            badge_class = "badge rounded-pill text-bg-danger"
        else:
            badge_class = "badge rounded-pill text-bg-warning"

    shift_percentage = min((shift_hours_this_week / 5) * 100, 100)

    users = db.execute("SELECT id, username FROM users")

    user_shift_hours = {}

    for user in users:
        user_id = user["id"]
        user_activities = db.execute(
            "SELECT activity, timestamp FROM activities WHERE user_id = ? ORDER BY timestamp ASC",
            user_id
        )

        total_shift_hours = calculate_total_shift_hours(user_activities)
        user_shift_hours[user["username"]] = total_shift_hours

    top_users = sorted(user_shift_hours.items(), key=lambda x: x[1], reverse=True)[:3]
    leaderboard = [{"username": user[0], "hours": user[1]} for user in top_users]

    streak_data = db.execute(
        """
        SELECT 
            user_id, 
            strftime('%Y', timestamp) as year, 
            strftime('%W', timestamp) as week
        FROM 
            activities 
        WHERE 
            activity = 'Weekly Meeting' 
        GROUP BY 
            user_id, year, week
        ORDER BY 
            user_id, year, week
        """
    )

    current_streak = calculate_current_streak(streak_data, session["user_id"])

    return render_template("index.html", activities_shown=activities_shown, activities=activities, 
                           shift_percentage=shift_percentage, leaderboard=leaderboard, 
                           current_streak=current_streak, badge_class=badge_class,
                           usernames_shift_in=usernames_shift_in)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    session.clear()

    if request.method == "POST":
        if not request.form.get("username"):
            return apology("must provide username", 400)
        elif not request.form.get("password"):
            return apology("must provide password", 400)
        elif not request.form.get("confirmation"):
            return apology("must confirm password", 400)
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("password do not match", 400)

        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        if len(rows) != 0:
            return apology("username already exists", 400)

        db.execute("INSERT INTO users (username, hash) VALUES(?, ?)",
                   request.form.get("username"), generate_password_hash(request.form.get("password")))

        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        session["user_id"] = rows[0]["id"]

        return redirect("/")

    else:
        return render_template("register.html")


@app.route("/attendance", methods=["GET", "POST"])
@login_required
def attendance():
    if request.method == "POST":
        # Get form data
        activity = request.form.get("symbol")
        user_id = session["user_id"]
        user_lat = request.form.get("user_lat")  # Added hidden input in attendance.html
        user_lon = request.form.get("user_lon")  # Added hidden input in attendance.html

        if not activity or activity == "Select an activity":
            flash("Please select a valid activity.")
            return redirect("/attendance")
        
        # Get current UTC time
        utc_now = datetime.utcnow()

        # Convert UTC time to Jakarta time (same as Surabaya time)
        jakarta_tz = pytz.timezone('Asia/Jakarta')
        jakarta_now = utc_now.replace(tzinfo=pytz.utc).astimezone(jakarta_tz)
        formatted_time = jakarta_now.strftime("%Y-%m-%d %H:%M:%S")

        # Insert into activities table using timestamp column
        db.execute("INSERT INTO activities (user_id, activity, timestamp, user_lat, user_lon) VALUES (?, ?, ?, ?, ?)",
                   user_id, activity, formatted_time, user_lat, user_lon)
        
        flash(f"Submitted!")
        return redirect("/")
    
    else:
        return render_template("attendance.html")
    

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        if request.form.get("admin_password") == ADMIN_PASSWORD:
            session["admin_authenticated"] = True
            return redirect("/admin")
        else:
            flash("Invalid admin password!")
            return redirect("/admin")
    else:
        if not session.get("admin_authenticated"):
            return render_template("admin_login.html")
        
        # Fetch usernames
        users = db.execute("SELECT id, username FROM users")

        # Determine the start of the week (Monday) for each of the last 8 weeks
        today = datetime.today()
        current_start_of_week = today - timedelta(days=today.weekday())  # Monday of the current week
        weeks = [(current_start_of_week - timedelta(days=7 * i)).strftime('%Y-%m-%d') for i in range(8)]

        # Create a dictionary to store user data
        user_data = {}
        for user in users:
            user_id = user["id"]
            username = user["username"]

            user_data[username] = {
                "attendance": [],
                "shift_hours": []
            }

            for week_start in weeks:
                week_end = (datetime.strptime(week_start, '%Y-%m-%d') + timedelta(days=4)).strftime('%Y-%m-%d 23:59:59')

                # Check for weekly meeting attendance
                meeting_count = db.execute(
                    "SELECT COUNT(*) as count FROM activities WHERE user_id = ? AND activity = 'Weekly Meeting' AND timestamp BETWEEN ? AND ?",
                    user_id, week_start, week_end
                )[0]["count"]

                user_data[username]["attendance"].append(meeting_count > 0)

                # Check for shift hours
                shifts = db.execute(
                    "SELECT activity, timestamp FROM activities WHERE user_id = ? AND timestamp BETWEEN ? AND ?",
                    user_id, week_start, week_end
                )

                shift_hours = 0
                day_activities = {}

                for shift in shifts:
                    shift_date = shift["timestamp"].split(' ')[0]
                    shift_time = datetime.strptime(shift["timestamp"], '%Y-%m-%d %H:%M:%S')

                    if shift_date not in day_activities:
                        day_activities[shift_date] = []
                    day_activities[shift_date].append((shift["activity"], shift_time))

                for date, acts in day_activities.items():
                    sorted_acts = sorted(acts, key=lambda x: x[1])
                    i = 0
                    while i < len(sorted_acts) - 1:
                        if (sorted_acts[i][0].lower() == 'shift-in' and
                            sorted_acts[i + 1][0].lower() == 'shift-out' and
                            sorted_acts[i][1].date() == sorted_acts[i + 1][1].date()):
                            shift_hours += (sorted_acts[i + 1][1] - sorted_acts[i][1]).seconds / 3600.0
                            i += 2  # Move to the next pair
                        else:
                            i += 1  # Move to the next activity

                user_data[username]["shift_hours"].append(shift_hours >= 5)

        # Generate week labels
        week_labels = [(datetime.strptime(week, '%Y-%m-%d').strftime('%d/%m') + " - " +
                        (datetime.strptime(week, '%Y-%m-%d') + timedelta(days=4)).strftime('%d/%m')) for week in weeks]

        return render_template("admin.html", user_data=user_data, week_labels=reversed(week_labels))


@app.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        # Get form data
        username = request.form.get("username")
        new_password = request.form.get("new_password")
        confirmation = request.form.get("confirmation")

        # Ensure the username is correct
        user = db.execute("SELECT * FROM users WHERE username = ?", username)
        if not user:
            flash("Username not found.")
            return redirect("/change_password")

        # Ensure new password and confirmation match
        if new_password != confirmation:
            flash("Passwords do not match.")
            return redirect("/change_password")

        # Hash the new password
        hash = generate_password_hash(new_password)

        # Update the password in the database
        db.execute("UPDATE users SET hash = ? WHERE username = ?", hash, username)

        flash("Password successfully updated!")
        return redirect("/")

    # If GET request, render the change password form
    return render_template("change_password.html")


@app.errorhandler(404)
def not_found_error(error):
    return apology("Page doesn't exist.", 404)


if __name__ == "__main__":
    app.run(debug=True)