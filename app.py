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

@app.template_filter('datetimeformat')
def datetimeformat(value):
    if value:
        return value.strftime('%Y-%m-%dT%H:%M')
    return ""

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

    # Count seats dynamically
    seat_keys = [key for key in request.form if key.startswith("seat_id_")]
    passenger_count = len(seat_keys)

    if passenger_count == 0:
        return "No seats selected", 400

    pnr = generate_pnr()
    conn = get_connection()

    try:
        with conn:
            with conn.cursor() as cur:

                # Insert booking
                cur.execute("""
                    INSERT INTO bookings(pnr, schedule_id, user_id)
                    VALUES (%s, %s, %s)
                    RETURNING booking_id;
                """, (pnr, schedule_id, session['user_id']))

                booking_id = cur.fetchone()[0]

                # Loop seats
                for i in range(1, passenger_count + 1):

                    first_name = request.form[f'first_name_{i}']
                    last_name = request.form[f'last_name_{i}']
                    email = request.form[f'email_{i}']
                    seat_id = request.form[f'seat_id_{i}']

                    cur.execute("""
    INSERT INTO passengers(first_name, last_name, email, booking_id)
    VALUES (%s,%s,%s,%s)
    RETURNING passenger_id;
""", (first_name, last_name, email, booking_id))
                    
                    passenger_id = cur.fetchone()[0]
                    
                    cur.execute("""
    INSERT INTO seat_allocations(booking_id, schedule_id, seat_id, passenger_id)
    VALUES (%s,%s,%s,%s);
""", (booking_id, schedule_id, seat_id, passenger_id))

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

@app.route('/my-bookings')
@user_required
def my_bookings():

    query = """
        SELECT 
            b.booking_id,
            b.pnr,
            b.status,
            fs.departure_time,
            fs.arrival_time,
            f.flight_number,
            a1.city AS from_city,
            a2.city AS to_city
        FROM bookings b
        JOIN flight_schedules fs ON b.schedule_id = fs.schedule_id
        JOIN flights f ON fs.flight_id = f.flight_id
        JOIN airports a1 ON f.departure_airport = a1.airport_id
        JOIN airports a2 ON f.arrival_airport = a2.airport_id
        WHERE b.user_id = %s
        ORDER BY fs.departure_time DESC;
    """

    bookings = execute_query(query, (session['user_id'],), fetchall=True)

    for booking in bookings:
        details_query = """
    SELECT 
        p.passenger_id,
        p.first_name,
        p.last_name,
        s.seat_number
    FROM passengers p
    JOIN seat_allocations sa 
        ON sa.passenger_id = p.passenger_id
    JOIN seats s 
        ON s.seat_id = sa.seat_id
    WHERE p.booking_id = %s;
"""
        booking['passengers'] = execute_query(
            details_query,
            (booking['booking_id'],),
            fetchall=True
        )

    return render_template('my_bookings.html', bookings=bookings)

@app.route('/cancel-seat', methods=['POST'])
@user_required
def cancel_seat():

    passenger_id = request.form['passenger_id']
    conn = get_connection()

    try:
        with conn:
            with conn.cursor() as cur:

                # Get booking_id before deletion
                cur.execute("""
                    SELECT booking_id FROM passengers
                    WHERE passenger_id = %s;
                """, (passenger_id,))
                row = cur.fetchone()

                if not row:
                    return "Invalid passenger", 400

                booking_id = row[0]

                # Delete passenger (CASCADE removes seat_allocation)
                cur.execute("""
                    DELETE FROM passengers
                    WHERE passenger_id = %s;
                """, (passenger_id,))

                # Check remaining passengers
                cur.execute("""
                    SELECT COUNT(*) FROM passengers
                    WHERE booking_id = %s;
                """, (booking_id,))
                remaining = cur.fetchone()[0]

                # If no passengers left → cancel booking
                if remaining == 0:
                    cur.execute("""
                        UPDATE bookings
                        SET status = 'CANCELLED'
                        WHERE booking_id = %s;
                    """, (booking_id,))

        return redirect('/my-bookings')

    except Exception as e:
        conn.rollback()
        return f"Error: {str(e)}", 400

    finally:
        conn.close()

@app.route('/change-seat/<int:passenger_id>')
@user_required
def change_seat(passenger_id):

    query = """
        SELECT 
            p.booking_id,
            b.schedule_id,
            s.seat_id,
            s.seat_number
        FROM passengers p
        JOIN bookings b ON p.booking_id = b.booking_id
        JOIN seat_allocations sa ON sa.passenger_id = p.passenger_id
        JOIN seats s ON s.seat_id = sa.seat_id
        WHERE p.passenger_id = %s;
    """

    data = execute_query(query, (passenger_id,), fetchone=True)
    current_seat_id = data['seat_id']

    if not data:
        return "Invalid passenger", 400

    schedule_id = data['schedule_id']

    seats_query = """
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

    seats = execute_query(seats_query, (schedule_id, schedule_id), fetchall=True)

    return render_template(
        'change_seat.html',
        passenger_id=passenger_id,
        schedule_id=schedule_id,
        seats=seats, 
        current_seat_id=current_seat_id
    )

@app.route('/update-seat', methods=['POST'])
@user_required
def update_seat():

    passenger_id = request.form['passenger_id']
    schedule_id = request.form['schedule_id']
    new_seat_id = request.form['seat_id']

    conn = get_connection()

    try:
        with conn:
            with conn.cursor() as cur:

                # Remove old seat allocation
                cur.execute("""
                    DELETE FROM seat_allocations
                    WHERE passenger_id = %s;
                """, (passenger_id,))

                # Insert new seat
                cur.execute("""
                    INSERT INTO seat_allocations
                    (booking_id, schedule_id, seat_id, passenger_id)
                    SELECT booking_id, %s, %s, %s
                    FROM passengers
                    WHERE passenger_id = %s;
                """, (schedule_id, new_seat_id,
                      passenger_id, passenger_id))

        return redirect('/my-bookings')

    except Exception as e:
        conn.rollback()
        return f"Seat change failed: {str(e)}", 400

    finally:
        conn.close()

@app.route('/add-seat/<int:booking_id>')
@user_required
def add_seat(booking_id):

    query = """
        SELECT schedule_id
        FROM bookings
        WHERE booking_id = %s
        AND user_id = %s
        AND status = 'CONFIRMED';
    """

    booking = execute_query(
        query,
        (booking_id, session['user_id']),
        fetchone=True
    )

    if not booking:
        return "Invalid booking", 400

    schedule_id = booking['schedule_id']

    seats_query = """
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

    seats = execute_query(
        seats_query,
        (schedule_id, schedule_id),
        fetchall=True
    )

    return render_template(
        'add_seat.html',
        booking_id=booking_id,
        schedule_id=schedule_id,
        seats=seats
    )

@app.route('/confirm-add-seat', methods=['POST'])
@user_required
def confirm_add_seat():

    booking_id = request.form['booking_id']
    schedule_id = request.form['schedule_id']

    seat_keys = [k for k in request.form if k.startswith("seat_id_")]
    seat_count = len(seat_keys)

    if seat_count == 0:
        return "No seats selected", 400

    conn = get_connection()

    try:
        with conn:
            with conn.cursor() as cur:

                for i in range(1, seat_count + 1):

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

                    # Insert seat allocation
                    cur.execute("""
                        INSERT INTO seat_allocations
                        (booking_id, schedule_id, seat_id, passenger_id)
                        VALUES (%s,%s,%s,%s);
                    """, (booking_id, schedule_id, seat_id, passenger_id))

        return redirect('/my-bookings')

    except Exception as e:
        conn.rollback()
        return f"Error adding seat: {str(e)}", 400

    finally:
        conn.close()

@app.route('/cancel-booking', methods=['POST'])
@user_required
def cancel_booking():

    booking_id = request.form['booking_id']
    conn = get_connection()

    try:
        with conn:
            with conn.cursor() as cur:

                # Verify booking belongs to user
                cur.execute("""
                    SELECT status FROM bookings
                    WHERE booking_id = %s
                    AND user_id = %s;
                """, (booking_id, session['user_id']))

                row = cur.fetchone()

                if not row:
                    return "Invalid booking", 400

                if row[0] == 'CANCELLED':
                    return "Booking already cancelled", 400

                # Soft cancel booking
                cur.execute("""
                    UPDATE bookings
                    SET status = 'CANCELLED'
                    WHERE booking_id = %s;
                """, (booking_id,))

                # Delete passengers (cascade deletes seat_allocations)
                cur.execute("""
                    DELETE FROM passengers
                    WHERE booking_id = %s;
                """, (booking_id,))

        return redirect('/my-bookings')

    except Exception as e:
        conn.rollback()
        return f"Cancellation failed: {str(e)}", 400

    finally:
        conn.close()

@app.route('/admin/create-aircraft', methods=['GET','POST'])
@admin_required
def create_aircraft():

    if request.method == 'POST':

        model = request.form['model']
        total_seats = int(request.form['total_seats'])

        conn = get_connection()

        try:
            with conn:
                with conn.cursor() as cur:

                    # Insert aircraft
                    cur.execute("""
                        INSERT INTO aircraft(model, total_seats)
                        VALUES (%s,%s)
                        RETURNING aircraft_id;
                    """, (model, total_seats))

                    aircraft_id = cur.fetchone()[0]

                    # Generate seats
                    seats_per_row = 6
                    letters = ['A','B','C','D','E','F']

                    total_rows = total_seats // seats_per_row

                    seat_counter = 0

                    for row in range(1, total_rows + 1):
                        for letter in letters:

                            if seat_counter >= total_seats:
                                break

                            seat_number = f"{row}{letter}"

                            cur.execute("""
                                INSERT INTO seats
                                (aircraft_id, seat_number, class_type)
                                VALUES (%s,%s,%s);
                            """, (aircraft_id, seat_number, 'Economy'))

                            seat_counter += 1

            return redirect('/admin')

        except Exception as e:
            conn.rollback()
            return f"Error creating aircraft: {str(e)}", 400

        finally:
            conn.close()

    return render_template('create_aircraft.html')

@app.route('/admin/create-flight', methods=['GET','POST'])
@admin_required
def create_flight():

    airports = execute_query("SELECT airport_id, city FROM airports;", fetchall=True)

    if request.method == 'POST':
        flight_number = request.form['flight_number']
        departure = request.form['departure']
        arrival = request.form['arrival']
        duration = request.form['duration']

        execute_query("""
            INSERT INTO flights(flight_number, departure_airport, arrival_airport, duration_minutes)
            VALUES (%s,%s,%s,%s);
        """, (flight_number, departure, arrival, duration))

        return redirect('/admin')

    return render_template('create_flight.html', airports=airports)

@app.route('/admin/create-schedule', methods=['GET','POST'])
@admin_required
def create_schedule():

    flights = execute_query("SELECT flight_id, flight_number FROM flights;", fetchall=True)
    aircrafts = execute_query("SELECT aircraft_id, model FROM aircraft;", fetchall=True)

    if request.method == 'POST':
        flight_id = request.form['flight_id']
        aircraft_id = request.form['aircraft_id']
        departure = request.form['departure_time']
        arrival = request.form['arrival_time']
        price = request.form['price']

        execute_query("""
            INSERT INTO flight_schedules
            (flight_id, aircraft_id, departure_time, arrival_time, price)
            VALUES (%s,%s,%s,%s,%s);
        """, (flight_id, aircraft_id, departure, arrival, price))

        return redirect('/admin')

    return render_template(
        'create_schedule.html',
        flights=flights,
        aircrafts=aircrafts
    )

@app.route('/admin/schedules')
@admin_required
def view_schedules():

    schedules = execute_query("""
        SELECT fs.schedule_id,
       f.flight_number,
       a1.city AS departure,
       a2.city AS arrival,
       fs.departure_time,
       fs.arrival_time,
       fs.price
FROM flight_schedules fs
JOIN flights f ON fs.flight_id = f.flight_id
JOIN airports a1 ON f.departure_airport = a1.airport_id
JOIN airports a2 ON f.arrival_airport = a2.airport_id
ORDER BY fs.departure_time DESC;
    """, fetchall=True)

    return render_template('view_schedules.html', schedules=schedules)

@app.route('/admin/users')
@admin_required
def view_users():

    users = execute_query("""
        SELECT user_id, username, email, role, created_at
        FROM users
        ORDER BY created_at DESC;
    """, fetchall=True)

    return render_template('admin_users.html', users=users)

@app.route('/admin/bookings')
@admin_required
def view_all_bookings():

    bookings = execute_query("""
        SELECT 
            b.booking_id,
            b.pnr,
            b.status,
            u.username,
            f.flight_number,
            fs.departure_time
        FROM bookings b
        JOIN users u ON b.user_id = u.user_id
        JOIN flight_schedules fs ON b.schedule_id = fs.schedule_id
        JOIN flights f ON fs.flight_id = f.flight_id
        ORDER BY fs.departure_time DESC;
    """, fetchall=True)

    for booking in bookings:
        passengers = execute_query("""
            SELECT p.first_name, p.last_name, s.seat_number
            FROM passengers p
            JOIN seat_allocations sa 
                ON sa.passenger_id = p.passenger_id
            JOIN seats s 
                ON s.seat_id = sa.seat_id
            WHERE p.booking_id = %s;
        """, (booking['booking_id'],), fetchall=True)

        booking['passengers'] = passengers

    return render_template('admin_bookings.html', bookings=bookings)

@app.route('/admin/aircraft')
@admin_required
def view_aircraft():

    aircraft = execute_query("""
        SELECT aircraft_id, model, total_seats
        FROM aircraft;
    """, fetchall=True)

    return render_template('admin_aircraft.html', aircraft=aircraft)

@app.route('/admin/flights')
@admin_required
def view_flights():

    flights = execute_query("""
        SELECT 
            f.flight_id,
            f.flight_number,
            a1.city AS departure,
            a2.city AS arrival,
            f.duration_minutes
        FROM flights f
        JOIN airports a1 ON f.departure_airport = a1.airport_id
        JOIN airports a2 ON f.arrival_airport = a2.airport_id;
    """, fetchall=True)

    return render_template('admin_flights.html', flights=flights)

@app.route('/admin/edit-flight/<int:flight_id>', methods=['GET','POST'])
@admin_required
def edit_flight(flight_id):

    airports = execute_query(
        "SELECT airport_id, city FROM airports;",
        fetchall=True
    )

    if request.method == 'POST':

        flight_number = request.form['flight_number']
        departure = request.form['departure']
        arrival = request.form['arrival']
        duration = request.form['duration']

        execute_query("""
            UPDATE flights
            SET flight_number=%s,
                departure_airport=%s,
                arrival_airport=%s,
                duration_minutes=%s
            WHERE flight_id=%s;
        """, (flight_number, departure, arrival,
              duration, flight_id))

        return redirect('/admin/flights')

    flight = execute_query("""
        SELECT * FROM flights
        WHERE flight_id=%s;
    """, (flight_id,), fetchone=True)

    return render_template(
        'edit_flight.html',
        flight=flight,
        airports=airports
    )

@app.route('/admin/delete-flight', methods=['POST'])
@admin_required
def delete_flight():

    flight_id = request.form['flight_id']

    # Check if schedules exist
    schedules = execute_query("""
        SELECT COUNT(*) AS count
        FROM flight_schedules
        WHERE flight_id=%s;
    """, (flight_id,), fetchone=True)

    if schedules['count'] > 0:
        return "Cannot delete flight with schedules.", 400

    execute_query("""
        DELETE FROM flights
        WHERE flight_id=%s;
    """, (flight_id,))

    return redirect('/admin/flights')

@app.route('/admin/edit-schedule/<int:schedule_id>', methods=['GET','POST'])
@admin_required
def edit_schedule(schedule_id):

    flights = execute_query(
        "SELECT flight_id, flight_number FROM flights;",
        fetchall=True
    )

    aircrafts = execute_query(
        "SELECT aircraft_id, model FROM aircraft;",
        fetchall=True
    )

    if request.method == 'POST':

        flight_id = request.form['flight_id']
        aircraft_id = request.form['aircraft_id']
        departure = request.form['departure_time']
        arrival = request.form['arrival_time']
        price = request.form['price']

        execute_query("""
            UPDATE flight_schedules
            SET flight_id=%s,
                aircraft_id=%s,
                departure_time=%s,
                arrival_time=%s,
                price=%s
            WHERE schedule_id=%s;
        """, (flight_id, aircraft_id,
              departure, arrival,
              price, schedule_id))

        return redirect('/admin/schedules')

    schedule = execute_query("""
        SELECT * FROM flight_schedules
        WHERE schedule_id=%s;
    """, (schedule_id,), fetchone=True)

    return render_template(
        'edit_schedule.html',
        schedule=schedule,
        flights=flights,
        aircrafts=aircrafts
    )

@app.route('/admin/delete-schedule', methods=['POST'])
@admin_required
def delete_schedule():

    schedule_id = request.form['schedule_id']

    bookings = execute_query("""
        SELECT COUNT(*) AS count
        FROM bookings
        WHERE schedule_id=%s
        AND status='CONFIRMED';
    """, (schedule_id,), fetchone=True)

    if bookings['count'] > 0:
        return "Cannot delete schedule with active bookings.", 400

    execute_query("""
        DELETE FROM flight_schedules
        WHERE schedule_id=%s;
    """, (schedule_id,))

    return redirect('/admin/schedules')

# -------------------------
# Run App
# -------------------------
if __name__ == '__main__':
    app.run(debug=True)