import os
from dotenv import load_dotenv
load_dotenv(".env")
class Config(object):
    SECRET_KEY = '0d6ba14fc678f6ccda715b8b7ddc11f2'
    SQLALCHEMY_DATABASE_URI = f'mysql+pymysql://{os.environ["DB_USERNAME"]}:{os.environ["DB_PASSWORD"]}@{os.environ["DB_HOST"]}:{os.environ["DB_PORT"]}/{os.environ["DB_NAME"]}'
    SQLALCHEMY_ECHO = False
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif'}
    MAX_CONTENT_LENGTH = 16 * 1000 * 1000
    S3BUCKET = os.environ["S3BUCKET"]
    FRONTEND_PORT=os.environ['FRONTEND_PORT']
    MANAGERAPP_PORT=os.environ['MANAGERAPP_PORT']
    MEMCACHE_PORT=os.environ['MEMCACHE_PORT']
    AUTOSCALAR_PORT=os.environ['AUTOSCALAR_PORT']
    AMI_ID = os.environ["AMI_ID"]
    SECURITY_GROUP_ID = os.environ["SECURITY_GROUP_ID"]
    KEY_NAME = os.environ["KEY_NAME"]