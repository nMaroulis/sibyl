from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
import uvicorn, requests
from settings import SERVER_IP, SERVER_PORT
from accountant.endpoint import router as accountant_router
from analyst.endpoint import router as analyst_router
# from oracle.endpoint import router as oracle_router
from broker.endpoint import router as broker_router
from reporter.endpoint import router as reporter_router
from technician.endpoint import router as technician_router
from db.query_handler import db_init

# Define Router endpoints
router = APIRouter()
router.include_router(accountant_router)
router.include_router(analyst_router)
router.include_router(broker_router)
router.include_router(reporter_router)
router.include_router(technician_router)


app = FastAPI()

# origins = ["http://127.0.0.1:8000"]
#
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=origins,
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

app.include_router(router)


# Route for the root path "/"
@app.get("/")
def read_root():
    return {"Sibyl Server Status": "Running"}


# Entry point for running the application
if __name__ == "__main__":

    db_init()  # Initialize DB
    # Run the application using the Uvicorn server
    uvicorn.run(app, host=SERVER_IP, port=SERVER_PORT, log_level='debug', access_log=True)
