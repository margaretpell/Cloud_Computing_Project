from datetime import datetime, timedelta
from re import I
from sys import excepthook
from flask import request
from app import webapp, db
from flask import json, Blueprint
import base64
import os
import requests
from werkzeug.utils import secure_filename
from app.models import Image
from pytz import timezone
from sqlalchemy.exc import SQLAlchemyError
import boto3
import hashlib

api = Blueprint('api', __name__)

frontend_port= webapp.config['FRONTEND_PORT']
memcache_port = webapp.config['MEMCACHE_PORT']
autoscalar_port= webapp.config['AUTOSCALAR_PORT']
bucket = webapp.config['S3BUCKET']
eastern = timezone('US/Eastern')

ec2 = boto3.resource('ec2', region_name='us-east-1')
s3 = boto3.client('s3')


@api.route('/key/<key_value>', methods=['POST'])
def get(key_value):
    webapp.logger.info(
        "{} request api/key/<key_value> received with key_value {}".format(request.method, key_value))
    # check key_value
    if not key_value:
        response = webapp.response_class(
            response=json.dumps(
                {"success": "false",
                 "error": {
                     "code": 400,
                     "message": "Empty key_value."
                 }}),
            status=400,
            mimetype='application/json'
        )
        return response

    # check if the key_value key exists in memcache
    # send request to memcache to get the image if exists.
    try:
        memcache_host = route_requests(key_value)
    except Exception as e:
        webapp.logger.warning(e)
    else:     
        try:
            memcache_url = f"http://{memcache_host}:{memcache_port}/get"
            memcache_response = requests.post(
                memcache_url, params={"key": key_value})
            data = memcache_response.json()
            if data["success"] == "true":
                webapp.logger.info("key_value found in memcache")
                value = data["image"]
                response = webapp.response_class(
                    response=json.dumps({"success": "true", "content": value}),
                    status=200,
                    mimetype='application/json'
                )
                return response
        except requests.exceptions.RequestException as e:  # This is the correct syntax
            webapp.logger.warning(e)

    # find image info from database
    try:
        image = db.session.query(Image).filter_by(name=key_value).first()
    except SQLAlchemyError as e:
        webapp.logger.error("Fail to access the database")
        response = webapp.response_class(
            response=json.dumps(
                {"success": "false",
                 "error": {
                     "code": 500,
                     "message": "Fail to access the database."
                 }}),
            status=500,
            mimetype='application/json'
        )
        return response

    hasExists = bool(image)
    # Handle key does not exist in database
    if not hasExists:
        webapp.logger.error("key_value is not found in database.")
        response = webapp.response_class(
            response=json.dumps(
                {"success": "false",
                 "error": {
                     "code": 404,
                     "message": "Unknown key"
                 }}),
            status=404,
            mimetype='application/json'
        )
        return response

    # Get image from S3 bucket
    try:
        path = image.path
        data = s3.get_object(Bucket=bucket, Key=path)
        content = base64.b64encode(data['Body'].read()).decode("utf-8")
    except FileNotFoundError:
        webapp.logger.error("Failed to read file from S3 bucket.")
        response = webapp.response_class(
            response=json.dumps(
                {"success": "false",
                 "error": {
                     "code": 500,
                     "message": "Fail to open the file."
                 }}),
            status=500,
            mimetype='application/json'
        )
        return response
    except:
        webapp.logger.error("Failed to get the image.")
        response = webapp.response_class(
            response=json.dumps(
                {"success": "false",
                    "error": {
                        "code": 500,
                        "message": "Fail to get the image."
                    }}),
            status=500,
            mimetype='application/json'
        )
        return response
    else:
        try:
            memcache_host = route_requests(key_value)
            memcache_url = f"http://{memcache_host}:{memcache_port}/put"
            files = {'file': content}
            requests.post(memcache_url, params={"key": key_value}, files=files)
            webapp.logger.info("Done put key_value and value into memcache")
        except requests.exceptions.RequestException as e:
            webapp.logger.warning(e)
        except Exception as e:
            webapp.logger.warning(e)
    
    response = webapp.response_class(
            response=json.dumps({"success": "true", "key":key_value, "content": content}),
        status=200,
        mimetype='application/json'
    )
    return response


@api.route('/upload', methods=['POST'])
def put():
    key = request.form['key']
    # check key not empty
    if not key:
        response = webapp.response_class(
            response=json.dumps(
                {"success": "false",
                 "error": {
                     "code": 400,
                     "message": "Empty key."
                 }}),
            status=400,
            mimetype='application/json'
        )
        return response

    # check if the post request has the file part
    if 'file' not in request.files:
        response = webapp.response_class(
            response=json.dumps(
                {"success": "false",
                 "error": {
                     "code": 400,
                     "message": "Post request does not have file part."
                 }}),
            status=400,
            mimetype='application/json'
        )
        return response

    file = request.files.get('file')

    webapp.logger.info(
        "{} request api/upload received with key {} and file {}".format(request.method, key, file.filename))

    filename = secure_filename(file.filename)
    file_name, file_ext = os.path.splitext(filename)

    # empty file without a filename.
    if filename == '':
        response = webapp.response_class(
            response=json.dumps(
                {"success": "false",
                 "error": {
                     "code": 400,
                     "message": "Empty filename."
                 }}),
            status=400,
            mimetype='application/json'
        )
        return response
    if file_ext.lower() not in webapp.config['UPLOAD_EXTENSIONS']:
        response = webapp.response_class(
            response=json.dumps(
                {"success": "false",
                 "error": {
                     "code": 400,
                     "message": "File type not supported."
                 }}),
            status=400,
            mimetype='application/json'
        )
        return response

    new_filename = key + file_ext
    new_path = new_filename

    try:
        # check database if the key exists
        image = db.session.query(Image).filter_by(name=key).first()
    except:
        webapp.logger.error("Fail to access the database.")
        response = webapp.response_class(
            response=json.dumps(
                {"success": "false",
                 "error": {
                     "code": 500,
                     "message": "Fail to access the database."
                 }}),
            status=500,
            mimetype='application/json'
        )
        return response

    try:
        hasExists = bool(image)
        if hasExists:
            webapp.logger.info("key has already exists")
            original_path = image.path

            # update database
            image.ext = file_ext
            image.path = new_path
            image.created_time = datetime.now(eastern)
            db.session.commit()

        else:
            # put image info to database
            new_image = Image(name=key, ext=file_ext,
                              path=new_path, created_time=datetime.now(eastern))
            db.session.add(new_image)
            db.session.commit()

        # write the file to S3 bucket
        s3.upload_fileobj(file, bucket, new_path)
        webapp.logger.info("Save file to S3 bucket")

    except SQLAlchemyError as e:
        webapp.logger.error(
            "Fail to save/update the image information into the database.")
        response = webapp.response_class(
            response=json.dumps(
                {"success": "false",
                 "error": {
                     "code": 500,
                     "message": "Fail to save/update the image information into the database."
                 }}),
            status=500,
            mimetype='application/json'
        )
        return response
    except:
        webapp.logger.error(
            "Fail to save/delete the image from the S3 bucket.")
        response = webapp.response_class(
            response=json.dumps(
                {"success": "false",
                 "error": {
                     "code": 500,
                     "message": "Fail to save/delete the image from the S3 bucket."
                 }}),
            status=500,
            mimetype='application/json'
        )
        return response

    # invalidate key in memcache
    try:
        memcache_host = route_requests(key)
    except Exception as e:
        webapp.logger.warning(e)
    else:
        try:
            memcache_url = f"http://{memcache_host}:{memcache_port}/invalidateKey"
            memcache_params = {'key': key}
            requests.post(memcache_url, params=memcache_params)
        except requests.exceptions.RequestException as e:
            webapp.logger.warning(e)

    response = webapp.response_class(
            response=json.dumps({"success": "true","key":key}),
        status=200,
        mimetype='application/json'
    )
    return response


@api.route('/list_keys', methods=['POST'])
def list_keys():
    webapp.logger.info(
        "{} request api/list_keys received".format(request.method))
    try:
        keys = [key[0] for key in db.session.query(Image.name).all()]
        response = webapp.response_class(
            response=json.dumps({"success": "true", "keys": keys}),
            status=200,
            mimetype='application/json'
        )
    except Exception as e:
        webapp.logger.error(e)
        response = webapp.response_class(
            response=json.dumps(
                {"success": "false",
                 "error": {
                     "code": 500,
                     "message": "Fail to fetch the list of all keys."
                 }}),
            status=500,
            mimetype='application/json'
        )
    return response


def route_requests(key):
    try:
        url = "http://" + request.host.replace(frontend_port, autoscalar_port) + '/getStartedNodes'
        response = requests.get(url)
        data = response.json()
        memcache_nodes = data['memcache_nodes']
        num_nodes = len(memcache_nodes)
    except requests.exceptions.RequestException as e:
        webapp.logger.warning(e)
    else:
        hash_value = hashlib.md5(key.encode()).hexdigest()
        bits = 124
        bucket_size = 2**bits
        index = int(hash_value, 16) // bucket_size + 1 # if prefer index 1...16
        ip = memcache_nodes[(index - 1) % num_nodes]['ip']
        webapp.logger.info(f"route request key {key} with hash_value {hash_value} to memcache {index} with ip {ip}")
    return ip

@api.route('/getNumNodes', methods=['POST'])
def getNumNodes():
    webapp.logger.info(
        "{} request api/getNumNodes received".format(request.method))
    try:
        url = "http://" + request.host.replace(frontend_port, autoscalar_port) + '/getStartedNodes'
        response = requests.get(url)
        data = response.json()
        memcache_nodes = data['memcache_nodes']
        num_nodes = len(memcache_nodes)
        response = webapp.response_class(
            response=json.dumps({"success": "true", "numNodes": num_nodes}),
            status=200,
            mimetype='application/json'
        )
    except Exception as e:
        webapp.logger.error(e)
        response = webapp.response_class(
            response=json.dumps(
                {"success": "false",
                 "error": {
                     "code": 500,
                     "message": "Fail to fetch the number of nodes."
                 }}),
            status=500,
            mimetype='application/json'
        )
    return response

@api.route('/getRate', methods=['POST'])
def getRate():
    webapp.logger.info(
        "{} request api/getRate received".format(request.method))
    # Parse the rate parameter from the request
    rate = request.args.get('rate')
    client = boto3.client('cloudwatch')
    current_time = datetime.utcnow()
    average_miss_rate = 0
    try:
        if rate == 'miss':
            miss_rate_stats = client.get_metric_statistics(
                Period=1 * 60,
                StartTime=current_time - timedelta(seconds=30 * 60),
                EndTime=current_time,
                MetricName="MissRate",
                Namespace="MemcacheService",
                Unit='Percent',
                Statistics=['Average'],
                Dimensions=[{'Name': 'Target', 'Value': 'MemCache'}]
            )
            if miss_rate_stats['Datapoints']:
                average_miss_rate = miss_rate_stats['Datapoints'][0]['Average']
            # Return the JSON response with the calculated rate value
            rate_value = average_miss_rate
            response = webapp.response_class(
                response=json.dumps(
                    {"success": "true", 'rate': rate, 'value': rate_value}),
                status=200,
                mimetype='application/json'
        )
    except Exception as e:
        webapp.logger.error(e)
        response = webapp.response_class(
            response=json.dumps(
                {"success": "false",
                 "error": {
                     "code": 500,
                     "message": "Fail to fetch the rate."
                 }}),
            status=500,
            mimetype='application/json'
        )
    return response

