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
VALUES (
    'admin',
    'admin@airline.com',
    '$2b$12$3upS6aoHITVk1If7os1P9eJk0agxI0jopdNfPBtQmbuoOwcm7GYTG',
    'ADMIN'
);