import subprocess, sys, os, signal, time
from frontend.db.db_connector import db_init, fetch_fields, update_fields

backend_server = None
frontend_ui = None


def main() -> int:
    global backend_server, frontend_ui
    print('main :: Starting Frontend & Backend Services...')
    db_init()  # create DB if not exists and populate with defaults
    fetch_fields()  # print fields and initiate cache
    backend_server = subprocess.Popen("python3.11 backend/rest_server.py", shell=True)
    # time.sleep(3) # Let some time for backend to start
    frontend_ui = subprocess.Popen("streamlit run frontend/home_page.py", shell=True)

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
