import sys, os
if os.path.abspath(os.path.dirname(__file__)) not in sys.path:
    sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
import subprocess, signal, time
from frontend.db.db_connector import db_init, fetch_fields, update_fields
from streamlit.runtime.scriptrunner import add_script_run_ctx,get_script_run_ctx

backend_server = None
frontend_ui = None


def main() -> int:
    global backend_server, frontend_ui
    print('main :: Starting Frontend & Backend & gRPC LLM Services...')

    # ------- ENV Variables -------
    env = os.environ.copy()
    env['PYTHONPATH'] = ':'.join(sys.path)  # Add the modified sys.path to PYTHONPATH

    # ------- BACKEND -------
    backend_server = subprocess.Popen("python3.12 backend/rest_server.py", shell=True, env=env)
    # time.sleep(2)  # Let some time for backend to start

    # ------- GRPC LLM SERVER -------
    grpc_server = subprocess.Popen("python3.12 llm_hub/grpc_server.py", shell=True, env=env)

    # ------- FRONTEND -------
    ## Frontend DB
    db_init()  # create DB if not exists and populate with defaults
    fetch_fields()  # print fields and initiate cache
    os.environ["STREAMLIT_CONFIG"] = ".streamlit/config.toml"
    # ctx = get_script_run_ctx(suppress_warning=True)
    frontend_ui = subprocess.Popen("python3.12 -m streamlit run frontend/index_router.py", shell=True, env=env)
    # add_script_run_ctx(frontend_ui, ctx)

    return 0


def ctrl_handler(signum, frm):
    global backend_server, frontend_ui

    # if frontend_ui is not None:
    #     frontend_ui.kill() # os.killpg(os.getpgid(backend_server.pid), signal.SIGTERM)
    # if backend_server is not None:
    #     backend_server.kill()

    print('main :: Bye Bye!')
    sys.exit(0)


signal.signal(signal.SIGINT, ctrl_handler)


if __name__ == '__main__':
    main()
    while True:
        pass
    # sys.exit(main())
