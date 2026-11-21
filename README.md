# Mini Project 2 — News & HR Analytics API

Bootcamp Fullstack AI Engineer for GenAI & AI Agent (DigitalSkola), gabungan materi **Session 9–11**.

Dua pipeline data, satu API:

- **Path A — ETL:** scrape RSS berita, books.toscrape, dan quotes.toscrape → dibersihkan di pandas → di-load ke PostgreSQL (`articles_<STUDENT_NAME>`).
- **Path B — ELT:** CSV IBM HR Attrition di-load mentah (`raw_attrition_<STUDENT_NAME>`) → di-transform dengan SQL saat query.

## Endpoint Mini Project 2

| Task | Endpoint | Keterangan |
|---|---|---|
| 1 | `GET /articles/search` | Filter `source`, `title` (case-insensitive), `date_from` & `date_to` (YYYY-MM-DD, inklusif) + pagination `page` (default 1) dan `per_page` (default 10, max 50). Response: `data`, `page`, `per_page`, `total_items`, `total_pages`. |
| 2 | `GET /articles/stats` | Total artikel + jumlah per source (`GROUP BY source`). |
| 3 | `GET /attrition/department/{dept_name}` | Statistik lengkap satu department + 3 top earner (`RANK() OVER`). Nama department tidak case-sensitive; department yang tidak ada → 404. |
| 4 | `GET /attrition/risk-profile` | Karyawan high-risk: `OverTime = Yes`, `YearsAtCompany < 3`, gaji di bawah rata-rata department-nya (CTE + JOIN). Query param `limit` (default 20, max 100). |

Semua endpoint data membutuhkan autentikasi, salah satu dari:

- **API Key:** header `X-API-Key`
- **JWT Bearer:** `POST /token` dengan `client_id` + `client_secret`, lalu header `Authorization: Bearer <token>`

Endpoint dari Session 11 (`/articles`, `/articles/{id}`, `/attrition/summary`, `/attrition/by-department`, `/attrition/by-overtime`, `/attrition/by-tenure`, `/attrition/top-earners`) tetap tersedia.

## Struktur file

| File | Isi |
|---|---|
| `main.py` | Aplikasi FastAPI: endpoint, response model Pydantic, autentikasi API Key + JWT |
| `db.py` | Koneksi PostgreSQL (SQLAlchemy) dan semua query SQL |
| `pipeline.py` | Menjalankan Path A (ETL) dan Path B (ELT) |
| `scraper.py` | Scraping RSS, books.toscrape, quotes.toscrape |
| `cleaner.py` | Cleaning data hasil scraping dengan pandas |
| `transform_attrition.sql` | Query transform ELT dari Session 9 |
| `cek_db.py` | Helper untuk mengecek koneksi database dan schema |
| `Session11_API.postman_collection.json` | Postman collection dari Session 11 |
| `.env.example` | Contoh konfigurasi (salin menjadi `.env`) |

## Cara menjalankan

```bash
# 1. Install dependency
python -m pip install -r requirements.txt

# 2. Salin .env.example menjadi .env lalu isi nilainya

# 3. Isi database (taruh employee_attrition.csv dari Kaggle di folder ini)
python pipeline.py

# 4. Nyalakan API, lalu buka http://127.0.0.1:8000/docs
python -m uvicorn main:app --reload
```

## Catatan teknis

- Tabel berada di schema `ai_engineer3`.
- `DATABASE_URL` boleh ditulis `postgresql://...`; `db.py` otomatis memakai driver `psycopg2` karena SQLAlchemy 2.1 mengganti driver bawaannya ke `psycopg` (v3).
- `pool_pre_ping=True` dipakai karena server database memutus koneksi yang menganggur.
- `/articles/search` dan `/articles/stats` didefinisikan **sebelum** `/articles/{article_id}` agar tidak terbaca sebagai ID artikel (422).
- Urutan pagination: `published_at DESC NULLS LAST, id DESC`, supaya setiap halaman konsisten dan tidak tumpang tindih.
