# Smart Document Management System

A secure, division-aware document hub built for the TRIAD AI DMS take-home assignment. Backend implementation is on `feature/triad-dms`.

## Features

- Flask REST API with bearer-token authentication and role-based access control.
- MongoDB documents plus GridFS file storage; dynamic metadata fields and values.
- Division isolation enforced by API queries and per-document download checks.
- Cross-division access request, approval, and rejection workflow.
- PDF text extraction with OCR fallback for scanned PDFs and raster images; OCR status is recorded independently of upload success.
- Authorized search across title, arbitrary metadata values, and extracted text.
- React single-page UI with authentication, dashboard, document details, access inbox, advanced search, and admin/settings views.

## Architecture

`app/` contains the Flask application factory, MongoDB setup, auth, document, metadata, access, search and OCR modules. MongoDB stores users, divisions, metadata field definitions, document records, and access requests. GridFS stores every uploaded original. The Vite/React application in `frontend/` consumes the REST API.

## Requirements and setup

- Python 3.10+ and Node.js 18+.
- MongoDB 6+ reachable from the backend. Files are stored in the `documents.files`/`documents.chunks` GridFS collections.
- For OCR: Tesseract OCR and Poppler (`pdftoppm`) installed on the host. Text-based PDFs use PyMuPDF without OCR.

```bash
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env                   # set SECRET_KEY and MONGO_URI
flask --app run.py run --debug
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL (normally http://localhost:5173). The dev server proxies `/api` to Flask on port 5000. Configure `VITE_API_URL` if serving the UI separately.

### Configuration

See `.env.example`. `SECRET_KEY` must be a long random secret in production. `MONGO_URI` defaults to local MongoDB. `BOOTSTRAP_ADMIN_EMAIL` grants the admin role only to that email at registration; all other registrations receive the ordinary user role. Registration takes a division name and the server resolves/creates the division; clients cannot choose their role or division ID. `MAX_CONTENT_LENGTH` defaults to 25 MiB.

## REST API

All protected endpoints use `Authorization: Bearer <token>`.

- `POST /api/auth/register` JSON `{ "name", "email", "password", "division" }`
- `POST /api/auth/login` JSON `{ "email", "password" }` → `{ token, user }`
- `GET /api/divisions` list divisions for signup
- `POST /api/documents/upload` multipart `file`, optional `metadata` JSON and `title`. Document's division is always taken from the authenticated user's account. Returns 201 even if OCR fails; `ocr_status` reports `completed`, `failed`, or `pending`.
- `GET /api/documents` accessible records and dynamic query filters (e.g. `?Report%20Type=Financial`)
- `GET /api/documents/<doc_id>` authorized document details, or 403 plus `request_access_available` for an unapproved cross-division record.
- `GET /api/documents/<doc_id>/download` authorized GridFS download.
- `POST /api/access/request` JSON `{ "doc_id" }`
- `GET /api/access/requests` pending/incoming requests for the caller's division; `?outgoing=true` lists own requests.
- `POST /api/access/approve` JSON `{ "request_id", "decision": "approve" | "reject" }` (approval endpoint also accepts the legacy required `request_id` shape; absent decision defaults to approve).
- `GET /api/search?q=...` authorized search across title, metadata, and OCR text.
- `GET /api/metadata/fields` list configurable metadata definitions.
- `POST /api/metadata/fields` and `PUT /api/metadata/fields/<field_id>` create/edit definitions (admin only).

Errors use JSON `{ "error": "..." }`. Search/list results never include OCR body text. The database creates indexes for email uniqueness, division lookup, access workflow, and document search fields.

## UI pages

The navigation exposes Authentication (login/signup), Dashboard/Document Hub (filtering/upload), Document Details (metadata/download/request access), Access Requests Inbox (approve/reject), Advanced Search, and Admin/Settings (dynamic metadata field management). Admin API actions require the admin role; access requests are reviewable by members of the owning division.

## Tests

```bash
pytest -q
```

The included unit tests cover token/auth helpers, file validation, and OCR failure behavior. Set up MongoDB and run the server for API-level/manual workflows. The official repository's `test_api.py` is a one-case unauthenticated upload smoke test; the required secure upload API requires a login token, so that script as published receives 401 unless amended to register/login and send its bearer token. No unauthenticated-upload bypass is provided because it would defeat division isolation. The official script was inspected but cannot be run from this GitHub-only environment (no running MongoDB/server or shell execution is available); no test pass is claimed.

## Example workflow

1. Register a user in a division and log in.
2. Upload a PDF/image; the server stores it in GridFS and records OCR status/text separately.
3. Create metadata field definitions as an admin, then attach any configured or ad-hoc key/value metadata to uploads.
4. A user from another division may see document summaries from the hub/search without contents, open the detail page, and request access. A document's owner-division member can approve/reject; approval adds that user to the document's access list.
5. The approved user can download. The API denies downloads before approval.

## Security notes and limitations

- Set a strong secret and use HTTPS in deployment. Passwords are Werkzeug PBKDF2 hashes; tokens expire after 12 hours.
- MongoDB should use authenticated credentials and network restrictions in production.
- OCR requires host-installed Tesseract/Poppler for scanned pages; failures are persisted as OCR status/error and do not silently claim success.
- Email notifications, malware scanning, and production-grade rate limiting are outside this take-home implementation.
