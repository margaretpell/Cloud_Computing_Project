from datetime import datetime
from flask import Flask
from app.config import Config
from flask_sqlalchemy import SQLAlchemy
import boto3
import os

webapp = Flask(__name__)
webapp.config.from_object(Config)

db = SQLAlchemy(webapp)

from app.main import main

from app.models import Mem_cache_configuration
db.create_all()

from pytz import timezone
eastern = timezone('US/Eastern')
debug_value = True

try:
    records = db.session.query(Mem_cache_configuration).all()
    if len(records) == 0:
        initial_cache_config = Mem_cache_configuration(capacity=15, replacement_policy = 'RND', modify_time=datetime.now(eastern))
        db.session.add(initial_cache_config)
        db.session.commit()
except Exception as e:
    webapp.logger.warning(e)    
    
ec2 = boto3.resource('ec2', region_name='us-east-1')
running_instances = ec2.instances.filter(
    Filters=[
        {
            'Name': 'instance-state-name',
            'Values': [
                'running'
            ]
        },
        {'Name':'tag:Name', 'Values':['MemCache']}
    ]
)
if len(list(running_instances)) == 0:
    if not debug_value or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        user_data_script = """#!/bin/bash
        source /home/ubuntu/ECE1779_Project/Assignment2/venv/bin/activate
        cd /home/ubuntu/ECE1779_Project/Assignment2_new/memcache
        python3 run.py
        """
        instances = ec2.create_instances(
                ImageId=webapp.config['AMI_ID'],
                MinCount=1,
                MaxCount=1,
                InstanceType="t2.micro",
                SecurityGroupIds=[
                webapp.config['SECURITY_GROUP_ID'],
                ],
                KeyName = webapp.config['KEY_NAME'],
                UserData = user_data_script,
                TagSpecifications = [
                    {
                        'ResourceType': 'instance',
                        'Tags': [
                            {
                                'Key': 'Name',
                                'Value': 'MemCache'
                            }
                        ]
                    }
                ]

        )
        create_time=datetime.now(eastern)
        cloudwatch = boto3.client('cloudwatch')
        cloudwatch.put_metric_data(
        Namespace='MemcacheService',
        MetricData=[
            {
                'MetricName': 'NumberOfNodes',
                'Dimensions': [
                    {
                        'Name': 'Target',
                        'Value': 'Pool'
                    }
                ],
                'Value': 1,
                'Unit': 'Count',
                'Timestamp': create_time
            },
        ]
        )
webapp.register_blueprint(main, url_prefix='')
