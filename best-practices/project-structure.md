# Project Structure Examples

## React Feature-Based Structure

```
src/
├── features/
│   ├── auth/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── types/
│   │   └── api/
│   ├── users/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── types/
│   │   └── api/
│   └── products/
│       ├── components/
│       ├── hooks/
│       ├── types/
│       └── api/
├── shared/
│   ├── components/
│   ├── hooks/
│   ├── lib/
│   └── types/
└── App.tsx
```

## FastAPI Layered Structure

```
app/
├── api/              # Route handlers (thin)
├── core/             # Config, security, permissions
├── db/               # Database setup, sessions
├── dependencies/     # FastAPI dependencies
├── models/           # SQLAlchemy ORM models
├── repositories/     # Data access layer
├── schemas/          # Pydantic schemas
├── services/         # Business logic
└── main.py
```
