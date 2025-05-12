import os, sys
# Environment Check
script_path = os.path.abspath(os.path.dirname(__file__))[0:-8]
if script_path not in sys.path:
    sys.path.insert(0, script_path)
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
import uvicorn, requests
from settings import SERVER_IP, SERVER_PORT
from database.api_keys_db_client import APIEncryptedDatabase
from backend.src.accountant.endpoint import router as accountant_router
from backend.src.analyst.endpoint import router as analyst_router
from backend.src.chronos.endpoint import router as chronos_router
from backend.src.broker.endpoint import router as broker_router
from backend.src.reporter.endpoint import router as reporter_router
from backend.src.technician.endpoint import router as technician_router
from backend.src.explorer.endpoint import router as explorer_router
from backend.src.stock_analyst.endpoint import router as stock_analyst_router
from backend.src.wiki.endpoint import router as wiki_router

from database.trade_history_db_client import TradeHistoryDBClient


# Define Router endpoints
router = APIRouter()
router.include_router(accountant_router)
router.include_router(analyst_router)
router.include_router(broker_router)
router.include_router(explorer_router)
router.include_router(chronos_router)
router.include_router(reporter_router)
router.include_router(technician_router)
router.include_router(stock_analyst_router)
router.include_router(wiki_router)

app = FastAPI()

# SECURITY OPTIONS
origins = ["http://localhost:8501"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Allow only the localhost streamlit frontend
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT"],  # Restrict methods
    allow_headers=["*"],
)

app.include_router(router)

@app.get("/")
def read_root():
    return {"Sibyl Server Status": "Running"}


# Entry point for running the application
if __name__ == "__main__":
    # Initialize Trade History DB
    TradeHistoryDBClient.db_init()
    # Initialize encryption and API storage database
    APIEncryptedDatabase.init_cipher()
    APIEncryptedDatabase.init_db()
    # Run the application using the Uvicorn server
    print("Backend :: Starting Server...")
    uvicorn.run(app, host=SERVER_IP, port=SERVER_PORT, log_level='debug', access_log=True)
