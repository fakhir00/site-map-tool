import uuid
import sqlalchemy as sa
from sqlalchemy.orm import declarative_base, Session

Base = declarative_base()

class TestUrl(Base):
    __tablename__ = "test_urls"
    id = sa.Column(sa.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    url = sa.Column(sa.Text)

engine = sa.create_engine("sqlite:///:memory:", echo=True)
Base.metadata.create_all(engine)

with Session(engine) as session:
    u1 = TestUrl(url="url1")
    u2 = TestUrl(url="url2")
    session.add_all([u1, u2])
    session.commit()
    
    ids = [u1.id, u2.id]
    print(f"IDs: {ids}")
    
    # Try .in_ with UUID objects
    results = session.execute(sa.select(TestUrl).where(TestUrl.id.in_(ids))).scalars().all()
    print(f"Results with UUID objects: {len(results)}")
    
    # Try .in_ with string objects
    str_ids = [str(i) for i in ids]
    results2 = session.execute(sa.select(TestUrl).where(TestUrl.id.in_(str_ids))).scalars().all()
    print(f"Results with string objects: {len(results2)}")
    
    # Try .in_ with hex objects
    hex_ids = [i.hex for i in ids]
    results3 = session.execute(sa.select(TestUrl).where(TestUrl.id.in_(hex_ids))).scalars().all()
    print(f"Results with hex objects: {len(results3)}")
