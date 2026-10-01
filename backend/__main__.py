import os
import uvicorn
from . import config  # Load .env before reading HOST and PORT.

if __name__ == '__main__':
    uvicorn.run('backend.main:app', host=os.environ.get('HOST', '127.0.0.1'),
                port=int(os.environ.get('PORT', '6174')))
