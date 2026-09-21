import uuid
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    model: type[ModelType]

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, id_: uuid.UUID) -> ModelType | None:
        return self.db.get(self.model, id_)

    def add(self, instance: ModelType) -> ModelType:
        self.db.add(instance)
        self.db.flush()
        self.db.refresh(instance)
        return instance

    def delete(self, instance: ModelType) -> None:
        self.db.delete(instance)
        self.db.flush()

    def commit(self) -> None:
        self.db.commit()

    def list_all(self) -> list[ModelType]:
        return list(self.db.scalars(select(self.model)))
