from sqlalchemy import create_engine, select, Column, String, Text
from sqlalchemy.orm import declarative_base, Session
import sqlalchemy as sa
import uuid

Base = declarative_base()

class TestUrl(Base):
    __tablename__ = "urls"
    # Using String because we are querying the existing table, let's just map it as String for a second
    id = Column(sa.UUID(as_uuid=True), primary_key=True)
    url = Column(Text)

engine = create_engine("sqlite:///backend/sitemapseo.db", echo=True)

with Session(engine) as session:
    results = session.execute(select(TestUrl.id).limit(2)).scalars().all()
    print("Found IDs:", results)
    if results:
        # Now try IN
        try:
            in_results = session.execute(select(TestUrl).where(TestUrl.id.in_(results))).scalars().all()
            print("IN results:", len(in_results))
        except Exception as e:
            print("ERROR IN:", e)
