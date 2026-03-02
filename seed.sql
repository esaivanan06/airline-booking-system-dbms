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
('CJB', 'Coimbatore International Airport', 'Coimbatore', 'India'),
('IXM', 'Madurai Airport', 'Madurai', 'India'),
('TRZ', 'Tiruchirappalli International Airport', 'Tiruchirappalli', 'India'),
('SXV', 'Salem Airport', 'Salem', 'India'),
('TCR', 'Tuticorin Airport', 'Thoothukudi', 'India');

INSERT INTO aircraft (model, total_seats) VALUES
('Airbus A320', 30),
('Boeing 737', 24);

INSERT INTO flights (flight_number, departure_airport, arrival_airport, duration_minutes) VALUES

-- Chennai ↔ Coimbatore
('TN101',
 (SELECT airport_id FROM airports WHERE airport_code='MAA'),
 (SELECT airport_id FROM airports WHERE airport_code='CJB'),
 60),

('TN102',
 (SELECT airport_id FROM airports WHERE airport_code='CJB'),
 (SELECT airport_id FROM airports WHERE airport_code='MAA'),
 60),

-- Chennai ↔ Madurai
('TN201',
 (SELECT airport_id FROM airports WHERE airport_code='MAA'),
 (SELECT airport_id FROM airports WHERE airport_code='IXM'),
 75),

('TN202',
 (SELECT airport_id FROM airports WHERE airport_code='IXM'),
 (SELECT airport_id FROM airports WHERE airport_code='MAA'),
 75),

-- Chennai ↔ Trichy
('TN301',
 (SELECT airport_id FROM airports WHERE airport_code='MAA'),
 (SELECT airport_id FROM airports WHERE airport_code='TRZ'),
 70),

('TN302',
 (SELECT airport_id FROM airports WHERE airport_code='TRZ'),
 (SELECT airport_id FROM airports WHERE airport_code='MAA'),
 70),

-- Chennai ↔ Salem
('TN401',
 (SELECT airport_id FROM airports WHERE airport_code='MAA'),
 (SELECT airport_id FROM airports WHERE airport_code='SXV'),
 80),

('TN402',
 (SELECT airport_id FROM airports WHERE airport_code='SXV'),
 (SELECT airport_id FROM airports WHERE airport_code='MAA'),
 80),

-- Chennai ↔ Tuticorin
('TN501',
 (SELECT airport_id FROM airports WHERE airport_code='MAA'),
 (SELECT airport_id FROM airports WHERE airport_code='TCR'),
 90),

('TN502',
 (SELECT airport_id FROM airports WHERE airport_code='TCR'),
 (SELECT airport_id FROM airports WHERE airport_code='MAA'),
 90);

INSERT INTO flight_schedules
(flight_id, aircraft_id, departure_time, arrival_time, price)
VALUES

-- TN101 Morning
((SELECT flight_id FROM flights WHERE flight_number='TN101'),
 1,
 '2026-03-10 08:00:00',
 '2026-03-10 09:00:00',
 2500),

-- TN101 Evening
((SELECT flight_id FROM flights WHERE flight_number='TN101'),
 2,
 '2026-03-10 18:00:00',
 '2026-03-10 19:00:00',
 2800),

-- TN201 Morning
((SELECT flight_id FROM flights WHERE flight_number='TN201'),
 1,
 '2026-03-10 09:30:00',
 '2026-03-10 10:45:00',
 3200),

-- TN301 Afternoon
((SELECT flight_id FROM flights WHERE flight_number='TN301'),
 2,
 '2026-03-10 14:00:00',
 '2026-03-10 15:10:00',
 2700),

-- TN401 Evening
((SELECT flight_id FROM flights WHERE flight_number='TN401'),
 1,
 '2026-03-10 17:30:00',
 '2026-03-10 18:50:00',
 2600);

 INSERT INTO seats (aircraft_id, seat_number, class_type)
SELECT 
    1,
    row_num || letter,
    'Economy'
FROM generate_series(1, 5) AS row_num,
     unnest(ARRAY['A','B','C','D','E','F']) AS letter;

INSERT INTO seats (aircraft_id, seat_number, class_type)
SELECT 
    2,
    row_num || letter,
    'Economy'
FROM generate_series(1, 4) AS row_num,
     unnest(ARRAY['A','B','C','D','E','F']) AS letter;