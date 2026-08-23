# Local Wishlist testing

## 1. MongoDB (Docker)

From `portfolio-backend/`:

```bash
docker compose up -d
```

This starts Mongo on `localhost:27017` (volume `mongo-data`).

Backend `.env` should include:

```
DATABASE_URL=mongodb://localhost:27017
DATABASE_NAME=portfolio_db
SECRET_KEY=...
```

## 2. Backend API

```bash
cd portfolio-backend/backend
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Health: http://127.0.0.1:8000/api/health  
Docs: http://127.0.0.1:8000/docs (Wishlist tag)

## 3. Frontend

`my-portfolio-website/.env.local`:

```
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

```bash
cd my-portfolio-website
npm install
npm run dev
```

Open http://127.0.0.1:3000/wishlist

## 4. Smoke flow

1. Register / login at `/login`
2. Create a group on `/wishlist`
3. Open the group → copy share link (`/wishlist/access/<token>`)
4. Incognito: open share link → add product → reserve as a name
5. Same browser after login: Mark bought (needs JWT + saved guest id)
