from sqlalchemy.orm import declarative_base, Session
from sqlalchemy import Column, Integer
from sqlalchemy import create_engine

Base = declarative_base()

class TestUrl(Base):
    __tablename__ = "test_urls"
    id = Column(Integer, primary_key=True)

engine = create_engine("sqlite:///:memory:")
Base.metadata.create_all(engine)

with Session(engine) as session:
    u = TestUrl(id=1)
    session.add(u)
    session.commit()
    
    u.scraped_text = "hello"
    session.commit()
    print("Success! u.scraped_text:", u.scraped_text)
