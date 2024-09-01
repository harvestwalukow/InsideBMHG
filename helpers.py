import pytz
from datetime import datetime

from cs50 import SQL

from flask import redirect, render_template, session
from functools import wraps


db = SQL("sqlite:///bmhg.db")


def apology(message, code=400):
    """Render message as an apology to user."""

    def escape(s):
        """
        Escape special characters.

        https://github.com/jacebrowning/memegen#special-characters
        """
        for old, new in [
            ("-", "--"),
            (" ", "-"),
            ("_", "__"),
            ("?", "~q"),
            ("%", "~p"),
            ("#", "~h"),
            ("/", "~s"),
            ('"', "''"),
        ]:
            s = s.replace(old, new)
        return s

    return render_template("apology.html", top=code, bottom=escape(message)), code


def login_required(f):
    """
    Decorate routes to require login.

    https://flask.palletsprojects.com/en/latest/patterns/viewdecorators/
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)

    return decorated_function


# UNTUK INDEX.HTML

def clear_unmatched_shift_ins():
    jakarta_tz = pytz.timezone('Asia/Jakarta')
    now = datetime.now(jakarta_tz)
    reset_time = now.replace(hour=23, minute=59, second=0, microsecond=0)
    
    # Check if the current time is exactly or after 23:59 PM WIB
    if now >= reset_time:
        # Find Shift-In entries that do not have a corresponding Shift-Out
        unmatched_shift_ins = db.execute("""
            SELECT a1.id FROM activities a1
            LEFT JOIN activities a2 ON a1.user_id = a2.user_id
                                     AND a2.activity = 'Shift-Out'
                                     AND a2.timestamp > a1.timestamp
            WHERE a1.activity = 'Shift-In' AND a2.id IS NULL
        """)

        # Delete unmatched Shift-In entries
        if unmatched_shift_ins:
            shift_in_ids = [entry['id'] for entry in unmatched_shift_ins]
            db.execute("DELETE FROM activities WHERE id IN (?)", shift_in_ids)
            print(f"Deleted {len(shift_in_ids)} unmatched Shift-In entries.")

def calculate_shift_hours(activities, start_date, end_date):
    shift_hours = 0
    day_activities = {}

    for activity in activities:
        activity_time = datetime.strptime(activity["timestamp"], '%Y-%m-%d %H:%M:%S')
        if start_date <= activity_time <= end_date and activity["activity"] in ["Shift-In", "Shift-Out"]:
            activity_date = activity_time.date()
            if activity_date not in day_activities:
                day_activities[activity_date] = []
            day_activities[activity_date].append((activity["activity"], activity_time))
    
    for date, acts in day_activities.items():
        shifts = sorted(acts, key=lambda x: x[1])
        i = 0
        while i < len(shifts) - 1:
            if (shifts[i][0] == 'Shift-In' and
                shifts[i + 1][0] == 'Shift-Out' and
                shifts[i][1].date() == shifts[i + 1][1].date()):
                shift_hours += (shifts[i + 1][1] - shifts[i][1]).seconds / 3600.0
                i += 2
            else:
                i += 1

    return round(shift_hours, 2)

def calculate_total_shift_hours(activities):
    total_shift_hours = 0
    day_activities = {}

    for activity in activities:
        activity_time = datetime.strptime(activity["timestamp"], '%Y-%m-%d %H:%M:%S')
        if activity["activity"] in ["Shift-In", "Shift-Out"]:
            activity_date = activity_time.date()
            if activity_date not in day_activities:
                day_activities[activity_date] = []
            day_activities[activity_date].append((activity["activity"], activity_time))

    for date, acts in day_activities.items():
        shifts = sorted(acts, key=lambda x: x[1])
        i = 0
        while i < len(shifts) - 1:
            if (shifts[i][0] == 'Shift-In' and
                shifts[i + 1][0] == 'Shift-Out' and
                shifts[i][1].date() == shifts[i + 1][1].date()):
                total_shift_hours += (shifts[i + 1][1] - shifts[i][1]).seconds / 3600.0
                i += 2
            else:
                i += 1

    return round(total_shift_hours, 2)

def check_weekly_attendance(activities, start_date, end_date):
    for activity in activities:
        activity_time = datetime.strptime(activity["timestamp"], '%Y-%m-%d %H:%M:%S')
        if start_date <= activity_time <= end_date and activity["activity"] == 'Weekly Meeting':
            return True
    return False

def calculate_current_streak(streak_data, user_id):
    streaks = {}
    for record in streak_data:
        if record['user_id'] not in streaks:
            streaks[record['user_id']] = []
        streaks[record['user_id']].append((int(record['year']), int(record['week'])))

    user_streaks = streaks.get(user_id, [])
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

        return longest_streak
    return 0
