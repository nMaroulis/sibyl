import subprocess, sys, os, signal, time

backend_server = None
frontend_ui = None


def main() -> int:
    global backend_server, frontend_ui
    print('Starting Frontend & Backed Services...')
    backend_server = subprocess.Popen("python3.11 backend/rest_server.py", shell=True)
    frontend_ui = subprocess.Popen("streamlit run frontend/home_page.py", shell=True)

    return 0


def ctrl_handler(signum, frm):
    global backend_server, frontend_ui

    # if frontend_ui is not None:
    #     frontend_ui.kill() # os.killpg(os.getpgid(backend_server.pid), signal.SIGTERM)
    # if backend_server is not None:
    #     backend_server.kill()

    print('Bye Bye!')
    sys.exit(0)


signal.signal(signal.SIGINT, ctrl_handler)


if __name__ == '__main__':
    main()
    while True:
        pass
    # sys.exit(main())
