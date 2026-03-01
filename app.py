from flask import session, flash
import bcrypt
from flask import Flask, render_template, request, redirect, url_for
from db import execute_query, get_connection
import random
import string
from datetime import datetime
from functools import wraps

# Login Required
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function


# User Role Required
def user_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'role' not in session or session['role'] != 'USER':
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function


# Admin Role Required
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'role' not in session or session['role'] != 'ADMIN':
            return "Unauthorized Access", 403
        return f(*args, **kwargs)
    return decorated_function

app = Flask(__name__)

app.secret_key = "super_secret_key"

# -------------------------
# Utility: Generate PNR
# -------------------------
def generate_pnr():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


# -------------------------
# Home Page
# -------------------------
@app.route('/')
def home():
    return render_template('home.html')


# -------------------------
# Search Flights
# -------------------------
@app.route('/search', methods=['POST'])
@user_required
def search():
    source = request.form['source']
    destination = request.form['destination']
    date = request.form['date']

    query = """
        SELECT fs.schedule_id,
               f.flight_number,
               fs.departure_time,
               fs.arrival_time,
               fs.price
        FROM flight_schedules fs
        JOIN flights f ON fs.flight_id = f.flight_id
        JOIN airports a1 ON f.departure_airport = a1.airport_id
        JOIN airports a2 ON f.arrival_airport = a2.airport_id
        WHERE a1.city = %s
        AND a2.city = %s
        AND DATE(fs.departure_time) = %s
        ORDER BY fs.departure_time;
    """

    flights = execute_query(query, (source, destination, date), fetchall=True)

    return render_template('results.html', flights=flights)


# -------------------------
# Booking Page
# -------------------------
@app.route('/book/<int:schedule_id>')
@user_required
def book(schedule_id):
    query = """
        SELECT s.seat_id,
               s.seat_number,
               CASE WHEN sa.seat_id IS NOT NULL THEN TRUE ELSE FALSE END AS is_booked
        FROM seats s
        LEFT JOIN seat_allocations sa
        ON s.seat_id = sa.seat_id
        AND sa.schedule_id = %s
        WHERE s.aircraft_id = (
            SELECT aircraft_id
            FROM flight_schedules
            WHERE schedule_id = %s
        )
        ORDER BY s.seat_number;
    """

    seats = execute_query(query, (schedule_id, schedule_id), fetchall=True)

    return render_template('booking.html', schedule_id=schedule_id, seats=seats)

# -------------------------
# Confirm Booking
# -------------------------
@app.route('/confirm', methods=['POST'])
@user_required
def confirm():

    schedule_id = request.form['schedule_id']
    passenger_count = int(request.form['passenger_count'])

    pnr = generate_pnr()
    conn = get_connection()

    try:
        with conn:
            with conn.cursor() as cur:

                # 1️⃣ Insert booking first
                cur.execute("""
                    INSERT INTO bookings(pnr, schedule_id, user_id)
                    VALUES (%s, %s, %s)
                    RETURNING booking_id;
                """, (pnr, schedule_id, session['user_id']))

                booking_id = cur.fetchone()[0]

                # 2️⃣ Insert passengers & allocate seats
                for i in range(1, passenger_count + 1):

                    first_name = request.form[f'first_name_{i}']
                    last_name = request.form[f'last_name_{i}']
                    email = request.form[f'email_{i}']
                    seat_id = request.form[f'seat_id_{i}']

                    # Insert passenger
                    cur.execute("""
                        INSERT INTO passengers(first_name, last_name, email, booking_id)
                        VALUES (%s,%s,%s,%s)
                        RETURNING passenger_id;
                    """, (first_name, last_name, email, booking_id))

                    passenger_id = cur.fetchone()[0]

                    # Allocate seat
                    cur.execute("""
                        INSERT INTO seat_allocations(booking_id, schedule_id, seat_id)
                        VALUES (%s,%s,%s);
                    """, (booking_id, schedule_id, seat_id))

        return render_template('confirmation.html', pnr=pnr)

    except Exception as e:
        conn.rollback()
        return f"Booking failed: {str(e)}", 400

    finally:
        conn.close()
        
@app.route('/cancel')
@user_required
def cancel_page():
    return render_template('cancel.html')

@app.route('/process_cancel', methods=['POST'])
@user_required
def process_cancel():
    pnr = request.form['pnr']

    conn = get_connection()

    try:
        with conn:
            with conn.cursor() as cur:

                # Lock booking row
                cur.execute("""
                    SELECT booking_id, schedule_id, status
                    FROM bookings
                    WHERE pnr = %s
                    FOR UPDATE;
                """, (pnr,))

                booking = cur.fetchone()

                if not booking:
                    return "Invalid PNR", 404

                booking_id, schedule_id, status = booking

                if status == 'CANCELLED':
                    return "Booking already cancelled", 400

                # Update booking status
                cur.execute("""
                    UPDATE bookings
                    SET status = 'CANCELLED'
                    WHERE booking_id = %s;
                """, (booking_id,))

                # Remove seat allocation
                cur.execute("""
                    DELETE FROM seat_allocations
                    WHERE booking_id = %s;
                """, (booking_id,))

        return f"Booking {pnr} successfully cancelled."

    except Exception as e:
        conn.rollback()
        return f"Error during cancellation: {str(e)}", 500

    finally:
        conn.close()

@app.route('/admin')
@admin_required
def admin_dashboard():

    # Total Revenue
    revenue_query = """
        SELECT COALESCE(SUM(fs.price),0) AS total_revenue
        FROM bookings b
        JOIN flight_schedules fs ON b.schedule_id = fs.schedule_id
        WHERE b.status = 'CONFIRMED';
    """

    revenue = execute_query(revenue_query, fetchone=True)

    # Total Confirmed Bookings
    bookings_query = """
        SELECT COUNT(*) AS total_bookings
        FROM bookings
        WHERE status = 'CONFIRMED';
    """

    total_bookings = execute_query(bookings_query, fetchone=True)

    # Most Popular Route
    route_query = """
        SELECT 
            a1.city || ' → ' || a2.city AS route,
            COUNT(b.booking_id) AS total_bookings
        FROM bookings b
        JOIN flight_schedules fs ON b.schedule_id = fs.schedule_id
        JOIN flights f ON fs.flight_id = f.flight_id
        JOIN airports a1 ON f.departure_airport = a1.airport_id
        JOIN airports a2 ON f.arrival_airport = a2.airport_id
        WHERE b.status = 'CONFIRMED'
        GROUP BY route
        ORDER BY total_bookings DESC
        LIMIT 1;
    """

    popular_route = execute_query(route_query, fetchone=True)

    # Occupancy %
    occupancy_query = """
        SELECT 
            f.flight_number,
            COUNT(sa.seat_id) * 100.0 / COUNT(s.seat_id) AS occupancy_percentage
        FROM flight_schedules fs
        JOIN flights f ON fs.flight_id = f.flight_id
        JOIN seats s ON s.aircraft_id = fs.aircraft_id
        LEFT JOIN seat_allocations sa 
            ON sa.schedule_id = fs.schedule_id 
            AND sa.seat_id = s.seat_id
        GROUP BY f.flight_number;
    """

    occupancy = execute_query(occupancy_query, fetchall=True)

    return render_template(
        'admin.html',
        revenue=revenue,
        total_bookings=total_bookings,
        popular_route=popular_route,
        occupancy=occupancy
    )

@app.route('/signup', methods=['GET','POST'])
def signup():

    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        try:
            # Insert user and return user_id + role
            user = execute_query("""
                INSERT INTO users(username, email, password_hash)
                VALUES (%s,%s,%s)
                RETURNING user_id, role;
            """, (username, email, hashed.decode('utf-8')), fetchone=True)

            # Automatically log user in
            session['user_id'] = user['user_id']
            session['username'] = username
            session['role'] = user['role']

            return redirect('/')

        except Exception:
            return "Username or Email already exists"

    return render_template('signup.html')

@app.route('/login', methods=['GET','POST'])
def login():

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        user = execute_query("""
            SELECT * FROM users WHERE email=%s;
        """, (email,), fetchone=True)

        if user:
            if bcrypt.checkpw(password.encode('utf-8'),
                              user['password_hash'].encode('utf-8')):

                session['user_id'] = user['user_id']
                session['role'] = user['role']
                session['username'] = user['username']

                if user['role'] == 'ADMIN':
                    return redirect('/admin')
                else:
                    return redirect('/')

        return "Invalid credentials"

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')
    
@app.route('/admin-login', methods=['GET','POST'])
def admin_login():

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        user = execute_query("""
            SELECT * FROM users WHERE email=%s AND role='ADMIN';
        """, (email,), fetchone=True)

        if user:
            if bcrypt.checkpw(password.encode('utf-8'),
                              user['password_hash'].encode('utf-8')):

                session['user_id'] = user['user_id']
                session['role'] = user['role']
                session['username'] = user['username']

                return redirect('/admin')

        return "Invalid Admin Credentials"

    return render_template('admin_login.html')

# -------------------------
# Run App
# -------------------------
if __name__ == '__main__':
    app.run(debug=True)