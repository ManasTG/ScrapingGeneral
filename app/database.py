import json
from contextlib import contextmanager
from typing import Generator, List, Optional
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, Session
from app.config import DATABASE_URL
from app.models import Base, DBScrapeJob, DBScrapedProduct

# Create SQLite database engine
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    
    # Check if new columns exist, and dynamically add them if missing
    inspector = inspect(engine)
    columns = [col["name"] for col in inspector.get_columns("scraped_products")]
    
    with engine.begin() as conn:
        if "seller" not in columns:
            conn.execute(text("ALTER TABLE scraped_products ADD COLUMN seller VARCHAR(255)"))
        if "warranty" not in columns:
            conn.execute(text("ALTER TABLE scraped_products ADD COLUMN warranty VARCHAR(255)"))
        if "reviews" not in columns:
            conn.execute(text("ALTER TABLE scraped_products ADD COLUMN reviews TEXT"))

@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Dependency for FastAPI routes
def get_db() -> Generator[Session, None, None]:
    with get_db_context() as db:
        yield db

# DB helper actions
def create_scrape_job(db: Session, job_id: str, website: str, search_query: str, limit: int) -> DBScrapeJob:
    job = DBScrapeJob(
        id=job_id,
        website=website,
        search_query=search_query,
        limit=limit,
        status="pending"
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job

def update_job_status(db: Session, job_id: str, status: str, error_message: Optional[str] = None) -> None:
    job = db.query(DBScrapeJob).filter(DBScrapeJob.id == job_id).first()
    if job:
        job.status = status
        if error_message:
            job.error_message = error_message
        db.commit()

def save_scraped_product(db: Session, job_id: str, product_data: dict) -> DBScrapedProduct:
    # Serialize JSON fields
    specs_str = json.dumps(product_data.get("specifications", {}))
    about_str = json.dumps(product_data.get("about_items", []))
    reviews_str = json.dumps(product_data.get("reviews", []))
    
    product = DBScrapedProduct(
        job_id=job_id,
        title=product_data.get("title", ""),
        url=product_data.get("url", ""),
        price=product_data.get("price"),
        rating=product_data.get("rating"),
        reviews_count=product_data.get("reviews_count"),
        image_url=product_data.get("image_url"),
        brand=product_data.get("brand"),
        specifications=specs_str,
        about_items=about_str,
        description=product_data.get("description"),
        seller=product_data.get("seller"),
        warranty=product_data.get("warranty"),
        reviews=reviews_str
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product

def get_job_by_id(db: Session, job_id: str) -> Optional[DBScrapeJob]:
    return db.query(DBScrapeJob).filter(DBScrapeJob.id == job_id).first()

def get_jobs_history(db: Session, skip: int = 0, limit: int = 20) -> List[DBScrapeJob]:
    return db.query(DBScrapeJob).order_by(DBScrapeJob.created_at.desc()).offset(skip).limit(limit).all()
