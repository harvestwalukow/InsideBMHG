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
application = app

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

ADMIN_PASSWORD = "Admin#1234"  # Change this to your desired admin password

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
    # Query all activities from the database
    activities_shown = db.execute(
        "SELECT activity, timestamp FROM activities WHERE user_id = ? ORDER BY timestamp DESC LIMIT 5",
        session["user_id"]
    )

    activities = db.execute(
        "SELECT activity, timestamp FROM activities WHERE user_id = ? ORDER BY timestamp DESC",
        session["user_id"]
    )

    # Query users who are currently Shift-In but not yet Shift-Out
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

    # Process activities to calculate total shift hours for the week
    shift_hours = 0
    day_activities = {}

    # Define the start and end of the current week (Monday to Friday)
    today = datetime.now()
    start_of_week = (today - timedelta(days=today.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)  # Monday
    end_of_week = (start_of_week + timedelta(days=4)).replace(hour=23, minute=59, second=59, microsecond=999999)  # Friday

    print(f"Start of week: {start_of_week}")
    print(f"End of week: {end_of_week}")

    # Filter activities within the current week
    for activity in activities:
        activity_time = datetime.strptime(activity["timestamp"], '%Y-%m-%d %H:%M:%S')
        if start_of_week <= activity_time <= end_of_week and activity["activity"] in ["Shift-In", "Shift-Out"]:
            activity_date = activity_time.date()
            if activity_date not in day_activities:
                day_activities[activity_date] = []
            day_activities[activity_date].append((activity["activity"], activity_time))
    
    print(f"Filtered activities: {day_activities}")

    # Calculate shift hours
    for date, acts in day_activities.items():
        shifts = sorted(acts, key=lambda x: x[1])
        i = 0
        while i < len(shifts) - 1:
            if (shifts[i][0] == 'Shift-In' and
                shifts[i + 1][0] == 'Shift-Out' and
                shifts[i][1].date() == shifts[i + 1][1].date()):
                shift_hours += (shifts[i + 1][1] - shifts[i][1]).seconds / 3600.0
                i += 2  # Move to the next pair
            else:
                i += 1  # Move to the next activity

    print(f"Total shift hours: {shift_hours}")

    shift_percentage = min((shift_hours / 5) * 100, 100)
    print(f"Shift percentage: {shift_percentage}")

    # Query all users
    users = db.execute("SELECT id, username FROM users")

    user_shift_hours = {}

    for user in users:
        user_id = user["id"]
        user_activities = db.execute(
            "SELECT activity, timestamp FROM activities WHERE user_id = ? ORDER BY timestamp ASC",
            user_id
        )

        # Calculate total shift hours for the user
        total_shift_hours = 0
        user_day_activities = {}

        for activity in user_activities:
            activity_time = datetime.strptime(activity["timestamp"], '%Y-%m-%d %H:%M:%S')
            if activity["activity"] in ["Shift-In", "Shift-Out"]:
                activity_date = activity_time.date()
                if activity_date not in user_day_activities:
                    user_day_activities[activity_date] = []
                user_day_activities[activity_date].append((activity["activity"], activity_time))

        for date, acts in user_day_activities.items():
            shifts = sorted(acts, key=lambda x: x[1])
            i = 0
            while i < len(shifts) - 1:
                if (shifts[i][0] == 'Shift-In' and
                    shifts[i + 1][0] == 'Shift-Out' and
                    shifts[i][1].date() == shifts[i + 1][1].date()):
                    total_shift_hours += (shifts[i + 1][1] - shifts[i][1]).seconds / 3600.0
                    i += 2  # Move to the next pair
                else:
                    i += 1  # Move to the next activity

        user_shift_hours[user["username"]] = total_shift_hours

    # Sort users by total shift hours and select top 3
    top_users = sorted(user_shift_hours.items(), key=lambda x: x[1], reverse=True)[:3]
    leaderboard = [{"username": user[0], "hours": user[1]} for user in top_users]

    print(f"Leaderboard: {leaderboard}")

    # Calculate weekly streak for the user
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

    # Find the current streak for the logged-in user
    current_streak = 0
    if streak_data:
        streaks = {}
        for record in streak_data:
            user_id = record['user_id']
            year = int(record['year'])
            week = int(record['week'])
            if user_id not in streaks:
                streaks[user_id] = []
            streaks[user_id].append((year, week))

        user_streaks = streaks.get(session["user_id"], [])
        if user_streaks:
            longest_streak = 1
            current_streak = 1
            for i in range(1, len(user_streaks)):
                prev_year, prev_week = user_streaks[i-1]
                curr_year, curr_week = user_streaks[i]
                if (curr_year == prev_year and curr_week == prev_week + 1) or (curr_year == prev_year + 1 and prev_week == 52 and curr_week == 0):
                    current_streak += 1
                    longest_streak = max(longest_streak, current_streak)
                else:
                    current_streak = 1

            current_streak = longest_streak

    return render_template("index.html", activities_shown=activities_shown, activities=activities, shift_percentage=shift_percentage, leaderboard=leaderboard, current_streak=current_streak, usernames_shift_in=usernames_shift_in)



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



@app.errorhandler(404)
def not_found_error(error):
    return apology("Page doesn't exist.", 404)
    
if __name__ == "__main__":
    app.run(debug=True)