from datetime import datetime
from flask import Flask
from app.config import Config
from flask_sqlalchemy import SQLAlchemy

webapp = Flask(__name__)
webapp.config.from_object(Config)

db = SQLAlchemy(webapp)

from app.main import main
from app.api import api

from app.models import Mem_cache_configuration
webapp.app_context().push()
db.create_all()

from pytz import timezone
eastern = timezone('US/Eastern')

try:
    records = db.session.query(Mem_cache_configuration).all()
    if len(records) == 0:
        initial_cache_config = Mem_cache_configuration(capacity=15, replacement_policy = 'RND', modify_time=datetime.now(eastern))
        db.session.add(initial_cache_config)
        db.session.commit()
except Exception as e:
    webapp.logger.warning(e)    
    
webapp.register_blueprint(main, url_prefix='')
webapp.register_blueprint(api, url_prefix='/api')
