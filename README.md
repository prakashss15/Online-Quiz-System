# Online Quiz System

A Django-based online quiz system for creating timed quizzes, assigning them by year/branch/section, auto-evaluating student attempts, tracking tab switches, and viewing leaderboards/results.

## Features

- Student and teacher registration/login flows
- Teacher dashboard for creating quizzes and managing questions
- Timed quiz attempts with randomized question and option order
- Automatic scoring after submission or timeout
- Student results and quiz leaderboards
- Teacher result views with CSV export
- SQLite database for local development

## Project Structure

```text
online_quiz_system/
+-- config/              # Django project settings and root URLs
+-- quizzes/             # Main quiz app: models, forms, views, URLs, templates, static files
+-- db.sqlite3           # Local SQLite database
+-- manage.py            # Django management script
`-- README.md
```

## Prerequisites

- Python 3.10 or newer
- pip

This project uses Django 5.2.x. If your virtual environment does not already have Django installed, install it with the setup steps below.

## Setup

From the project root:

```powershell
cd d:\santosh\online_quiz_system
```

Create and activate a virtual environment:

```powershell
python -m venv env
.\env\Scripts\Activate.ps1
```

If PowerShell blocks script activation, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\env\Scripts\Activate.ps1
```

Install Django:

```powershell
python -m pip install --upgrade pip
python -m pip install "Django==5.2.12"
```

For macOS/Linux:

```bash
python3 -m venv env
source env/bin/activate
python -m pip install --upgrade pip
python -m pip install "Django==5.2.12"
```

## Database Setup

Apply database migrations:

```powershell
python manage.py migrate
```

Optional: create an admin/superuser account:

```powershell
python manage.py createsuperuser
```

The repository includes `db.sqlite3` for local development, but running migrations is still recommended after setup.

## Run the Project

Start the Django development server:

```powershell
python manage.py runserver
```

Open the app in your browser:

```text
http://127.0.0.1:8000/
```

By default, `/` redirects signed-in users to the correct dashboard.

## Useful URLs

- Student login: `http://127.0.0.1:8000/student/login/`
- Student registration: `http://127.0.0.1:8000/student/register/`
- Student dashboard: `http://127.0.0.1:8000/student/dashboard/`
- Teacher login: `http://127.0.0.1:8000/teacher/login/`
- Teacher registration: `http://127.0.0.1:8000/teacher/register/`
- Teacher dashboard: `http://127.0.0.1:8000/teacher/dashboard/`
- Quiz list: `http://127.0.0.1:8000/quizzes/`

## Basic Usage

1. Register a teacher account from `/teacher/register/`.
2. Log in as the teacher and create a quiz from the teacher dashboard.
3. Add questions to the quiz. Each question should have exactly four options and one correct option.
4. Register a student account from `/student/register/`.
5. Make sure the student's year, branch, and section match the quiz assignment.
6. Log in as the student, open the quiz, enter the access code if required, and submit the attempt.
7. View scores from the student results page or teacher results pages.

## Development Commands

Run Django checks:

```powershell
python manage.py check
```

Create new migrations after model changes:

```powershell
python manage.py makemigrations
```

Apply migrations:

```powershell
python manage.py migrate
```

## Notes

- The app uses SQLite through `db.sqlite3`.
- `DEBUG` is enabled for local development in `config/settings.py`.
- Teacher accounts are Django users with `is_staff=True`.
- Student accounts include a `StudentProfile` with roll number, year, branch, and section.
- The current URL configuration does not expose Django's built-in `/admin/` route; use the teacher dashboard for quiz management.
