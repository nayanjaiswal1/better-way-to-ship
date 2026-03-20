# Testing

## Test Naming
- Describe behavior: `should_return_user_when_valid_id`
- Pattern: `should_<expected>_when_<condition>`

## AAA Pattern
- **Arrange** - set up test data
- **Act** - perform action
- **Assert** - verify outcome

## What to Mock
- External APIs (wrap in adapter, mock the adapter)
- Databases (in unit tests)
- Time (use fake timers)

## What NOT to Mock
- Built-in functions
- External APIs directly (always wrap in your own adapter first)

---

## React Testing (Vitest + RTL)

```tsx
// components/UserProfile.test.tsx
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';           // MSW v2 API
import { setupServer } from 'msw/node';
import { UserProfile } from './UserProfile';

const server = setupServer();
beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

describe('UserProfile', () => {
  it('should_display_user_data_when_loaded', async () => {
    const queryClient = createTestQueryClient();

    // ARRANGE: Mock the API response
    server.use(
      http.get('/api/users/1', () => {
        return HttpResponse.json({ id: 1, name: 'John Doe', email: 'john@example.com' });
      })
    );

    // ACT: Render and wait for data
    render(
      <QueryClientProvider client={queryClient}>
        <UserProfile userId={1} />
      </QueryClientProvider>
    );

    // ASSERT: Check the data is displayed
    await waitFor(() => {
      expect(screen.getByText('John Doe')).toBeInTheDocument();
    });
    expect(screen.getByText('john@example.com')).toBeInTheDocument();
  });

  it('should_show_error_when_request_fails', async () => {
    const queryClient = createTestQueryClient();

    server.use(
      http.get('/api/users/999', () => {
        return HttpResponse.json({ detail: 'User not found' }, { status: 404 });
      })
    );

    render(
      <QueryClientProvider client={queryClient}>
        <UserProfile userId={999} />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText(/error|not found/i)).toBeInTheDocument();
    });
  });
});
```

---

## FastAPI Testing (pytest + pytest-asyncio)

```python
# tests/test_users.py
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.session import get_db
from app.db.base import Base                        # import declarative Base
from app.models.user import User
from app.core.security import hash_password         # import hash_password
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Note: SQLite is used here for simplicity. For full PostgreSQL parity
# (e.g. FOR UPDATE, JSON operators), use testcontainers-python instead.
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"

@pytest.fixture
async def db_session():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    yield async_session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session()

    app.dependency_overrides[get_db] = override_get_db  # wire the override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_should_return_user_when_valid_id(client, db_session):
    # ARRANGE: Create test user
    user = User(email="test@example.com", hashed_password=hash_password("secret"))
    async with db_session() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)

    # ACT
    response = await client.get(f"/api/v1/users/{user.id}")

    # ASSERT
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "test@example.com"
    assert "hashed_password" not in data

@pytest.mark.asyncio
async def test_should_return_404_when_user_not_found(client):
    # ACT
    response = await client.get("/api/v1/users/99999")

    # ASSERT
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "User not found"
```
