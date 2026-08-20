from pydantic import BaseModel, Field
from typing import List
import uuid
from datetime import datetime

class KeywordOut(BaseModel):
    id: uuid.UUID
    phrase: str
    keyword_type: str
    frequency: int
    search_volume: int | None
    difficulty: float | None
    source_urls: List[str] = Field(default_factory=list)
    created_at: datetime

    class Config:
        from_attributes = True

class Keyword:
    def __init__(self):
        self.id = uuid.uuid4()
        self.phrase = "test"
        self.keyword_type = "primary"
        self.frequency = 1
        self.search_volume = None
        self.difficulty = None
        self.created_at = datetime.now()

try:
    kw = Keyword()
    out = KeywordOut.model_validate(kw)
    print("Success")
except Exception as e:
    import traceback
    traceback.print_exc()
