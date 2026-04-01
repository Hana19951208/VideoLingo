from __future__ import annotations

import uvicorn


def main() -> None:
    uvicorn.run('control_plane.app:create_app', host='127.0.0.1', port=8000, factory=True, reload=False)


if __name__ == '__main__':
    main()
