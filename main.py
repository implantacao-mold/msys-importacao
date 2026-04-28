import sys
import os
import threading
import webbrowser

sys.path.insert(0, os.path.dirname(__file__))

from gui.web_server import create_app

if __name__ == "__main__":
    app = create_app()
    port = 5000
    threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
