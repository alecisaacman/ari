from __future__ import annotations

import uvicorn
from ari_core.core.env import load_local_env
from ari_core.self_review import write_with_model

from ari_api import create_app

# The brain needs ANTHROPIC_API_KEY and the workspace setting, from Alec's private file.
load_local_env()
app = create_app(review_writer=write_with_model)


def main() -> None:
    uvicorn.run("ari_api.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
