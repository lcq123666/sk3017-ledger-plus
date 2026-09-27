"""应用入口。

启动：
    python run.py
默认监听 http://127.0.0.1:5001
"""
import os

from app import create_app

app = create_app(os.getenv("FLASK_CONFIG", "default"))


if __name__ == "__main__":
    port = int(os.getenv("FLASK_RUN_PORT", "5001"))
    debug = os.getenv("FLASK_DEBUG", "1") == "1"
    app.run(host="127.0.0.1", port=port, debug=debug)
