from __future__ import annotations

import uvicorn

from ari_api import create_app


app = create_app()


def main() -> None:
    uvicorn.run("ari_api.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
