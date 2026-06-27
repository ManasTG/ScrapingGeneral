import json
import os
import hashlib
from contextlib import contextmanager
from typing import Generator, List, Optional
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, Session
from app.config import DATABASE_URL, BASE_DIR
from app.models import Base, DBScrapeJob, DBScrapedProduct, DBUser, DBSession

# Create database engine for central database
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(
        DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_recycle=3600,
        pool_pre_ping=True
    )
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Cache engines and session makers for tenants
_engines = {}
_sessionmakers = {}

def get_tenant_db_session(db_name: str) -> Session:
    if db_name not in _engines:
        db_path = os.path.join(BASE_DIR, f"{db_name}.db")
        db_url = f"sqlite:///{db_path}"
        tenant_engine = create_engine(db_url, connect_args={"check_same_thread": False})
        
        # Initialize tables for this tenant
        Base.metadata.create_all(bind=tenant_engine)
        
        # Ensure schema upgrades / compatibility on tenant SQLite database
        inspector = inspect(tenant_engine)
        prod_columns = [col["name"] for col in inspector.get_columns("scraped_products")]
        job_columns = [col["name"] for col in inspector.get_columns("scrape_jobs")]
        
        with tenant_engine.begin() as conn:
            if "seller" not in prod_columns:
                conn.execute(text("ALTER TABLE scraped_products ADD COLUMN seller VARCHAR(255)"))
            if "warranty" not in prod_columns:
                conn.execute(text("ALTER TABLE scraped_products ADD COLUMN warranty VARCHAR(255)"))
            if "reviews" not in prod_columns:
                conn.execute(text("ALTER TABLE scraped_products ADD COLUMN reviews TEXT"))
            if "company_name" not in prod_columns:
                conn.execute(text("ALTER TABLE scraped_products ADD COLUMN company_name VARCHAR(255)"))
            if "company_name" not in job_columns:
                conn.execute(text("ALTER TABLE scrape_jobs ADD COLUMN company_name VARCHAR(255)"))
                
        _engines[db_name] = tenant_engine
        _sessionmakers[db_name] = sessionmaker(autocommit=False, autoflush=False, bind=tenant_engine)
        
    return _sessionmakers[db_name]()

def init_db() -> None:
    # Ensure central tables exist
    Base.metadata.create_all(bind=engine)
    
    # Check if new columns exist in central DB, and dynamically add them if missing
    inspector = inspect(engine)
    prod_columns = [col["name"] for col in inspector.get_columns("scraped_products")]
    job_columns = [col["name"] for col in inspector.get_columns("scrape_jobs")]
    
    with engine.begin() as conn:
        if "seller" not in prod_columns:
            conn.execute(text("ALTER TABLE scraped_products ADD COLUMN seller VARCHAR(255)"))
        if "warranty" not in prod_columns:
            conn.execute(text("ALTER TABLE scraped_products ADD COLUMN warranty VARCHAR(255)"))
        if "reviews" not in prod_columns:
            conn.execute(text("ALTER TABLE scraped_products ADD COLUMN reviews TEXT"))
        if "company_name" not in prod_columns:
            conn.execute(text("ALTER TABLE scraped_products ADD COLUMN company_name VARCHAR(255)"))
        if "company_name" not in job_columns:
            conn.execute(text("ALTER TABLE scrape_jobs ADD COLUMN company_name VARCHAR(255)"))
            
    # Seed default superadmin if no users exist
    db = SessionLocal()
    try:
        user_exists = db.query(DBUser).first() is not None
        if not user_exists:
            password = "superadmin_password"
            salt = os.urandom(16)
            key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
            password_hash = salt.hex() + ":" + key.hex()
            
            superadmin = DBUser(
                username="superadmin",
                password_hash=password_hash,
                role="superadmin",
                company_name="SaaS Provider",
                db_name="scraper"
            )
            db.add(superadmin)
            db.commit()
            print("\n" + "="*50)
            print("SEEDING DATABASE: Default SuperAdmin Created")
            print("Username: superadmin")
            print("Password: superadmin_password")
            print("="*50 + "\n")
    finally:
        db.close()

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
def create_scrape_job(db: Session, job_id: str, website: str, search_query: str, limit: int, company_name: Optional[str] = None) -> DBScrapeJob:
    job = DBScrapeJob(
        id=job_id,
        website=website,
        search_query=search_query,
        limit=limit,
        status="pending",
        company_name=company_name
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

def save_scraped_product(db: Session, job_id: str, product_data: dict, company_name: Optional[str] = None) -> DBScrapedProduct:
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
        reviews=reviews_str,
        company_name=company_name
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product

def get_job_by_id(db: Session, job_id: str) -> Optional[DBScrapeJob]:
    return db.query(DBScrapeJob).filter(DBScrapeJob.id == job_id).first()

def get_jobs_history(db: Session, skip: int = 0, limit: int = 20) -> List[DBScrapeJob]:
    return db.query(DBScrapeJob).order_by(DBScrapeJob.created_at.desc()).offset(skip).limit(limit).all()

# Mirroring utilities (strictly central DB actions)
def mirror_create_job(job_id: str, website: str, search_query: str, limit: int, company_name: str) -> None:
    with get_db_context() as central_db:
        # Check if already exists to prevent duplicate key errors on retry
        existing = central_db.query(DBScrapeJob).filter(DBScrapeJob.id == job_id).first()
        if not existing:
            job = DBScrapeJob(
                id=job_id,
                website=website,
                search_query=search_query,
                limit=limit,
                status="pending",
                company_name=company_name
            )
            central_db.add(job)
            central_db.commit()

def mirror_update_job_status(job_id: str, status: str, error_message: Optional[str] = None) -> None:
    with get_db_context() as central_db:
        job = central_db.query(DBScrapeJob).filter(DBScrapeJob.id == job_id).first()
        if job:
            job.status = status
            if error_message:
                job.error_message = error_message
            central_db.commit()

def mirror_save_scraped_product(job_id: str, product_data: dict, company_name: str) -> None:
    specs_str = json.dumps(product_data.get("specifications", {}))
    about_str = json.dumps(product_data.get("about_items", []))
    reviews_str = json.dumps(product_data.get("reviews", []))
    
    with get_db_context() as central_db:
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
            reviews=reviews_str,
            company_name=company_name
        )
        central_db.add(product)
        central_db.commit()

