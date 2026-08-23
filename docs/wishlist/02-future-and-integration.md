# Wishlist — Later work, integration, and cloning the next product

This document is **out of v1 scope**. Implement v1 from [`01-scaffold-and-conventions.md`](./01-scaffold-and-conventions.md) and [`03-prd-hld-lld.md`](./03-prd-hld-lld.md) first.

Use this file when you:

- Add URL scrape, cron expiry, or a frontend
- Clone Wishlist’s hexagonal folder into a **second product**
- Wire CI, Docker, or env for those later pieces

---

## 1. What v1 already leaves ready

| Port / seam | v1 adapter | Later adapter |
|-------------|------------|---------------|
| `ProductPreview` | `NullPreviewAdapter` — always “enter manually” | `HttpScrapeAdapter` (httpx, timeouts, allowlist) |
| `Clock` | `UtcClock` | Same; cron job also calls expire use case |
| `AccessTokenGen` | UUID4 | Unchanged |
| HTTP router | JSON API | Unchanged contract; frontend is a client |
| Domain `ProductOption` | Manual `title`, `url`, `notes`, `price?`, `image_url?` | Scrape fills the same fields |

Do not redesign collections for scrape. Options already have URL and image slots.

---

## 2. URL scrape (post-v1)

### Goal

`POST /{group_id}/preview-url` `{ "url": "https://..." }` → draft option. Client confirms, then creates/updates a product.

### Integration steps

1. Implement `HttpScrapeAdapter` behind `ProductPreview` in `wiring.py` only.
2. Env (do not commit secrets):

   - `WISHLIST_PREVIEW_ENABLED=true`
   - `WISHLIST_PREVIEW_TIMEOUT_S=8`
   - Optional: `WISHLIST_PREVIEW_USER_AGENT`

3. Security:

   - Allow `http`/`https` only
   - Block private/link-local IPs (SSRF)
   - Max response size
   - Rate-limit preview (stricter than add-product, e.g. 10/min)
   - Never follow redirects to internal hosts

4. Failure path stays product-valid: if scrape fails, API returns 422/502 with “enter manually” — same as v1.

5. Do **not** persist scrape HTML. Persist only the confirmed option fields.

---

## 3. Reservation expiry job

v1 uses **lazy expire** (on reserve / view / purchase).

Later:

1. Add `application/reservations.py` `expire_due(now)` already used by lazy path.
2. Add `backend/app/wishlist/adapters/jobs/expire_reservations.py` that calls the same use case.
3. Run via:

   - `cron` in the backend container, or
   - a one-shot Docker service, or
   - GitHub Action on a schedule (only if the job is idempotent and authenticated to prod — prefer in-cluster cron)

4. Batch size + index on `reservations.expires_at` + `status=active`.
5. Job must be idempotent. Lazy + cron together is safe.

---

## 4. Frontend integration (later)

Backend remains the source of truth. Suggested client rules:

| Concern | How |
|---------|-----|
| Auth | Existing JWT (`/api/auth`) — same as TripSync UI |
| Share page | Open `/access/{token}` then send `X-Wishlist-Access` on every call |
| Guest continuity | Persist `X-Wishlist-Guest` in `localStorage` (or cookie) for that group |
| Spoiler | Trust server-filtered `GET /{id}`; do not infer reserved from a second endpoint as owner |
| Bought | Login redirect, then `POST .../purchase` with both JWT and guest header if the reserve was anonymous |
| Combined vs personal | `GET /{id}` + `?owner_member_id=` |

No new OAuth. Do not store the share token in query strings after the first landing (header only).

When a frontend repo exists, add a short “Wishlist env” section there (`VITE_API_URL` / similar). Do not put frontend code inside `app/wishlist/`.

---

## 5. Leader settings after create

v1: `owners_can_see_fulfillment` is fixed at create.

Later endpoint (leader only):

- `PATCH /{id}/settings` — `max_active_reservations` only at first
- Changing spoiler mode later is a **product** decision (people may have already seen state). If allowed, audit it.

---

## 6. Optional later features (do not build until asked)

- Password on share link
- Email invite (still `link-self` after click)
- Explicit **leader transfer** endpoint (v1 has auto-succession only)
- **Per-group** `reservation_ttl_days` (today a module constant)
- **Access link expiry** (`link_expires_at` — dropped from v1 for simplicity)
- “Which option I bought” required on purchase
- Notifications (reserved / expiring)
- AI suggest options (own prompts + nonce, **not** TripSync AI modules)
- Payments — purchase stays a flag unless you add a payments port

If AI is added: new `adapters/ai/` + application port. Copy TripSync’s *propose/apply + nonce* idea, reimplement. No imports from `app.tripsync`.

---

## 7. Cloning this scaffold for the next product

Wishlist is the **template**. Next product (example: `potluck`, `registry`, `split`) should be a folder copy, not a shared “platform” library, until a third app proves duplication is painful.

### 7.1 Copy

```
cp -R backend/app/wishlist backend/app/<product>
# then rename package, prefixes, headers, collection names
```

### 7.2 Find-and-replace checklist

| Wishlist | Next product |
|----------|----------------|
| `app.wishlist` | `app.<product>` |
| `/api/wishlist` | `/api/<product>` |
| `X-Wishlist-*` | `X-<Product>-*` |
| `wishlist_*` collections | `<product>_*` |
| OpenAPI tag `Wishlist` | new tag |
| Docs folder `docs/wishlist/` | `docs/<product>/` |

### 7.3 Integration (same three hooks)

1. `main.py` — `include_router`
2. `database.py` — `document_models += [...]`
3. Auth — **only** `current_active_user` / `current_optional_user` / `User`

### 7.4 Keep isolated

- New domain entities
- New actor resolver
- New audit collection
- New tests under `backend/tests/<product>/`

### 7.5 When to extract a tiny shared helper

Only after **three** products need the same 20 lines (e.g. UUID access-token compare). Even then, put it in `app/shared/access_token.py` — not inside TripSync and not a grab-bag `kernel`.

Default: **duplicate the small helper**.

---

## 8. Docker, CI/CD, production

v1: no compose change.

When HTTP exists, add to CI (same workflow style as `test-production-docker-compose.yml`):

1. After health check, `POST /api/auth/register` + `POST /api/wishlist/` (or use a fixture user)
2. `GET /api/wishlist/my` with JWT
3. On failure, print `portfolio-backend-prod` logs (already in the workflow)

Scrape later: CI should run with `WISHLIST_PREVIEW_ENABLED=false` so tests do not hit the network.

Expire job later: do not run cron against the CI compose that uses `-v` wipe.

Production Mongo: new collections are created by Beanie on startup. **No down-migration** of TripSync data. Indexes are defined on Wishlist documents only.

---

## 9. Observability later

- Structured audit actions: `group.create`, `member.link`, `product.create`, `reserve`, `release`, `expire`, `purchase`, `link.rotate`
- Metrics (if you add them): reserve 409 rate, purchase latency, scrape failures
- Never log share tokens, guest secrets, or JWTs

---

## 10. Suggested order after v1 ships

1. Frontend share + login purchase
2. Expire cron + index
3. URL preview adapter + SSRF guards
4. Clone scaffold only when a real second product starts
5. AI / payments only with a new PRD addendum

---

## 11. Pointers

- Implement now: [`01-scaffold-and-conventions.md`](./01-scaffold-and-conventions.md)
- Spec: [`03-prd-hld-lld.md`](./03-prd-hld-lld.md)
