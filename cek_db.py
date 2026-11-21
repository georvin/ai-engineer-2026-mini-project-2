"""Helper Mini Project 2: cek koneksi database dan schema yang tersedia."""
from sqlalchemy import create_engine, text
from db import settings, normalize_db_url

engine = create_engine(normalize_db_url(settings.database_url), connect_args={"connect_timeout": 10})
KANDIDAT_SCHEMA = ["ai_engineer", "ai_engineer3"]

try:
    with engine.connect() as conn:
        print("KONEKSI BERHASIL")
        print("User DB  :", conn.execute(text("SELECT current_user")).scalar())
        for schema in KANDIDAT_SCHEMA:
            ada = conn.execute(
                text("SELECT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = :s)"),
                {"s": schema},
            ).scalar()
            if not ada:
                print(f"Schema {schema:13s}: TIDAK ADA")
                continue
            boleh = conn.execute(text("SELECT has_schema_privilege(:s, 'CREATE')"), {"s": schema}).scalar()
            jumlah = conn.execute(
                text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = :s"), {"s": schema}
            ).scalar()
            tutor = conn.execute(
                text("SELECT string_agg(table_name, ', ') FROM information_schema.tables "
                     "WHERE table_schema = :s AND table_name LIKE '%tutor%'"), {"s": schema}
            ).scalar()
            milikmu = conn.execute(
                text("SELECT string_agg(table_name, ', ') FROM information_schema.tables "
                     "WHERE table_schema = :s AND table_name LIKE :n"), {"s": schema, "n": f"%{settings.student_name}%"}
            ).scalar()
            print(f"Schema {schema:13s}: ADA | {jumlah} tabel | boleh buat tabel: {'YA' if boleh else 'TIDAK'}")
            print(f"    tabel tutor   : {tutor or '-'}")
            print(f"    tabel {settings.student_name:8s}: {milikmu or '-'}")
except Exception as e:
    print("KONEKSI GAGAL")
    print(type(e).__name__, ":", str(e).strip().splitlines()[0])
