 Reward Management System
A modern full-stack Reward Management System built using Django, Django REST Framework (DRF), HTML, CSS, and JavaScript. The application helps users securely manage coupons, cashback offers, gift cards, loyalty rewards, and promotional vouchers through an intuitive web interface and RESTful APIs.

Features
Authentication
User Registration

Secure Login & Logout

Forgot Password

Password Reset

User Profile Management
Reward Management
Add Rewards

View Rewards

Update Rewards

Delete Rewards

Reward Details

Reward Categories

Search & Filter Rewards
Dashboard
Total Rewards

Active Rewards

Used Rewards

Expiring Rewards

Recent Rewards

Reminder System
Track Expiry Dates

Upcoming Expiring Rewards

Reminder-ready architecture

Security
Django Authentication

Password Hashing

User-specific Data Access

CSRF Protection

Secure Form Validation

REST API
Authentication APIs

Reward CRUD APIs

Profile APIs

Ready for Mobile Integration

Tech Stack
Backend
Python

Django

Django REST Framework (DRF)

Frontend
Django Templates

HTML5

CSS3

JavaScript

Database
SQLite (Development)

PostgreSQL (Production Ready)

Deployment
Gunicorn

WhiteNoise

Render

Project Structure
reward_manager/
│
├── apps/
│   ├── users/
│   ├── rewards/
│   ├── reminders/
│   └── ocr/
│
├── templates/
├── static/
│   ├── css/
│   ├── js/
│   └── images/
│
├── core/
├── manage.py
├── requirements.txt
└── README.md
Installation
Clone the repository

git clone <repository-url>
Move into the project

cd reward_manager
Create a virtual environment

python -m venv venv
Activate it

Windows
venv\Scripts\activate
Linux / macOS
source venv/bin/activate
Install dependencies

pip install -r requirements.txt
Run migrations

python manage.py migrate
Create an admin user

python manage.py createsuperuser
Start the server

python manage.py runserver
Open

http://127.0.0.1:8000/
🔗 API Endpoints
Method	Endpoint	Description
POST	/api/v1/auth/register/	Register User
POST	/api/v1/auth/login/	Login
POST	/api/v1/auth/logout/	Logout
GET	/api/v1/auth/me/	User Profile
GET	/api/v1/rewards/	List Rewards
POST	/api/v1/rewards/	Add Reward
PUT	/api/v1/rewards/{id}/	Update Reward
DELETE	/api/v1/rewards/{id}/	Delete Reward
📸 Application Modules
Login

Register

Forgot Password

Dashboard

Rewards List

Add Reward

Edit Reward

Reward Details

Profile

Admin Panel

🔮 Future Enhancements
OCR-based Reward Detection

QR/Barcode Scanner

Email Notifications

Push Notifications

Cloud Storage

Mobile Application

Analytics Dashboard

Dark Mode

Multi-language Support

Learning Outcomes
This project demonstrates practical knowledge of:

Django Development

Django REST Framework

REST API Design

Authentication & Authorization

CRUD Operations

Database Management

Responsive UI Development

Django Templates

Deployment on Render

Production-ready Project Structure

Author
Manju K

Python & Django Developer

📄 License
This project is developed for educational and portfolio purposes. Feel free to use and modify it for learning.
