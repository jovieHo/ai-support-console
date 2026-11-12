"""轻量 DDL 迁移
SQLAlchemy 的 create_all 只补缺表/缺索引，绝不会给已存在的表加列。
新增字段后在这里补一条 ALTER，启动前手动执行一次即可（幂等，重复跑只打印 skip）。
"""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

# 表名 -> [(列名, 列定义)]
ADDED_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "conversations": [
        ("is_favorite", "BOOLEAN DEFAULT 0"),
    ],
    "knowledge_documents": [
        ("parse_status", "VARCHAR(30) DEFAULT 'indexed'"),
        ("parse_message", "VARCHAR(500) DEFAULT '已完成解析并建立知识分块'"),
        ("parsed_at", "DATETIME"),
    ],
    "ai_invocations": [
        ("entry", "VARCHAR(20) DEFAULT 'chat'"),
        ("is_escalated", "BOOLEAN DEFAULT 0"),
    ],
}

# 表名 -> [(索引名, 列名)]
ADDED_INDEXES: dict[str, list[tuple[str, str]]] = {
    "ai_invocations": [
        ("ix_ai_invocations_entry", "entry"),
        ("ix_ai_invocations_is_escalated", "is_escalated"),
    ],
}


def apply_migrations(engine: Engine) -> None:
    """按清单补齐缺失的列和索引，幂等可重复执行。

    表尚不存在（首次启动、空库、create_all 尚未建表）时直接跳过，
    不会因 inspect 缺表而抛 NoSuchTableError。
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, columns in ADDED_COLUMNS.items():
            if table not in existing_tables:
                print(f"skip table {table} (not created yet)")
                continue
            existing = {column["name"] for column in inspector.get_columns(table)}
            for name, ddl_type in columns:
                if name in existing:
                    print(f"skip column {table}.{name}")
                    continue
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl_type}"))
                print(f"add column {table}.{name}")
        for table, indexes in ADDED_INDEXES.items():
            if table not in existing_tables:
                print(f"skip index table {table} (not created yet)")
                continue
            existing = {index["name"] for index in inspector.get_indexes(table)}
            for name, column in indexes:
                if name in existing:
                    print(f"skip index {name}")
                    continue
                conn.execute(text(f"CREATE INDEX {name} ON {table} ({column})"))
                print(f"add index {name}")


def main() -> None:
    from database import engine

    apply_migrations(engine)


if __name__ == "__main__":
    main()
