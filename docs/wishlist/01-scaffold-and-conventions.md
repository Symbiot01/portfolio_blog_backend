# Wishlist — Scaffold and project conventions

This is the **implementation handbook** for Wishlist inside `portfolio-backend`.

Covers:

- How Wishlist sits next to Auth, Blog, Admin, Uploads, TripSync
- What is **shared** vs **owned only by Wishlist**
- Hexagonal folder scaffold
- Integration points (`main.py`, Beanie, rate limits)
- Naming, headers, errors, testing

Product behavior, HLD, LLD → [`03-prd-hld-lld.md`](./03-prd-hld-lld.md).  
Later work (scrape, cron, frontend, cloning) → [`02-future-and-integration.md`](./02-future-and-integration.md).

When behavior and scaffold disagree, **PRD/LLD wins for behavior**, this file wins for **folder + integration**.

---

## 1. Placement

Wishlist is a new bounded context in the existing FastAPI + Beanie app.

| Existing module | Relationship |
|-----------------|--------------|
| `app/auth/` | **Shared.** Use `current_active_user` and `current_optional_user` only. |
| `app/models/user.py` | **Shared.** `User` is the identity. Do not add Wishlist fields. |
| `app/core/database.py` | **Shared hook.** Register Wishlist documents here. |
| `backend/main.py` | **Shared hook.** `include_router` at `/api/wishlist`. |
| `app/tripsync/` | **Peer, not a dependency.** Copy patterns, never import. |
| `app/blog/`, `app/admin/`, `app/uploads/` | Unrelated. |

- **Mount:** `/api/wishlist`
- **OpenAPI tag:** `Wishlist`
- **Python package:** `app.wishlist`

TripSync and Wishlist share process + Mongo + `User`, nothing else.

---

## 2. Shared vs isolated (hard rule)

### Allowed to import

- `from app.auth.core import current_active_user, current_optional_user`
- `from app.models.user import User`
- Beanie, Pydantic, FastAPI, `slowapi` (already in the app)
- Env vars already used: `DATABASE_URL`, `DATABASE_NAME`, `SECRET_KEY`

### Must stay Wishlist-local

- All Wishlist documents, schemas, deps, services, audit
- Access-token generation / validation
- Actor resolution (`resolve_wishlist_actor`)
- HTTP headers (`X-Wishlist-*`, not `X-Trip-*`)
- Router-local `Limiter` and `@limiter.limit(...)`

### Forbidden

- `from app.tripsync...`
- Reusing `Trip`, `TripDoc`, `TripAuditEvent`, `TripEditNonce`
- Adding Wishlist fields to `User`
- Placing Wishlist Beanie docs under `app/models/`

TripSync keeps its docs in `app/models/` for historical reasons. Wishlist keeps them **inside its own package** so the next product can be a folder copy.

---

## 3. Hexagonal folder scaffold

Rules:

- `domain/` has **no FastAPI, no Beanie, no httpx**.
- `application/` depends on **ports** (Protocol classes) only.
- `adapters/` implement ports.

```
backend/app/wishlist/
  __init__.py
  wiring.py                  # compose adapters + build use cases

  domain/
    __init__.py
    errors.py                # WishlistError subclasses
    actor.py                 # MemberActor | GuestActor
    group.py                 # Group, members, settings, link
    product.py               # Product + ProductOption + status
    reservation.py           # Reservation + status
    purchase.py              # Purchase record

  application/
    __init__.py
    ports.py                 # GroupRepo, ProductRepo, ReservationRepo,
                             # Clock, AccessTokenGen, ProductPreview
    groups.py                # create, list mine, view, leave, rotate/revoke
    members.py               # add slot, link-self
    products.py              # add, update, delete
    reservations.py          # reserve, release, expire, purchase
    views.py                 # combined / personal + spoiler filter

  adapters/
    __init__.py
    clock.py                 # UtcClock
    preview.py               # NullPreview (v1 = always "manual")
    http/
      __init__.py
      router.py              # routes + exception-to-HTTP mapping
      schemas.py             # Pydantic request/response
      deps.py                # resolve_wishlist_actor + Depends factories
    db/
      __init__.py
      documents.py           # Beanie Document classes + indexes in Settings
      repositories.py        # port implementations
```

Tests (v1):

```
backend/tests/wishlist/
  test_domain_reservation.py
  test_domain_leader.py
  test_application_reserve.py
  test_application_purchase.py
  test_http_auth_matrix.py
```

Domain and application tests use fakes. They must not need Mongo.

---

## 4. Integration hooks (only three)

These are the **only** edits outside `app/wishlist/`.

### 4.1 `backend/main.py`

```python
from app.wishlist.adapters.http.router import router as wishlist_router

app.include_router(wishlist_router, prefix="/api/wishlist", tags=["Wishlist"])
```

No Wishlist business logic in `main.py`.

### 4.2 `backend/app/core/database.py`

Import Wishlist documents and append to `document_models` in `init_beanie`. Do not open a second Mongo client.

### 4.3 Rate limiting

Router-local `Limiter(key_func=get_remote_address)` and `@limiter.limit(...)` on public preview and on mutating routes. The process-level limiter in `main.py` stays.

### 4.4 Env

v1 needs **no new secrets**.

### 4.5 Docker / CI

`docker-compose.prod.yaml` and the GitHub workflow are unchanged for v1. Health remains `/api/health`. Add Wishlist smoke tests only when routes exist.

---

## 5. Auth conventions

Identity is FastAPI-Users, already wired.

| Dependency | Wishlist use |
|------------|--------------|
| `current_active_user` | create, `GET /my`, link-self, leave, rotate/revoke, purchase |
| `current_optional_user` | inside `resolve_wishlist_actor` — login member **or** fall through to share token |

Do **not** create a second user manager, JWT backend, or a `guest User` row. Guests are Wishlist actors (`guest_id` + display name), never `User(is_guest=True)`.

---

## 6. HTTP conventions

### Headers (Wishlist-owned)

| Header | Purpose |
|--------|---------|
| `Authorization: Bearer <jwt>` | Logged-in user |
| `X-Wishlist-Access` | Share token (URL query fallback: `access_token`) |
| `X-Wishlist-Guest` | Per-group guest id, issued by the first reserve response |

No `X-Wishlist-Edit` gate: guests are expected to add and reserve. Purchase still requires JWT.

### Status codes

| Code | When |
|------|------|
| 201 | Group / product / reservation created |
| 204 | Revoke, leave with no body |
| 400 | Domain validation (own-list reserve, bad option payload) |
| 401 | Purchase / create / link-self without JWT |
| 403 | Missing/invalid/revoked share token; not linked member |
| 404 | Group / product / reservation not found |
| 409 | Already reserved, cap exceeded, already bought |

### Response style

- IDs as strings
- Datetimes ISO 8601 UTC
- Money is `float` + optional `currency` string
- Never echo the share `access_token` in a public preview response

---

## 7. Persistence conventions

| Collection | Document |
|------------|----------|
| `wishlist_groups` | `WishlistGroupDoc` (embeds members) |
| `wishlist_products` | `WishlistProductDoc` |
| `wishlist_reservations` | `WishlistReservationDoc` |
| `wishlist_purchases` | `WishlistPurchaseDoc` |
| `wishlist_audit_events` | `WishlistAuditEventDoc` *(optional)* |

Indexes (declared in each Document's `Settings.indexes`):

- `wishlist_groups`: unique `access_token`
- `wishlist_products`: `(group_id, owner_member_id)`
- `wishlist_reservations`:
  - **partial unique** `(product_id)` where `status = "active"` (enforces one active reservation per product)
  - `(group_id, guest_id, status)` and `(group_id, actor_user_id, status)` for cap queries
  - `(expires_at, status)` for later cron

Documents may hold `Link[User]` for linked members. Beanie stays inside adapters, not in `domain/`.

Members are embedded on `WishlistGroup`. **Cap embedded members at 20** to keep the document small; anything beyond that would need a separate collection.

---

## 8. Layer rules (review checklist)

1. `domain/` raises `WishlistError` subclasses only. No `HTTPException`.
2. `application/` orchestrates one use case per function. No FastAPI types.
3. `adapters/http/router.py` maps HTTP → use case → schema. Thin.
4. `adapters/db/repositories.py` is the only Beanie I/O.
5. `wiring.py` is the only place that instantiates concrete adapters.
6. Router obtains use cases via `Depends` factories. No import-time Mongo.

Minimum viable DI, in `wiring.py`:

```python
# adapters/http/deps.py
from fastapi import Depends
from app.wishlist.wiring import get_container

def reserve_use_case(c = Depends(get_container)):
    return c.reserve_product
```

```python
# wiring.py (sketch)
class Container:
    def __init__(self):
        clock = UtcClock()
        group_repo = MongoGroupRepo()
        product_repo = MongoProductRepo()
        reservation_repo = MongoReservationRepo()
        self.reserve_product = ReserveProduct(product_repo, reservation_repo, clock)
        # ... other use cases

_container: Container | None = None
def get_container() -> Container:
    global _container
    if _container is None:
        _container = Container()
    return _container
```

Repos are Beanie thin wrappers; no globals leak into `domain/`.

---

## 9. Patterns borrowed from TripSync

Copy the **behavior**, reimplement inside Wishlist:

| TripSync idea | Wishlist equivalent |
|---------------|---------------------|
| `resolve_trip_actor` | `resolve_wishlist_actor` in `adapters/http/deps.py` |
| Share UUID + rotate / revoke | Group `access_token` + `link_revoked` |
| `link-self` | Same shape, Wishlist members |
| Audit insert best-effort | `WishlistAuditEvent` (optional) |
| `@limiter.limit` on public token preview | Same on `GET /access/{token}` |
| Members embedded on parent doc | Members embedded on `WishlistGroup` |

Do not copy TripDoc JSON-patch, AI nonce, expenses, or itinerary.

---

## 10. Config defaults (v1)

| Setting | Where | Default | Notes |
|---------|-------|---------|--------|
| `owners_can_see_fulfillment` | `WishlistGroupDoc.settings` | required at create | Spoiler switch. Fixed in v1. |
| `max_active_reservations` | `WishlistGroupDoc.settings` | `2` (1–5) | Per actor per group. |
| `RESERVATION_TTL_DAYS` | Module constant in `application/reservations.py` | `14` | Not per-group in v1. Moves to a setting later. |

`UtcClock` is injected so tests expire reservations without sleeping.

---

## 11. Locked product rules (implementer checklist)

**Strict freeze (domain `Product.assert_can_patch` / `assert_can_delete`):**

| Status | PATCH | DELETE |
|--------|-------|--------|
| `open` | creator or leader | creator or leader |
| `reserved` | forbidden | forbidden |
| `bought` | forbidden | leader only |

**Rotate link:** new UUID + clear `link_revoked`; **auto-release all active guest reservations** (`guest_id is not None`); linked-member reservations keep `active`. Products with no remaining active reservation flip to `open`.

---

## 12. Security baseline

- Share token is a **capability**. Treat it like a password: random UUID, rotatable, revocable.
- Never log `access_token`.
- Guest id is `secrets.token_urlsafe(32)`, per group.
- Purchase requires JWT even when a guest header is present.
- Owner cannot reserve products on their own list.
- Spoiler filter lives in `application/views.py`, never bypassed by a raw document dump.
- Input limits: title/name caps, options list max 20, URL length cap, rate limits on reserve/add.

---

## 13. Doc map

| Doc | Audience | When |
|-----|----------|------|
| This file | Implementer | Before writing code |
| [`02-future-and-integration.md`](./02-future-and-integration.md) | Implementer / future self | After v1, or when adding scrape / cloning |
| [`03-prd-hld-lld.md`](./03-prd-hld-lld.md) | Product + engineering | Spec, HLD, LLD, API, state |
