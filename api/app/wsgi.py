import os
from datetime import datetime

import pytz
from src import app
from src.views import CovidView, TestView

datetime.now(tz=pytz.timezone('America/Montevideo'))

if __name__ == "__main__":
    app.run(use_reloader=True, debug=(os.getenv('FLASK_ENV') == 'development'))
