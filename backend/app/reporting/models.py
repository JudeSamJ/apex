import uuid
from sqlalchemy import Column, String, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from app.database import Base

class Budget(Base):
    __tablename__ = "budgets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_id = Column(String(36), ForeignKey("entities.id"), nullable=False)
    department_id = Column(String(36), ForeignKey("departments.id"), nullable=True)  # Scoped to dept
    category = Column(String(100), nullable=True)  # Scoped to spend category
    period = Column(String(7), nullable=False)  # YYYY-MM
    amount = Column(Numeric(18, 4), nullable=False)

    entity = relationship("Entity")
    department = relationship("Department")
