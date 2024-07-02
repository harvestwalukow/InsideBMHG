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
    # Query activities from database
    activities = db.execute("SELECT activity, timestamp FROM activities WHERE user_id = ?", session["user_id"])

    # Calculate the start and end of the current week
    today = datetime.now().date()
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    # Filter activities within the current week
    weekly_activities = [activity for activity in activities if start_of_week <= datetime.strptime(activity["timestamp"], '%Y-%m-%d %H:%M:%S').date() <= end_of_week]

    # Calculate total seconds available for 100% progress (5 hours)
    total_seconds_for_100_percent = 5 * 3600

    # Calculate total time spent in seconds
    total_seconds_spent = sum([(datetime.strptime(activity["timestamp"], '%Y-%m-%d %H:%M:%S') - datetime.combine(start_of_week, datetime.min.time())).total_seconds() for activity in weekly_activities])

    # Calculate weekly percentage
    if total_seconds_for_100_percent > 0:
        weekly_percentage = (total_seconds_spent / total_seconds_for_100_percent) * 100
    else:
        weekly_percentage = 0

    return render_template("index.html", activities=activities, weekly_percentage=weekly_percentage)

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
    
if __name__ == "__main__":
    app.run(debug=True)