from distutils.log import debug
from flask import Flask
from requests import request
from app.config import Config
from flask_sqlalchemy import SQLAlchemy
import boto3
from ec2_metadata import ec2_metadata
import requests
import os

global memcache, configurations, cache_statistics, debug_value

webapp = Flask(__name__)
webapp.config.from_object(Config)

db = SQLAlchemy(webapp)
memcache = {}
configurations = {'first_run':True}
debug_value = True
cache_statistics = {'current_size': 0.0, 'number_items': 0, 'requests_served' :0, 'hit_count' : 0, 'miss_count': 0, 'get_request_count': 0}

from app import main
from app.models import Mem_cache_configuration

try:
    record = db.session.query(Mem_cache_configuration).first()
    if record is not None:
        configurations['replacement_policy'] = getattr(record, 'replacement_policy')
        configurations['capacity'] = getattr(record, 'capacity')
    else: 
        configurations['replacement_policy'] = 'RND'
        configurations['capacity'] = 15
except Exception as e:
    webapp.logger.warning(e)
    configurations['replacement_policy'] = 'RND'
    configurations['capacity'] = 15
    
if not debug_value or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    ec2 = boto3.resource('ec2')
    autoscalar_port = webapp.config['AUTOSCALAR_PORT']
    running_instances = ec2.instances.filter(
        Filters=[
            {
                'Name': 'instance-state-name',
                'Values': [
                    'running'
                ]
            },
            {'Name':'tag:Name', 'Values':['Main']}
        ]
    )
    main_instance = list(running_instances)[0]
    params = {'public_ip': ec2_metadata.public_ipv4, 'instance_id': ec2_metadata.instance_id}
    url = f"http://{main_instance.public_ip_address}:{autoscalar_port}/updateStartedNodeCount"
    requests.post(url, params=params)
