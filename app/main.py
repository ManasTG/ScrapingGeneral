import os
import uuid
import queue
import importlib
import re
import hashlib
import pandas as pd
from typing import Dict, Optional
from fastapi import FastAPI, Request, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import BASE_DIR
from app.models import DBScrapeJob, SearchRequest, ScrapeJobResponse, DBUser, DBSession
from app.database import (
    init_db, get_db_context, get_tenant_db_session, SessionLocal,
    create_scrape_job, update_job_status, save_scraped_product,
    get_job_by_id, get_jobs_history,
    mirror_create_job, mirror_update_job_status, mirror_save_scraped_product
)

from app.scrapers.base import ScrapeCancelledException

# Initialize DB on application startup
init_db()

app = FastAPI(title="Universal Product Scraper API", version="1.0.0")

# Setup directories
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Password hashing utilities
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return salt.hex() + ":" + key.hex()

def verify_password(stored_password: str, provided_password: str) -> bool:
    try:
        salt_hex, key_hex = stored_password.split(":")
        salt = bytes.fromhex(salt_hex)
        key = bytes.fromhex(key_hex)
        new_key = hashlib.pbkdf2_hmac('sha256', provided_password.encode('utf-8'), salt, 100000)
        return new_key == key
    except Exception:
        return False

# Real-time log streaming setup
class LogManager:
    def __init__(self):
        self.queues: Dict[str, queue.Queue] = {}

    def register(self, job_id: str) -> None:
        self.queues[job_id] = queue.Queue()

    def log(self, job_id: str, message: str) -> None:
        if job_id in self.queues:
            self.queues[job_id].put(message)

    def cleanup(self, job_id: str) -> None:
        if job_id in self.queues:
            del self.queues[job_id]

log_manager = LogManager()
cancelled_jobs = set()

# Tenant-aware get_db dependency
def get_db(request: Request) -> Generator[Session, None, None]:
    token = request.cookies.get("session_token")
    if not token:
        with get_db_context() as db:
            yield db
        return
        
    with get_db_context() as central_db:
        session = central_db.query(DBSession).filter(DBSession.token == token).first()
        if not session:
            yield central_db
            return
            
        user = central_db.query(DBUser).filter(DBUser.username == session.username).first()
        if not user:
            yield central_db
            return
            
        if user.role == "superadmin":
            yield central_db
        else:
            tenant_db = get_tenant_db_session(user.db_name)
            try:
                yield tenant_db
            finally:
                tenant_db.close()

# Current user lookup helper
def get_current_user(request: Request) -> Optional[DBUser]:
    token = request.cookies.get("session_token")
    if not token:
        return None
    with get_db_context() as central_db:
        session = central_db.query(DBSession).filter(DBSession.token == token).first()
        if not session:
            return None
        user = central_db.query(DBUser).filter(DBUser.username == session.username).first()
        return user

# Background scraper task runner
def run_scraper_task(job_id: str, website: str, search_query: str, limit: int, headless: bool, db_name: Optional[str], company_name: Optional[str]) -> None:
    log_manager.register(job_id)
    log_manager.log(job_id, f"Job started with ID: {job_id}")
    
    # Establish dynamic tenant db session
    if db_name and db_name != "scraper":
        db = get_tenant_db_session(db_name)
    else:
        db = SessionLocal()
        
    try:
        update_job_status(db, job_id, "running")
        if company_name:
            mirror_update_job_status(job_id, "running")
            
        # Dynamically import the scraper module based on requested site key (e.g., 'amazon')
        log_manager.log(job_id, f"Loading modular scraper: app.scrapers.{website}...")
        try:
            scraper_module = importlib.import_module(f"app.scrapers.{website}")
            ScraperClass = getattr(scraper_module, "Scraper")
        except (ImportError, AttributeError) as err:
            raise ValueError(f"Modular scraper for website '{website}' is not implemented or not found.") from err
        
        # Instantiate scraper with custom log callback and cancellation callback
        scraper = ScraperClass(
            job_id=job_id,
            headless=headless,
            log_callback=lambda msg: log_manager.log(job_id, msg),
            is_cancelled_callback=lambda: job_id in cancelled_jobs
        )
        
        # Scrape details
        results = scraper.scrape(search_query, limit)
        
        # Save results to DB
        log_manager.log(job_id, "Saving scraped products to database...")
        for product in results:
            save_scraped_product(db, job_id, product, company_name=company_name)
            if company_name:
                mirror_save_scraped_product(job_id, product, company_name)
        
        update_job_status(db, job_id, "completed")
        if company_name:
            mirror_update_job_status(job_id, "completed")
        log_manager.log(job_id, "Task complete. Scraping completed successfully.")
        
    except ScrapeCancelledException as e:
        log_manager.log(job_id, "WARNING: Scraping cancelled by user.")
        log_manager.log(job_id, f"Saving {len(e.results)} partially scraped products to database...")
        for product in e.results:
            save_scraped_product(db, job_id, product, company_name=company_name)
            if company_name:
                mirror_save_scraped_product(job_id, product, company_name)
        update_job_status(db, job_id, "stopped")
        if company_name:
            mirror_update_job_status(job_id, "stopped")
        log_manager.log(job_id, "Task terminated due to errors.")
    except Exception as e:
        error_msg = str(e)
        log_manager.log(job_id, f"FATAL ERROR: {error_msg}")
        update_job_status(db, job_id, "failed", error_message=error_msg)
        if company_name:
            mirror_update_job_status(job_id, "failed", error_message=error_msg)
        log_manager.log(job_id, "Task terminated due to errors.")
    finally:
        db.close()
        cancelled_jobs.discard(job_id)

# Frontend Web Interface route
@app.get("/")
def read_root(request: Request):
    return templates.TemplateResponse(request, "index.html", {"request": request})

# Authentication Endpoints
class LoginPayload(BaseModel):
    username: str
    password: str

@app.post("/api/auth/login")
def login(payload: LoginPayload):
    with get_db_context() as central_db:
        user = central_db.query(DBUser).filter(DBUser.username == payload.username).first()
        if not user or not verify_password(user.password_hash, payload.password):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        
        # Create a new session
        token = str(uuid.uuid4())
        session = DBSession(token=token, username=user.username)
        central_db.add(session)
        central_db.commit()
        
        response = JSONResponse(content={
            "message": "Logged in successfully",
            "role": user.role,
            "company_name": user.company_name
        })
        response.set_cookie(
            key="session_token",
            value=token,
            httponly=True,
            max_age=86400,
            samesite="lax"
        )
        return response

@app.post("/api/auth/logout")
def logout(request: Request):
    token = request.cookies.get("session_token")
    if token:
        with get_db_context() as central_db:
            central_db.query(DBSession).filter(DBSession.token == token).delete()
            central_db.commit()
            
    response = JSONResponse(content={"message": "Logged out successfully"})
    response.delete_cookie("session_token")
    return response

@app.get("/api/me")
def get_me(user: Optional[DBUser] = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {
        "username": user.username,
        "role": user.role,
        "company_name": user.company_name,
        "db_name": user.db_name
    }

# SuperAdmin Management Endpoints
class CompanyCreatePayload(BaseModel):
    company_name: str
    username: str
    password: str

@app.get("/api/superadmin/companies")
def get_companies(user: Optional[DBUser] = Depends(get_current_user)):
    if not user or user.role != "superadmin":
        raise HTTPException(status_code=403, detail="Access denied")
        
    with get_db_context() as central_db:
        admins = central_db.query(DBUser).filter(DBUser.role == "admin").all()
        return [
            {
                "id": admin.id,
                "username": admin.username,
                "company_name": admin.company_name,
                "db_name": admin.db_name,
                "created_at": admin.created_at
            } for admin in admins
        ]

@app.post("/api/superadmin/companies")
def create_company(payload: CompanyCreatePayload, user: Optional[DBUser] = Depends(get_current_user)):
    if not user or user.role != "superadmin":
        raise HTTPException(status_code=403, detail="Access denied")
        
    # Generate database name from company name
    company_slug = re.sub(r'[^a-zA-Z0-9]', '_', payload.company_name.lower())
    db_name = f"tenant_{company_slug}"
    
    with get_db_context() as central_db:
        existing_user = central_db.query(DBUser).filter(DBUser.username == payload.username).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Username already exists")
            
        pwd_hash = hash_password(payload.password)
        new_admin = DBUser(
            username=payload.username,
            password_hash=pwd_hash,
            role="admin",
            company_name=payload.company_name,
            db_name=db_name
        )
        central_db.add(new_admin)
        central_db.commit()
        
        # Initialize tenant database session once (creates schema)
        tenant_session = get_tenant_db_session(db_name)
        tenant_session.close()
        
        return {"message": f"Company '{payload.company_name}' provisioned successfully with database '{db_name}'"}

# Scraping API Routes
@app.post("/api/scrape")
def trigger_scrape(payload: SearchRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db), user: Optional[DBUser] = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
        
    job_id = str(uuid.uuid4())
    comp_name = user.company_name if user.role == "admin" else None
    
    # Save jobs in session DB
    create_scrape_job(db, job_id, payload.website, payload.search_query, payload.limit, company_name=comp_name)
    
    # If standard Admin, pre-create job in central database for mirroring
    if user.role == "admin" and comp_name:
        mirror_create_job(job_id, payload.website, payload.search_query, payload.limit, comp_name)
    
    # Start task in background
    background_tasks.add_task(
        run_scraper_task,
        job_id=job_id,
        website=payload.website,
        search_query=payload.search_query,
        limit=payload.limit,
        headless=payload.headless,
        db_name=user.db_name,
        company_name=comp_name
    )
    
    return {"job_id": job_id, "message": "Scrape task triggered successfully"}

@app.post("/api/scrape/{job_id}/stop")
def stop_scrape(job_id: str, db: Session = Depends(get_db), user: Optional[DBUser] = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
        
    job = get_job_by_id(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scrape job not found")
    
    if job.status not in ["pending", "running"]:
        return JSONResponse(
            status_code=400,
            content={"message": f"Job is already in '{job.status}' state and cannot be stopped."}
        )
    
    # Signal the scraper
    cancelled_jobs.add(job_id)
    
    # Update local DB state
    update_job_status(db, job_id, "stopped")
    
    # Mirror stopped state to central DB
    if user.role == "admin":
        mirror_update_job_status(job_id, "stopped")
    
    log_manager.log(job_id, "WARNING: Stop signal received. Terminating scraper task...")
    
    return {"message": "Stop command sent successfully"}

# Real-time SSE endpoint for logs
@app.get("/api/logs/{job_id}")
def stream_logs(job_id: str, user: Optional[DBUser] = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
        
    def event_generator():
        if job_id not in log_manager.queues:
            yield "data: Error: Active job stream not found\n\n"
            return
            
        q = log_manager.queues[job_id]
        job_finished = False
        
        while not job_finished:
            try:
                msg = q.get(timeout=1.0)
                yield f"data: {msg}\n\n"
                
                if any(keyword in msg.lower() for keyword in ["scraping completed", "terminated due to errors", "fatal error", "stopped by user", "task stopped by user"]):
                    job_finished = True
            except queue.Empty:
                yield ": ping\n\n"
            except Exception as e:
                yield f"data: SSE error: {str(e)}\n\n"
                break
                
        log_manager.cleanup(job_id)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# Fetch single job results
@app.get("/api/results/{job_id}", response_model=ScrapeJobResponse)
def get_results(job_id: str, db: Session = Depends(get_db), user: Optional[DBUser] = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
        
    job = get_job_by_id(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scrape job not found")
    
    import json
    for p in job.products:
        try:
            p.specifications = json.loads(p.specifications) if p.specifications else {}
        except Exception:
            p.specifications = {}
            
        try:
            p.about_items = json.loads(p.about_items) if p.about_items else []
        except Exception:
            p.about_items = []

        try:
            p.reviews = json.loads(p.reviews) if p.reviews else []
        except Exception:
            p.reviews = []
            
    return job

# History of past runs
@app.get("/api/history")
def get_history(db: Session = Depends(get_db), user: Optional[DBUser] = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
        
    jobs = get_jobs_history(db)
    return [
        {
            "id": j.id,
            "website": j.website,
            "search_query": j.search_query,
            "limit": j.limit,
            "status": j.status,
            "created_at": j.created_at,
            "company_name": j.company_name
        } for j in jobs
    ]

# Export to CSV
@app.get("/api/export/{job_id}/csv")
def export_csv(job_id: str, db: Session = Depends(get_db), user: Optional[DBUser] = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
        
    job = get_job_by_id(db, job_id)
    if not job or not job.products:
        raise HTTPException(status_code=404, detail="Job has no data to export")
        
    data = []
    import json
    for p in job.products:
        try:
            specs = json.loads(p.specifications) if p.specifications else {}
        except:
            specs = {}
        row = {
            "Title": p.title,
            "URL": p.url,
            "Price": p.price,
            "Rating": p.rating,
            "Reviews Count": p.reviews_count,
            "Brand": p.brand,
            "Seller": p.seller,
            "Warranty": p.warranty,
            "Description": p.description,
        }
        if user.role == "superadmin":
            row["Company"] = p.company_name
            
        for k, v in specs.items():
            row[f"Spec_{k}"] = v
        data.append(row)
        
    df = pd.DataFrame(data)
    csv_data = df.to_csv(index=False)
    
    filename = f"scraped_data_{job_id[:8]}.csv"
    return StreamingResponse(
        iter([csv_data]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# Export to JSON
@app.get("/api/export/{job_id}/json")
def export_json(job_id: str, db: Session = Depends(get_db), user: Optional[DBUser] = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
        
    job = get_job_by_id(db, job_id)
    if not job or not job.products:
        raise HTTPException(status_code=404, detail="Job has no data to export")
        
    data = []
    import json
    for p in job.products:
        try:
            specs = json.loads(p.specifications) if p.specifications else {}
        except:
            specs = {}
        try:
            about = json.loads(p.about_items) if p.about_items else []
        except:
            about = []
        try:
            prod_reviews = json.loads(p.reviews) if p.reviews else []
        except:
            prod_reviews = []
            
        item = {
            "title": p.title,
            "url": p.url,
            "price": p.price,
            "rating": p.rating,
            "reviews_count": p.reviews_count,
            "brand": p.brand,
            "description": p.description,
            "seller": p.seller,
            "warranty": p.warranty,
            "specifications": specs,
            "about_items": about,
            "reviews": prod_reviews
        }
        if user.role == "superadmin":
            item["company_name"] = p.company_name
            
        data.append(item)
        
    import json as pyjson
    json_data = pyjson.dumps(data, indent=2)
    
    filename = f"scraped_data_{job_id[:8]}.json"
    return StreamingResponse(
        iter([json_data]),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

