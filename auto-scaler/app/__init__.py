from datetime import datetime
from flask import Flask
from app.config import Config
from flask_sqlalchemy import SQLAlchemy

webapp = Flask(__name__)
webapp.config.from_object(Config)

db = SQLAlchemy(webapp)
debug_value = True
auto_scalling_configuration = {'enabled': False, 'max_miss_rate_threshold': 0.8, 'min_miss_rate_threshold': 0.1, 'ratio_to_expand': 2.0, 'ratio_to_shrink': 0.5 }
autoscaling_configuration = {'mode':'' , 'numNodes': 0, 'cacheSize': 0, 'policy': '', 'expRatio': 0.0, 'shrinkRatio':0.0,'maxMiss': 0.0, 'minMiss':0.0  }
memcache_monitor = {'running' : []}
from app import main


