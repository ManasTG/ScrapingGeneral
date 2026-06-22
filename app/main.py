import os
import uuid
import queue
import importlib
import pandas as pd
from typing import Dict
from fastapi import FastAPI, Request, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import BASE_DIR
from app.models import DBScrapeJob, SearchRequest, ScrapeJobResponse
from app.database import (
    init_db, get_db, get_db_context,
    create_scrape_job, update_job_status, save_scraped_product,
    get_job_by_id, get_jobs_history
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

def run_scraper_task(job_id: str, website: str, search_query: str, limit: int, headless: bool) -> None:
    log_manager.register(job_id)
    log_manager.log(job_id, f"Job started with ID: {job_id}")
    
    with get_db_context() as db:
        try:
            update_job_status(db, job_id, "running")
            
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
                save_scraped_product(db, job_id, product)
            
            update_job_status(db, job_id, "completed")
            log_manager.log(job_id, "Task complete. Scraping completed successfully.")
            
        except ScrapeCancelledException as e:
            log_manager.log(job_id, "WARNING: Scraping cancelled by user.")
            log_manager.log(job_id, f"Saving {len(e.results)} partially scraped products to database...")
            for product in e.results:
                save_scraped_product(db, job_id, product)
            update_job_status(db, job_id, "stopped")
            log_manager.log(job_id, "Task terminated due to errors.")
        except Exception as e:
            error_msg = str(e)
            log_manager.log(job_id, f"FATAL ERROR: {error_msg}")
            update_job_status(db, job_id, "failed", error_message=error_msg)
            log_manager.log(job_id, "Task terminated due to errors.")
        finally:
            cancelled_jobs.discard(job_id)

# Frontend Web Interface route
@app.get("/")
def read_root(request: Request):
    return templates.TemplateResponse(request, "index.html", {"request": request})

# API Routes
@app.post("/api/scrape")
def trigger_scrape(payload: SearchRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    job_id = str(uuid.uuid4())
    create_scrape_job(db, job_id, payload.website, payload.search_query, payload.limit)
    
    # Start task in background
    background_tasks.add_task(
        run_scraper_task,
        job_id=job_id,
        website=payload.website,
        search_query=payload.search_query,
        limit=payload.limit,
        headless=payload.headless
    )
    
    return {"job_id": job_id, "message": "Scrape task triggered successfully"}

# Endpoint to stop scraping midway
@app.post("/api/scrape/{job_id}/stop")
def stop_scrape(job_id: str, db: Session = Depends(get_db)):
    job = get_job_by_id(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scrape job not found")
    
    if job.status not in ["pending", "running"]:
        return JSONResponse(
            status_code=400,
            content={"message": f"Job is already in '{job.status}' state and cannot be stopped."}
        )
    
    # Signal the scraper by adding the job to cancelled_jobs
    cancelled_jobs.add(job_id)
    
    # Update state in DB immediately
    update_job_status(db, job_id, "stopped")
    
    # Log stopping event to stream
    log_manager.log(job_id, "WARNING: Stop signal received. Terminating scraper task...")
    
    return {"message": "Stop command sent successfully"}

# Real-time SSE endpoint for logs
@app.get("/api/logs/{job_id}")
def stream_logs(job_id: str):
    def event_generator():
        if job_id not in log_manager.queues:
            yield "data: Error: Active job stream not found\n\n"
            return
            
        q = log_manager.queues[job_id]
        job_finished = False
        
        while not job_finished:
            try:
                # Poll queue for logs
                msg = q.get(timeout=1.0)
                yield f"data: {msg}\n\n"
                
                # Check for termination keywords
                if any(keyword in msg.lower() for keyword in ["scraping completed", "terminated due to errors", "fatal error", "stopped by user", "task stopped by user"]):
                    job_finished = True
            except queue.Empty:
                # SSE ping to keep connection alive
                yield ": ping\n\n"
            except Exception as e:
                yield f"data: SSE error: {str(e)}\n\n"
                break
                
        # Clean up queue
        log_manager.cleanup(job_id)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# Fetch single job results
@app.get("/api/results/{job_id}", response_model=ScrapeJobResponse)
def get_results(job_id: str, db: Session = Depends(get_db)):
    job = get_job_by_id(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scrape job not found")
    
    # Parse specifications, about items and reviews from JSON strings in response construction
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
def get_history(db: Session = Depends(get_db)):
    jobs = get_jobs_history(db)
    return [{"id": j.id, "website": j.website, "search_query": j.search_query, "limit": j.limit, "status": j.status, "created_at": j.created_at} for j in jobs]

# Export to CSV
@app.get("/api/export/{job_id}/csv")
def export_csv(job_id: str, db: Session = Depends(get_db)):
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
        # Flatten specifications as columns
        for k, v in specs.items():
            row[f"Spec_{k}"] = v
        data.append(row)
        
    df = pd.DataFrame(data)
    
    # Generate CSV in memory
    csv_data = df.to_csv(index=False)
    
    filename = f"scraped_data_{job_id[:8]}.csv"
    return StreamingResponse(
        iter([csv_data]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# Export to JSON
@app.get("/api/export/{job_id}/json")
def export_json(job_id: str, db: Session = Depends(get_db)):
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
        data.append({
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
        })
        
    import json as pyjson
    json_data = pyjson.dumps(data, indent=2)
    
    filename = f"scraped_data_{job_id[:8]}.json"
    return StreamingResponse(
        iter([json_data]),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
