TRUNCATE TABLE 
    seat_allocations,
    bookings,
    passengers,
    flight_schedules,
    flights,
    seats,
    aircraft,
    airports,
    users
RESTART IDENTITY CASCADE;

INSERT INTO users (username, email, password_hash, role)
VALUES
('admin', 'admin@airline.com', '$2b$12$yTB.WkQtaSzYlOShRNsmUerl2c4tt4J56FziuQ0tieeUQhuEf2lhy', 'ADMIN'),
('john', 'john@mail.com', '$2b$12$yTB.WkQtaSzYlOShRNsmUerl2c4tt4J56FziuQ0tieeUQhuEf2lhy', 'USER');

INSERT INTO airports (airport_code, airport_name, city, country) VALUES
('MAA', 'Chennai International Airport', 'Chennai', 'India'),
('CJB', 'Coimbatore International Airport', 'Coimbatore', 'India');

INSERT INTO aircraft (model, total_seats)
VALUES ('Airbus A320', 30);

INSERT INTO seats (aircraft_id, seat_number, class_type)
SELECT 1,
       row_num || letter,
       'Economy'
FROM generate_series(1, 4) AS row_num,
     unnest(ARRAY['A','B','C']) AS letter;

INSERT INTO flights (flight_number, departure_airport, arrival_airport, duration_minutes)
VALUES
('TN101',
 (SELECT airport_id FROM airports WHERE airport_code='MAA'),
 (SELECT airport_id FROM airports WHERE airport_code='CJB'),
 60);

INSERT INTO flight_schedules
(flight_id, aircraft_id, departure_time, arrival_time, price)
VALUES
(1, 1, '2026-03-10 08:00:00', '2026-03-10 09:00:00', 2500);