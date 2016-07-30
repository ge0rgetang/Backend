'''
Created on May 31, 2016

@author: Michael
'''
from application import db
from application.models import Base, users, id_interests, chats

Base.metadata.drop_all(bind=db.engine)
Base.metadata.create_all(bind=db.engine)

print("DB created.")