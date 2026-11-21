from typing import Optional, List, Dict, Tuple
from datetime import date, timedelta
from sqlalchemy import create_engine, text
from pydantic_settings import BaseSettings, SettingsConfigDict
import pandas as pd
import logging

log = logging.getLogger(__name__)

class DBSettings(BaseSettings):
    database_url: str
    student_name: str

    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=False, extra="ignore"
    )

settings = DBSettings()


def normalize_db_url(url: str) -> str:
    """SQLAlchemy 2.1+ memakai driver psycopg (v3) untuk 'postgresql://'.
    Project ini memakai psycopg2-binary, jadi driver-nya ditulis eksplisit."""
    if url.startswith("postgresql://"):
        return "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


engine = create_engine(
    normalize_db_url(settings.database_url),
    # Server database kelas memutus koneksi yang menganggur. pool_pre_ping mengecek
    # koneksi sebelum dipakai dan otomatis menyambung ulang kalau sudah putus;
    # pool_recycle mengganti koneksi yang umurnya lebih dari 5 menit.
    pool_pre_ping=True,
    pool_recycle=300,
)

SCHEMA = "ai_engineer3"
ARTICLES_TABLE = f'"{SCHEMA}".articles_{settings.student_name}'
ATTRITION_TABLE_NAME = f"raw_attrition_{settings.student_name}"
ATTRITION_TABLE = f'"{SCHEMA}".{ATTRITION_TABLE_NAME}'

def init_db():
    """Create tables and indexes if they don't exist."""
    ddl = f"""
    CREATE TABLE IF NOT EXISTS {ARTICLES_TABLE} (
        id           SERIAL PRIMARY KEY,
        title        TEXT NOT NULL,
        url          TEXT UNIQUE NOT NULL,
        source       TEXT NOT NULL,
        content      TEXT,
        published_at TIMESTAMP,
        scraped_at   TIMESTAMP DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_articles_source
        ON {ARTICLES_TABLE}(source);
    CREATE INDEX IF NOT EXISTS idx_articles_published
        ON {ARTICLES_TABLE}(published_at DESC);
    """
    with engine.begin() as conn:
        conn.execute(text(ddl))
    log.info("Database ready. Table: %s", ARTICLES_TABLE)

def save_articles(df: pd.DataFrame) -> int:
    """Insert articles with ON CONFLICT — safe to re-run."""
    if df.empty:
        log.warning("DataFrame kosong, tidak ada yang di-insert.")
        return 0

    inserted = 0
    with engine.begin() as conn:
        for _, row in df.iterrows():
            result = conn.execute(
                text(f"""
                    INSERT INTO {ARTICLES_TABLE}
                        (title, url, source, content, published_at)
                    VALUES
                        (:title, :url, :source, :content, :published_at)
                    ON CONFLICT (url) DO NOTHING
                """),
                {
                    "title": row["title"],
                    "url": row["url"],
                    "source": row["source"],
                    "content": row["content"],
                    "published_at": row["published_at"]
                    if pd.notna(row["published_at"])
                    else None,
                },
            )
            inserted += result.rowcount

    log.info("Insert selesai: %d baru dari %d record.", inserted, len(df))
    return inserted


def count_articles() -> int:
    """Count total articles in DB."""
    with engine.connect() as conn:
        result = conn.execute(text(f"SELECT COUNT(*) FROM {ARTICLES_TABLE}"))
        return result.scalar()

def count_articles_by_source() -> Dict[str, int]:
    """
    Hitung jumlah artikel per source.
    Return contoh: {"bbc": 50, "nytimes": 30, "books.toscrape": 200}
    """
    # TODO 18: Tulis query SELECT source, COUNT(*) ... GROUP BY source
    #          Lalu convert hasil ke dictionary {source: count}
    with engine.connect() as conn:
        rows = conn.execute(text(
            f"SELECT source, COUNT(*) as cnt FROM {ARTICLES_TABLE}"
            f" GROUP BY source ORDER BY cnt DESC"
        )).mappings().all()
    return {row["source"]: row["cnt"] for row in rows}

def get_articles(
    source: Optional[str] = None,
    title: Optional[str] = None,
    limit: int = 20,
) -> List[Dict]:
    """
    Cari articles dengan optional filter source dan title.

    Contoh pemanggilan:
      get_articles(source="bbc", limit=5)           → artikel BBC saja
      get_articles(title="python", limit=10)         → judul mengandung "python"
      get_articles(source="bbc", title="AI", limit=5) → BBC + judul ada "AI"
    """
    # TODO 19: Bangun query SELECT secara dinamis berdasarkan parameter
    #
    # Hint:
    #   - Mulai dengan: query = f"SELECT * FROM {ARTICLES_TABLE} WHERE 1=1"
    #   - Jika source ada:   tambah " AND source = :source"
    #   - Jika title ada:    tambah " AND title ILIKE :title"
    #     (ILIKE = case-insensitive LIKE di PostgreSQL)
    #     params["title"] = f"%{title}%"   ← wildcard di kedua sisi
    #   - Akhiri dengan: ORDER BY published_at DESC NULLS LAST LIMIT :limit
    #   - Execute dengan parameterized query (JANGAN string format untuk values!)
    #   - Return list of dicts: [dict(r) for r in rows]
    query = f"SELECT * FROM {ARTICLES_TABLE} WHERE 1=1"
    params: dict = {}

    if source:
        query += " AND source = :source"
        params["source"] = source.lower()

    if title:
        query += " AND title ILIKE :title"
        params["title"] = f"%{title}%"

    query += " ORDER BY published_at DESC NULLS LAST LIMIT :limit"
    params["limit"] = limit

    with engine.connect() as conn:
        rows = conn.execute(text(query), params).mappings().all()
    return [dict(r) for r in rows]

def get_article_by_id(article_id: int) -> Optional[Dict]:
    """Get single article by ID. Return None jika tidak ditemukan."""
    # TODO 20: SELECT * FROM ... WHERE id = :id
    #
    # Hint:
    with engine.connect() as conn:
        row = conn.execute(
            text(f"SELECT * FROM {ARTICLES_TABLE} WHERE id = :id"),
            {"id": article_id},
        ).mappings().first()
    return dict(row) if row else None

def get_attrition_summary() -> Dict:
    """
    Overall stats: total karyawan, jumlah & rate attrition.
    Return contoh: {"total_employees": 1470, "attrition_yes": 237, ...}
    """
    # TODO 21: Hitung total karyawan dan jumlah yang Attrition = 'Yes'
    with engine.connect() as conn:
        row = conn.execute(text(f"""
            SELECT 
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE "Attrition" = 'Yes') AS attrition_yes
            FROM {ATTRITION_TABLE}
        """)).mappings().one()
        total = row["total"]
        attrition_yes = row["attrition_yes"]
    return {
        "total_employees": total,
        "attrition_yes": attrition_yes,
        "attrition_no": total - attrition_yes,
        "attrition_rate": round(attrition_yes / total, 4) if total > 0 else 0.0,
    }

def get_attrition_by_department() -> List[Dict]:
    """
    Attrition rate + avg income per department.
    Ini gabungan query 1 & 2 dari transform_attrition.sql Session 9.
    """
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT
                "Department",
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE "Attrition" = 'Yes') AS attrition_count,
                ROUND(
                    COUNT(*) FILTER (WHERE "Attrition" = 'Yes')::numeric / COUNT(*), 3
                ) AS attrition_rate,
                ROUND(AVG("MonthlyIncome")::numeric, 2) AS avg_income
            FROM {ATTRITION_TABLE}
            GROUP BY "Department"
            ORDER BY attrition_rate DESC
        """)).mappings().all()
    return [dict(r) for r in rows]

def get_attrition_by_tenure() -> List[Dict]:
    """
    Attrition by tenure bucket.
    Ini query 3 dari transform_attrition.sql Session 9.
    """
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT
                CASE
                    WHEN "YearsAtCompany" < 2 THEN '1. new (<2y)'
                    WHEN "YearsAtCompany" < 5 THEN '2. mid (2-5y)'
                    ELSE '3. veteran (5y+)'
                END AS tenure_bucket,
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE "Attrition" = 'Yes') AS attrition_count,
                ROUND(
                    COUNT(*) FILTER (WHERE "Attrition" = 'Yes')::numeric / COUNT(*), 3
                ) AS attrition_rate
            FROM {ATTRITION_TABLE}
            GROUP BY tenure_bucket
            ORDER BY tenure_bucket
        """)).mappings().all()
    return [dict(r) for r in rows]


def get_attrition_by_overtime() -> List[Dict]:
    """
    Attrition by overtime status.
    Ini query 4 dari transform_attrition.sql Session 9.
    """
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT
                "OverTime",
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE "Attrition" = 'Yes') AS attrition_count,
                ROUND(
                    COUNT(*) FILTER (WHERE "Attrition" = 'Yes')::numeric / COUNT(*), 3
                ) AS attrition_rate
            FROM {ATTRITION_TABLE}
            GROUP BY "OverTime"
            ORDER BY "OverTime"
        """)).mappings().all()
    return [dict(r) for r in rows]


def get_top_earners_by_department(limit_per_dept: int = 5) -> List[Dict]:
    """
    Top earners per department menggunakan RANK() window function.
    Ini query 5 dari transform_attrition.sql Session 9.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(f"""
                SELECT *
                FROM (
                    SELECT
                        "EmployeeNumber",
                        "Department",
                        "JobRole",
                        "MonthlyIncome",
                        "Attrition",
                        RANK() OVER (
                            PARTITION BY "Department"
                            ORDER BY "MonthlyIncome" DESC
                        ) AS income_rank
                    FROM {ATTRITION_TABLE}
                ) ranked
                WHERE income_rank <= :limit_per_dept
                ORDER BY "Department", income_rank
            """),
            {"limit_per_dept": limit_per_dept},
        ).mappings().all()
    return [dict(r) for r in rows]


# ==================================================================
# MINI PROJECT 2
# ==================================================================

# ---------- TASK 1: Article Search dengan Pagination ----------

def _build_article_filters(
    source: Optional[str],
    title: Optional[str],
    date_from: Optional[date],
    date_to: Optional[date],
) -> Tuple[str, Dict]:
    """Bangun klausa WHERE + params. Dipakai bersama oleh query COUNT dan query data,
    supaya total_items dan isi halaman selalu memakai filter yang sama."""
    where = " WHERE 1=1"
    params: Dict = {}

    if source:
        where += " AND source = :source"
        params["source"] = source.strip().lower()

    if title:
        where += " AND title ILIKE :title"
        params["title"] = f"%{title}%"

    if date_from:
        where += " AND published_at >= :date_from"
        params["date_from"] = date_from

    if date_to:
        # date_to inklusif: artikel sepanjang hari itu (s/d 23:59:59) tetap ikut,
        # jadi dibandingkan dengan "< hari berikutnya"
        where += " AND published_at < :date_to_next"
        params["date_to_next"] = date_to + timedelta(days=1)

    return where, params


def search_articles(
    source: Optional[str] = None,
    title: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = 1,
    per_page: int = 10,
) -> Tuple[List[Dict], int]:
    """Cari artikel dengan filter + pagination. Return (data_halaman_ini, total_items)."""
    where, params = _build_article_filters(source, title, date_from, date_to)
    offset = (page - 1) * per_page

    with engine.connect() as conn:
        total_items = conn.execute(
            text(f"SELECT COUNT(*) FROM {ARTICLES_TABLE}{where}"), params
        ).scalar()

        rows = conn.execute(
            text(
                f"SELECT * FROM {ARTICLES_TABLE}{where}"
                # id sebagai penentu urutan kedua: artikel dengan published_at sama
                # (atau NULL, misalnya buku) tetap punya urutan pasti antar halaman
                " ORDER BY published_at DESC NULLS LAST, id DESC"
                " LIMIT :limit OFFSET :offset"
            ),
            {**params, "limit": per_page, "offset": offset},
        ).mappings().all()

    return [dict(r) for r in rows], total_items


# ---------- TASK 3: Department Detail ----------

def get_department_detail(dept_name: str) -> Optional[Dict]:
    """Statistik lengkap satu department + 3 top earner. Return None jika tidak ada."""
    with engine.connect() as conn:
        stats = conn.execute(
            text(f"""
                SELECT
                    "Department" AS department,
                    COUNT(*) AS total_employees,
                    COUNT(*) FILTER (WHERE "Attrition" = 'Yes') AS attrition_count,
                    ROUND(
                        COUNT(*) FILTER (WHERE "Attrition" = 'Yes')::numeric / COUNT(*), 4
                    ) AS attrition_rate,
                    ROUND(AVG("MonthlyIncome")::numeric, 2) AS avg_income,
                    MIN("MonthlyIncome") AS min_income,
                    MAX("MonthlyIncome") AS max_income
                FROM {ATTRITION_TABLE}
                WHERE LOWER("Department") = LOWER(:dept)
                GROUP BY "Department"
            """),
            {"dept": dept_name.strip()},
        ).mappings().first()

        if stats is None:
            return None

        top_earners = conn.execute(
            text(f"""
                SELECT "EmployeeNumber", "JobRole", "MonthlyIncome"
                FROM (
                    SELECT
                        "EmployeeNumber",
                        "JobRole",
                        "MonthlyIncome",
                        RANK() OVER (ORDER BY "MonthlyIncome" DESC) AS income_rank
                    FROM {ATTRITION_TABLE}
                    WHERE "Department" = :dept
                ) ranked
                ORDER BY income_rank, "EmployeeNumber"
                LIMIT 3
            """),
            {"dept": stats["department"]},
        ).mappings().all()

    result = dict(stats)
    result["top_earners"] = [dict(r) for r in top_earners]
    return result


# ---------- TASK 4: Attrition Risk Profile ----------

def get_attrition_risk_profile(limit: int = 20) -> Dict:
    """Karyawan high-risk: OverTime = 'Yes', YearsAtCompany < 3,
    dan MonthlyIncome di bawah rata-rata department-nya sendiri."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(f"""
                WITH dept_avg AS (
                    SELECT "Department", AVG("MonthlyIncome") AS avg_income
                    FROM {ATTRITION_TABLE}
                    GROUP BY "Department"
                )
                SELECT
                    e."EmployeeNumber",
                    e."Department",
                    e."JobRole",
                    e."YearsAtCompany",
                    e."OverTime",
                    e."MonthlyIncome",
                    ROUND(d.avg_income::numeric, 2) AS dept_avg_income,
                    e."Attrition",
                    -- dihitung SEBELUM LIMIT, jadi berisi total seluruh karyawan high-risk
                    COUNT(*) OVER () AS total_high_risk,
                    COUNT(*) FILTER (WHERE e."Attrition" = 'Yes') OVER () AS total_left
                FROM {ATTRITION_TABLE} e
                JOIN dept_avg d ON e."Department" = d."Department"
                WHERE e."OverTime" = 'Yes'
                  AND e."YearsAtCompany" < 3
                  AND e."MonthlyIncome" < d.avg_income
                ORDER BY e."MonthlyIncome" ASC, e."EmployeeNumber"
                LIMIT :limit
            """),
            {"limit": limit},
        ).mappings().all()

    employees = [dict(r) for r in rows]
    total_high_risk = employees[0]["total_high_risk"] if employees else 0
    total_left = employees[0]["total_left"] if employees else 0
    for emp in employees:
        emp.pop("total_high_risk")
        emp.pop("total_left")

    return {
        "criteria": {
            "OverTime": "Yes",
            "YearsAtCompany": "< 3",
            "MonthlyIncome": "di bawah rata-rata department",
        },
        "total_high_risk": total_high_risk,
        "high_risk_attrition_rate": (
            round(total_left / total_high_risk, 4) if total_high_risk else 0.0
        ),
        "limit": limit,
        "employees": employees,
    }
