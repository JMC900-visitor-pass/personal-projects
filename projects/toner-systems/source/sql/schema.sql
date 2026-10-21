-- Toner Request System schema
-- Run: mysql -u root -p < sql/schema.sql

CREATE DATABASE IF NOT EXISTS toner_system CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE toner_system;

CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(50) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rooms (
  id INT AUTO_INCREMENT PRIMARY KEY,
  room_name VARCHAR(100) NOT NULL,
  building VARCHAR(100) DEFAULT '',
  notes TEXT,
  UNIQUE KEY uq_room (room_name, building)
);

CREATE TABLE IF NOT EXISTS toners (
  id INT AUTO_INCREMENT PRIMARY KEY,
  toner_name VARCHAR(100) NOT NULL,
  toner_model VARCHAR(100) NOT NULL,
  quantity INT NOT NULL DEFAULT 0,
  cost DECIMAL(10,2) NOT NULL DEFAULT 0.00,
  low_stock_threshold INT NOT NULL DEFAULT 2
);

CREATE TABLE IF NOT EXISTS printers (
  id INT AUTO_INCREMENT PRIMARY KEY,
  printer_name VARCHAR(100) NOT NULL,
  printer_model VARCHAR(100) NOT NULL,
  ip_address VARCHAR(45) DEFAULT '',
  room_id INT NOT NULL,
  toner_id INT NOT NULL,
  FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE CASCADE,
  FOREIGN KEY (toner_id) REFERENCES toners(id)
);

CREATE TABLE IF NOT EXISTS requests (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(100) NOT NULL,
  room_id INT NOT NULL,
  printer_id INT NOT NULL,
  toner_id INT NOT NULL,
  status ENUM('Pending','In Progress','Completed') NOT NULL DEFAULT 'Pending',
  notes TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  completed_at TIMESTAMP NULL,
  FOREIGN KEY (room_id) REFERENCES rooms(id),
  FOREIGN KEY (printer_id) REFERENCES printers(id),
  FOREIGN KEY (toner_id) REFERENCES toners(id),
  INDEX idx_status (status),
  INDEX idx_created (created_at)
);

-- ---- Sample data (delete or edit freely) ----
INSERT INTO rooms (room_name, building) VALUES
  ('A12', 'Main Building'),
  ('B04', 'Main Building'),
  ('Library Office', 'Library Block');

INSERT INTO toners (toner_name, toner_model, quantity, cost, low_stock_threshold) VALUES
  ('HP 410X Black',  'CF410X', 6, 89.99, 2),
  ('HP 26A Black',   'CF226A', 3, 74.50, 2),
  ('Brother TN-2420','TN-2420', 1, 49.00, 2);

INSERT INTO printers (printer_name, printer_model, ip_address, room_id, toner_id) VALUES
  ('A12 Office Printer', 'HP LaserJet Pro M452', '10.0.1.21', 1, 1),
  ('A12 Copier',         'HP LaserJet M426',     '10.0.1.22', 1, 2),
  ('B04 Printer',        'Brother HL-L2350DW',   '10.0.1.30', 2, 3),
  ('Library Printer',    'HP LaserJet M426',     '10.0.1.40', 3, 2);
