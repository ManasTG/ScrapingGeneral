from datetime import datetime
from typing import Dict, List, Optional, Any
from pydantic import BaseModel
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# SQLAlchemy Database Models
class DBUser(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False)  # "superadmin" or "admin"
    company_name = Column(String(255), nullable=True)
    db_name = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class DBSession(Base):
    __tablename__ = "user_sessions"
    
    token = Column(String(255), primary_key=True)
    username = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class DBScrapeJob(Base):
    __tablename__ = "scrape_jobs"
    
    id = Column(String(36), primary_key=True)
    website = Column(String(255), nullable=False)
    search_query = Column(String(255), nullable=False)
    limit = Column(Integer, default=5)
    status = Column(String(50), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    error_message = Column(Text, nullable=True)
    company_name = Column(String(255), nullable=True)
    
    products = relationship("DBScrapedProduct", back_populates="job", cascade="all, delete-orphan")

class DBScrapedProduct(Base):
    __tablename__ = "scraped_products"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(36), ForeignKey("scrape_jobs.id"), nullable=False)
    title = Column(Text, nullable=False)
    url = Column(Text, nullable=False)
    price = Column(String(50), nullable=True)
    rating = Column(String(50), nullable=True)
    reviews_count = Column(String(50), nullable=True)
    image_url = Column(Text, nullable=True)
    brand = Column(String(255), nullable=True)
    specifications = Column(Text, nullable=True)  # JSON-encoded string
    about_items = Column(Text, nullable=True)     # JSON-encoded string
    description = Column(Text, nullable=True)
    seller = Column(String(255), nullable=True)
    warranty = Column(String(255), nullable=True)
    reviews = Column(Text, nullable=True)         # JSON-encoded list of reviews
    scraped_at = Column(DateTime, default=datetime.utcnow)
    company_name = Column(String(255), nullable=True)
    
    job = relationship("DBScrapeJob", back_populates="products")

# Pydantic Schemas
class SearchRequest(BaseModel):
    website: str
    search_query: str
    limit: int = 5
    headless: bool = True

class ScrapedProductResponse(BaseModel):
    id: int
    job_id: str
    title: str
    url: str
    price: Optional[str] = None
    rating: Optional[str] = None
    reviews_count: Optional[str] = None
    image_url: Optional[str] = None
    brand: Optional[str] = None
    specifications: Dict[str, str] = {}
    about_items: List[str] = []
    description: Optional[str] = None
    seller: Optional[str] = None
    warranty: Optional[str] = None
    reviews: List[Dict[str, Any]] = []
    scraped_at: datetime
    company_name: Optional[str] = None

    class Config:
        from_attributes = True

class ScrapeJobResponse(BaseModel):
    id: str
    website: str
    search_query: str
    limit: int
    status: str
    created_at: datetime
    error_message: Optional[str] = None
    products: List[ScrapedProductResponse] = []
    company_name: Optional[str] = None

    class Config:
        from_attributes = True

