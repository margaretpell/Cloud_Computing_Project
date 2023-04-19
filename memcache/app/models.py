from app import db

class Mem_cache_configuration(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    capacity = db.Column(db.Integer, index=True, nullable=False)
    replacement_policy = db.Column(db.String(12), index=True, nullable=False)
    modify_time = db.Column(db.DateTime)

    def __repr__(self):
        return f"<Mem_cache_configuration ('{self.id}', '{self.capacity}', '{self.replacement_policy}', '{self.modify_time}')>"
