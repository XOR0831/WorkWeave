from alembic import context
from sqlalchemy import create_engine

from app.config import get_settings

url = context.config.attributes.get("url") or get_settings().url()


def run() -> None:
    engine = create_engine(url)
    with engine.connect() as conn:
        context.configure(connection=conn, version_table_schema="workweave", transactional_ddl=True)
        with context.begin_transaction():
            context.run_migrations()


run()
