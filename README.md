# Cloud Computing Website on Amazon EC2
## Description
This is a Flask Python website that provides users with the ability to upload images to AWS S3, search images from a database (RDS) and memcache, list all key values of the images from the database, and choose the memcache configuration size (MB) and policy such as LRU or Random Replacement. It also shows the chart of the statistics of memcache hit rate, miss rate, number of items, total size of items in cache, and number of requests served per minute for the last 30 minutes at 1-minute granularity. Additionally, it supports choosing the memcache resizing mode (expand and shrink memcache nodes by one on EC2 using manual mode or automatically choose Max Miss Rate threshold, Min Miss Rate threshold, Ratio by which to expand the pool, Ratio by which to shrink the pool) to grow or shrink the memcache nodes. Finally, it can delete all things from the app or only clear the memcache. 
## Getting Started
### Installation
1.Install the required packages:
```
pip install -r requirements.txt
```
2.Configure the environment variables:
```
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=your_region
AWS_S3_BUCKET=your_bucket
RDS_HOST=your_rds_host
RDS_PORT=your_rds_port
RDS_USERNAME=your_rds_username
RDS_PASSWORD=your_rds_password
RDS_DB_NAME=your_rds_db_name
SECURITY_GROUP_ID= your_security_group
KEY_NAME=your_key_name
AMI_ID=your_ami
FRONTEND_PORT=5000
MANAGERAPP_PORT=5001
MEMCACHE_PORT=5002
AUTOSCALAR_PORT=5003
```
3.Run the application:
```
python3 run.py
```
### Display Websites
#### This is application's home page
![alt text](https://github.com/margaretpell/Cloud_Computing_Project/blob/main/images/app_home.jpg)
#### This is managerapp's home page
![alt text](https://github.com/margaretpell/Cloud_Computing_Project/blob/main/images/managerapp_home.jpg)
#### Upload and search images
![alt text](https://github.com/margaretpell/Cloud_Computing_Project/blob/main/images/MTVideo%202.GIF)
#### Configure memcache in auto mode
![alt text](https://github.com/margaretpell/Cloud_Computing_Project/blob/main/images/MTVideo%203.GIF)
#### delete all and expand and shrink memcache
![alt text](https://github.com/margaretpell/Cloud_Computing_Project/blob/main/images/MTVideo.GIF)






