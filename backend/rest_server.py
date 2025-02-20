import os, sys
# Environment Check
script_path = os.path.abspath(os.path.dirname(__file__))[0:-8]
if script_path not in sys.path:
    sys.path.insert(0, script_path)
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
import uvicorn, requests
from settings import SERVER_IP, SERVER_PORT
from backend.src.accountant.endpoint import router as accountant_router
from backend.src.analyst.endpoint import router as analyst_router
from backend.src.oracle.endpoint import router as oracle_router
from backend.src.broker.endpoint import router as broker_router
from backend.src.reporter.endpoint import router as reporter_router
from backend.src.technician.endpoint import router as technician_router
from backend.src.explorer.endpoint import router as explorer_router
from backend.src.stock_analyst.endpoint import router as stock_analyst_router
from db.trade_history_db_client import TradeHistoryDBClient


# Define Router endpoints
router = APIRouter()
router.include_router(accountant_router)
router.include_router(analyst_router)
router.include_router(broker_router)
router.include_router(explorer_router)
router.include_router(oracle_router)
router.include_router(reporter_router)
router.include_router(technician_router)
router.include_router(stock_analyst_router)

app = FastAPI()

# origins = ["http://127.0.0.1:8000"]
# app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.include_router(router)


@app.get("/")
def read_root():
    return {"Sibyl Server Status": "Running"}


# Entry point for running the application
if __name__ == "__main__":
    TradeHistoryDBClient.db_init()  # Initialize DB
    # Run the application using the Uvicorn server
    print("Starting Server")
    uvicorn.run(app, host=SERVER_IP, port=SERVER_PORT, log_level='debug', access_log=True)
