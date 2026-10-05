# InvestLens – Two-Layer Investment Framework

Full-stack version of the original single-file app.

```
investlens/
├── frontend/            Static UI (served by the backend)
│   ├── index.html
│   ├── css/styles.css
│   └── js/app.js        Calls the REST API
├── backend/             Flask REST API
│   ├── app.py           Routes: auth, analyze, signal, assistant, portfolio
│   ├── scoring.py       Layer 1 / Layer 2 / assistant rules
│   ├── db.py            SQLite connection helpers
│   └── requirements.txt
└── database/
    └── schema.sql       SQLite schema (investlens.db is created on first run)
```

## Run it

Requires Python 3.9+.

```bash
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000 — the database file `database/investlens.db` and a
session secret `database/.secret_key` are created automatically.

### Configuration (environment variables, all optional)

| Variable        | Default                       | Purpose                                   |
|-----------------|-------------------------------|-------------------------------------------|
| `PORT`          | `5000`                        | Port to listen on                         |
| `HOST`          | `127.0.0.1`                   | Use `0.0.0.0` to expose on your network   |
| `SECRET_KEY`    | generated & saved on 1st run  | Signs the login cookie                    |
| `INVESTLENS_DB` | `database/investlens.db`      | Path to the SQLite file                   |
| `COOKIE_SECURE` | off                           | Set `1` when serving over HTTPS           |
| `FLASK_DEBUG`   | off                           | Set `1` for auto-reload while developing  |

## API

| Method | Path                         | Description                                        |
|--------|------------------------------|----------------------------------------------------|
| POST   | `/api/auth/register`         | `{username, email, password}` → creates account    |
| POST   | `/api/auth/login`            | `{email, password}`                                |
| POST   | `/api/auth/logout`           |                                                    |
| GET    | `/api/auth/me`               | Current user                                       |
| GET    | `/api/portfolio`             | Saved inputs + last analysis                       |
| POST   | `/api/analyze`               | `{budget, risk, companies[]}` → scores + allocation|
| POST   | `/api/signal`                | `{company, prices}` → green/yellow/red signal      |
| GET    | `/api/assistant/summary`     | `?company=&horizon=`                               |
| GET    | `/api/assistant/history`     | `?company=`                                        |
| POST   | `/api/assistant`             | `{company, horizon, question}` → answer            |

## Database tables

`users`, `settings`, `companies`, `analyses`, `signals`, `chat_messages`
(see `database/schema.sql`). Passwords are stored as salted scrypt hashes.

## Production notes

- Run behind a real WSGI server, e.g. `pip install gunicorn && gunicorn -w 2 app:app` from `backend/`, with HTTPS and `COOKIE_SECURE=1`.
- There is no login rate-limiting or email verification yet; add them before exposing publicly.
- Educational tool using simple rules on user-entered numbers. Not financial advice.
