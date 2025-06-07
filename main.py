import sys, os
if os.path.abspath(os.path.dirname(__file__)) not in sys.path:
    sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
import subprocess, signal, time
import argparse
from frontend.db.db_connector import db_init, fetch_fields
from streamlit.runtime.scriptrunner import add_script_run_ctx,get_script_run_ctx

backend_server = None
frontend_ui = None
grpc_server = None

env = os.environ.copy()
env['PYTHONPATH'] = ':'.join(sys.path)  # Add the modified sys.path to PYTHONPATH


def init_backend_server() -> int:
    global backend_server, grpc_server
    print('main :: Initializing Backend & gRPC LLM Services...')
    backend_server = subprocess.Popen("python3 backend/rest_server.py", shell=True, env=env) # fastAPI backend server
    grpc_server = subprocess.Popen("python llm_gateway/grpc_server.py", shell=True, env=env) # gRPC inference server
    return 0

def init_frontend() -> int:
    global frontend_ui
    print('main :: Initializing Frontend Service...')
    db_init()  # create DB if not exists and populate with defaults
    fetch_fields()  # print fields and initiate cache
    os.environ["STREAMLIT_CONFIG"] = ".streamlit/config.toml"
    # ctx = get_script_run_ctx(suppress_warning=True)
    frontend_ui = subprocess.Popen("python -m streamlit run frontend/index_router.py", shell=True, env=env)
    # add_script_run_ctx(frontend_ui, ctx)
    return 0


def update_wiki_rag_embeddings_db() -> int:
    print('main :: Updating RAG Wiki documents with latest papers...')
    wiki_rag = subprocess.Popen("python llm_gateway/rag/download_documents.py", shell=True, env=env) # fastAPI backend server
    return 0

def ctrl_handler(signum, frm):
    global backend_server, frontend_ui, grpc_server

    if frontend_ui: frontend_ui.kill() # os.killpg(os.getpgid(backend_server.pid), signal.SIGTERM)
    if backend_server: backend_server.kill()
    if grpc_server: grpc_server.kill()
    print('main :: Bye Bye!')
    sys.exit(0)


signal.signal(signal.SIGINT, ctrl_handler)


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="A script to perform tasks based on flags.")
    parser.add_argument('--backend', action='store_true', help="Run only backend")
    parser.add_argument('--wiki', action='store_true', help="Update RAG chroma DB with new paper embeddings.")
    args = parser.parse_args()

    if args.backend:
        init_backend_server()
    elif args.wiki:
        update_wiki_rag_embeddings_db()
    else:
        print("No flag defined. Available flags --backend or --wiki")
        init_backend_server()
        time.sleep(2)
        init_frontend()

    while True:
        pass
