'''
Created on May 30, 2016

@author: Michael
'''

from sqlalchemy import Column, Integer, Float, String, Date, Table, MetaData, ForeignKey, DateTime, CHAR, Numeric, Boolean, PrimaryKeyConstraint, UniqueConstraint
import datetime, bcrypt
from sqlalchemy.ext.declarative import declarative_base


Base=declarative_base()


class users(Base):
    __tablename__='users'
    u_id = Column('u_id', Integer, primary_key=True, nullable=False, autoincrement=True)
    u_email = Column('u_email', String(42), unique=True, nullable=False)
    u_name = Column('u_name', String(25), nullable=False)
    u_handle = Column('u_handle', String(15), unique=True, nullable=False)
    u_key = Column('u_key',String(255), nullable=False, default='default')
    u_dob = Column('u_dob', Date, nullable=True, default=datetime.date(1901,1,1))
    u_paswd = Column('u_paswd', String(255), nullable=False)
    u_description = Column ('u_description', String(255), nullable = True, default='No description set')
    u_phone = Column('u_phone', String(15), nullable=True, default = 'N/A')   
    u_stipend_points = Column('stipend_points',Integer, nullable=False, default=0)
    u_personal_points = Column('personal_points', Integer, nullable=False, default=0)
    account_created = Column('account_created', DateTime, default=datetime.datetime.utcnow)
    last_stipend_date = Column('last_stipend_date', DateTime, default=datetime.datetime.utcnow)
    
    def verify_password(self, password):
        pwhash = bcrypt.hashpw(password.encode('utf-8'), self.paswd.encode('utf-8'))
        return self.paswd == pwhash   
    def __init__(self, email, u_name, paswd, u_handle, stipend_points=0, u_description='No description set', personal_points=0, key='default'):
        self.email=email
        self.u_name=u_name
        self.u_paswd=paswd
        self.u_key=key
        self.u_handle=u_handle
        self.u_description=u_description
        self.u_stipend_points=stipend_points
        self.u_personal_points=personal_points
        
    def get_bucket(self):
        return 'hostpostuserprof'

    def __repr__(self):
        return '<User %r>' % self.u_id 

class chats(Base):
    __tablename__='chats'
    messg_id = Column('messg_id', Integer, primary_key=True, nullable=False, autoincrement=True)
    send_id = Column('send_id', Integer, ForeignKey("users.u_id"), nullable=False)
    recip_id = Column('recip_id', Integer, ForeignKey("users.u_id"), nullable=False)
    date_time = Column('date_time', DateTime, default=datetime.datetime.utcnow)
    messg_cont = Column('messg_cont', String(255), nullable=False)
    
    def __init__(self, send_id, recip_id, messg_cont):
        self.send_id = send_id
        self.recip_id = recip_id
        self.messg_cont = messg_cont

    def __repr__(self):
        return '<Message %r>' % self.messg_id
    
class friends(Base):
    __tablename__='friends'
    friend_id = Column('friend_id', Integer, primary_key=True, nullable=False, autoincrement=True)
    friend_a = Column('friend_a', Integer, ForeignKey("users.u_id"), nullable=False)
    friend_b = Column('friend_b', Integer, ForeignKey("users.u_id"), nullable=False)
    friend_status = Column('friend_status', CHAR, nullable=False)
    date_time_request = Column ('date_time_request', DateTime, default=datetime.datetime.utcnow)
    requester = Column('requester', CHAR, nullable=False)
    last_chat = Column('last_chat', String(255), nullable=True)
    
    def requested(self, someID):
        if someID == self.requester:
            return True
        else:
            return False
    
    def __init__(self, friend_a, friend_b, requester, friend_status='P'):
        self.friend_a = friend_a
        self.friend_b = friend_b
        self.requester = requester
        self.friend_status = friend_status

    def __repr__(self):
        return '<Friendship %r>' % self.friend_id

class forumPosts(Base):
    __tablename__='forumPosts'
    post_id = Column('post_id', Integer, primary_key=True, nullable=False, autoincrement=True)
    post_u_id = Column('post_u_id', Integer, ForeignKey("users.u_id"), nullable=False)
    post_long = Column('post_long', Numeric(precision=11, scale=8), nullable=True)
    post_lat = Column('post_lat', Numeric(precision=10, scale=8), nullable=True)
    post_cont = Column('post_cont', String(255), nullable=False)
    original_post_id = Column('original_post_id', Integer, nullable=False, default=0)
    date_time = Column('date_time', DateTime, default=datetime.datetime.utcnow)
    points_count = Column('points_count', Integer, default=0)
    date_time_edited = Column('date_time_edited', DateTime, default=datetime.datetime.utcnow)
    reply_count = Column('reply_count', Integer, nullable=False, default = 0)
    
    def __init__(self, post_u_id, post_cont, post_long=-1, post_lat=-1, original_post_id=0):
        self.post_u_id=post_u_id
        self.post_long=post_long
        self.post_lat=post_lat
        self.post_cont=post_cont
        self.original_post_id = original_post_id

    def __repr__(self):
        return '<Post %r>' % self.post_id

class groupDetails(Base):
    __tablename__='groupDetails'
    group_id = Column('group_id', Integer, primary_key=True, nullable=False, autoincrement=True)
    group_handle = Column('group_handle', String(24), unique=True, nullable=False)
    group_name = Column('group_name', String(60), nullable=False)
    group_key = Column('group_key', String(255), nullable = False, default = 'default')
    group_description = Column('group_description', String(255), nullable=False)
    group_city = Column('group_city', String(60), nullable = False)
    group_create_date = Column('group_create_date', DateTime, default=datetime.datetime.utcnow)
    group_searchable = Column('searchable', Boolean, nullable = False) #Y=Yes, N=No
    group_readable = Column('readable', Boolean, nullable = False)
    group_on_profile = Column('on_profile', Boolean, nullable = False)
    group_invite_only = Column('invite_only', String(1), nullable = False) #'N' not required, 'M' Member only, 'H' Host only
    group_long = Column('group_long', Numeric(precision=11, scale=8), nullable=False)
    group_lat = Column('group_lat', Numeric(precision=10, scale=8), nullable=False)
    group_num_members = Column('group_num_members', Integer, nullable=False, default=1)
    group_category = Column('group_category', String(60), nullable = False, default='N/A')
    group_active = Column('group_active', String(1), nullable = False, default = 'Y') # y=yes, n=no
    
    def __init__(self, group_name, group_handle, group_description, group_city, group_lat, group_long, group_category='N/A', searchable = True, readable = True, on_profile = True, invite_only = 'H'):
        self.group_name = group_name
        self.group_handle = group_handle
        self.group_description = group_description
        self.group_city = group_city
        self.group_long = group_long
        self.group_lat = group_lat
        self.searchable = searchable
        self.readable = readable
        self.on_profile = on_profile
        self.invite_only = invite_only
        self.group_category = group_category

    def get_bucket(self):
        return 'somesBucketString'

    def __repr__(self):
        return '<Group %r>' % self.group_id
    
class groupMembers(Base):
    __tablename__ = 'groupMembers'
    group_id = Column('group_id', Integer, ForeignKey("groupDetails.group_id"), nullable=False)
    member_id = Column('member_id', Integer, ForeignKey("users.u_id"), nullable=False)
    member_role = Column('member_role', String(1), nullable=False) #O=Owner, H=Host, M=Member, 
    member_status = Column('member_status', String(1), nullable=False) #B=Blocked, S = Request Received from user, I = Invited to Group, R=Refused, M=Member, N=Not Member
    last_host_post_seen = Column('last_host_post_seen', Integer, ForeignKey("groupPosts.group_post_id"))
    last_post_seen = Column('last_post_seen', Integer, ForeignKey("groupPosts.group_post_id"))
    last_event_seen = Column('last_event_seen', Integer, ForeignKey("groupEventPosts.group_event_post_id"))
    approved_by = Column('approved_by', Integer, ForeignKey("users.u_id"), nullable=True)
    member_message = Column('member_message', String(255), nullable = True, default = 'N/A')
    __table_args__ = (PrimaryKeyConstraint('group_id','member_id',name='group_member_pk'),)    


    def __init__(self, group_id, member_id, member_role, member_status, member_message = 'N/A'):
        self.group_id = group_id
        self.member_id = member_id
        self.member_role = member_role
        self.member_status = member_status
        self.member_message = member_message

    def __repr__(self):
        return '<Membership %r>' % self.group_id    
    
class groupPosts(Base):
    __tablename__='groupPosts'
    group_post_id = Column('group_post_id', Integer, primary_key=True, nullable=False, autoincrement=True)
    group_id = Column('group_id', Integer, ForeignKey("groupDetails.group_id"), nullable=False)
    post_u_id = Column('post_u_id', Integer, ForeignKey("users.u_id"), nullable=False)
    date_time = Column('date_time', DateTime, default=datetime.datetime.utcnow)
    group_post_cont = Column('group_post_cont', String(255), nullable = False)
    internet_points = Column('internet_points', Integer, default=0)
    original_post_id = Column('original_post_id', Integer, nullable=False, default=0)
    reply_count = Column('reply_count', Integer, nullable=False, default=0)
    points_count = Column('points_count', Integer, default=0)
    date_time_edited = Column('date_time_edited', DateTime, default=datetime.datetime.utcnow)
    
    def __init__(self, group_id, post_u_id, group_post_cont, original_post_id = 0):
        self.group_id = group_id
        self.post_u_id = post_u_id
        self.group_post_cont = group_post_cont
        self.original_post_id = original_post_id

    def __repr__(self):
        return '<Group Post ID %r>' % self.group_post_id   
    
class groupEventDetails(Base):
    __tablename__ = 'groupEventDetails'
    event_id = Column('event_id', Integer, primary_key=True, nullable=False, autoincrement=True)
    group_id = Column('group_id', Integer, ForeignKey("groupDetails.group_id"), nullable=False)
    event_name = Column('event_name', String(60), nullable=False)
    event_description = Column('event_description', String(255), nullable=False)
    event_start = Column('event_start', DateTime, nullable=False)
    event_end = Column('event_end', DateTime, nullable=False)
    attending_count = Column('attending_count', Integer, nullable=False, default=0)
    event_post_count = Column('event_post_count', Integer, nullable=False, default=0)

    def __init__(self, group_id, event_name, event_description, event_start, event_end):
        self.group_id = group_id
        self.event_name = event_name
        self.event_description = event_description
        self.event_start = event_start
        self.event_end = event_end

    def __repr__(self):
        return '<Event ID %r>' % self.event_id 

class groupEventPosts(Base):
    __tablename__ = 'groupEventPosts'
    group_event_post_id = Column('group_event_post_id', Integer, primary_key=True, nullable=False, autoincrement=True)
    event_id = Column('event_id', Integer, ForeignKey("groupEventDetails.event_id"), nullable=False)
    group_id = Column('group_id', Integer, ForeignKey("groupDetails.group_id"), nullable=False)
    group_event_post_u_id = Column('group_event_u_id', Integer, ForeignKey("users.u_id"), nullable=False)
    date_time = Column('date_time', DateTime, default=datetime.datetime.utcnow)
    group_event_post_cont = Column('group_event_post_cont', String(255), nullable = False)
    internet_points = Column('internet_points', Integer, default=0)
    cell_type = Column('cell_type', String(1), default = 'T', nullable=False) #I = Image, T = Text
    image_key = Column('image_key',String(255), nullable=False, default='default') 
    date_time_edited = Column('date_time_edited', DateTime, default=datetime.datetime.utcnow)
    reply_count = Column('reply_count', Integer, nullable=False, default=0)
    points_count = Column('points_count', Integer, default=0)

    def __init__(self, event_id, group_id, group_post_u_id, group_event_post_cont,cell_type='T',image_key='default'):
        self.event_id = event_id
        self.group_id = group_id
        self.group_post_user_id = group_post_u_id
        self.group_event_post_cont = group_event_post_cont
        self.cell_type = cell_type
        self.image_key = image_key

    def get_image_bucket(self):
        return 'hostposteventimage'

    def __repr__(self):
        return '<Event Post ID %r>' % self.group_event_post_id

class groupEventUsers(Base):
    __tablename__ = 'groupEventUsers'
    event_id = Column('event_id', Integer, ForeignKey("groupEventDetails.event_id"), nullable=False)
    attendee_id = Column('attendee_id', Integer, ForeignKey("users.u_id"), nullable=False)
    event_role = Column('event_role', String(1), nullable=False) #M = attending N = not attending
    __table_args__ = (PrimaryKeyConstraint('event_id','attendee_id',name='event_attendee_pk'),)

    def __init__(self, event_id, attendee_id, event_role):
        self.event_id = event_id
        self.attendee_id = attendee_id
        self.event_role = event_role

    def __repr__(self):
        return '<Attendee ID %r>' % self.event_id
    
class forumPostUpvoted(Base):
    __tablename__ = 'forumPostUpvoted'
    voter_id = Column('voter_id', Integer, ForeignKey("users.u_id"), nullable=False)
    post_id = Column('post_id', Integer, ForeignKey("forumPosts.post_id"), nullable=False)
    points = Column('points', Integer, default=0, nullable=False)
    __table_args__ = (PrimaryKeyConstraint('voter_id','post_id',name='forum_voter_post_pk'),)
    
    def __init__(self, voter_id, post_id, points):
        self.voter_id = voter_id
        self.post_id = post_id
        self.points = points
        
    def __repr__(self):
        return '<Forum Upvote %r %r>' % self.voter_id % self.post_id

class groupPostUpvoted(Base):
    __tablename__ = 'groupPostUpvoted'
    voter_id = Column('voter_id', Integer, ForeignKey("users.u_id"), nullable=False)
    post_id = Column('post_id', Integer, ForeignKey("groupPosts.group_post_id"), nullable=False)
    points = Column('points', Integer, default=0, nullable=False)
    __table_args__ = (PrimaryKeyConstraint('voter_id','post_id',name='forum_voter_post_pk'),)
    
    def __init__(self, voter_id, post_id, points):
        self.voter_id = voter_id
        self.post_id = post_id
        self.points = points
        
    def __repr__(self):
        return '<Forum Upvote %r %r>' % self.voter_id % self.post_id
    
class eventPostUpvoted(Base):
    __tablename__ = 'eventPostUpvoted'
    voter_id = Column('voter_id', Integer, ForeignKey("users.u_id"), nullable=False)
    post_id = Column('post_id', Integer, ForeignKey("groupEventPosts.group_event_post_id"), nullable=False)
    points = Column('points', Integer, default=0, nullable=False)
    __table_args__ = (PrimaryKeyConstraint('voter_id','post_id',name='forum_voter_post_pk'),)
    
    def __init__(self, voter_id, post_id, points):
        self.voter_id = voter_id
        self.post_id = post_id
        self.points = points
        
    def __repr__(self):
        return '<Forum Upvote %r %r>' % self.voter_id % self.post_id
   
class systemMessages(Base):
    __tablename__='systemMessages'
    message_id = Column('message_id', Integer, primary_key=True, autoincrement = True)
    message_name = Column('message_name', String(20), nullable=False, unique = True)
    message_contents = Column('message_contents', String(254), nullable = False)
    
    def __init__(self, message_name, message_contents):
        self.message_name = message_name
        self.message_contents = message_contents
        
    def __repr__(self):
        return '<Message ID %r>' % self.message_id
    
class reportedPosts(Base):
    __tablename__='reportedPosts'
    report_id = Column('report_id', Integer, primary_key=True, autoincrement=True)
    post_id = Column('post_id', Integer, nullable=False)
    post_type = Column('post_type', String(1), nullable=False) #F=Forum, G=Group, E=Event
    reporter_u_id = Column('reporter_u_id', Integer, ForeignKey("users.u_id"), nullable=False)
    report_reason = Column('report_reason', String(255), nullable=True, default='N/A')
        
    def __init__(self, post_id, post_type, report_u_id, report_reason='N/A'):
        self.post_id = post_id
        self.post_type = post_type
        self.reporter_u_id=report_u_id
        self.report_reason=report_reason
        
    def __repr__(self):
        return '<Reported ID %r>' % self.report_id
    
    
'''
triggers to increment last posts seen, num posts, last_chat
trigger to update last post seen, num members, attending count, event post
ensure unique friend_a/friend_b


'''    
    