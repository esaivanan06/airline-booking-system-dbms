-- ----------------------------
-- Airports
-- ----------------------------
CREATE TABLE airports (
    airport_id SERIAL PRIMARY KEY,
    airport_code CHAR(3) UNIQUE NOT NULL,
    airport_name VARCHAR(100) NOT NULL,
    city VARCHAR(100) NOT NULL,
    country VARCHAR(100) NOT NULL
);

-- ----------------------------
-- Aircraft
-- ----------------------------
CREATE TABLE aircraft (
    aircraft_id SERIAL PRIMARY KEY,
    model VARCHAR(100) NOT NULL,
    total_seats INT CHECK (total_seats > 0)
);

-- ----------------------------
-- Flights (Route Definition)
-- ----------------------------
CREATE TABLE flights (
    flight_id SERIAL PRIMARY KEY,
    flight_number VARCHAR(10) UNIQUE NOT NULL,
    departure_airport INT REFERENCES airports(airport_id),
    arrival_airport INT REFERENCES airports(airport_id),
    duration_minutes INT CHECK (duration_minutes > 0),
    CHECK (departure_airport <> arrival_airport)
);

-- ----------------------------
-- Flight Schedules
-- ----------------------------
CREATE TABLE flight_schedules (
    schedule_id SERIAL PRIMARY KEY,
    flight_id INT REFERENCES flights(flight_id) ON DELETE CASCADE,
    aircraft_id INT REFERENCES aircraft(aircraft_id),
    departure_time TIMESTAMP NOT NULL,
    arrival_time TIMESTAMP NOT NULL,
    price NUMERIC(10,2) CHECK (price > 0)
);

-- ----------------------------
-- Passengers
-- ----------------------------
CREATE TABLE passengers (
    passenger_id SERIAL PRIMARY KEY,
    first_name VARCHAR(50),
    last_name VARCHAR(50),
    email VARCHAR(120) UNIQUE,
    phone VARCHAR(20)
);

-- ----------------------------
-- Bookings
-- ----------------------------
CREATE TABLE bookings (
    booking_id SERIAL PRIMARY KEY,
    pnr VARCHAR(10) UNIQUE NOT NULL,
    passenger_id INT REFERENCES passengers(passenger_id) ON DELETE CASCADE,
    schedule_id INT REFERENCES flight_schedules(schedule_id) ON DELETE CASCADE,
    booking_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) CHECK (status IN ('CONFIRMED','CANCELLED')) DEFAULT 'CONFIRMED'
);

CREATE TABLE seats (
    seat_id SERIAL PRIMARY KEY,
    aircraft_id INT REFERENCES aircraft(aircraft_id) ON DELETE CASCADE,
    seat_number VARCHAR(5),
    class_type VARCHAR(20) CHECK (class_type IN ('Economy','Business','First')),
    UNIQUE (aircraft_id, seat_number)
);

CREATE TABLE seat_allocations (
    allocation_id SERIAL PRIMARY KEY,
    booking_id INT REFERENCES bookings(booking_id) ON DELETE CASCADE,
    schedule_id INT REFERENCES flight_schedules(schedule_id) ON DELETE CASCADE,
    seat_id INT REFERENCES seats(seat_id),
    UNIQUE (schedule_id, seat_id)
);