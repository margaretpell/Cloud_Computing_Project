import os
from apscheduler.schedulers.background import BackgroundScheduler
from flask import flash, render_template, url_for, request
from app import webapp, memcache, configurations, cache_statistics, db, debug_value
from app.models import Mem_cache_configuration
from flask import json
from app.replacementPolicyHelper import applyRandomReplacementPolicy, applyLeastRecentUsedPolicy
from datetime import datetime
from pytz import timezone
import boto3
import requests
from dateutil import parser

eastern = timezone('US/Eastern')
cloudwatch = boto3.client('cloudwatch')
memcache_port = webapp.config['MEMCACHE_PORT']
autoscalar_port = webapp.config['AUTOSCALAR_PORT']
ec2 = boto3.resource('ec2', region_name='us-east-1')

def save_statistics():
    get_requests_served = cache_statistics['get_request_count']
    if  get_requests_served != 0:
        missing_rate = cache_statistics['miss_count'] / get_requests_served
        hit_rate = cache_statistics['hit_count'] / get_requests_served
    else:
        missing_rate = 0.0
        hit_rate = 0.0  
    
    create_time=datetime.now(eastern)
    cloudwatch.put_metric_data(
    Namespace='MemcacheService',
    MetricData=[
        {
            'MetricName': 'NumberOfItems',
            'Dimensions': [
                {
                    'Name': 'Target',
                    'Value': 'MemCache'
                }
            ],
            'Value': cache_statistics['number_items'],
            'Unit': 'Count',
            'Timestamp': create_time
        },
    ]
    )

    cloudwatch.put_metric_data(
    Namespace='MemcacheService',
    MetricData=[
        {
            'MetricName': 'UtilizedCapacity',
            'Dimensions': [
                {
                    'Name': 'Target',
                    'Value': 'MemCache'
                }
            ],
            'Value': cache_statistics['current_size'],
            'Unit': 'Count',
            'Timestamp': create_time
        },
    ]
    )

    cloudwatch.put_metric_data(
    Namespace='MemcacheService',
    MetricData=[
        {
            'MetricName': 'NumberOfRequestsServered',
            'Dimensions': [
                {
                    'Name': 'Target',
                    'Value': 'MemCache'
                }
            ],
            'Value': cache_statistics['requests_served'],
            'Unit': 'Count',
            'Timestamp': create_time
        },
    ]
    )

    cloudwatch.put_metric_data(
    Namespace='MemcacheService',
    MetricData=[
        {
            'MetricName': 'MissRate',
            'Dimensions': [
                {
                    'Name': 'Target',
                    'Value': 'MemCache'
                }
            ],  
            'Value': missing_rate,
            'Unit': 'Percent',
            'Timestamp': create_time
        },
    ]
    )
    
    cloudwatch.put_metric_data(
    Namespace='MemcacheService',
    MetricData=[
        {
            'MetricName': 'HitRate',
            'Dimensions': [
                {
                    'Name': 'Target',
                    'Value': 'MemCache'
                }
            ],
            'Value': hit_rate,
            'Unit': 'Percent',
            'Timestamp': create_time
        },
    ]
    )
                                 
if not debug_value or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    sched = BackgroundScheduler(daemon=True)
    sched.add_job(save_statistics,'interval',seconds=5, max_instances=1)
    sched.start()
    
@webapp.route('/')
def main():
    cache_statistics['requests_served'] += 1
    return render_template("main.html")

@webapp.route('/get',methods=['POST'])
def get():
    webapp.logger.info(
        "{} request /get received with key {}".format(request.method, request.args.get('key')))
    key = request.args.get('key')
    cache_statistics['requests_served'] += 1
    cache_statistics['get_request_count'] += 1
    
    # if the key is found in the memCache
    if key in memcache:
        value = memcache[key]['data']
        response = webapp.response_class(
            response=json.dumps({"success": "true", 'image': value.decode("utf-8")}),
            status=200,
            mimetype='application/json'
        )
        cache_statistics['hit_count'] += 1
        memcache[key]['access_time'] = datetime.now(eastern)
        
    # if the key is not in memCache
    else:
        response = webapp.response_class(
            response=json.dumps({"success": "false",
                                 "error": {
                                     "code": 404,
                                     "message": "Unknown key"}}),
            status=404,
            mimetype='application/json'
        )
        cache_statistics['miss_count']+= 1
    
    return response

@webapp.route('/put',methods=['POST'])
def put():
    webapp.logger.info(
        "{} request /put received with key {}".format(request.method, request.args.get('key')))
    key = request.args.get('key')
    cache_statistics['requests_served'] += 1
    
    # clean up the statistics for image override
    if key in memcache:
        previous_value = memcache.pop(key)
        cache_statistics['current_size'] -= previous_value['size']
        cache_statistics['number_items'] -= 1

    value = request.files.get('file').read()
    value_size = len(value) / 1000000

    # check if the memCache has the enough capacity  
    if value_size <=  configurations['capacity']:
        available_size = configurations['capacity'] - cache_statistics['current_size']
        
        # if not enough size, then apply replacement policy
        if value_size > available_size:
            policy = configurations['replacement_policy']
            required_size = value_size - available_size
            if policy == 'RND':
                keys = applyRandomReplacementPolicy(required_size)
            if policy == 'LRU':
                keys = applyLeastRecentUsedPolicy(required_size)
            for drop_key in keys:
                drop_value = memcache.pop(drop_key)
                cache_statistics['current_size'] -= drop_value['size']
                cache_statistics['number_items'] -= 1
                
        # store the key and image into the memCache, update the corresponding statistics            
        memcache[key] = {'data':value, 'size': value_size, 'access_time': datetime.now(eastern)}
        cache_statistics['current_size'] += value_size
        cache_statistics['number_items'] += 1
        
    response = webapp.response_class(
        response=json.dumps({"success": "true"}),
        status=200,
        mimetype='application/json'
    )

    return response

@webapp.route('/clear', methods=['POST'])
def clear():
    webapp.logger.info("{} request /clear received.".format(request.method))
    
    # clear up the memCache dict, and update the statistics accordingly
    memcache.clear()
    cache_statistics['current_size'] = 0
    cache_statistics['number_items'] = 0
    cache_statistics['requests_served'] += 1

    response = webapp.response_class(
        response=json.dumps({"success": "true"}),
        status=200,
        mimetype='application/json'
    )
    return response

@webapp.route('/invalidateKey', methods=['POST'])
def invalidateKey():
    webapp.logger.info(
        "{} request /invalidateKey received with key {}".format(request.method, request.args.get('key')))
    
    cache_statistics['requests_served'] += 1
    key = request.args.get('key')
    # only proceed when the key is inside the memCache
    if key in memcache:
        value = memcache.pop(key)
        cache_statistics['current_size'] -= value['size']
        cache_statistics['number_items'] -= 1
    
    response = webapp.response_class(
        response=json.dumps({"success": "true"}),
        status=200,
        mimetype='application/json'
    )
    return response

@webapp.route('/refreshConfiguration', methods=['POST'])
def refreshConfiguration():
    webapp.logger.info(
        "{} request /refreshConfiguration received.".format(request.method))

    try:# get the updated configuration values from the database
        record = db.session.query(Mem_cache_configuration).first()

        # record should not be None as the request will be triggered after a database changes committed
        replacement_policy = getattr(record, 'replacement_policy')
        cache_capacity= getattr(record, 'capacity')
        webapp.logger.info(
        "The memCache will be configured with capacity {} MB and Replacement Policy of {}.".format(cache_capacity, replacement_policy))
        
        # taking care of the case that the new cache capacity is smaller than the exsiting cache usage
        if cache_capacity < cache_statistics['current_size']:
            required_size = cache_statistics['current_size'] - cache_capacity
            webapp.logger.info(
                "Need to apply the replacement policy as the memCache is facing {} shortage.".format(required_size))
            if replacement_policy == 'RND':
                keys = applyRandomReplacementPolicy(required_size)
            if replacement_policy == 'LRU':
                keys = applyLeastRecentUsedPolicy(required_size)
            for drop_key in keys:
                value = memcache.pop(drop_key)
                cache_statistics['current_size'] -= value['size']
                cache_statistics['number_items'] -= 1
                
        configurations['replacement_policy'] = replacement_policy
        configurations['capacity'] = cache_capacity
        cache_statistics['requests_served'] += 1
    except Exception as e:
        webapp.logger.error(e)
        response = webapp.response_class(
            response=json.dumps(
                {"success": "false", 
                 "error": {
                    "code": 500,
                    "message": "Fail to refresh the configuration from the memCache side."
                    }}),
            status=500,
            mimetype='application/json'
        )
        return response
    response = webapp.response_class(
        response=json.dumps({"success": "true"}),
        status=200,
        mimetype='application/json'
    )
    return response

@webapp.route('/getAllCache', methods=['POST'])
def getAllCache():
    webapp.logger.info(
        "{} request /getAllCache received.".format(request.method))

    cache_statistics['requests_served'] += 1
    
    result = {}
    for name, content in memcache.items():
        image = content['data']
        image_decoded = image.decode("utf-8")
        value = {'data':image_decoded, 'size': content['size'], 'access_time': content['access_time']}
        result.update({name:value})
        
    response = webapp.response_class(
        response=json.dumps({"success": "true", 'caches': result}),
        status=200,
        mimetype='application/json'
    )
    
    return response

@webapp.route('/insertCaches', methods=['POST'])
def insertCache():
    webapp.logger.info(
        "{} request /insertCache received.".format(request.method))
    
    data = request.get_json()
    cache_statistics['requests_served'] += 1
    
    for key, content in data.items():
        content['access_time'] = parser.parse(content['access_time'])
        
    policy = configurations['replacement_policy']
    if policy == 'LRU':
        data = sorted(data.items(),key=lambda x: x[1]['access_time'],reverse=True)
    else:
        data = data.items()
    for key, file_content in data:
        # this is for re-distribution. If exsit, might be uploaded by the user prior to the distribution
        if key not in memcache:

            image = file_content.get('data').encode()
            value_size = file_content.get('size')

            # check if the memCache has the enough capacity  
            if value_size <=  configurations['capacity']:
                available_size = configurations['capacity'] - cache_statistics['current_size']
                
                # if not enough size, then apply replacement policy
                if value_size > available_size:
                    required_size = value_size - available_size
                    if policy == 'RND':
                        keys = applyRandomReplacementPolicy(required_size)
                        for drop_key in keys:
                            drop_value = memcache.pop(drop_key)
                            cache_statistics['current_size'] -= drop_value['size']
                            cache_statistics['number_items'] -= 1
                    if policy == 'LRU':
                        break    
                # store the key and image into the memCache, update the corresponding statistics            
                memcache[key] = {'data':image, 'size': value_size, 'access_time': file_content.get('access_time')}
                cache_statistics['current_size'] += value_size
                cache_statistics['number_items'] += 1
        
    response = webapp.response_class(
        response=json.dumps({"success": "true"}),
        status=200,
        mimetype='application/json'
    )

    return response
