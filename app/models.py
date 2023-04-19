from datetime import datetime
#from tkinter import image_names
from app import db
# from pytz import timezone
# tz = timezone('US/Eastern')
# datetime.now(tz)
import sqlalchemy as sal
# from flask_sqlalchemy import sqlalchemy
from sqlalchemy import create_engine


class Image(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), index=True, unique=True, nullable=False)
    ext = db.Column(db.String(10), index=True, nullable=False)
    path = db.Column(db.String(128), index=True, unique=True, nullable=False)
    created_time = db.Column(db.DateTime)

    def __repr__(self):
        return f"<Image ('{self.id}', '{self.name}', '{self.ext}', '{self.path}', '{self.created_time}')>"


class Mem_cache_configuration(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    capacity = db.Column(db.Integer, index=True, nullable=False)
    replacement_policy = db.Column(db.String(12), index=True, nullable=False)
    modify_time = db.Column(db.DateTime)

    def __repr__(self):
        return f"<Mem_cache_configuration ('{self.id}', '{self.capacity}', '{self.replacement_policy}', '{self.modify_time}')>"