import os

os.environ['FLASK_DEBUG'] = '1'
from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, jsonify
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, timedelta
import pytz

from helpers import apology, login_required

# Configure application
app = Flask(__name__)

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///bmhg.db")

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
    # Get current date and the start and end dates for the week
    today = datetime.today()
    start_of_week = today - timedelta(days=today.weekday())  # Monday of the current week
    end_of_week = start_of_week + timedelta(days=4)  # Friday of the current week

    # Query activities from database for the current week
    activities = db.execute(
        "SELECT activity, timestamp FROM activities WHERE user_id = ? AND timestamp BETWEEN ? AND ?",
        session["user_id"], start_of_week.strftime('%Y-%m-%d'), end_of_week.strftime('%Y-%m-%d')
    )

    # Process activities to calculate total shift hours for the week
    shift_hours = 0
    day_activities = {}

    for activity in activities:
        activity_date = activity["timestamp"].split(' ')[0]
        activity_time = datetime.strptime(activity["timestamp"], '%Y-%m-%d %H:%M:%S')

        if activity_date not in day_activities:
            day_activities[activity_date] = []
        day_activities[activity_date].append((activity["activity"], activity_time))

    for date, acts in day_activities.items():
        shifts = sorted(acts, key=lambda x: x[1])
        i = 0
        while i < len(shifts) - 1:
            if (shifts[i][0].lower() == 'shift-in' and
                shifts[i+1][0].lower() == 'shift-out' and
                shifts[i][1].date() == shifts[i+1][1].date()):
                shift_hours += (shifts[i+1][1] - shifts[i][1]).seconds / 3600.0
                i += 2  # Move to the next pair
            else:
                i += 1  # Move to the next activity

    shift_percentage = (shift_hours / 5) * 100 if shift_hours <= 5 else 100

    # Query top 3 users by shift hours (all-time)
    leaderboard = db.execute(
        "SELECT u.username, SUM((julianday(shift_out.timestamp) - julianday(shift_in.timestamp)) * 24) as hours "
        "FROM activities AS shift_in "
        "JOIN activities AS shift_out ON shift_in.user_id = shift_out.user_id AND shift_in.activity = 'Shift-In' "
        "AND shift_out.activity = 'Shift-Out' AND shift_in.id < shift_out.id "
        "AND date(shift_in.timestamp) = date(shift_out.timestamp) "
        "JOIN users u ON shift_in.user_id = u.id "
        "GROUP BY shift_in.user_id "
        "ORDER BY hours DESC "
        "LIMIT 3"
    )

    # Calculate weekly streak for the user
    streak_data = db.execute(
        "SELECT DISTINCT strftime('%W', timestamp) as week FROM activities WHERE user_id = ? AND activity = 'weekly meeting' ORDER BY week",
        session["user_id"]
    )
    current_streak = 0

    if streak_data:
        expected_week = int(streak_data[0]['week'])

        for record in streak_data:
            if int(record['week']) == expected_week:
                current_streak += 1
                expected_week += 1
            else:
                current_streak = 0
                break

    return render_template("index.html", activities=activities, shift_percentage=shift_percentage, leaderboard=leaderboard, current_streak=current_streak)



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
        
        # Get current UTC time
        utc_now = datetime.utcnow()

        # Convert UTC time to Jakarta time (same as Surabaya time)
        jakarta_tz = pytz.timezone('Asia/Jakarta')
        jakarta_now = utc_now.replace(tzinfo=pytz.utc).astimezone(jakarta_tz)
        formatted_time = jakarta_now.strftime("%Y-%m-%d %H:%M:%S")

        # Insert into activities table using timestamp column
        db.execute("INSERT INTO activities (user_id, activity, timestamp, user_lat, user_lon) VALUES (?, ?, ?, ?, ?)",
                   user_id, activity, formatted_time, user_lat, user_lon)
        
        flash(f"Attendance recorded at {formatted_time}!")
        return redirect("/")
    
    else:
        return render_template("attendance.html")

@app.errorhandler(404)
def not_found_error(error):
    return apology("Page doesn't exist.", 404)
    
if __name__ == "__main__":
    app.run(debug=True)