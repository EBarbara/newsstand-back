from pydantic import BaseModel
from datetime import date


class PersonSchema(BaseModel):
    id: int
    name: str


class SectionSchema(BaseModel):
    id: int
    name: str


class CreditSchema(BaseModel):
    person: PersonSchema
    role: str | None


class IssueSectionSchema(BaseModel):
    section: SectionSchema
    page: int | None
    page_indexes: list[int]
    credits: list[CreditSchema]


class IssueSchema(BaseModel):
    id: int
    publishing_date: date
    edition: int | None
    sections: list[IssueSectionSchema]