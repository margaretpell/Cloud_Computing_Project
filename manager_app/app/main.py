from flask import Blueprint, render_template, url_for, request, redirect, flash, json
from app import webapp, db
import requests
from app.models import Image, Mem_cache_configuration
from pytz import timezone
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError
import boto3
from datetime import timedelta

main = Blueprint('main', __name__, static_folder="static",
                 template_folder="template")

memcache_port = webapp.config['MEMCACHE_PORT']
autoscalar_port = webapp.config['AUTOSCALAR_PORT']
manager_port = webapp.config['MANAGERAPP_PORT']
eastern = timezone('US/Eastern')

@main.route('/', methods=['GET'])
def landing():
    return render_template("landing.html")


@main.route('/statistics', methods=['GET'])
def statistics():
    client = boto3.client('cloudwatch')
    current_time = datetime.utcnow()
    try:
        item_list_stats = client.get_metric_statistics(
                    Period=1 * 60,
                    StartTime = current_time - timedelta(seconds=30 * 60),
                    EndTime = current_time,
                    MetricName="NumberOfItems",
                    Namespace="MemcacheService", 
                    Unit='Count',
                    Statistics=['Sum'],
                    Dimensions=[{'Name': 'Target', 'Value': 'MemCache'}]
            )
    except IndexError: 
        item_list_stats = {'Datapoints': [{'Sum': 0.0}]}

    try:
        miss_rate_stats = client.get_metric_statistics(
                Period=1 * 60,
                StartTime = current_time - timedelta(seconds=30 * 60),
                EndTime = current_time,
                MetricName="MissRate",
                Namespace="MemcacheService", 
                Unit='Percent',
                Statistics=['Average'],
                Dimensions=[{'Name': 'Target', 'Value': 'MemCache'}]
        )
    except IndexError: 
        miss_rate_stats = {'Datapoints': [{'Average': 0.0}]}

    try:    
        hit_rate_stats = client.get_metric_statistics(
                Period=1 * 60,
                StartTime = current_time - timedelta(seconds=30 * 60),
                EndTime = current_time,
                MetricName="HitRate",
                Namespace="MemcacheService", 
                Unit='Percent',
                Statistics=['Average'],
                Dimensions=[{'Name': 'Target', 'Value': 'MemCache'}]
        )
    except IndexError: 
        hit_rate_stats = {'Datapoints': [{'Average': 0.0}]}
    
    try:
        cache_size_stats = client.get_metric_statistics(
                    Period=1 * 60,
                    StartTime = current_time - timedelta(seconds=30 * 60),
                    EndTime = current_time,
                    MetricName="UtilizedCapacity",
                    Namespace="MemcacheService", 
                    Unit='Count',
                    Statistics=['Sum'],
                    Dimensions=[{'Name': 'Target', 'Value': 'MemCache'}]
            )
    except IndexError: 
        cache_size_stats = {'Datapoints': [{'Sum': 0.0}]}
        
    try:  
        request_served_stats = client.get_metric_statistics(
                Period=1 * 60,
                StartTime = current_time - timedelta(seconds=30 * 60),
                EndTime = current_time,
                MetricName="NumberOfRequestsServered",
                Namespace="MemcacheService", 
                Unit='Count',
                Statistics=['Sum'],
                Dimensions=[{'Name': 'Target', 'Value': 'MemCache'}]
        )
    except IndexError: 
        request_served_stats = {'Datapoints': [{'Sum': 0.0}]}

    try:    
        node_number_stats = client.get_metric_statistics(
                Period=1 * 60,
                StartTime = current_time - timedelta(seconds=30 * 60),
                EndTime = current_time,
                MetricName="NumberOfNodes",
                Namespace="MemcacheService", 
                Unit='Count',
                Statistics=['Average'],
                Dimensions=[{'Name': 'Target', 'Value': 'Pool'}]
        )
    except (IndexError,ValueError):
        node_number_stats = {'Datapoints': [{'Average': 0.0}]}

    # Process Number of Item data 
    item_list = item_list_stats.get('Datapoints')
    miss_rate = miss_rate_stats.get('Datapoints')
    hit_rate = hit_rate_stats.get('Datapoints')
    cache_size = cache_size_stats.get('Datapoints')
    request_served = request_served_stats.get('Datapoints')
    node_number = node_number_stats.get('Datapoints')
    miss_rate_list = []
    hit_rate_list = []
    item_sum_list = []
    cache_size_list = []
    request_served_list = []
    node_number_list = []
    time_stamp_list = []

    for i in range(len(item_list)):
        item_sum_list.append(item_list[i].get('Sum'))
    
    for i in range(len(miss_rate)):
        miss_rate_list.append(miss_rate[i].get('Average'))
    
    for i in range(len(hit_rate)):
        hit_rate_list.append(hit_rate[i].get('Average'))

    for i in range(len(cache_size)):
        cache_size_list.append(cache_size[i].get('Sum'))
    
    for i in range(len(request_served)):
        request_served_list.append(request_served[i].get('Sum'))

    for i in range(len(node_number)):
        node_number_list.append(node_number[i].get('Average'))
        time_stamp_list.append(node_number[i].get('Timestamp'))

    return render_template("statistics.html", SumList=item_sum_list, 
                            HitRate=hit_rate_list, MissRate=miss_rate_list,
                            CacheSize=cache_size_list, Request=request_served_list, Node=node_number_list, Timestamp=time_stamp_list)


@main.route('/configuration', methods=['GET'])
def configuration():
    return render_template("configuration.html")


@main.route('/resizing-mode', methods=['GET'])
def resizing_mode():
    return render_template("resizing_mode.html")


@main.route('/clear-data', methods=['GET'])
def clear_data():
    return render_template("clear_data.html")


@main.route('/refreshConfiguration', methods=['POST'])
def refreshConfiguration():
    try:
        cache_capacity = request.form.get('capacity')
        replacement_policy = request.form.get('policy')

        mem_cache_configuration = db.session.query(Mem_cache_configuration).first()
        mem_cache_configuration.capacity = cache_capacity
        mem_cache_configuration.replacement_policy = replacement_policy
        mem_cache_configuration.modify_time = datetime.now(eastern)
        db.session.commit()
    except SQLAlchemyError as e:
        webapp.logger.error(e)
        flash("Fail to save the new configuration into the database.", 'error')
        return redirect(url_for('main.configuration'))
    try:
        url = "http://" + request.host.replace(manager_port, autoscalar_port) + '/getStartedNodes'
        response = requests.get(url)
        data = response.json()
        memcache_nodes = data['memcache_nodes']
    except Exception as e:
        webapp.logger.error(e)
        flash('Fail to get ec2 instances data.', 'error')
    else:
        # send refresh configuration requests to all memcache
        flag = False
        for node in memcache_nodes:
            try:
                public_ip = node['ip']
                url = f"http://{public_ip}:{memcache_port}/refreshConfiguration"
                webapp.logger.info(url)
                response = requests.post(url)
            except requests.exceptions.RequestException as e:
                webapp.logger.error(e)
                flash(f"Fail to refresh configuration memCache {node}.", 'error')
                flag = True
                continue
        if not flag:
            flash("Update all memcache configuration successfully", 'success')
    return redirect(url_for('main.configuration'))


@main.route('switch_to_manual', methods=['POST'])
def switch_to_manual():
    
    webapp.logger.info('The manual scalling mode is {}'.format(request.form.get('manual_mode')))

    try:
        auto_scalar_url = "http://" + request.host.replace(manager_port, autoscalar_port) + '/disableAutoMode'
        response = requests.post(auto_scalar_url)
    except requests.exceptions.RequestException as e:  # This is the correct syntax
        webapp.logger.warning(e)
        
    action = request.form.get('manual_mode')
    try:
        if action == 'shrink':
            url = "http://" + request.host.replace(manager_port, autoscalar_port) + '/shrinkByOne'
        else:
            url = "http://" + request.host.replace(manager_port, autoscalar_port) + '/expandByOne'
        response = requests.post(url)
        if response is None:
            flash('Fail to configure the manual mode.', 'error')
        else:
            data = response.json()
            if data["success"] == 'true':
                flash("Configure the manual mode successfully.", 'success')
            else:
                flash('Fail to configure the manual mode.', 'error')
    except requests.exceptions.RequestException as e:  # This is the correct syntax
        webapp.logger.warning(e)
        flash('Fail to configure the manual mode.', 'error')

    return redirect(url_for('main.resizing_mode'))
    
@main.route('switch_to_auto', methods=['POST'])
def switch_to_auto():
    
    webapp.logger.info('The  max_threshold is {}, min_threshold is {}, expand_ratio is {}, shrink_ratio is {}'.format( 
                       request.form.get('max_threshold'), request.form.get('min_threshold'), 
                       request.form.get('expand_ratio'),request.form.get('shrink_ratio')))
    
    miss_rate_tr_max = request.form.get('max_threshold')
    miss_rate_tr_min = request.form.get('min_threshold')
    expand_ratio = request.form.get('expand_ratio')
    shrink_ratio = request.form.get('shrink_ratio')
    
    if miss_rate_tr_max <= miss_rate_tr_min:
        flash('The max threshold should be greater than the min threshold.', 'error')
        return redirect(url_for('main.resizing_mode'))
    
    try:
        params = {'max_miss_rate_threshold': miss_rate_tr_max,'min_miss_rate_threshold': miss_rate_tr_min,
                  'ratio_to_expand':expand_ratio,'ratio_to_shrink':shrink_ratio}
    
        auto_scalar_url = "http://" + request.host.replace(manager_port, autoscalar_port) + '/configurePolicy'
        response = requests.post(auto_scalar_url, params=params)
        if response is None:
            flash('Fail to configure auto-scalar policy parameters.', 'error')
        else:
            data = response.json()
            if data["success"] == 'true':
                flash("Enable automatic scalling mode with desired policy parameters successfully.", 'success')
            else:
                flash('Fail to enable automatic scalling mode with desired policy parameters.', 'error')
    except requests.exceptions.RequestException as e:  # This is the correct syntax
        webapp.logger.warning(e)
        flash('Fail to enable automatic scalling mode with desired policy parameters.', 'error')
        
    return redirect(url_for('main.resizing_mode'))


@main.route('/clear-all', methods=['POST'])
def clear_all():
    """
    Deleteing all application data including image data stored in RDS,
    all image files stored in S3 and the content of all memcache nodes
    in the pool.

    Route URL: '/clear-all'
    Methods: ['POST'],
    Parameters:
        None
    Returns:
        Redirection response.
    """
    delete_all_url = "http://" + request.host + '/delete_all'
    response = requests.post(delete_all_url)
    data = response.json()
    if data["success"] == 'true':
        flash('deleted')
    else:
        flash('Unable to delete', 'error')

    return redirect(url_for('main.clear_data'))


@main.route('/delete_all', methods=['POST'])
def delete_all():
    flag = False
    # clear image data stored in RDS
    try:
        db.session.query(Image).delete()
        db.session.commit()
    except SQLAlchemyError as e:
        webapp.logger.error(e)
        flag = True

    # clear image files stored in S3
    try:
        s3 = boto3.resource('s3')
        bucket = s3.Bucket(webapp.config['S3BUCKET'])
        bucket.objects.all().delete()
    except Exception as e:
        webapp.logger.error(e)
        flag = True

    # clear the content of all memcache nodes in the pool
    try:
        url = "http://" + request.host.replace(manager_port, autoscalar_port) + '/getStartedNodes'
        response = requests.get(url)
        data = response.json()
        memcache_nodes = data['memcache_nodes']
    except Exception as e:
        webapp.logger.error(e)
        flag = True
    else:
        # send clear memcache requests to all ec2 instances
        for node in memcache_nodes:
            try:
                public_ip = node['ip']
                url = f"http://{public_ip}:{memcache_port}/clear"
                webapp.logger.info("send request: " + url)
                response = requests.post(url)
            except requests.exceptions.RequestException as e:
                webapp.logger.error(e)
                flag = True
                continue
    if not flag:
        response = webapp.response_class(
            response=json.dumps(
                {"success": "true",
                 "error": {
                     "code": 200
                 }}),
            status=400,
            mimetype='application/json')
        return response
    response = webapp.response_class(
        response=json.dumps(
            {"success": "false",
             "error": {
                 "code": 400
             }}),
        status=400,
        mimetype='application/json')
    return response

@main.route('/clear-memcache', methods=['POST'])
def clear_memcache():
    webapp.logger.info("clear memcache data")
    # clear the content of all memcache nodes in the pool
    try:
        url = "http://" + request.host.replace(manager_port, autoscalar_port) + '/getStartedNodes'
        response = requests.get(url)
        data = response.json()
        memcache_nodes = data['memcache_nodes']
    except Exception as e:
        webapp.logger.error(e)
        flash('Fail to get ec2 instances data.', 'error')
    else:
        # send clear memcache requests to all ec2 instances
        flag = False
        for node in memcache_nodes:
            try:
                public_ip = node['ip']
                url = f"http://{public_ip}:{memcache_port}/clear"
                webapp.logger.info("send request: " + url)
                response = requests.post(url)
            except requests.exceptions.RequestException as e: 
                webapp.logger.error(e)
                flash(f"Fail to connect memCache {node}.", 'error')
                flag = True
                continue
        if not flag:
            flash('Clear memcache data successfully', 'success')
    return redirect(url_for('main.clear_data'))