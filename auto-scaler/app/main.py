import os
from apscheduler.schedulers.background import BackgroundScheduler
from flask import render_template, redirect, url_for, request, g, json
from app import webapp, auto_scalling_configuration, debug_value, memcache_monitor, autoscaling_configuration
import boto3
from datetime import datetime, timedelta
from pytz import timezone
import requests
import math
import hashlib
import time

ec2 = boto3.resource('ec2')
cloudwatch = boto3.client('cloudwatch')
memcache_port = webapp.config['MEMCACHE_PORT']
eastern = timezone('US/Eastern')
MIN_SIZE = webapp.config['MIN_SIZE']
MAX_SIZE = webapp.config['MAX_SIZE']
AMI_ID = webapp.config["AMI_ID"]
SECURITY_GROUP_ID = webapp.config["SECURITY_GROUP_ID"]
KEY_NAME = webapp.config["KEY_NAME"]

@webapp.route('/',methods=['GET'])
@webapp.route('/index',methods=['GET'])
@webapp.route('/main',methods=['GET'])
# Display an HTML page with links
def main():
    return render_template("main.html",title="Landing Page")

@webapp.route('/configurePolicy', methods=['POST'])
def configure_policy():
    
    webapp.logger.info(
        "{} request /configurePolicy received with Max Miss Rate threshold {}, Min Miss Rate threshold {}, Ratio to expand the pool {}, Ratio to shrink the pool {}."
        .format(request.method, request.args.get('max_miss_rate_threshold'), request.args.get('min_miss_rate_threshold'), 
                request.args.get('ratio_to_expand'),request.args.get('ratio_to_shrink')))

    auto_scalling_configuration['enabled'] = True
    
    auto_scalling_configuration['max_miss_rate_threshold'] = request.args.get('max_miss_rate_threshold')
    auto_scalling_configuration['min_miss_rate_threshold'] = request.args.get('min_miss_rate_threshold')
    auto_scalling_configuration['ratio_to_expand'] = request.args.get('ratio_to_expand')
    auto_scalling_configuration['ratio_to_shrink'] = request.args.get('ratio_to_shrink')
    response = webapp.response_class(
        response=json.dumps({"success": "true"}),
        status=200,
        mimetype='application/json'
    )
    if not sched.running:
        sched.start()
    elif sched.state == 2:
        sched.resume()
    return response

@webapp.route('/disableAutoMode', methods=['POST'])
def disableAutoMode():
    webapp.logger.info("{} request /disableAutoMode received.".format(request.method))
    auto_scalling_configuration['enabled'] = False
    if sched.running:
        sched.pause()
    response = webapp.response_class(
        response=json.dumps({"success": "true"}),
        status=200,
        mimetype='application/json'
    )
    return response

@webapp.route('/expandByOne', methods=['POST'])
def expandByOne():
    webapp.logger.info("{} request /expandByOne received.".format(request.method))
    running_instances = memcache_monitor['running']
    expand(running_instances, 1)   
    response = webapp.response_class(
        response=json.dumps({"success": "true"}),
        status=200,
        mimetype='application/json'
    )
    return response

@webapp.route('/shrinkByOne', methods=['POST'])
def shrinkByOne():
    webapp.logger.info("{} request /shrinkByOne received.".format(request.method))
    running_instances = memcache_monitor['running']
    shrink(running_instances, 1)   
    response = webapp.response_class(
        response=json.dumps({"success": "true"}),
        status=200,
        mimetype='application/json'
    )
    return response


@webapp.route('/updateStartedNodeCount', methods=['POST'])
def updateStartedNodeCount():
    webapp.logger.info("{} request /updateStartedNodeCount received.".format(request.method))
    time_stamp = datetime.now(eastern)
    memCache_info = {'ip': request.args.get('public_ip'), 'instance_id':request.args.get('instance_id'), 'ready_time':time_stamp}
    memcache_monitor['running'].append(memCache_info)
    response = webapp.response_class(
        response=json.dumps({"success": "true"}),
        status=200,
        mimetype='application/json'
    )
    return response


@webapp.route('/getStartedNodes', methods=['GET'])
def getStartedNodes():
    webapp.logger.info("{} request /getStartedNodes received.".format(request.method))
    response = webapp.response_class(
        response=json.dumps({"success": "true", "memcache_nodes": memcache_monitor['running']}),
        status=200,
        mimetype='application/json'
    )
    return response


def auto_scalling():
    if auto_scalling_configuration['enabled'] == True:
        # get the miss rate from cloud watch
        current_time = datetime.utcnow()
        running_instances = memcache_monitor['running']
        item_list_stats = cloudwatch.get_metric_statistics(
            Period=1 * 60,
            StartTime = current_time - timedelta(seconds=5 * 60),
            EndTime = current_time,
            MetricName="MissRate",
            Namespace="MemcacheService", 
            Unit='Percent',
            Statistics=['Average'],
            Dimensions=[{'Name': 'Target', 'Value': 'MemCache'}]
        )
        #skip if there is no new data
        data_points = item_list_stats['Datapoints']
        data_points = sorted(data_points, key=lambda x: x['Timestamp'], reverse=True)
        if len(data_points) > 0:
            webapp.logger.info('Obtained data points from cloudwatch.')
            avg_for_all = data_points[0]['Average']

            if avg_for_all >= float(auto_scalling_configuration['max_miss_rate_threshold']):
                # scale up using ratio to expend
                expand_size = round(float(auto_scalling_configuration['ratio_to_expand']) * len(running_instances)) - len(running_instances)
                expand(running_instances, expand_size)
                
            elif avg_for_all <= float(auto_scalling_configuration['min_miss_rate_threshold']):
                # scale up using ratio to shrink
                shrink_size = round(float(auto_scalling_configuration['ratio_to_shrink']) * len(running_instances))
                shrink(running_instances, shrink_size)


def expand(running_instances, expand_size):
    max = MAX_SIZE - len(running_instances)
    if max > 0:
        if max < expand_size:
            expand_size = max

        # create new nodes
        nodes = create_node(len(running_instances), expand_size)
        # sync memeCache Configuration
        for node in nodes:
            node.load()
            url = f"http://{node.public_ip_address}:{memcache_port}/refreshConfiguration"
            webapp.logger.info("sending /refreshConfiguration request to {}.".format(url))
            requests.post(url)
        
        # re-distribute based on the hashing
        new_pool = memcache_monitor['running']
        # sort by the launch time 
        running_instances = sorted(running_instances,key=lambda x: x['ready_time'])
        new_pool = sorted(new_pool, key=lambda x: x['ready_time'])
        
        re_distribute_cache(running_instances, new_pool, 'expand')
        
        create_time=datetime.now(eastern)
        # comment this for now as no more quota
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
                    'Value': len(new_pool),
                    'Unit': 'Count',
                    'Timestamp': create_time
                },
            ]
        )

def shrink(running_instances, shrink_size):
    if len(running_instances) > 1: 

        new_size = len(running_instances) - shrink_size
        if new_size < 1:
            new_size = 1

        # sort by the launch time
        running_instances = sorted(running_instances,key=lambda x: x['ready_time'])
        new_pool = running_instances[:new_size]
        memcache_monitor['running'] = new_pool
        
        # re-distribute based on the hashing
        re_distribute_cache(running_instances, new_pool, 'shrink')
    
        create_time=datetime.now(eastern)
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
                'Value': len(new_pool),
                'Unit': 'Count',
                'Timestamp': create_time
            },
        ]
        )
        
        

def re_distribute_cache(original_pool, new_pool, action): 
    
    all_caches = {}
    
    pool_idx = [str(i) for i in range(len(new_pool))]
    hash_circle = pool_idx * math.ceil(16 / len(pool_idx))
    hash_circle = hash_circle[:16]
    
    node_cache = {}
    for node_idx in pool_idx:
        node_cache.update({node_idx:{}})
    
    for node in original_pool:
        
        #collect all the content from memCache
        url = f"http://{node['ip']}:{memcache_port}/getAllCache"
        webapp.logger.info(url)
        response = requests.post(url)
        cache = response.json()["caches"]
        all_caches.update(cache)
        
        #clear data
        url = f"http://{node['ip']}:{memcache_port}/clear"
        webapp.logger.info(url)
        requests.post(url)
        
    if action == 'shrink':
        # destory the shrinked running nodes.
        print("start to terminate nodes")
        clean_pending_nodes = original_pool[len(new_pool):]
        clean_pending_nodes_ids = [node['instance_id'] for node in clean_pending_nodes]
        ec2.instances.filter(InstanceIds=clean_pending_nodes_ids).terminate()
        
    #re-distribution
    for name_key, cache_content in all_caches.items():
        hashing = hashlib.md5(name_key.encode("utf-8")).hexdigest()
        hashing_index = int(hashing, 16) // (2**124)
        des_instance = hash_circle[hashing_index]
        node_cache.get(des_instance).update({name_key:cache_content})
        
    for node_idx, caches in node_cache.items():
        node_idx = int(node_idx)
        node = new_pool[node_idx]
        url = f"http://{node['ip']}:{memcache_port}/insertCaches"
        webapp.logger.info(url)
        # params = {}
        data = {}
        for name, cache_content in caches.items():
            data.update({name:cache_content})
        response = requests.post(url, json=data)

def create_node(original_node_count, node_num):
    if node_num != 0:
        webapp.logger.info('Creating new nodes')
        instances = ec2.create_instances(
                ImageId=AMI_ID,
                MinCount=1,
                MaxCount=node_num,
                InstanceType="t2.micro",
                SecurityGroupIds=[
                    SECURITY_GROUP_ID,
                ],
                KeyName = KEY_NAME,


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
        #the count of memCache as the while loop condition
        while (len(memcache_monitor['running']) - original_node_count) != node_num:
            time.sleep(10)
        webapp.logger.info('Done node creations.')
        return instances
    return []

@webapp.route('/configure_cache', methods=['POST'])
def configure_cache():
    # setup the config
    autoscaling_configuration['mode'] = request.args.get('mode')
    autoscaling_configuration['numNodes'] = int(request.args.get('numNodes'))
    autoscaling_configuration['cacheSize'] = int(request.args.get('cacheSize'))
    autoscaling_configuration['policy'] = request.args.get('policy')
    autoscaling_configuration['expRatio'] = request.args.get('expRatio')
    autoscaling_configuration['shrinkRatio'] = request.args.get('shrinkRatio')
    autoscaling_configuration['maxMiss'] = request.args.get('maxMiss')
    autoscaling_configuration['minMiss'] = request.args.get('minMiss')

    response = webapp.response_class(
        response=json.dumps({"success": "true", "mode": autoscaling_configuration['mode'],"numNodes":autoscaling_configuration['numNodes'], 'cacheSize':autoscaling_configuration['cacheSize'],"policy":autoscaling_configuration['policy']}),
        status=200,
        mimetype='application/json'
    )

    return response

if not debug_value or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    sched = BackgroundScheduler(daemon=True)
    sched.add_job(auto_scalling,'interval',seconds=5, max_instances=1)
