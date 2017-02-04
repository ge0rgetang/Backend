'''
Created on May 31, 2016

@author: Michael
'''

'''
Commenting out code so accidental runs does not do anything.
'''
print 'DB Creation script disabled. Please un-comment to enable'

'''

from application import db
from application.models import Base

Base.metadata.drop_all(bind=db.engine)
Base.metadata.create_all(bind=db.engine)

print("DB created.")
'''