"""启动入口：python -m app；首次运行先执行 python -m app init-db。"""

import argparse

from config import WEB
from web import create_app, init_database

# 保留 `from app import app` 与 Flask CLI 的入口兼容性；导入不连接数据库。
app = create_app()


def main():
    parser = argparse.ArgumentParser(description="招聘分析仪表盘")
    parser.add_argument("command", nargs="?", choices=("serve", "init-db"), default="serve")
    args = parser.parse_args()
    if args.command == "init-db":
        with app.app_context():
            init_database()
        print("Database tables initialized.")
    else:
        app.run(host=WEB["host"], port=WEB["port"], debug=app.config["DEBUG"])


if __name__ == "__main__":
    main()
