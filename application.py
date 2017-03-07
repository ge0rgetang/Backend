'''
Created on May 30, 2016

@author: Michael Tam

'''

from flask import Flask, request
from application.models import users, chats, friends, forumPosts, groupDetails, groupMembers, groupPosts, groupEventDetails, groupEventPosts, groupEventUsers, forumPostUpvoted, groupPostUpvoted, eventPostUpvoted, systemMessages, reportedPosts, notific, anonForumPosts, anonForumPostUpvoted, globalNotific, bugReport, pinnedPostUpvoted, pinnedPosts
from application import db
import json, bcrypt, boto3, os, re, time, re, requests
import boto.sns
from email.utils import parseaddr
from sqlalchemy import or_, update, and_, case, func, literal_column, union_all #in_
from sqlalchemy.orm import load_only, aliased
from math import cos
from decimal import Decimal
from datetime import datetime, timedelta, time, date
from firebase import firebase
from firebase_token_generator import create_token
from Crypto.Cipher import AES
import base64
import threading
from multiprocessing import Pool
from flask_sslify import SSLify



PROF_BUCKET = 'hostpostuserprof'
GROUP_BUCKET = 'hostpostgroup'
EVENT_BUCKET = 'hostposteventimage'
#PLATFORM_APPLICATION_ARN = 'arn:aws:sns:us-west-1:554061732115:app/APNS_SANDBOX/hostPostDev' #Test
PLATFORM_APPLICATION_ARN = 'arn:aws:sns:us-west-1:554061732115:app/APNS/.native'
AWS_ACCESS_KEY_ID = "AKIAJFOIRUAH3BFBSW4A"#"AKIAIAWLQ6C2HQNAFCOA"
AWS_SECRET_ACCESS_KEY = "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"#"r9Cb5qyfGttKN5V7qEiGuV/XDp4pYUCI8NrhG56L"
DEFAULT_LIMIT = 42
SECONDARY_LIMIT = 88
FIREBASE_URL = 'https://dotnative-2ec5a.firebaseio.com'
FIREBASE_SECRET = 'zBQLIb0ly88Sw2mjLPdfo6tbsUEQ5TpOMvXX9HyA'

EXCLUDED_HANDLES = ["ge0rgetang", "georgetang", "gtang", "gtang42", "gtang43", "george", "georget", "tang", "simon", "randy", "MTVacuum"]

MODE = AES.MODE_CBC

DEFAULT_STIPEND = 108
DEFAULT_STIPEND_TIME = timedelta(days=7)

MAX_RADIUS = 5
MAX_TIME = 108

ENABLE_ERRORS=False


application = Flask(__name__)
sslify = SSLify(application)

application.secret_key = 'cC1YCIWOj9GgWspgNEo2'


@application.before_request
def before_request():
    if not(request.endpoint in ('getPondPost','getAnonPondPost','getMixedPost') and 'myID' in request.form and int(request.form['myID'])==0):
        if request.endpoint not in ('front.FBAppLink','front.appTester', 'test', 'newDeviceID', 'handleCheck', 'front.front','static', 'reportBug','getBugReports'): 
            if not (validate()):
                return json.dumps({'status':'error','message':'Unauthorized'})


@application.route('/login', methods=['POST'])
def login():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('deviceID','userEmail')):
            userEmail = request.form['userEmail']   
            login_method = 0 #login via email
            devID = request.form['deviceID']
        elif all (k in request.form for k in ('deviceID','userHandle')):
            userHandle = request.form['userHandle']
            login_method = 1 #login via handle
            devID = request.form['deviceID']
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    result = {'status':'error', 'message':'Invalid User Name or Password'}
    try:
        if login_method == 0:
            login_check = db.session.query(users).filter(users.u_email==userEmail).one() 
        else: #login via handle
            login_check = db.session.query(users).filter(users.u_handle==userHandle).one() 
        if login_check != []:
            dev_arn = register_device(devID,login_check.u_id)
            #result['deviceReg']=dev_arn 
            if dev_arn != False:
                db.session.query(users).filter(users.u_id==login_check.u_id).update({'device_arn':dev_arn})
                db.session.commit()
                #result['deviceReg']='True'
            result['status'] = 'success'
            result['message'] = 'Successful Login'
            result['myID'] = login_check.u_id
            result['myEmail'] = login_check.u_email
            result['bucket'] = PROF_BUCKET
            result['smallKey'] = login_check.u_key + '_small'
            result['mediumKey'] = login_check.u_key + '_medium'
            result['largeKey'] = login_check.u_key + '_large'
            result['handle'] = login_check.u_handle
            result['userName'] = first_and_initial(login_check.u_name)
            result['userFullName'] = login_check.u_name
            '''
            if (datetime.now() - login_check.last_stipend_date > DEFAULT_STIPEND_TIME):
                login_check.stipend_points = DEFAULT_STIPEND
            '''
        db.session.close()
    except Exception, e:
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Login failed'}
        pass    
    return json.dumps(result)

@application.route('/logout', methods=['POST'])
def logout():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if 'myID' in request.form:
            userID = request.form['myID']
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    try:
        user_check = db.session.query(users.u_id).filter(users.u_id==userID).update({'device_arn':0})
        db.session.commit()
        result['status']='success'  
        result['message']='logged out'
    except Exception, e:
        db.session.rollback()
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Logout error'}
    finally:
        db.session.close()
    return json.dumps(result)

@application.route('/register', methods=['POST'])
def register():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myIDFIR','deviceID','userEmail','userName','userHandle','isPicSet')):
            userEmail = request.form['userEmail']
            userHandle = request.form['userHandle']
            if userHandle.lower() in EXCLUDED_HANDLES:
                return json.dumps(result)
            userName = request.form['userName']
            #hashpaswrd = hash_password(request.form['userPassword'].encode('utf-8'))
            picSet = request.form['isPicSet']
            devID = request.form['deviceID']
            fireBID = request.form['myIDFIR']
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    if not (validate_email(userEmail) or validate_handle(userHandle)):
        return json.dumps(result)    

    data_entered = users(u_email = userEmail, u_name=userName, u_handle = userHandle, stipend_points = DEFAULT_STIPEND, firebase_id=fireBID, device_arn = register_device(devID))
    result={'status':'error','message':'User already registered'}
    try:
        message_check = db.session.query(systemMessages.message_contents).filter(systemMessages.message_name == 'welcome').first()
        result['message'] = message_check.message_contents     
    except:
        result['message'] = 'Welcome to .native - please tell your friends!'
    finally:
        db.session.close()
    handle_exist = 1
    email_exist = 1
    try:
        handle_exist = db.session.query(users.u_handle).filter(func.upper(users.u_handle) == func.upper(userHandle)).count()
        email_exist = db.session.query(users.u_email).filter(func.upper(users.u_email) == func.upper(userEmail)).count()
    except:
        result={'status':'error','message':'User already registered'}
    finally:
        db.session.close()
    if email_exist != 0:
        result['message'] = 'User email already exists'
        return json.dumps(result)
    elif handle_exist !=0:
        result['message'] = 'User handle already exists'
        return json.dumps(result)
    try:
        db.session.add(data_entered)
        db.session.flush()
        user_id = data_entered.u_id
        result['myID']=user_id
        if picSet == 'yes':
            key=str(user_id)+'_userProfPic'
            result['smallKey'] = key + '_small'
            result['mediumKey'] = key + '_medium'
            result['largeKey'] = key + '_large'
            db.session.query(users.u_key).filter(users.u_id==user_id).update({"u_key":key})
        else:
            result['smallKey'] = 'default_small'
            result['mediumKey'] = 'default_medium'
            result['largeKey'] = 'default_large'
        result['bucket']= PROF_BUCKET
        result['status'] = 'success'
        db.session.commit()
    except Exception, e:
        db.session.rollback()
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Registration failed'}
    finally:
        db.session.close()
    return json.dumps(result)

@application.route('/getMixedPost', methods=['POST']) #sort new, hot=all posts in last 24 hours ordered by points
def getMixedPost():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','lastPostID','size')):
            myID = request.form['myID']
            lastPostID = int(request.form['lastPostID'])
            size = request.form['size']
            if all (m in request.form for m in ('longitude','latitude','sort','isExact')):
                isExact = request.form['isExact']
                if isExact == 'yes':
                    radius = (1.5) #Decimal
                else:
                    radius = (5.0)
                myLong = float(request.form['longitude'])
                myLat = float(request.form['latitude'])
                sort = request.form['sort']
            else:
                return json.dumps(result)
        else:
            return json.dumps(result)
    else:    
        return json.dumps(result)    
    result = {'status':'error', 'message':'No posts found'}
    try:
        '''
        get_forum_check = []
        get_anon_check = []
        '''
        min_long, max_long, min_lat, max_lat = getMinMaxLongLat(myLong, myLat, radius)
        if sort == 'new':
            get_forum_check = db.session.query(forumPosts.post_id, users.u_id, users.u_name, users.u_handle,users.u_key, users.firebase_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points, forumPosts.is_pinned).filter(forumPosts.deleted==False).filter(forumPosts.post_u_id==users.u_id).filter(forumPosts.original_post_id==0).filter(forumPosts.post_lat.between(min_lat, max_lat)).filter(forumPosts.post_long.between(min_long, max_long)).outerjoin(forumPostUpvoted, and_(forumPostUpvoted.post_id==forumPosts.post_id, forumPostUpvoted.voter_id==myID))
            get_anon_check = db.session.query(anonForumPosts.a_post_id, users.u_id, users.firebase_id, anonForumPosts.a_post_cont, anonForumPosts.a_points_count, anonForumPosts.a_reply_count, anonForumPosts.a_date_time, anonForumPosts.a_date_time_edited, anonForumPostUpvoted.points, anonForumPosts.is_pinned).filter(anonForumPosts.deleted==False).filter(anonForumPosts.a_post_u_id==users.u_id).filter(anonForumPosts.a_original_post_id==0).filter(anonForumPosts.a_post_lat.between(min_lat, max_lat)).filter(anonForumPosts.a_post_long.between(min_long, max_long)).outerjoin(anonForumPostUpvoted, and_(anonForumPostUpvoted.post_id==anonForumPosts.a_post_id, anonForumPostUpvoted.voter_id==myID))
            if lastPostID !=0:
                get_forum_check = get_forum_check.filter(forumPosts.post_id < lastPostID)    
                get_anon_check = get_anon_check.filter(anonForumPosts.a_post_id < lastPostID)
            get_forum_check = get_forum_check.order_by(forumPosts.date_time.desc()).distinct().limit(DEFAULT_LIMIT)
            get_anon_check = get_anon_check.order_by(anonForumPosts.a_date_time.desc()).distinct().limit(DEFAULT_LIMIT)
        elif sort == 'hot':
            timeCut = datetime.now() - timedelta(days=7) # adjust time range?
            get_forum_check = db.session.query(forumPosts.post_id, users.u_id, users.u_name, users.u_handle,users.u_key, users.firebase_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points, forumPosts.is_pinned).filter(forumPosts.deleted==False).filter(forumPosts.date_time > timeCut).filter(forumPosts.post_u_id==users.u_id).filter(forumPosts.original_post_id==0).filter(forumPosts.post_lat.between(min_lat, max_lat)).filter(forumPosts.post_long.between(min_long, max_long)).filter(forumPosts.points_count!=0).outerjoin(forumPostUpvoted, and_(forumPostUpvoted.post_id==forumPosts.post_id, forumPostUpvoted.voter_id==myID))
            get_anon_check = db.session.query(anonForumPosts.a_post_id, users.u_id, users.firebase_id, anonForumPosts.a_post_cont, anonForumPosts.a_points_count, anonForumPosts.a_reply_count, anonForumPosts.a_date_time, anonForumPosts.a_date_time_edited, anonForumPostUpvoted.points, anonForumPosts.is_pinned).filter(anonForumPosts.deleted==False).filter(anonForumPosts.a_date_time > timeCut).filter(anonForumPosts.a_post_u_id==users.u_id).filter(anonForumPosts.a_original_post_id==0).filter(anonForumPosts.a_post_lat.between(min_lat, max_lat)).filter(anonForumPosts.a_post_long.between(min_long, max_long)).filter(anonForumPosts.a_points_count!=0).outerjoin(anonForumPostUpvoted, and_(anonForumPostUpvoted.post_id==anonForumPosts.a_post_id, anonForumPostUpvoted.voter_id==myID))
            if lastPostID !=0:
                get_forum_check = get_forum_check.filter(forumPosts.post_id < lastPostID)
                get_anon_check = get_anon_check.filter(anonForumPosts.a_post_id < lastPostID)
            get_forum_check = get_forum_check.order_by(forumPosts.points_count.desc()).distinct().limit(DEFAULT_LIMIT) 
            get_anon_check = get_anon_check.order_by(anonForumPosts.a_points_count.desc()).distinct().limit(DEFAULT_LIMIT) 
        else:
            result={'status':'error', 'message':'Invalid Sort'}   
        if get_forum_check.first() is None or get_anon_check.first() is None:
            result = {'status':'success','message':'No posts found'}
        if get_forum_check.first() is not None or get_anon_check.first() is not None:           
            result['status'] = 'success'        
            if get_forum_check == [] and get_anon_check == []:
                result['message'] = 'No results found'
            else:
                result['message'] = 'Results Found'
                anon_labels = ['postID','userID','firebaseID','postContent','pointsCount','replyCount','timestamp','timestampEdited','didIVote','isPinned']
                add_all = 'bucket'
                anonForumPostsList = add_labels(anon_labels,get_anon_check, first_initial=True)
                forum_labels = ['postID','userID','userName','userHandle','key','firebaseID','postContent','pointsCount','replyCount','timestamp','timestampEdited','didIVote','isPinned']
                forumPostsList = add_labels(forum_labels,get_forum_check,add_all,PROF_BUCKET, True, keySize=size)
                result['posts']=[]
                if sort == 'new':
                    a=0
                    a_max = len(anonForumPostsList)
                    f=0
                    f_max = len(forumPostsList)
                    if a_max == 0:
                        a+=1
                    if f_max == 0:
                        f+=1
                    for _ in xrange(0,DEFAULT_LIMIT): 
                        if f < f_max and a < a_max:
                            #print forumPostsList[f]['pointsCount']
                            #print anonForumPostsList[a]['pointsCount']
                            if anonForumPostsList[a]['timestamp'] > forumPostsList[f]['timestamp']:
                                result['posts'].append(anonForumPostsList[a])
                                a+=1
                            elif anonForumPostsList[a]['timestamp'] < forumPostsList[f]['timestamp']:
                                result['posts'].append(forumPostsList[f])
                                f+=1
                            else: #same time value; forum first
                                result['posts'].append(forumPostsList[f])
                                f+=1
                        elif f >= f_max and a < a_max:
                            result['posts'].append(anonForumPostsList[a])
                            a+=1
                        elif a >= a_max and f < f_max:
                            result['posts'].append(forumPostsList[f])
                            f+=1
                elif sort == 'hot':
                    a=0
                    a_max = len(anonForumPostsList)
                    f=0
                    f_max = len(forumPostsList)
                    if a_max == 0:
                        a+=1
                    if f_max == 0:
                        f+=1
                    for i in range(0,DEFAULT_LIMIT): 
                        if f < f_max and a < a_max:
                            #print forumPostsList[f]['pointsCount']
                            #print anonForumPostsList[a]['pointsCount']
                            if anonForumPostsList[a]['pointsCount'] > forumPostsList[f]['pointsCount']:
                                result['posts'].append(anonForumPostsList[a])
                                a+=1
                            elif anonForumPostsList[a]['pointsCount'] < forumPostsList[f]['pointsCount']:
                                result['posts'].append(forumPostsList[f])
                                f+=1
                            else: #same point value; go by timestamp
                                if anonForumPostsList[a]['timestamp'] > forumPostsList[f]['timestamp']:
                                    result['posts'].append(anonForumPostsList[a])
                                    a+=1
                                elif anonForumPostsList[a]['timestamp'] < forumPostsList[f]['timestamp']:
                                    result['posts'].append(forumPostsList[f])
                                    f+=1
                                else:
                                    result['posts'].append(forumPostsList[f])
                                    f+=1
                        elif f >= f_max and a < a_max:
                            result['posts'].append(anonForumPostsList[a])
                            a+=1
                        elif a >= a_max and f < f_max:
                            result['posts'].append(forumPostsList[f])
                            f+=1
                else:
                    result={'status':'error', 'message':'Invalid request'}
                if result['posts'] == []:
                    result['message'] = 'No results found'
            result['status']='success'
    except Exception, e:
        db.session.rollback()
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'No Posts Found'}
    finally:
        db.session.close() 
        #result['status']='success'  
    return json.dumps(result) 


@application.route('/getPondPost', methods=['POST']) #sort hot=all posts in last 24 hours ordered by points
def getPondPost():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID', 'postID','lastPostID','size')):
            myID = request.form['myID']
            postID = int(request.form['postID'])
            lastPostID = int(request.form['lastPostID'])
            size = request.form['size']
            timeDel = 0
            myRad = 0
            if postID == 0: #get parent posts or get my posts
                if 'isMine' in request.form:
                    isMine = str(request.form['isMine'])
                    if isMine == 'no':
                        if all (m in request.form for m in ('longitude','latitude','sort','isExact','radius','timeDel')):
                            isExact = request.form['isExact']
                            sort = request.form['sort']
                            timeDel = int(request.form['timeDel'])
                            if timeDel == 0:
                                if sort == 'hot':
                                    timeDel = 24
                                elif sort == 'new':
                                    timeDel = 336
                            myRad = float(request.form['radius']) # 0 if same request
                            if myRad != 0.0:
                                radius = myRad
                            elif isExact == 'yes':
                                radius = (1.5) 
                            else:
                                radius = (5.0)
                            myLong = float(request.form['longitude'])
                            myLat = float(request.form['latitude'])
                        else:
                            return json.dumps(result)
                else:
                        return json.dumps(result)
            else: #post ID == actual post ID - get replies
                isMine = None
                isExact = None
                radius = None
                sort = None
        else:
            return json.dumps(result)
    else:    
        return json.dumps(result)
    
    result = {'status':'error', 'message':'No posts found'}
    try:
        if postID == 0: #get parent posts or get my posts 
            if isMine == 'yes': #get parent posts you created and parent posts you replied to
                subq = db.session.query(forumPosts.original_post_id).filter(forumPosts.post_u_id == myID).filter(forumPosts.original_post_id != 0).distinct().subquery()
                subq2 = db.session.query(forumPostUpvoted.post_id).filter(forumPostUpvoted.voter_id == myID).distinct().subquery()
                if lastPostID == 0:
                    get_my_posts = db.session.query(forumPosts.post_id, users.u_id, users.u_name, users.u_handle,users.u_key,users.firebase_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points, forumPosts.is_pinned).filter(forumPosts.deleted==False).filter(forumPosts.post_u_id==users.u_id).filter(or_(forumPosts.post_u_id==myID, forumPosts.post_id.in_(subq2), forumPosts.post_id.in_(subq))).filter(forumPosts.original_post_id==0).outerjoin(forumPostUpvoted, and_(forumPostUpvoted.post_id==forumPosts.post_id, forumPostUpvoted.voter_id==myID)).order_by(forumPosts.date_time.desc()).distinct().limit(DEFAULT_LIMIT)
                else:
                    db.session.query(forumPosts.post_id, users.u_id, users.u_name, users.u_handle,users.u_key,users.firebase_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points, forumPosts.is_pinned).filter(forumPosts.deleted==False).filter(forumPosts.post_u_id==users.u_id).filter(or_(forumPosts.post_u_id==myID, forumPosts.post_id.in_(subq2), forumPosts.post_id.in_(subq))).filter(forumPosts.original_post_id==0).filter(forumPosts.post_id < lastPostID).outerjoin(forumPostUpvoted, and_(forumPostUpvoted.post_id==forumPosts.post_id, forumPostUpvoted.voter_id==myID)).order_by(forumPosts.date_time.desc()).distinct().limit(DEFAULT_LIMIT)
                if get_my_posts.first() is not None:    
                    #query for post count
                    #return json.dumps({'result':'here'})
                    result['status'] = 'success'        
                    if get_my_posts == []:
                        result['message'] = 'No results found'
                    else:
                        result['message'] = 'Results Found'
                        labels = ['postID','userID','userName','userHandle','key','firebaseID','postContent','pointsCount','replyCount','timestamp','timestampEdited','didIVote','isPinned']
                        add_all = 'bucket'
                        result['pondPosts'] = add_labels(labels,get_my_posts,add_all,PROF_BUCKET, True, keySize=size)
            elif isMine == 'no':
                radius, timeDel = dynamicRadiusHelper(myLong, myLat, 'pond', sort, radius, timeDel, lastPostID)
                min_long, max_long, min_lat, max_lat = getMinMaxLongLat(myLong, myLat, radius)
                if sort == 'new':
                    timeCut = datetime.now() - timedelta(hours = timeDel)
                    if lastPostID == 0:
                        get_post_check = db.session.query(forumPosts.post_id, users.u_id, users.u_name, users.u_handle,users.u_key, users.firebase_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points, forumPosts.is_pinned).filter(forumPosts.deleted==False).filter(forumPosts.date_time > timeCut).filter(forumPosts.post_u_id==users.u_id).filter(forumPosts.original_post_id==0).filter(forumPosts.post_lat.between(min_lat, max_lat)).filter(forumPosts.post_long.between(min_long, max_long)).outerjoin(forumPostUpvoted, and_(forumPostUpvoted.post_id==forumPosts.post_id, forumPostUpvoted.voter_id==myID)).order_by(forumPosts.date_time.desc()).distinct().limit(DEFAULT_LIMIT)
                    else:                         
                        get_post_check = db.session.query(forumPosts.post_id, users.u_id, users.u_name, users.u_handle,users.u_key, users.firebase_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points, forumPosts.is_pinned).filter(forumPosts.deleted==False).filter(forumPosts.date_time > timeCut).filter(forumPosts.post_u_id==users.u_id).filter(forumPosts.original_post_id==0).filter(forumPosts.post_id < lastPostID).filter(forumPosts.post_lat.between(min_lat, max_lat)).filter(forumPosts.post_long.between(min_long, max_long)).outerjoin(forumPostUpvoted, and_(forumPostUpvoted.post_id==forumPosts.post_id, forumPostUpvoted.voter_id==myID)).order_by(forumPosts.date_time.desc()).distinct().limit(DEFAULT_LIMIT)
                elif sort == 'hot':
                    timeCut = datetime.now() - timedelta(hours = timeDel) # adjust time range?
                    if lastPostID == 0:    
                        get_post_check = db.session.query(forumPosts.post_id, users.u_id, users.u_name, users.u_handle,users.u_key, users.firebase_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points, forumPosts.is_pinned).filter(forumPosts.deleted==False).filter(forumPosts.date_time > timeCut).filter(forumPosts.post_u_id==users.u_id).filter(forumPosts.original_post_id==0).filter(forumPosts.post_lat.between(min_lat, max_lat)).filter(forumPosts.post_long.between(min_long, max_long)).outerjoin(forumPostUpvoted, and_(forumPostUpvoted.post_id==forumPosts.post_id, forumPostUpvoted.voter_id==myID)).order_by(forumPosts.points_count.desc()).distinct().limit(DEFAULT_LIMIT) #restrict by date
                    else:
                        get_post_check = db.session.query(forumPosts.post_id, users.u_id, users.u_name, users.u_handle,users.u_key, users.firebase_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points, forumPosts.is_pinned).filter(forumPosts.deleted==False).filter(forumPosts.date_time > timeCut).filter(forumPosts.post_u_id==users.u_id).filter(forumPosts.original_post_id==0).filter(forumPosts.post_id < lastPostID).filter(forumPosts.post_lat.between(min_lat, max_lat)).filter(forumPosts.post_long.between(min_long, max_long)).outerjoin(forumPostUpvoted, and_(forumPostUpvoted.post_id==forumPosts.post_id, forumPostUpvoted.voter_id==myID)).order_by(forumPosts.points_count.desc()).distinct().limit(DEFAULT_LIMIT) #restrict by date
                else:
                    return json.dumps(result)
                if get_post_check.first() is not None:
                    result['status'] = 'success'        
                    if get_post_check == []:
                        result['message'] = 'No results found'
                    else:                        
                        result['radius'] = radius
                        result['timeDel']= timeDel
                        result['message'] = 'Results Found'
                        labels = ['postID','userID','userName','userHandle','key','firebaseID','postContent','pointsCount','replyCount','timestamp','timestampEdited','didIVote','isPinned']
                        add_all = 'bucket'
                        result['pondPosts'] = add_labels(labels,get_post_check,add_all,PROF_BUCKET, True, keySize=size)
        else: #actual postID sort by desc but send parent in first position
            reps = db.session.query(forumPosts.post_id).filter(forumPosts.original_post_id==postID).filter(forumPosts.deleted==False).count()
            db.session.query(forumPosts.reply_count).filter(forumPosts.post_id==postID).update({'reply_count':reps})
            db.session.commit()
            if lastPostID==0:           
                get_posts = db.session.query(forumPosts.post_id, users.u_id, users.u_name, users.u_handle,users.u_key, users.firebase_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points, forumPosts.is_pinned).filter(forumPosts.deleted==False).outerjoin(forumPostUpvoted, and_(forumPostUpvoted.post_id==forumPosts.post_id, forumPostUpvoted.voter_id==myID)).filter(forumPosts.post_u_id==users.u_id).filter(forumPosts.post_id==postID).distinct().limit(DEFAULT_LIMIT)
                get_replies = db.session.query(forumPosts.post_id, users.u_id, users.u_name, users.u_handle, users.u_key, users.firebase_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points, forumPosts.is_pinned).filter(forumPosts.deleted==False).filter(forumPosts.post_u_id==users.u_id).filter(forumPosts.original_post_id==postID).outerjoin(forumPostUpvoted, and_(forumPostUpvoted.post_id==forumPosts.post_id, forumPostUpvoted.voter_id==myID)).order_by(forumPosts.post_id.desc()).distinct().limit(DEFAULT_LIMIT) 
            else:
                get_posts = db.session.query(forumPosts.post_id, users.u_id, users.u_name, users.u_handle,users.u_key, users.firebase_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points, forumPosts.is_pinned).filter(forumPosts.deleted==False).filter(forumPosts.post_id < lastPostID).outerjoin(forumPostUpvoted, and_(forumPostUpvoted.post_id==forumPosts.post_id, forumPostUpvoted.voter_id==myID)).filter(forumPosts.post_u_id==users.u_id).filter(forumPosts.post_id==postID).distinct().limit(DEFAULT_LIMIT)
                get_replies = db.session.query(forumPosts.post_id, users.u_id, users.u_name, users.u_handle, users.u_key, users.firebase_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points, forumPosts.is_pinned).filter(forumPosts.deleted==False).filter(forumPosts.post_id < lastPostID).filter(forumPosts.post_u_id==users.u_id).filter(forumPosts.original_post_id==postID).outerjoin(forumPostUpvoted, and_(forumPostUpvoted.post_id==forumPosts.post_id, forumPostUpvoted.voter_id==myID)).order_by(forumPosts.post_id.desc()).distinct().limit(DEFAULT_LIMIT) 
            if get_posts is not None:
                if get_posts == []:
                    result['message'] = 'No results found'
                else:
                    result['status'] = 'success' 
                    result['message'] = 'Results Found'
                    labels = ['postID','userID','userName','userHandle','key','firebaseID','postContent','pointsCount','replyCount','timestamp','timestampEdited','didIVote','isPinned']
                    add_all = 'bucket'
                    result['pondPosts'] = add_labels(labels,get_posts,add_all,PROF_BUCKET, first_initial=True, keySize=size) + add_labels(labels,get_replies,add_all,PROF_BUCKET, first_initial=True, keySize=size)
                    '''
                    if get_replies is not None:
                        if get_replies == []:
                            result['message'] = result['message'] + '. No replies found'
                        else:
                            result['pondPosts'] = add_labels(labels,get_replies,add_all,PROF_BUCKET)
                            result['message'] = result['message'] + '. Replies found'
                    '''
        db.session.close()
        result['status']='success'
    except Exception, e:
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'No Posts Found'}        
        pass
    data = json.dumps(result)
    return data

@application.route('/sendPondPost', methods=['POST'])
def sendPondPost():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID', 'postContent', 'postID')):
            myID = request.form['myID']
            postCont = request.form['postContent']
            postID = int(request.form['postID'])
            if postID == 0:
                if all (l in request.form for l in ('longitude','latitude')):
                    postLong = request.form['longitude']
                    postLat = request.form['latitude']
                else:
                    return json.dumps(result)
            #userHandles for tagging
            userHandles=[]
            if 'userHandles' in request.form:
                userHandles=parseHandles(request.form['userHandles'])
        else:
            return json.dumps(result)
    else:    
            return json.dumps(result)
    if postID == 0:
        data_entered = forumPosts(post_u_id = myID, post_cont = postCont, post_long = postLong, post_lat = postLat)
    else:
        data_entered = forumPosts(post_u_id = myID, post_cont = postCont, original_post_id = postID)
    try:
        db.session.add(data_entered)
        db.session.flush()
        result['postID']=data_entered.post_id
        db.session.commit() 
        my_check = db.session.query(users.u_handle).filter(users.u_id==myID).one()
        if postID not in (0, -1):
            db.session.query(forumPosts).filter(forumPosts.post_id==postID).update({'reply_count':forumPosts.reply_count + 1})
            db.session.commit()
            user_check = db.session.query(users.u_id, users.u_handle, users.device_arn, users.firebase_id).filter(users.u_id==forumPosts.post_u_id).filter(forumPosts.post_id==postID).one()        
            if user_check is not None and user_check != [] and int(user_check.u_id) != int(myID):                    
                cont = '@' + my_check.u_handle + ' replied to your pond post: ' + postCont
                subj = 'getMyPondPost'
                notificType = 'F'
                notificUID = user_check.u_id
                inNot = inNotification(user_check.firebase_id)
                if inNot == True:
                    result['notificationSent']=logNotification(notificUID, cont, subj, notificType, notificPostID=postID)      
                    firebaseNotification(user_check.firebase_id, cont)
                    db.session.commit()
                #print user_check.firebase_id
                inPID = inPostID(user_check.firebase_id)
                # inPostID == parentPostID, do NOT send push. 
                if user_check.u_id != myID and inPID != 0 and inPID!=postID and user_check.device_arn != 0 and inNot==False:             
                    result['notificationSent']=logNotification(notificUID, cont, subj, notificType, notificPostID=(data_entered.post_id if postID in (0, -1) else postID))      
                    firebaseNotification(user_check.firebase_id, cont)
                    db.session.commit()
                    badge = db.session.query(notific.notific_id).filter(notific.n_u_id==user_check.u_id).filter(notific.notific_seen==False).count()
                    push(user_check.device_arn, badge, cont, subj)
        result['status'] = 'success'
        result['message'] = 'Posted'
        #send notifications now for tagged users
        if userHandles != []:
            tagged = sendTagNotifications(userHandles, my_check.u_handle, myID, 'getMyPondPost','host' if postID==-1 else 'pond',postCont, (data_entered.post_id if postID in (0, -1) else postID))
            result['numTagged'] = len(userHandles)
            if tagged:
                result['taggedNotifications']='success'
            else:
                result['taggedNotifications']=tagged
            db.session.commit()
    except Exception, e:
        db.session.rollback()
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Post not sent'}
        pass
    finally:
        db.session.close()
    data = json.dumps(result)
    return data

def parseHandles(userHandles): #returns array of handles
    userHandles = userHandles.replace(' ', '')
    userHandles = userHandles.replace('"', '')
    userHandles = userHandles[1:-1] #do I need a check?
    userHandles = userHandles.split(',')
    userHandles = list(set(userHandles))
    return userHandles

def sendTagNotifications(userHandles, senderHandle, senderID, subj, postType, postContent, postID, groupID=-1, poolHandle=None, chapterName = None, eventID=None): #array, sender handle/id, groupID if need to check
    try:
        if userHandles != []:
            tag_check = db.session.query(users.u_id, users.u_handle, users.device_arn, users.firebase_id).filter(users.u_handle.in_(userHandles)).filter(users.u_id != senderID).all()
            if tag_check is not None and tag_check !=[]:
                #print 'what is happening?\n\n'
                for u in tag_check:
                    #print 'u_id: ',u.u_id
                    if u is not None and u != [] and u.u_id != senderID:
                        #print 'here'
                        if postType == 'chapter':
                            cont = '@' + senderHandle +' tagged you in .' + poolHandle+', ' + chapterName + ': ' +postContent
                        elif postType in ('scrap', 'scrapImage'):
                            cont = '@' + senderHandle +' tagged you in the scrapbook: ' + postContent
                        elif postType == 'pool':
                            cont = '@' + senderHandle +' tagged you in .' + poolHandle +': ' + postContent
                        else:
                            cont = '@' + senderHandle +' tagged you in a ' + postType + ' post: ' + postContent
                        if postType == 'pond':
                            notificType = 'P'
                        elif postType == 'pool':
                            notificType = 'G'
                        elif postType =='host':
                            notificType ='H'
                        elif postType == 'scrap':
                            notificType = 'S'
                        elif postType == 'scrapImage':
                            notificType = 'T'
                        elif postType =='chapter':
                            notificType = 'E'
                        else:
                            notificType =''
                            #print postType
                        notificUID = u.u_id
                        inNot = inNotification(u.firebase_id)
                        if inNot == True: #write to firebase if not in notifications
                            #print 'and here\n\n'
                            #print 'notificUID ', notificUID
                            #print 'u.u_id', str(u.u_id)
                            #print 'notificationSent' + str(u.u_id)
                            resNot = 'notificationSent' + str(u.u_id)
                            resNot=logNotification(notificUID, cont, subj, notificType, notificPostID=postID, notificGroupID=None if groupID==-1 else groupID, notificEventID=eventID)
                            firebaseNotification(u.firebase_id, cont)
                            db.session.commit()
                        #inPID = inPostID(u.firebase_id) # inPostID == parentPostID, do NOT send push.
                        #print 'inPID',inPID
                        #print 'inNot', inNot
                        #print 'devARN',u.device_arn
                        if u.device_arn != 0 and inNot==False:      #inPID != 0 and inPID!=postID and       
                            logNotification(notificUID, cont, subj, notificType, notificPostID=postID, notificGroupID=None if groupID==-1 else groupID, notificEventID=eventID)  
                            firebaseNotification(u.firebase_id, cont)
                            db.session.commit()
                            badge = db.session.query(notific.notific_id).filter(notific.n_u_id==u.u_id).filter(notific.notific_seen==False).count()
                            push(u.device_arn, badge, cont, subj)
            else:
                return False
        return True
    except Exception, e:
        #print str(e)
        return False
        

@application.route('/getAnonPondPost', methods=['POST']) #sort hot=all posts in last 24 hours ordered by points
def getAnonPondPost():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID', 'postID', 'lastPostID')):
            myID = int(request.form['myID'])
            postID = int(request.form['postID'])
            lastPostID = int(request.form['lastPostID'])
            if postID == 0: #get parent posts or get my posts
                if 'isMine' in request.form:
                    isMine = str(request.form['isMine'])
                    if isMine == 'no':
                        if all (m in request.form for m in ('longitude','latitude','sort','isExact','radius','timeDel')):
                            isExact = request.form['isExact']
                            sort = request.form['sort']
                            timeDel = int(request.form['timeDel'])
                            if timeDel == 0:
                                if sort == 'hot':
                                    timeDel = 24
                                elif sort == 'new':
                                    timeDel = 336
                            myRad = float(request.form['radius']) # 0 if same request
                            if myRad != 0.0:
                                radius = myRad
                            elif isExact == 'yes':
                                radius = (1.5) 
                            else:
                                radius = (5.0)
                            myLong = float(request.form['longitude'])
                            myLat = float(request.form['latitude'])
                        else:
                            return json.dumps(result)
                else:
                        return json.dumps(result)
            else: #post ID == actual post ID - get replies
                isMine = None
                isExact = None
                radius = None
                sort = None
        else:
            return json.dumps(result)
    else:    
        return json.dumps(result)
    
    result = {'status':'error', 'message':'No posts found'}
    try:
        if postID == 0: #get parent posts or get my posts 
            if isMine == 'yes': #get parent posts you created and parent posts you replied to
                subq = db.session.query(anonForumPosts.a_original_post_id).filter(anonForumPosts.a_post_u_id == myID).filter(anonForumPosts.a_original_post_id != 0).distinct().subquery()
                subq2 = db.session.query(anonForumPostUpvoted.post_id).filter(anonForumPostUpvoted.voter_id == myID).distinct().subquery()
                if lastPostID == 0:
                    get_my_posts = db.session.query(anonForumPosts.a_post_id, users.u_id, users.u_name, users.firebase_id, anonForumPosts.a_post_cont, anonForumPosts.a_points_count, anonForumPosts.a_reply_count, anonForumPosts.a_date_time, anonForumPosts.a_date_time_edited, anonForumPostUpvoted.points, anonForumPosts.is_pinned).filter(anonForumPosts.deleted==False).filter(anonForumPosts.a_post_u_id==users.u_id).filter(or_(anonForumPosts.a_post_u_id==myID, anonForumPosts.a_post_id.in_(subq2), anonForumPosts.a_post_id.in_(subq))).filter(anonForumPosts.a_original_post_id==0).outerjoin(anonForumPostUpvoted, and_(anonForumPostUpvoted.post_id==anonForumPosts.a_post_id, anonForumPostUpvoted.voter_id==myID)).order_by(anonForumPosts.a_date_time.desc()).distinct().limit(DEFAULT_LIMIT)
                else:                
                    get_my_posts = db.session.query(anonForumPosts.a_post_id, users.u_id, users.u_name, users.firebase_id, anonForumPosts.a_post_cont, anonForumPosts.a_points_count, anonForumPosts.a_reply_count, anonForumPosts.a_date_time, anonForumPosts.a_date_time_edited, anonForumPostUpvoted.points, anonForumPosts.is_pinned).filter(anonForumPosts.deleted==False).filter(anonForumPosts.a_post_u_id==users.u_id).filter(or_(anonForumPosts.a_post_u_id==myID, anonForumPosts.a_post_id.in_(subq2), anonForumPosts.a_post_id.in_(subq))).filter(anonForumPosts.a_original_post_id==0).filter(anonForumPosts.a_post_id < lastPostID).outerjoin(anonForumPostUpvoted, and_(anonForumPostUpvoted.post_id==anonForumPosts.a_post_id, anonForumPostUpvoted.voter_id==myID)).order_by(anonForumPosts.a_date_time.desc()).distinct().limit(DEFAULT_LIMIT)
                if get_my_posts is not None and get_my_posts != []:    
                    #query for post count
                    #return json.dumps({'result':'here'})
                    result['status'] = 'success'        
                    result['message'] = 'Results Found'
                    labels = ['postID','userID','userName', 'firebaseID', 'postContent', 'pointsCount', 'replyCount', 'timestamp', 'timestampEdited', 'didIVote','isPinned']
                    result['anonPondPosts'] = add_labels(labels,get_my_posts,first_initial=True)
                    if result['anonPondPosts'] == []:
                        result['message'] = 'No results found'
            elif isMine == 'no':
                radius, timeDel = dynamicRadiusHelper(myLong, myLat, 'anon', sort, radius, timeDel, lastPostID)
                min_long, max_long, min_lat, max_lat = getMinMaxLongLat(myLong, myLat, radius)
                if sort == 'new':  
                    timeCut = datetime.now() - timedelta(hours = timeDel)
                    if lastPostID==0:
                        get_post_check = db.session.query(anonForumPosts.a_post_id, users.u_id, users.firebase_id, anonForumPosts.a_post_cont, anonForumPosts.a_points_count, anonForumPosts.a_reply_count, anonForumPosts.a_date_time, anonForumPosts.a_date_time_edited, anonForumPostUpvoted.points, anonForumPosts.is_pinned).filter(anonForumPosts.deleted==False).filter(anonForumPosts.a_post_u_id==users.u_id).filter(anonForumPosts.a_original_post_id==0).filter(anonForumPosts.a_post_lat.between(min_lat, max_lat)).filter(anonForumPosts.a_post_long.between(min_long, max_long)).outerjoin(anonForumPostUpvoted, and_(anonForumPostUpvoted.post_id==anonForumPosts.a_post_id, anonForumPostUpvoted.voter_id==myID)).order_by(anonForumPosts.a_date_time.desc()).distinct().limit(DEFAULT_LIMIT)  
                    else:
                        get_post_check = db.session.query(anonForumPosts.a_post_id, users.u_id, users.firebase_id, anonForumPosts.a_post_cont, anonForumPosts.a_points_count, anonForumPosts.a_reply_count, anonForumPosts.a_date_time, anonForumPosts.a_date_time_edited, anonForumPostUpvoted.points, anonForumPosts.is_pinned).filter(anonForumPosts.deleted==False).filter(anonForumPosts.a_post_u_id==users.u_id).filter(anonForumPosts.a_post_id < lastPostID).filter(anonForumPosts.a_original_post_id==0).filter(anonForumPosts.a_post_lat.between(min_lat, max_lat)).filter(anonForumPosts.a_post_long.between(min_long, max_long)).outerjoin(anonForumPostUpvoted, and_(anonForumPostUpvoted.post_id==anonForumPosts.a_post_id, anonForumPostUpvoted.voter_id==myID)).order_by(anonForumPosts.a_date_time.desc()).distinct().limit(DEFAULT_LIMIT)
                    #return json.dumps({'status':'error','message':'got here'})
                elif sort == 'hot':
                    timeCut = datetime.now() - timedelta(hours = timeDel) # adjust time range?
                    if lastPostID == 0:
                        get_post_check = db.session.query(anonForumPosts.a_post_id, users.u_id, users.firebase_id, anonForumPosts.a_post_cont, anonForumPosts.a_points_count, anonForumPosts.a_reply_count, anonForumPosts.a_date_time, anonForumPosts.a_date_time_edited, anonForumPostUpvoted.points, anonForumPosts.is_pinned).filter(anonForumPosts.deleted==False).filter(anonForumPosts.a_date_time > timeCut).filter(anonForumPosts.a_post_u_id==users.u_id).filter(anonForumPosts.a_original_post_id==0).filter(anonForumPosts.a_post_lat.between(min_lat, max_lat)).filter(anonForumPosts.a_post_long.between(min_long, max_long)).outerjoin(anonForumPostUpvoted, and_(anonForumPostUpvoted.post_id==anonForumPosts.a_post_id, anonForumPostUpvoted.voter_id==myID)).order_by(anonForumPosts.a_points_count.desc()).distinct().limit(DEFAULT_LIMIT) #restrict by date
                    else:                        
                        get_post_check = db.session.query(anonForumPosts.a_post_id, users.u_id, users.firebase_id, anonForumPosts.a_post_cont, anonForumPosts.a_points_count, anonForumPosts.a_reply_count, anonForumPosts.a_date_time, anonForumPosts.a_date_time_edited, anonForumPostUpvoted.points, anonForumPosts.is_pinned).filter(anonForumPosts.deleted==False).filter(anonForumPosts.a_date_time > timeCut).filter(anonForumPosts.a_post_u_id==users.u_id).filter(anonForumPosts.a_post_id < lastPostID).filter(anonForumPosts.a_original_post_id==0).filter(anonForumPosts.a_post_lat.between(min_lat, max_lat)).filter(anonForumPosts.a_post_long.between(min_long, max_long)).outerjoin(anonForumPostUpvoted, and_(anonForumPostUpvoted.post_id==anonForumPosts.a_post_id, anonForumPostUpvoted.voter_id==myID)).order_by(anonForumPosts.a_points_count.desc()).distinct().limit(DEFAULT_LIMIT) #restrict by date
                else:
                    return json.dumps(result)
                if get_post_check.first() is not None:                                        
                    result['radius'] = radius
                    result['timeDel']= timeDel
                    result['status'] = 'success'        
                    result['message'] = 'Results Found'
                    labels = ['postID','userID', 'firebaseID', 'postContent','pointsCount','replyCount','timestamp','timestampEdited','didIVote', 'isPinned']
                    result['anonPondPosts'] = add_labels(labels,get_post_check,first_initial=True)
                    if result['anonPondPosts'] == []:
                        result['message'] = 'No results found'
        else: #actual postID
            reps = db.session.query(anonForumPosts.a_post_id).filter(anonForumPosts.a_original_post_id==postID).filter(anonForumPosts.deleted==False).count()
            db.session.query(anonForumPosts.a_reply_count).filter(anonForumPosts.a_post_id==postID).update({'a_reply_count':reps})
            db.session.commit()
            if lastPostID==0:
                '''
                get_posts = db.session.query(anonForumPosts.a_post_id, users.u_id, users.firebase_id, anonForumPosts.a_post_cont, anonForumPosts.a_points_count, anonForumPosts.a_reply_count, anonForumPosts.a_date_time, anonForumPosts.a_date_time_edited, anonForumPostUpvoted.points, anonForumPosts.is_pinned).filter(anonForumPosts.a_post_u_id==users.u_id).filter(or_(anonForumPosts.a_post_id==postID, anonForumPosts.a_original_post_id==postID)).outerjoin(anonForumPostUpvoted, and_(anonForumPostUpvoted.post_id==anonForumPosts.a_post_id, anonForumPostUpvoted.voter_id==myID)).distinct().order_by(anonForumPosts.a_post_id.desc()).limit(DEFAULT_LIMIT)
                '''
                get_posts = db.session.query(anonForumPosts.a_post_id, users.u_id, users.firebase_id, anonForumPosts.a_post_cont, anonForumPosts.a_points_count, anonForumPosts.a_reply_count, anonForumPosts.a_date_time, anonForumPosts.a_date_time_edited, anonForumPostUpvoted.points, anonForumPosts.is_pinned).filter(anonForumPosts.deleted==False).filter(anonForumPosts.a_post_u_id==users.u_id).filter(anonForumPosts.a_post_id==postID).outerjoin(anonForumPostUpvoted, and_(anonForumPostUpvoted.post_id==anonForumPosts.a_post_id, anonForumPostUpvoted.voter_id==myID)).distinct().first()
                get_replies = db.session.query(anonForumPosts.a_post_id, users.u_id, users.firebase_id, anonForumPosts.a_post_cont, anonForumPosts.a_points_count, anonForumPosts.a_reply_count, anonForumPosts.a_date_time, anonForumPosts.a_date_time_edited, anonForumPostUpvoted.points, anonForumPosts.is_pinned).filter(anonForumPosts.deleted==False).filter(anonForumPosts.a_post_u_id==users.u_id).filter(anonForumPosts.a_original_post_id==postID).outerjoin(anonForumPostUpvoted, and_(anonForumPostUpvoted.post_id==anonForumPosts.a_post_id, anonForumPostUpvoted.voter_id==myID)).order_by(anonForumPosts.a_post_id.desc()).distinct().limit(DEFAULT_LIMIT)
            else:
                '''
                get_posts = db.session.query(anonForumPosts.a_post_id, users.u_id, users.firebase_id, anonForumPosts.a_post_cont, anonForumPosts.a_points_count, anonForumPosts.a_reply_count, anonForumPosts.a_date_time, anonForumPosts.a_date_time_edited, anonForumPostUpvoted.points, anonForumPosts.is_pinned).filter(anonForumPosts.a_post_id < lastPostID).filter(anonForumPosts.a_post_u_id==users.u_id).filter(or_(anonForumPosts.a_post_id==postID, anonForumPosts.a_original_post_id==postID)).outerjoin(anonForumPostUpvoted, and_(anonForumPostUpvoted.post_id==anonForumPosts.a_post_id, anonForumPostUpvoted.voter_id==myID)).distinct().order_by(anonForumPosts.a_post_id.desc()).limit(DEFAULT_LIMIT)                
                '''
                get_posts = db.session.query(anonForumPosts.a_post_id, users.u_id, users.firebase_id, anonForumPosts.a_post_cont, anonForumPosts.a_points_count, anonForumPosts.a_reply_count, anonForumPosts.a_date_time, anonForumPosts.a_date_time_edited, anonForumPostUpvoted.points, anonForumPosts.is_pinned).filter(anonForumPosts.deleted==False).filter(anonForumPosts.a_post_u_id==users.u_id).filter(anonForumPosts.a_post_id==postID).outerjoin(anonForumPostUpvoted, and_(anonForumPostUpvoted.post_id==anonForumPosts.a_post_id, anonForumPostUpvoted.voter_id==myID)).distinct().first()
                get_replies = db.session.query(anonForumPosts.a_post_id, users.u_id, users.firebase_id, anonForumPosts.a_post_cont, anonForumPosts.a_points_count, anonForumPosts.a_reply_count, anonForumPosts.a_date_time, anonForumPosts.a_date_time_edited, anonForumPostUpvoted.points, anonForumPosts.is_pinned).filter(anonForumPosts.deleted==False).filter(anonForumPosts.a_post_id < lastPostID).filter(anonForumPosts.a_post_u_id==users.u_id).filter(anonForumPosts.a_original_post_id==postID).outerjoin(anonForumPostUpvoted, and_(anonForumPostUpvoted.post_id==anonForumPosts.a_post_id, anonForumPostUpvoted.voter_id==myID)).order_by(anonForumPosts.a_post_id.desc()).distinct().limit(DEFAULT_LIMIT) 
            if get_posts is not None and get_posts != []:
                result['status'] = 'success' 
                result['message'] = 'Results Found'
                labels = ['postID','userID', 'firebaseID', 'postContent','pointsCount','replyCount','timestamp','timestampEdited','didIVote','isPinned']
                add_all = 'bucket'
                if get_replies is not None and get_replies != []:
                    result['anonPondPosts'] = add_labels(labels, get_posts, add_all, PROF_BUCKET, first_initial=True) + add_labels(labels,get_replies,add_all,PROF_BUCKET, first_initial=True)
                else:
                    result['anonPondPosts'] = add_labels(labels, get_posts, add_all, PROF_BUCKET, first_initial=True)
                if result['anonPondPosts'] == []:
                    result['message'] = 'No results found'
                    if get_replies is not None:
                        if get_replies == []:
                            result['message'] = result['message'] + '. No replies found'
                        else:
                            result['message'] = result['message'] + '. Replies found'
        db.session.close()
        result['status']='success'
    except Exception, e:
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'No Posts Found'}
        pass
    data = json.dumps(result)
    return data

@application.route('/sendAnonPondPost', methods=['POST'])
def sendAnonPondPost():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID', 'postContent', 'postID')):
            myID = request.form['myID']
            postCont = request.form['postContent']
            postID = int(request.form['postID'])
            if postID == 0:
                if all (l in request.form for l in ('longitude','latitude')):
                    postLong = request.form['longitude']
                    postLat = request.form['latitude']
                else:
                    return json.dumps(result)
        else:
            return json.dumps(result)
    else:    
        return json.dumps(result)
    if postID == 0:
        data_entered = anonForumPosts(a_post_u_id = myID, a_post_cont = postCont, a_post_long = postLong, a_post_lat = postLat)
    else:
        data_entered = anonForumPosts(a_post_u_id = myID, a_post_cont = postCont, a_original_post_id = postID) 
    try:
        db.session.add(data_entered)
        db.session.flush()
        result['postID']=data_entered.a_post_id
        db.session.commit()
        if postID not in (0, -1):
            db.session.query(anonForumPosts).filter(anonForumPosts.a_post_id==postID).update({'a_reply_count':anonForumPosts.a_reply_count + 1})
            db.session.commit()
            user_check = db.session.query(users.u_id, users.u_handle, users.device_arn, users.firebase_id).filter(users.u_id==anonForumPosts.a_post_u_id).filter(anonForumPosts.a_post_id==postID).one()
            inPID = inPostID(user_check.firebase_id) # inPostID == parentPostID, do NOT send push.
            if user_check is not None and user_check != {} and int(user_check.u_id) != int(myID):  
                cont = 'Your anon pond post has been replied to: ' + postCont
                subj = 'getMyAnonPondPost'
                notificType = 'A'
                notificUID = user_check.u_id
                inNot = inNotification(user_check.firebase_id)
                if inNot == True:
                    result['notificationSent']=logNotification(notificUID, cont, subj, notificType, notificPostID=postID)
                    firebaseNotification(user_check.firebase_id, cont)
                if user_check.u_id != myID and user_check.device_arn != 0 and inNot==False and inPID!=postID:             
                    result['notificationSent']=logNotification(notificUID, cont, subj, notificType, notificPostID=postID)
                    firebaseNotification(user_check.firebase_id, cont)
                    db.session.commit()
                    badge = db.session.query(notific.notific_id).filter(notific.n_u_id==user_check.u_id).filter(notific.notific_seen==False).count()
                    push(user_check.device_arn, badge, cont, subj)        
        result['status'] = 'success'
        result['message'] = 'Posted'
    except Exception, e:
        db.session.rollback()
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Post not sent'}
        pass
    finally:
        db.session.close()
    data = json.dumps(result)
    return data

@application.route('/getFriendList', methods=['POST'])
def getFriendList():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':        
        if all (k in request.form for k in ('myID','size','lastUserName')):
            userID = request.form['myID']
            lastUserName = request.form['lastUserName']
            if request.form['size'] in ('small','medium','large'):
                size = request.form['size']
            else:
                return json.dumps(result)
            #attribute = request.form['attribute']
        else:
            return json.dumps(result)
    else:    
        return json.dumps(result)
    result = {'status':'error', 'message':'No results found'}
    try:
        chat_subq = db.session.query(users.u_id, users.firebase_id, users.u_handle, users.u_key, chats.send_id, chats.recip_id, chats.messg_cont, chats.date_time, chats.messg_id).filter(users.u_id != userID).filter(and_(or_(chats.send_id==userID, chats.recip_id==userID)),or_(chats.send_id==users.u_id, chats.recip_id==users.u_id)).distinct().order_by(chats.messg_id.desc()).subquery('c')
        chat_messg = db.session.query(chat_subq.c.u_id, chat_subq.c.firebase_id, chat_subq.c.u_handle, chat_subq.c.u_key, chat_subq.c.send_id, chat_subq.c.recip_id, chat_subq.c.messg_cont, chat_subq.c.date_time,friends.friend_status,friends.requester, chat_subq.c.messg_id).filter(or_(chats.send_id==users.u_id, chats.recip_id==users.u_id)).filter(users.u_id==userID).outerjoin(friends, or_(and_(friends.friend_a==chat_subq.c.u_id, friends.friend_b==userID),and_(friends.friend_b==chat_subq.c.u_id,friends.friend_a==userID))).distinct().group_by(chat_subq.c.send_id * chat_subq.c.recip_id).order_by(chat_subq.c.messg_id.desc()).limit(DEFAULT_LIMIT)
        friend_list = db.session.query(users.u_id, users.u_name, users.u_handle, users.firebase_id, friends.friend_a, friends.friend_b, friends.requester, friends.friend_status, users.u_key).filter(users.u_id!=userID).filter(or_(users.u_id==friends.friend_a, users.u_id==friends.friend_b)).filter(or_(friends.friend_a==userID,friends.friend_b==userID)).filter(or_(friends.friend_status == 'F',friends.friend_status == 'P')).filter(users.u_name > lastUserName).distinct().order_by(users.u_name).limit(DEFAULT_LIMIT)
        db.session.close()
        result['status']='success'
        if friend_list.first() is not None and friend_list!=[]:
            result['message']='Friends Found'
            groupsFriends = filter_friends(friend_list,size)
            result['currentFriends']=groupsFriends['currentFriends']
            result['receivedRequests']=groupsFriends['receivedRequests']
            #result['sentRequests']=groupsFriends['sentRequests']
            '''
            for a in result['currentFriends']:
                print a['key']
                print '\n'
            '''
        else:
            result['message']='No Friends Found'
            result['currentFriends']=[]
            result['receivedRequests']=[]
        if chat_messg is not None and chat_messg !=[]:
            label = ['userID','firebaseID','userHandle','key','senderID','recipID','messageContent','timestamp','isFriend','requester','messgID']
            result['chats']=add_labels(label, chat_messg,'bucket',PROF_BUCKET, keySize=size)
            for c in result['chats']:
                #print c['messageContent']
                if c['isFriend']=='B':# and c['requester'] == userID:
                    result['chats'].remove(c)
        else:
            result['chats']=[]
    except Exception, e:
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Friend info not retrieved'}
        pass
    data = json.dumps(result)
    return data

@application.route('/searchFriend', methods=['POST'])
def searchFriend():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('criteria','myID','size','lastUserID')): 
            criteria = request.form['criteria']
            myID = request.form['myID']
            lastUserID = request.form['lastUserID']
            if request.form['size'] in ('small','medium','large'):
                size = request.form['size']
            else:
                return json.dumps(result)
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    #handle
    search_term = '%' + criteria + '%'
    result = {'status':'error', 'message':'No results found'}
    try:
        search_check = db.session.query(users.u_id,users.u_name, users.u_handle, users.firebase_id, users.u_key, friends.friend_status).filter(or_(users.u_handle.like(search_term), users.u_name.like(search_term))).filter(users.u_id != myID).filter(users.u_name > lastUserID).filter(users.u_private == False).outerjoin(friends, or_(and_(friends.friend_a==users.u_id, friends.friend_b==myID),and_(friends.friend_b==users.u_id,friends.friend_a==myID))).order_by(users.u_id.asc()).distinct().limit(DEFAULT_LIMIT) #might have issues if a lot of blocked? probably not though
        block_check = db.session.query(friends.friend_a, friends.friend_b, friends.requester).filter(or_(friends.friend_a == myID, friends.friend_b == myID)).filter(friends.friend_status=='B').distinct().all()  
        db.session.close()
        if search_check.first() is not None:
            result['status'] = 'success'      
            if search_check == []:
                result['message'] = 'No results found'
            else:
                labels =['userID','userName','userHandle','firebaseID','key','isFriend']
                add_all = 'bucket'
                block_update = []
                if block_check != []:
                    search_list = []
                    for f in search_check:
                        for b in block_check:
                            if not ((f.u_id == b.friend_a or f.u_id == b.friend_b) and b.requester != myID):
                                if f.friend_status == 'B' and b.requester == myID:
                                    block_update.append(f.u_id)
                                search_list.append(f)
                    result['users']= add_labels(labels,search_list,add_all,PROF_BUCKET,keySize=size)
                    for b in block_update:
                        for r in result['users']:
                            if b==r['userID'] and r['isFriend']=='B':
                                r['isFriend']='BB'
                    if search_list == None:
                        result['message'] = 'No Results Found'
                else:
                    result['users']= add_labels(labels,search_check,add_all, PROF_BUCKET, True,keySize=size)
                    result['message'] = 'Results Found'              
        else:
            result['status'] = 'success'
            result['message'] = 'No Results Found'
    except Exception, e:
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Users not found'}
        pass
    data = json.dumps(result)
    return data

@application.route('/getCurrentFriends', methods=['POST'])
def getCurrentFriends():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','size','lastUserID','poolID')): 
            poolID = int(request.form['poolID'])
            myID = int(request.form['myID'])
            lastUserID = int(request.form['lastUserID'])
            if request.form['size'] in ('small','medium','large'):
                size = request.form['size']
            else:
                return json.dumps(result)
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    result = {'status':'error', 'message':'No results found'}
    try:
        search_check = db.session.query(users.u_id,users.u_name, users.u_handle, users.firebase_id, users.u_key, friends.friend_status).filter(or_(users.u_id==friends.friend_a, users.u_id==friends.friend_b)).filter(or_(friends.friend_a==myID, friends.friend_b==myID)).filter(users.u_id != myID).filter(friends.friend_status=='F')
        if poolID !=0:
            pool_sub = db.session.query(groupMembers.member_id).filter(groupMembers.group_id==poolID).filter(groupMembers.member_role.in_(('O','H','M'))).distinct().subquery()
            search_check = search_check.filter(~users.u_id.in_(pool_sub))
        if lastUserID != 0:
            search_check = search_check.filter(users.u_name > lastUserID)
        search_check = search_check.order_by(users.u_name).distinct().limit(DEFAULT_LIMIT)
        result['status']='success'
        if search_check is not None and search_check !=[]:
            groupsFriends = filter_friends(search_check,size)
            result['currentFriends']=groupsFriends['currentFriends']
            if result['currentFriends'] != []:
                result['message']='Friends Found'
            else:   
                result['message']='No Friends Found'
        else:
            result['message']='No Friends Found'
            result['currentFriends']=[]
        db.session.close()
    except Exception, e:
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Friend info not retrieved'}
        pass
    return json.dumps(result)
    
@application.route('/sendFriendRequest', methods=['POST']) #another table with just requests?
def sendFriendRequest():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','userID','action')):
            requester_ID = request.form['myID']
            friend_ID = request.form['userID']
            action = request.form['action']
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    try:
        #push
        #see if friend request has been made already
        friend_check = db.session.query(friends).filter(or_(and_(friends.friend_a==requester_ID, friends.friend_b==friend_ID),and_(friends.friend_a==friend_ID, friends.friend_b==requester_ID))).first() #first? or all? case to handle that?
        #if friends > 1 ? should never happen error
        if friend_check is not None and friend_check != []:
            f_status=friend_check.friend_status
            f_id = friend_check.friend_id
            req = True if(friend_check.requester == requester_ID) else False
            if action == 'block' and f_status != 'B':
                db.session.query(friends).filter(friends.friend_id==f_id).update({'friend_status':'B','requester':requester_ID})
                db.session.commit()
                result['status']='success'
                result['message']='Blocked'
            elif f_status == 'F': #friends already
                if action == 'unfriend': #unfriend
                    db.session.query(friends).filter(friends.friend_id==f_id).update({'friend_status':'U'})
                    db.session.commit()
                    result['status']='success'
                    result['message']='Friend un-friended'                  
            elif f_status == 'P': #pending
                if req and action == 'withdraw':
                    db.session.query(friends).filter(friends.friend_id==f_id).update({'friend_status':'W'})
                    db.session.commit()
                    result['status']='success'
                    result['message']='Friend request withdrawn'
                elif not req:
                    if action in ('accept','request'): #accept
                        db.session.query(friends).filter(friends.friend_id==f_id).update({'friend_status':'F'})
                        db.session.commit()
                        friend_name=db.session.query(users.u_name).filter(users.u_id==friend_ID).one()
                        result['fullName']=friend_name.u_name
                        result['status']='success'
                        result['message']='Friend request accepted'        
                        #update status to F
                    elif action == 'deny': #deny
                        db.session.query(friends).filter(friends.friend_id==f_id).update({'friend_status':'D'})
                        db.session.commit()
                        result['status']='success'
                        result['message']='Friend request denied'
                        #update status to D
            elif f_status == 'B' and req:
                if action == 'unblock': 
                    db.session.query(friends).filter(friends.friend_id==f_id).update({'friend_status':'N'})                    
                    db.session.commit()
                    result['status']='success'
                    result['message']='Unblocked'            
            elif action == 'request': #anything else, update as to a new request
                db.session.query(friends).filter(friends.friend_id==f_id).update({'friend_status':'P','requester':requester_ID})
                db.session.commit()
                result['status']='success'
                result['message']='Friend request sent'
                user_check = db.session.query(users.device_arn, users.firebase_id).filter(users.u_id==friend_ID).one()
                my_check = db.session.query(users.u_handle).filter(users.u_id==requester_ID).one()
                subj = 'getFriendList'
                cont = '@' + my_check.u_handle + ' has sent you a friend request :)'
                notificType = 'D'
                notificUID = friend_ID
                inNot = inNotification(user_check.firebase_id)
                if inNot == True:
                    result['notificationSent']=logNotification(notificUID, cont, subj, notificType, notificOtherID=requester_ID)
                    firebaseNotification(user_check.firebase_id, cont)
                if user_check is not None and user_check != []:
                    if user_check.device_arn != 0 and not inNotification(user_check.firebase_id):  
                        result['notificationSent']=logNotification(notificUID, cont, subj, notificType, notificOtherID=requester_ID)
                        firebaseNotification(user_check.firebase_id, cont)
                        db.session.commit()
                        badge = db.session.query(notific.notific_id).filter(notific.n_u_id==friend_ID).filter(notific.notific_seen==False).count()               
                        result['push']=push(user_check.device_arn, badge, cont, subj)
            else:
                result['status']='error'
                result['message']='Invalid Request'
        elif action == 'block':
            block_entered = friends(requester_ID, friend_ID, requester_ID, 'B')
            db.session.add(block_entered)
            db.session.commit()
            result['status'] = 'success'
            result['message'] = 'User blocked'
        elif action == 'request': #new request
            friend_entered = friends(requester_ID, friend_ID, requester_ID, 'P')
            db.session.add(friend_entered)
            db.session.commit()
            result['status']='success'
            result['message']='Friend request sent'
            user_check = db.session.query(users.device_arn, users.firebase_id).filter(users.u_id==friend_ID).one()
            my_check = db.session.query(users.u_handle).filter(users.u_id==requester_ID).one()
            subj='getFriendList'
            cont = '@' + my_check.u_handle + ' has sent you a friend request :)'
            notificType = 'D'
            notificUID = friend_ID
            inNot = inNotification(user_check.firebase_id)
            if inNot == True:
                result['notificationSent']=logNotification(notificUID, cont, subj, notificType, notificOtherID=requester_ID)
                firebaseNotification(user_check.firebase_id, cont)
            if user_check is not None and user_check != []:
                if user_check.device_arn != 0 and inNot==False:
                    result['notificationSent']=logNotification(notificUID, cont, subj, notificType, notificOtherID=requester_ID)
                    firebaseNotification(user_check.firebase_id, cont)
                    db.session.commit()
                    badge = db.session.query(notific.notific_id).filter(notific.n_u_id==friend_ID).filter(notific.notific_seen==False).count()
                    result['push']=push(user_check.device_arn, badge, cont, subj)
        else:
            result['status']='error'
            result['message']='Invalid Request'
    except Exception, e:
        db.session.rollback()
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Request not sent'}
        pass
    finally:
        db.session.close()
    data = json.dumps(result)
    return data

@application.route('/getUserProfile', methods=['POST'])
def getUserProfile():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','userID','limitInfo','lastPoolName')):
            userID = request.form['myID']
            otherID = request.form['userID']
            limitInfo = request.form['limitInfo']
            lastGroupName = request.form['lastPoolName']
            userPicSize='small'
            groupPicSize='small'
            if limitInfo == 'no' and all (j in request.form for j in ('userPicSize','poolPicSize')):
                if request.form['poolPicSize']:
                    groupPicSize = request.form['poolPicSize']  
                else:
                    return json.dumps(result)              
                if request.form['userPicSize'] in ('small','medium','large'):
                    userPicSize = request.form['userPicSize']
                else:
                    return json.dumps(result)
            elif limitInfo is 'no':
                return json.dumps(result)
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    if userID == otherID:
        return json.dumps(result)
    try:
        userProf_check = db.session.query(users.u_key, users.u_name, users.u_handle, users.firebase_id, users.u_description, users.u_stipend_points, users.u_personal_points).filter(users.u_id==otherID).first()
        if userProf_check is not None and userProf_check != []:
            result['status'] = 'success'
            result['message'] = 'successfully retrieved profile information.' 
            if limitInfo == 'no':
                result['key'] = userProf_check.u_key+'_'+userPicSize
                result['bucket'] = PROF_BUCKET
                other_groups = db.session.query(groupDetails.group_id, groupDetails.group_handle,groupDetails.group_name, groupDetails.group_key,groupDetails.group_city, groupDetails.group_description).filter(groupDetails.group_active=='Y').filter(groupMembers.member_id==otherID).filter(groupDetails.group_id==groupMembers.group_id).filter(groupMembers.member_role.in_(('M','H','O'))).filter(groupDetails.group_on_profile == True).filter(groupDetails.group_name > lastGroupName).order_by(groupDetails.group_name.asc()).limit(DEFAULT_LIMIT)
            else:
                other_groups = db.session.query(groupDetails.group_id, groupDetails.group_handle,groupDetails.group_name, groupDetails.group_city, groupDetails.group_description).filter(groupMembers.member_id==otherID).filter(groupDetails.group_id==groupMembers.group_id).filter(groupMembers.member_role.in_(('M','H','O'))).filter(groupDetails.group_on_profile == True).filter(groupDetails.group_name > lastGroupName).order_by(groupDetails.group_name.asc()).limit(DEFAULT_LIMIT)
            result['userHandle'] = userProf_check.u_handle
            result['userDescription'] = userProf_check.u_description
            result['pointsCount'] = userProf_check.u_personal_points
            result['firebaseID']=userProf_check.firebase_id
            is_Friends = db.session.query(friends).filter(or_(friends.friend_a==userID, friends.friend_b==userID)).filter(or_(friends.friend_a==otherID,friends.friend_b==otherID)).first()          
            db.session.close()
            result['isFriend'] = 'N'
            if is_Friends is not None and is_Friends != []:
                if is_Friends.friend_status == 'F':
                    result['isFriend']= 'F'
                elif is_Friends.friend_status == 'P':
                    if is_Friends.requester == userID:
                        result['isFriend']='S' #sent
                    elif is_Friends.requester == otherID:
                        result['isFriend']='R' #requested
                elif is_Friends.friend_status == 'B': #blocked #B=they blocked locked me BB=I blocked them
                    if is_Friends.requester == userID:
                        result['isFriend']='BB' #if B don't send 
                    else:
                        result['isFriend']='B'
                        result['key'] = 'default_'+userPicSize
                        result['userName'] = 'default'
            if other_groups is not None and other_groups != []:
                add_all = 'poolBucket'
                if limitInfo == 'no':
                    group_labels = ['poolID','poolHandle','poolName','poolKey','city','poolDescription']
                    result['pools'] = add_labels(group_labels, other_groups, add_all, GROUP_BUCKET, keySize= groupPicSize)
                else:
                    group_labels = ['poolID','poolHandle','poolName','city','poolDescription']
                    result['pools'] = add_labels(group_labels, other_groups)
            else: 
                result['message'] = 'successfully retrieved profile information. No groups found' 
            if result['isFriend'] != 'F':
                result['userName'] = first_and_initial(userProf_check.u_name)
            elif result['isFriend'] != 'B':
                result['userName'] = userProf_check.u_name
        else:
            result = {'status':'error', 'message':'Profile not found'}
            db.session.close()
    except Exception, e:
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Profile not found'}
        pass
    data = json.dumps(result)
    return data

@application.route('/getChat', methods=['POST'])
def getChat():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','userID','lastChatID')):
            myID = request.form['myID']
            otherID = request.form['userID']
            lastChatID = request.form['lastChatID']
        elif 'userID' not in request.form and all (k in request.form for k in ('myID','lastChatID')):
            myID = request.form['myID']
            otherID = myID
            lastChatID = request.form['lastChatID']
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    result = {'status':'error', 'message':'No Chats Available'}  
    try:
        chat_check = db.session.query(chats.messg_id, chats.send_id, chats.messg_cont, chats.date_time).filter(or_(myID==chats.send_id,myID==chats.recip_id)).filter(or_(otherID==chats.send_id,otherID==chats.recip_id)).filter(chats.messg_id > lastChatID).order_by(chats.date_time.desc()).limit(DEFAULT_LIMIT)
        user_check = db.session.query(users.u_handle).filter(users.u_id==otherID).first()
        db.session.close()
        if chat_check is not None:
            if chat_check != []:
                result['status'] = 'success'
                result['userHandle'] = user_check.u_handle #their handle
                if chat_check == []:
                    result['message'] = 'No Chats Found'
                else:
                    result['message'] = 'Chats Found'
                    label = ['chatID', 'userID', 'chatMessage','timestamp'] #senderID
                    result['chats'] = add_labels(label, chat_check)
            else:
                result['status'] = 'success'
                result['message'] = 'No Chats'
                result['chatID']=-1
        else:
            result['status'] = 'error'
            result['message'] = 'Error Retrieving Chats'
    except Exception, e:
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Chat not found'}
    return json.dumps(result)

@application.route('/sendChat', methods=['POST'])
def sendChat():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','userID','chatMessage')):
            sendID = request.form['myID']
            recipID = request.form['userID']
            mess = request.form['chatMessage']
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    if sendID==recipID:
        return json.dumps(result)
    data_entered = chats(sendID, recipID, mess)
    try:
        db.session.add(data_entered)
        db.session.commit()
        result['status'] = 'success'
        result['message'] = 'Chat Sent'
        chat_check = db.session.query(chats.messg_id).filter(chats.send_id==sendID).filter(chats.recip_id==recipID).filter(chats.messg_cont == mess).order_by(chats.messg_id.desc()).first()   
        if chat_check is not None and chat_check != []:
            result['chatID']=chat_check.messg_id
        else:
            result['status']='error'
            result['message']= 'Chat not sent'
        recip_check = db.session.query(users.u_handle, users.device_arn, users.firebase_id).filter(users.u_id==recipID).one()
        send_check = db.session.query(users.u_handle).filter(users.u_id==sendID).one()        
        subj = 'getFriendList'
        cont =  '@' + send_check.u_handle + ': ' + mess
        notificType = 'C'
        notificUID = recipID      
        if recip_check is not None and recip_check != []:
            #p = Pool(processes=1)              # Start a worker processes.
            #p.apply_async(notifyChat, [recip_check.device_arn, sendID, recipID, recip_check.firebase_id, subj, cont, notificType, notificUID])
            #p.close()
            if recip_check.device_arn != 0:
                inNot = inNotification(recip_check.firebase_id)
                if inNot==True:
                   result['notificationSent']=logNotification(notificUID, cont, subj, notificType, notificOtherID=sendID)
                   firebaseNotification(recip_check.firebase_id, cont) 
                if not checkInChat(sendID, recipID, recip_check.firebase_id): #checkInChat -> true if in chat, false if not. 
                    if inNot == False:
                        result['notificationSent']=logNotification(notificUID, cont, subj, notificType, notificOtherID=sendID)
                        firebaseNotification(recip_check.firebase_id, cont)
                        db.session.commit()
                        badge = db.session.query(notific.notific_id).filter(notific.n_u_id==recipID).filter(notific.notific_seen==False).count()
                        result['push'] = push(recip_check.device_arn, badge, cont, subj)
                    else:
                        result['push']='inNotification'
                else:
                    result['notificationSent']='inChat'
                    #result['sendID']=sendID
                    #result['recipID']=recipID
                    #result['fbID']=recip_check.firebase_id
            else:
                result['test']=recip_check.device_arn
        else:
            result['test2']='no recip_check ' + recipID
    except Exception, e:
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:   
            result = {'status':'error', 'message':'Chat not sent'}    
        db.session.rollback()
        pass    
    finally:
        db.session.close()
    data = json.dumps(result)
    return data

@application.route('/getMyProfile', methods=['POST'])
def getMyProfile():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','size')): 
            userID = request.form['myID']
            if request.form['size'] in ('small','medium','large'):
                size = request.form['size']
            else:
                return json.dumps(result)
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    try:
        userProf_check = db.session.query(users.u_name, users.u_email, users.u_handle, users.u_key, users.firebase_id, users.u_dob, users.u_description, users.u_phone, users.u_personal_points, users.u_stipend_points).filter(users.u_id==userID).first()
        if (userProf_check is not None) and (userProf_check != []):
                   
            result['status'] = 'success'
            result['message'] = 'successfully retrieved profile information'            
            result['key'] = userProf_check.u_key+'_'+size
            result['bucket'] = PROF_BUCKET
            result['myName'] = userProf_check.u_name
            result['myHandle'] = userProf_check.u_handle
            result['myDescription'] = userProf_check.u_description
            result['myEmail'] = userProf_check.u_email
            result['firebaseID']= userProf_check.firebase_id
            '''
            if (datetime.now() - userProf_check.last_stipend_date > DEFAULT_STIPEND_TIME):
                    userProf_check.stipend_points = DEFAULT_STIPEND
                    db.session.commit()
            '''
            result['weeklyPoints'] = userProf_check.u_stipend_points
            result['myPoints'] = userProf_check.u_personal_points
            if (userProf_check.u_dob == date(1901,1,1) or userProf_check.u_dob is None):
                result['myBirthday'] = 'Need to set'
            else:
                result['myBirthday'] = json_serial(datetime.combine(userProf_check.u_dob,time()))
            if (userProf_check.u_phone == 'N/A' or userProf_check.u_phone == ''):
                result['myPhoneNumber'] = 'Need to set'
            else:
                result['myPhoneNumber'] = format_phone(userProf_check.u_phone)
    except Exception, e:
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Profile info not retrieved'}    
        pass
    finally:
        db.session.close()
    data = json.dumps(result)
    return data

@application.route('/updateMyProfile', methods=['POST'])
def updateMyProfile():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','action')):
            userID = request.form['myID']
            action = request.form['action'] #only update
            if action =='edit' and all (l in request.form for l in ('myName','myHandle','myDescription','myBirthday','myPhoneNumber','myEmail','isPicSet')):
                newName = request.form['myName']
                newHandle = request.form['myHandle']
                newDescription = request.form['myDescription']
                if request.form['myBirthday'] == 'No birthday set':
                    newBirthday = date(1901,1,1)
                else:
                    try:
                        newBirthday = datetime.strptime(request.form['myBirthday'],"%b %d, %Y")
                    except:
                        return json.dumps({'status':'error','message':'Invalid Date'})
                newPhoneNumber = validate_phone(request.form['myPhoneNumber'])
                newEmail = request.form['myEmail'] #check
                picSet = request.form['isPicSet'] #yes, no, no_change
                #myPass = hash_password(request.form['myPassword'].encode('utf-8'))
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    try:
        if action=='edit':
            email_check = db.session.query(users.u_email).filter(users.u_id != userID).filter(users.u_email==newEmail).all()
            handle_check = db.session.query(users.u_handle).filter(users.u_id != userID).filter(users.u_handle==newHandle).all()
            if email_check is not None and email_check !=[]:
                result = {'status':'error','message':'eMail address already exists'}
            elif handle_check is not None and email_check !=[]:
                result = {'status':'error','message':'handle already exists'}
            else:        
                user_check = db.session.query(users.u_key).filter(users.u_id==userID).one()
                if user_check is not None and user_check !=[]:
                    if picSet == 'yes':
                        if user_check.u_key != 'default':
                            k_1, k_2 =user_check.u_key.split('_',1)
                            if '_' in k_2:
                                k_2,k_3=k_2.split('_')
                                k_2 = str(int(k_2)+1)
                                key=k_1+'_'+k_2+'_'+k_3
                            else:
                                key=k_1+'_0_'+k_2
                        else:
                            key=str(userID)+'_userProfPic'
                        result['smallKey'] = key + '_small'
                        result['mediumKey'] = key + '_medium'
                        result['largeKey'] = key + '_large'
                        result['key'] = key
                    elif picSet == 'no':
                        result['smallKey'] = 'default_small'
                        result['mediumKey'] = 'default_medium'
                        result['largeKey'] = 'default_large'
                        result['key']='default'
                    else: #picSet is anything else, so no change
                        result['key']=user_check.u_key
                    result['bucket'] = PROF_BUCKET
                    db.session.query(users).filter(users.u_id==userID).update({'u_name':newName,'u_handle':newHandle,'u_description':newDescription,'u_dob':newBirthday,'u_phone':newPhoneNumber,'u_email':newEmail,'u_key':result['key']})
                    result['status'] = 'success'
                    result['message'] = 'successfully updated profile information'
                else:
                    result = {'status':'error','message':'Invalid request'}                    
                #else:   
            #else:
            db.session.commit()
            result['status']='success'
    except Exception, e:
        db.session.rollback()
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Profile not updated'}        
        pass
    finally:
        db.session.close()
    data = json.dumps(result)
    return data

@application.route('/getMyPoolPost', methods=['POST'])
def getMyPoolPost():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','size')):
            myID = request.form['myID']
            if request.form['size'] in ('small','medium','large'):
                size = request.form['size']
            else:
                return json.dumps(result)
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    try:
        subq = db.session.query(groupPosts.original_post_id).filter(groupPosts.post_u_id==myID).filter(groupPosts.original_post_id!=0).distinct().subquery()
        get_my_posts = db.session.query(groupPosts.group_post_id, users.u_id, users.u_name, users.u_handle, users.firebase_id, users.u_key, groupPosts.group_post_cont, groupMembers.member_role, groupDetails.group_handle, groupPosts.points_count, groupPosts.reply_count, groupPosts.date_time, groupPosts.date_time_edited, groupPostUpvoted.points, groupPosts.original_post_id, groupPosts.group_id, groupPosts.is_pinned).filter(groupPosts.deleted==False).filter(groupPosts.post_u_id==users.u_id).filter(groupMembers.member_id == users.u_id).filter(groupMembers.group_id==groupPosts.group_id).filter(groupDetails.group_id==groupPosts.group_id).filter(or_(and_(groupPosts.original_post_id == 0,groupPosts.post_u_id==myID), groupPosts.group_post_id.in_(subq))).outerjoin(groupPostUpvoted, and_(groupPostUpvoted.post_id==groupPosts.group_post_id, groupPostUpvoted.voter_id==myID)).order_by(groupPosts.group_post_id.desc()).distinct().all()
        '''
        subq = db.session.query(groupPosts.group_post_id).filter(groupPosts.post_u_id == myID).filter(groupPosts.original_post_id != 0).distinct().subquery()
        get_my_posts = db.session.query(groupPosts.group_post_id, users.u_id, users.u_name, users.u_handle, users.firebase_id, users.u_key, groupPosts.group_post_cont, groupMembers.member_role, groupDetails.group_handle, groupPosts.points_count, groupPosts.reply_count, groupPosts.date_time, groupPosts.date_time_edited, groupPostUpvoted.points, groupPosts.original_post_id, groupPosts.group_id, groupPosts.is_pinned).filter(groupPosts.post_u_id==users.u_id).filter(groupMembers.member_id == users.u_id).filter(groupMembers.group_id==groupPosts.group_id).filter(groupPosts.post_u_id==myID).filter(groupDetails.group_id==groupPosts.group_id).filter(or_(groupPosts.original_post_id==0, groupPosts.group_post_id.in_(subq))).outerjoin(groupPostUpvoted, and_(groupPostUpvoted.post_id==groupPosts.group_post_id, groupPostUpvoted.voter_id==myID)).distinct().all()
        '''
        if get_my_posts is not None:    
            result['status'] = 'success'        
            if get_my_posts == []:
                result['message'] = 'No results found'
            else:
                result['message'] = 'Results Found'
                labels = ['postID','userID','userName','userHandle','firebaseID','key','postContent','memberRole', 'poolHandle', 'pointsCount','replyCount','timestamp','timestampEdited','didIVote','cellType','poolID','isPinned']
                add_all = 'bucket'
                result['poolPosts'] = add_labels(labels,get_my_posts,add_all,PROF_BUCKET,keySize=size)
    except Exception, e:
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Posts not found'}    
        pass
    data = json.dumps(result)
    return data

@application.route('/getPoolList', methods=['POST'])
def getPoolList():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','size', 'lastPoolName')):
            user_id = request.form['myID']
            lastGroupName = request.form['lastPoolName']
            if request.form['size'] in ('small','medium','large'):
                size = request.form['size']
            else:
                return json.dumps(result)
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)    
    try:
        group_list = db.session.query(users.u_id, users.u_name, users.u_handle, users.u_key, groupDetails.group_id, groupDetails.group_name, groupDetails.group_handle, groupDetails.group_key, groupMembers.member_role, groupMembers.last_post_seen, groupMembers.last_host_post_seen, groupMembers.last_event_seen).filter(groupDetails.group_active=='Y').filter(users.u_id==user_id).filter(groupMembers.member_id==users.u_id).filter(groupMembers.group_id==groupDetails.group_id).filter(groupMembers.member_role != "B").filter(groupDetails.group_name > lastGroupName).order_by(groupDetails.group_name.asc()).distinct().limit(DEFAULT_LIMIT)
        num_host_posts={}
        num_posts = {}
        num_events = {}
        for k in group_list: #number new group Posts, new event, new host post
            if k.member_role in ('M','H','O'):
                new_host_posts = db.session.query(groupPosts.group_post_id).filter(k.group_id == groupPosts.group_id).filter(groupPosts.original_post_id==0).filter(groupPosts.group_post_id > (0 if (k.last_host_post_seen is None) else k.last_host_post_seen)).count()
                new_posts= db.session.query(groupPosts.group_post_id).filter(k.group_id == groupPosts.group_id).filter(groupPosts.original_post_id==-1).filter(groupPosts.group_post_id > (0 if (k.last_post_seen is None) else k.last_post_seen)).count()
                new_events = db.session.query(groupEventDetails.event_id).filter(k.group_id == groupEventDetails.group_id).filter(groupEventDetails.deleted == False).filter(groupEventDetails.event_id > (0 if (k.last_event_seen is None) else k.last_event_seen)).count()
                num_host_posts[k.group_id]=new_host_posts if new_host_posts is not None else 0
                num_posts[k.group_id]=new_posts if new_posts is not None else 0
                num_events[k.group_id]=new_events if new_events is not None else 0
        groupsFriends = filter_groups(group_list, num_host_posts, num_posts, num_events, keySize=size) 
        if groupsFriends is not None and groupsFriends != {}: 
            result['status']='success'
            result['message']='Pool Found'       
            result['receivedRequests'] = groupsFriends['receivedRequests']
            result['currentPools'] = groupsFriends['currentGroups']   
            '''              
            for a in groupsFriends:
                result[a]=groupsFriends[a]
            '''
        else:
            result['message'] = 'No groups found'
            result['status']='success'
    except Exception, e:
        db.session.close()
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Groups not found'}
        pass
    finally:
        db.session.close()
    data = json.dumps(result)
    return data

@application.route('/searchPool', methods=['POST'])
def searchPool():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','criteria','longitude','latitude','isExact','poolSize','category','size')):
            user_id = request.form['myID']
            criteria = request.form['criteria']
            searchLong = float(request.form['longitude'])
            searchLat = float(request.form['latitude'])
            groupSize = request.form['poolSize'] #small <15 medium 15-50 large 50+ any
            if groupSize == 'small':
                minSize=0
                maxSize=15
            elif groupSize == 'medium':
                minSize=15
                maxSize=50
            elif groupSize == 'large':
                minSize=50
                maxSize= None
            elif groupSize == 'any':
                minSize= 0
                maxSize= None
            else:
                return json.dumps(result)
            isExact = request.form['isExact']
            if isExact == 'yes':
                radius = 5
            else:
                radius = 10
            category = request.form['category']
            if request.form['size'] in ('small','medium','large'):
                size = request.form['size']
            else:
                return json.dumps(result)
            if 'lastPoolName' in request.form:
                lastGroupName = request.form['lastPoolName']
            else:
                lastGroupName = '0'
            if 'pageNumber' in request.form:
                pageNum=int(request.form['pageNumber'])
            else:
                pageNum =0
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    minLong, maxLong, minLat, maxLat = getMinMaxLongLat(searchLong, searchLat, radius) #minLong, maxLong, minLat, maxLat
    #distance
    if criteria == '':
        criteria = '%'
    else:
        criteria = '%'+criteria+'%'
    try: #search by size
        if criteria == '%':
            group_search = db.session.query(groupDetails.group_id, groupDetails.group_handle, groupDetails.group_name, groupDetails.group_num_members, groupDetails.group_key, groupDetails.group_city, groupDetails.group_description, groupDetails.group_invite_only, groupMembers.member_role, groupDetails.group_readable).filter(groupDetails.group_active=='Y').filter(groupDetails.group_long >= minLong).filter(groupDetails.group_long <= maxLong).filter(groupDetails.group_lat >= minLat).filter(groupDetails.group_lat <= maxLat).filter(groupDetails.group_searchable == True).filter(groupDetails.group_num_members >= minSize).outerjoin(groupMembers, and_(groupMembers.group_id==groupDetails.group_id, groupMembers.member_id==user_id)).order_by(groupDetails.group_num_members.desc()).filter(groupDetails.group_name > lastGroupName).distinct().limit(DEFAULT_LIMIT).offset(DEFAULT_LIMIT * pageNum)
        elif groupSize in ('large','any'):
            if category == 'all':
                group_search = db.session.query(groupDetails.group_id, groupDetails.group_handle, groupDetails.group_name, groupDetails.group_num_members, groupDetails.group_key, groupDetails.group_city, groupDetails.group_description, groupDetails.group_invite_only, groupMembers.member_role, groupDetails.group_readable).filter(groupDetails.group_active=='Y').filter(groupDetails.group_long >= minLong).filter(groupDetails.group_long <= maxLong).filter(groupDetails.group_lat >= minLat).filter(groupDetails.group_lat <= maxLat).filter(groupDetails.group_searchable == True).filter(groupDetails.group_num_members >= minSize).filter(or_(groupDetails.group_handle.like(criteria),groupDetails.group_name.like(criteria),groupDetails.group_description.like(criteria))).outerjoin(groupMembers, and_(groupMembers.group_id==groupDetails.group_id, groupMembers.member_id==user_id)).filter(groupDetails.group_name > lastGroupName).order_by(groupDetails.group_name.asc()).distinct().limit(DEFAULT_LIMIT).offset(DEFAULT_LIMIT * pageNum)
            else:
                group_search = db.session.query(groupDetails.group_id, groupDetails.group_handle, groupDetails.group_name, groupDetails.group_num_members, groupDetails.group_key, groupDetails.group_city, groupDetails.group_description, groupDetails.group_invite_only, groupMembers.member_role, groupDetails.group_readable).filter(groupDetails.group_active=='Y').filter(groupDetails.group_long >= minLong).filter(groupDetails.group_long <= maxLong).filter(groupDetails.group_lat >= minLat).filter(groupDetails.group_lat <= maxLat).filter(groupDetails.group_searchable == True).filter(groupDetails.group_num_members >= minSize).filter(groupDetails.group_category ==category).filter(or_(groupDetails.group_handle.like(criteria),groupDetails.group_name.like(criteria),groupDetails.group_description.like(criteria))).outerjoin(groupMembers, and_(groupMembers.group_id==groupDetails.group_id, groupMembers.member_id==user_id)).order_by(groupDetails.group_name.asc()).filter(groupDetails.group_name > lastGroupName).distinct().limit(DEFAULT_LIMIT).offset(DEFAULT_LIMIT * pageNum)
        else: #small or medium
            if category == 'all':
                group_search = db.session.query(groupDetails.group_id, groupDetails.group_handle, groupDetails.group_name, groupDetails.group_num_members, groupDetails.group_key, groupDetails.group_city, groupDetails.group_description, groupDetails.group_invite_only, groupMembers.member_role, groupDetails.group_readable).filter(groupDetails.group_active=='Y').filter(groupDetails.group_long >= minLong).filter(groupDetails.group_long <= maxLong).filter(groupDetails.group_lat >= minLat).filter(groupDetails.group_lat <= maxLat).filter(groupDetails.group_searchable == True).filter(groupDetails.group_num_members >= minSize).filter(groupDetails.group_num_members <= maxSize).filter(or_(groupDetails.group_handle.like(criteria),groupDetails.group_name.like(criteria),groupDetails.group_description.like(criteria))).outerjoin(groupMembers, and_(groupMembers.group_id==groupDetails.group_id, groupMembers.member_id==user_id)).order_by(groupDetails.group_name).filter(groupDetails.group_name > lastGroupName).distinct().limit(DEFAULT_LIMIT).offset(DEFAULT_LIMIT * pageNum)
            else:
                group_search = db.session.query(groupDetails.group_id, groupDetails.group_handle, groupDetails.group_name, groupDetails.group_num_members, groupDetails.group_key, groupDetails.group_city, groupDetails.group_description, groupDetails.group_invite_only, groupMembers.member_role, groupDetails.group_readable).filter(groupDetails.group_active=='Y').filter(groupDetails.group_long >= minLong).filter(groupDetails.group_long <= maxLong).filter(groupDetails.group_lat >= minLat).filter(groupDetails.group_lat <= maxLat).filter(groupDetails.group_searchable == True).filter(groupDetails.group_num_members >= minSize).filter(groupDetails.group_num_members <= maxSize).filter(groupDetails.group_category == category).filter(or_(groupDetails.group_handle.like(criteria),groupDetails.group_name.like(criteria),groupDetails.group_description.like(criteria))).outerjoin(groupMembers, and_(groupMembers.group_id==groupDetails.group_id, groupMembers.member_id==user_id)).filter(groupDetails.group_name > lastGroupName).order_by(groupDetails.group_name).distinct().limit(DEFAULT_LIMIT).offset(DEFAULT_LIMIT * pageNum)
        '''
        count is not working right. need to figure a way to append them. maybe iterate through or add something? second query, not sure if there's a way to ensure accuracy

        '''
        if group_search.first() is not None and group_search !=[]:        
            blocked_search = db.session.query(groupDetails.group_id).filter(groupMembers.member_id == user_id).filter(groupMembers.group_id==groupDetails.group_id).filter(groupMembers.member_role=='B').all()
            label = ['poolID','poolHandle','poolName','membersCount','poolKey','city','poolDescription','inviteOnly','memberRole','readable','upcomingChaptersCount']             
            if blocked_search != []:
                group_list = []
                for k in group_search:
                    bl = True
                    temp2=[]
                    for i in blocked_search:
                        if k.group_id == i.group_id:
                            bl = False
                    if (bl): #append upcoming events count
                        for j in k:
                            temp2.append(j)                  
                        count = (db.session.query(groupEventDetails.event_id).filter(groupEventDetails.group_id == k.group_id).filter(groupEventDetails.deleted == False).filter(groupEventDetails.event_start > datetime.now()).distinct().count())
                        temp2.append(count)
                        group_list.append(temp2)
            else:
                #group_list=group_search
                temp=[]
                for k in group_search:
                    temp2=[]                  
                    for i in range(len(k)):
                        temp2.append(k[i])                
                    count =  (db.session.query(groupEventDetails.event_id).filter(groupEventDetails.group_id == k.group_id).filter(groupEventDetails.deleted == False).filter(groupEventDetails.event_start > datetime.now()).distinct().count())
                    temp2.append(count)
                    temp.append(temp2)
                group_list=temp
        else:
            group_list = []
        db.session.close()
        result['status']='success'
        if group_list != []:
            result['message']='Pools Found'
            result['pools']=add_labels(label, group_list,'poolBucket',GROUP_BUCKET,keySize=size)
        else:
            result['message']='No Pools Found'
    except Exception, e:
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Pools not found'}        
        pass
    data = json.dumps(result)
    return data

@application.route('/createPool', methods=['POST'])
def createPool():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','poolName','poolHandle','latitude','longitude','city','poolDescription','isPicSet','searchable','onProfile','readable','inviteOnly','category')):
            userID = request.form['myID']
            groupName = request.form['poolName']
            groupHandle = request.form['poolHandle']
            groupLat = request.form['latitude']
            groupLong = request.form['longitude']
            groupCity = request.form['city']
            groupDescription = request.form['poolDescription']
            picSet = request.form['isPicSet'] 
            tempSearchable = request.form['searchable']
            if tempSearchable == 'yes':
                searchable = True
            else:
                searchable = False
            tempOnProfile = request.form['onProfile']
            if tempOnProfile == 'yes':
                onProfile = True
            else:
                onProfile = False
            tempReadable = request.form['readable']
            if tempReadable == 'yes':
                readable = True
            else:
                readable = False
            inviteOnly = (request.form['inviteOnly']).upper()
            category = request.form['category']
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    data_entered = groupDetails(group_name=groupName, group_handle=groupHandle, group_description=groupDescription, group_city=groupCity, group_lat=groupLat, group_long=groupLong, group_category=category, group_searchable=searchable, group_readable=readable, group_on_profile=onProfile, group_invite_only=inviteOnly)
    result={'status':'error','message':'Pool already registered'}
    try:
        db.session.add(data_entered)
        db.session.flush()
        result['poolID']=data_entered.group_id
        group_check = db.session.query(groupDetails).filter(groupDetails.group_handle==groupHandle).first()
        user_check = db.session.query(users).filter(users.u_id == userID).first()
        if group_check != [] and user_check != []:
            memberData = groupMembers(group_id=group_check.group_id,member_id=user_check.u_id,member_role='O')
            db.session.add(memberData)
            db.session.commit()
        else:
            result['status'] = 'Error'
            result['message'] = 'Pool registration error'
            db.session.rollback()
            pass
        try:
            group_check_2 = db.session.query(groupDetails.group_id).filter(groupDetails.group_id == group_check.group_id).first()
            result['smallPoolKey'] = 'default_small'
            result['mediumPoolKey'] = 'default_medium'
            result['largePoolKey'] = 'default_large'
            result['poolBucket']= GROUP_BUCKET
            if picSet == 'yes':
                file_name=str(group_check_2.group_id)+'_poolPic'
                key = file_name
                db.session.query(groupDetails.group_key).filter(groupDetails.group_id==group_check_2.group_id).update({"group_key":key})
                db.session.commit()
                result['smallPoolKey'] = key + '_small'
                result['mediumPoolKey'] = key + '_medium'
                result['largePoolKey'] = key + '_large'
                db.session.close()
        except Exception, f:
            result['uploadStatus'] = 'error'
            result['error_message'] = str(f)
            pass
        db.session.commit()
        result['status'] = 'success'
        result['message'] = 'Pool created!'
    except Exception, e:
        db.session.rollback()
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Pool not created'}
        pass
    finally:
        db.session.close()
    data = json.dumps(result)
    return data

@application.route('/getPoolProfile', methods=['POST'])
def getPoolProfile():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','poolID','lastPostID','userPicSize','poolPicSize')):
            userID = request.form['myID']
            groupID = request.form['poolID']
            lastPostID = request.form['lastPostID']
            if request.form['userPicSize'] in ['small','medium','large'] and request.form['poolPicSize'] in ['small','medium','large']:
                userPicSize = request.form['userPicSize']
                groupPicSize = request.form['poolPicSize']
            else:
                return json.dumps(result)
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)  
    try: #if group is public do something else < invite_only is 'N'
        group_search = db.session.query(groupDetails.group_id, groupDetails.group_handle, groupDetails.group_name, groupDetails.group_key, groupDetails.group_city, groupDetails.group_description, groupDetails.group_num_members, groupDetails.group_invite_only, groupDetails.group_searchable, groupDetails.group_readable, groupDetails.group_on_profile,groupMembers.member_role, groupDetails.group_long, groupDetails.group_lat, groupDetails.group_category).filter(groupDetails.group_id==groupID).outerjoin(groupMembers, and_(groupMembers.member_id==userID,groupMembers.group_id==groupID)).distinct().all()
        blocked_search = db.session.query(groupDetails.group_id).filter(groupMembers.member_id == userID).filter(groupMembers.group_id==groupDetails.group_id).filter(groupMembers.member_role=='B').all()  
        blocked=False        
        if blocked_search is not None and blocked_search != []:
            for i in blocked_search:
                if i.group_id==group_search[0].group_id:
                    blocked=True
        if(blocked or group_search is None or group_search == []):
            result['status']='success'
            result['message']='No Pools Found'
        elif group_search != []:
            result['upcomingChaptersCount']=db.session.query(groupEventDetails.event_id).filter(groupEventDetails.group_id == groupID).filter(groupEventDetails.deleted == False).filter(groupEventDetails.event_start > datetime.now()).distinct().count()
            if group_search[0].member_role in ('O','H'):
                result['poolsRequestsCount']=db.session.query(groupMembers.member_id).filter(groupMembers.group_id == groupID).filter(groupMembers.member_role == 'S').distinct().count()
            else:
                result['poolRequestsCount']=-1
            #if group is public do something else
            result['message']='Pool found'
            label = ['poolID', 'poolHandle', 'poolName', 'poolKey', 'city', 'poolDescription', 'membersCount', 'inviteOnly', 'searchable', 'readable', 'onProfile', 'memberRole','longitude','latitude','category']
            result['poolInfo']=add_labels(label, group_search,'poolBucket',GROUP_BUCKET, keySize=groupPicSize)
            #print result['groupInfo']
            #get most recent host post and regular group posts   
            #print 'hostPostSearch'         
            hostPostSearch =  db.session.query(groupPosts.group_post_id, users.u_id, users.firebase_id, groupMembers.member_role, users.u_name, users.u_handle, users.u_key, groupPosts.date_time, groupPosts.date_time_edited, groupPosts.group_post_cont, groupPosts.reply_count).filter(groupPosts.deleted==False).filter(groupPosts.group_id == groupID).filter(groupPosts.post_u_id == users.u_id).filter(groupPosts.original_post_id==0).filter(groupMembers.group_id==groupID).filter(groupMembers.member_id==users.u_id).distinct().order_by(groupPosts.group_post_id.desc()).first()
            subq = db.session.query(groupPosts.original_post_id).filter(groupPosts.post_u_id==userID).filter(groupPosts.original_post_id == -1).distinct().subquery()
            postSearch = db.session.query(groupPosts.group_post_id, users.u_id, users.firebase_id, groupMembers.member_role, users.u_name, users.u_handle, users.u_key, groupPosts.date_time, groupPosts.date_time_edited, groupPosts.group_post_cont, groupPosts.reply_count, groupPosts.points_count, groupPostUpvoted.points).filter(groupPosts.deleted==False).filter(groupPosts.post_u_id == users.u_id).filter(groupPosts.post_u_id==groupMembers.member_id).filter(groupMembers.group_id==groupPosts.group_id).filter(groupPosts.group_id==groupID).filter(or_(groupPosts.original_post_id==-1, forumPosts.post_id.in_(subq))).outerjoin(groupPostUpvoted, and_(groupPostUpvoted.post_id==groupPosts.group_post_id, groupPostUpvoted.voter_id==userID)).filter(groupPosts.group_post_id > lastPostID).order_by(groupPosts.group_post_id.desc()).distinct().all()
            hostPostLabel = ['postID','userID','firebaseID','memberRole','userName','userHandle','key','timestamp','timestampEdited','postContent','replyCount']
            postLabel = ['postID','userID','firebaseID','memberRole','userName','userHandle','key','timestamp','timestampEdited','postContent','replyCount','pointsCount','didIVote']    
            if hostPostSearch is not None and hostPostSearch != [] and postSearch is not None and postSearch != []:
                result['hostPost']=add_labels(hostPostLabel,hostPostSearch, 'bucket', PROF_BUCKET, keySize=userPicSize)                
                result['poolPosts'] = add_labels(postLabel, postSearch,'bucket',PROF_BUCKET, keySize=userPicSize)
                result['status']='success'
                result['message']='Pool Found. Posts Found'    
                db.session.query(groupMembers.last_host_post_seen, groupMembers.last_post_seen).filter(groupMembers.member_id==userID, groupMembers.group_id==groupID).update({'last_host_post_seen':hostPostSearch.group_post_id,'last_post_seen':postSearch[0].group_post_id})
            elif hostPostSearch is not None and hostPostSearch != [] and not(postSearch is not None and postSearch != []):
                result['hostPost']=add_labels(hostPostLabel,hostPostSearch, 'bucket', PROF_BUCKET, keySize=userPicSize) 
                result['message'] = 'Pool Found. Host Post Found'
                result['status']='success'
                db.session.query(groupMembers.last_host_post_seen, groupMembers.last_post_seen).filter(groupMembers.member_id==userID, groupMembers.group_id==groupID).update({'last_host_post_seen':hostPostSearch.group_post_id})
            elif postSearch is not None and postSearch != [] and not (hostPostSearch is not None and hostPostSearch != []): 
                result['poolPosts'] = add_labels(postLabel, postSearch,'bucket',PROF_BUCKET, keySize=userPicSize)
                result['status']='success'
                result['message']='Group Found. Post Found'
                db.session.query(groupMembers.last_host_post_seen, groupMembers.last_post_seen).filter(groupMembers.member_id==userID, groupMembers.group_id==groupID).update({'last_post_seen':postSearch[0].group_post_id})
            else:
                result['status']='success'
                result['message']='Pool Found. No Posts Found'
        db.session.commit()
    except Exception, e:
        db.session.rollback()
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Pool not found'}        
        pass
    finally:
        db.session.close() 
    data = json.dumps(result)
    return data

@application.route('/sendPoolPost', methods=['POST'])
def sendPoolPost():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','poolID', 'postContent', 'postID')):
            myID = request.form['myID']
            groupID = int(request.form['poolID'])
            originalPostID = int(request.form['postID']) #checking on client side
            messgCont = request.form['postContent']
            userHandles=[]
            if 'userHandles' in request.form:
                userHandles=parseHandles(request.form['userHandles'])            
        else:
            return json.dumps(result)
    else:    
        return json.dumps(result)
    result = {'status':'error', 'message':'Invalid'}
    data_entered = groupPosts(group_id=groupID, post_u_id=myID, group_post_cont=messgCont, original_post_id=originalPostID)
    try:
        db.session.add(data_entered)
        db.session.flush()
        result['postID']=data_entered.group_post_id
        my_check = db.session.query(users.u_handle).filter(users.u_id==myID).one()
        group_handle_check = db.session.query(groupDetails.group_handle).filter(groupDetails.group_id==groupID).first()
        pool_num = db.session.query(groupDetails.group_num_members).filter(groupDetails.group_id==groupID).one()
        if (pool_num.group_num_members <= 5) and originalPostID==-1: #notify everyone in pool except you
            user_check = db.session.query(users.u_id, users.u_handle, users.device_arn, users.firebase_id, groupDetails.group_handle).filter(groupDetails.group_id==groupMembers.group_id).filter(users.u_id == groupMembers.member_id).filter(groupMembers.group_id==groupID).filter(users.u_id != myID).filter(groupMembers.member_role.in_(('M','H','O'))).all()
            #p = Pool(processes=1)              # Start a worker processes.
            #p.apply_async(notifyPool, [user_check, my_check.u_handle, messgCont, originalPostID, groupID, myID])
            #p.close()
            for u in user_check:
                if u is not None and u != [] and u.u_id != myID:
                    subj = 'getPoolPost'
                    cont = '.' + u.group_handle + ', @' + my_check.u_handle +': ' + messgCont
                    notificType = 'G'
                    notificUID = u.u_id
                    inNot = inNotification(u.firebase_id)
                    if inNot == True:
                        result['notificationSent' + str(u.u_id)]=logNotification(notificUID, cont, subj, notificType, notificPostID=(data_entered.group_post_id if originalPostID==-1 else originalPostID), notificGroupID=groupID)
                        firebaseNotification(u.firebase_id, cont)
                    inPo = inPool(u.firebase_id)
                    #result['inPool' + str(u.u_id)] = inPo
                    #result['inPool' + str(u.u_id) + '_check1']= (inPo!=groupID)
                    #result['inPool' + str(u.u_id) + '_check2']= (inPo>=0)
                    #result['inNot' + str(u.u_id) + '_check']= (inNot==False)
                    #result['inNotification' + str(u.u_id)] = inNot
                    if u.device_arn != 0 and (inNot==False) and (inPo!=groupID) and inPo>=0:  
                        result['notificationSent' + str(u.u_id)]=logNotification(notificUID, cont, subj, notificType, notificPostID=(data_entered.group_post_id if originalPostID==-1 else originalPostID), notificGroupID=groupID)
                        firebaseNotification(u.firebase_id, cont)  
                        db.session.commit()
                        badge = db.session.query(notific.notific_id).filter(notific.n_u_id==u.u_id).filter(notific.notific_seen==False).count()
                        push(u.device_arn, badge, cont, subj)
        elif originalPostID not in (0,-1):
            db.session.query(groupPosts.reply_count).filter(groupPosts.group_post_id==originalPostID).update({'reply_count':groupPosts.reply_count + 1})
            user_check = db.session.query(users.u_id, users.u_handle, users.device_arn, users.firebase_id, groupPosts.original_post_id).filter(users.u_id==groupPosts.post_u_id).filter(groupPosts.group_post_id == originalPostID).one()
            inPID = inPostID(user_check.firebase_id) # inPostID == parentPostID, do NOT send push. 
            if int(user_check.u_id) != int(myID):
                subj = 'getPoolPost'
                cont = '@' + my_check.u_handle + ' replied to your ' + ('host' if user_check.original_post_id == 0 else 'pool') + ' post: ' + messgCont
                notificType = 'G'
                notificUID = user_check.u_id
                inNot = inNotification(user_check.firebase_id)
                if inNot == True:
                    result['notificationSent']=logNotification(notificUID, cont, subj, notificType, notificPostID=(data_entered.group_post_id if originalPostID==-1 else originalPostID), notificGroupID=groupID)
                    firebaseNotification(user_check.firebase_id, cont)
                if user_check is not None and user_check != [] and user_check.u_id != myID and inPID!=originalPostID:
                    if user_check.device_arn != 0 and inNot == False:
                        result['notificationSent']=logNotification(notificUID, cont, subj, notificType, notificPostID=(data_entered.group_post_id if originalPostID==-1 else originalPostID), notificGroupID=groupID)
                        firebaseNotification(user_check.firebase_id, cont)
                        db.session.commit()
                        badge = db.session.query(notific.notific_id).filter(notific.n_u_id==user_check.u_id).filter(notific.notific_seen==False).count()
                        push(user_check.device_arn, badge, cont, subj)
        db.session.commit()
        result['status'] = 'success'
        result['message'] = 'Posted'
        if userHandles != []:
            tagged = sendTagNotifications(userHandles, my_check.u_handle, myID, 'getPoolPost','pool' if originalPostID == -1 else 'host', messgCont, (result['postID'] if originalPostID in (0, -1) else originalPostID), groupID=groupID, poolHandle=group_handle_check.group_handle)
            result['numTagged'] = len(userHandles)
            if tagged:
                result['taggedNotifications']='success'
            else:
                result['taggedNotifications']=tagged
            db.session.commit()
    except Exception, e:
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Post not sent'}        
        db.session.rollback()
        pass    
    finally:
        db.session.close()
    data = json.dumps(result)
    return data

@application.route('/getPoolPost', methods=['POST'])
def getPoolPost():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','postID','size','lastPostID','poolID')):
            userID = request.form['myID']
            lastPostID = int(request.form['lastPostID'])
            postID = int(request.form['postID'])  #0=hostPost,  else parent postID XX -1=groupPost,
            groupID = request.form['poolID']
            if request.form['size'] in ('small','medium','large'):
                size = request.form['size']
            else:
                return json.dumps(result)
        else:
            return json.dumps(result)
    else:    
        return json.dumps(result)
    result = {'status':'error', 'message':'No posts found'}
    try:
        member_check = db.session.query(groupMembers.member_role).filter(groupMembers.member_id==userID).filter(groupMembers.member_id==users.u_id).filter(groupMembers.group_id == groupID).filter(groupMembers.member_role.in_(('M','H','O'))).first()
        group_check = db.session.query(groupDetails.group_readable, groupDetails.group_handle).filter(groupDetails.group_id == groupID).first()
        if (member_check is not None and (group_check.group_readable or member_check.member_role in('M','H','O'))) or postID >0:
            result['myMemberRole']=member_check.member_role
            result['poolHandle']=group_check.group_handle
            if postID == 0:
                if lastPostID == 0:
                    host_post_check = db.session.query(groupPosts.group_post_id, users.u_id, users.firebase_id, users.u_key, users.u_name, users.u_handle, groupPosts.group_post_cont, groupPosts.date_time, groupPosts.date_time_edited, groupMembers.member_role, groupPosts.reply_count, groupPosts.original_post_id, groupPosts.is_pinned).filter(groupPosts.deleted==False).filter(groupPosts.group_id==groupID).filter(groupPosts.original_post_id==0).filter(groupPosts.post_u_id==users.u_id).filter(groupPosts.group_id == groupMembers.group_id).filter(groupMembers.member_id==users.u_id).order_by(groupPosts.group_post_id.desc()).distinct().limit(DEFAULT_LIMIT)
                else:                
                    host_post_check = db.session.query(groupPosts.group_post_id, users.u_id, users.firebase_id, users.u_key, users.u_name, users.u_handle, groupPosts.group_post_cont, groupPosts.date_time, groupPosts.date_time_edited, groupMembers.member_role, groupPosts.reply_count, groupPosts.original_post_id, groupPosts.is_pinned).filter(groupPosts.deleted==False).filter(groupPosts.group_post_id < lastPostID).filter(groupPosts.group_id==groupID).filter(groupPosts.original_post_id==0).filter(groupPosts.post_u_id==users.u_id).filter(groupPosts.group_id == groupMembers.group_id).filter(groupMembers.member_id==users.u_id).order_by(groupPosts.group_post_id.desc()).distinct().limit(DEFAULT_LIMIT)
                hostPostLabels = ['postID','userID','firebaseID','key','userName','userHandle','postContent','timestamp','timestampEdited','memberRole','replyCount','cellType']
                result['hostPosts'] = add_labels(hostPostLabels, host_post_check, 'bucket', PROF_BUCKET,keySize=size)
                result['status'] = 'success'
                result['message'] = 'Posts Found'
            else:
                if lastPostID==0:
                    post_check = db.session.query(groupPosts.group_post_id, users.u_id, users.firebase_id, users.u_key, users.u_name, users.u_handle, groupPosts.group_post_cont, groupPosts.date_time, groupPosts.date_time_edited, groupMembers.member_role, groupPosts.points_count, groupPosts.reply_count, groupPostUpvoted.points, groupPosts.original_post_id, groupPosts.is_pinned).filter(groupPosts.deleted==False).filter(groupPosts.post_u_id==users.u_id).filter(groupPosts.group_post_id == postID).filter(groupPosts.post_u_id==groupMembers.member_id).filter(groupPosts.group_id==groupMembers.group_id).outerjoin(groupPostUpvoted, and_(groupPostUpvoted.post_id==groupPosts.group_post_id, groupPostUpvoted.voter_id==userID)).distinct().order_by(groupPosts.group_post_id.desc()).limit(DEFAULT_LIMIT)
                    reply_check = db.session.query(groupPosts.group_post_id, users.u_id, users.firebase_id, users.u_key, users.u_name, users.u_handle, groupPosts.group_post_cont, groupPosts.date_time, groupPosts.date_time_edited, groupMembers.member_role, groupPosts.points_count, groupPosts.reply_count, groupPostUpvoted.points, groupPosts.original_post_id, groupPosts.is_pinned).filter(groupPosts.deleted==False).filter(groupPosts.post_u_id==users.u_id).filter(groupPosts.original_post_id == postID).filter(groupPosts.post_u_id==groupMembers.member_id).filter(groupPosts.group_id==groupMembers.group_id).outerjoin(groupPostUpvoted, and_(groupPostUpvoted.post_id==groupPosts.group_post_id, groupPostUpvoted.voter_id==userID)).distinct().order_by(groupPosts.group_post_id.desc()).limit(DEFAULT_LIMIT)
                else:
                    post_check = db.session.query(groupPosts.group_post_id, users.u_id, users.firebase_id, users.u_key, users.u_name, users.u_handle, groupPosts.group_post_cont, groupPosts.date_time, groupPosts.date_time_edited, groupMembers.member_role, groupPosts.points_count, groupPosts.reply_count, groupPostUpvoted.points, groupPosts.original_post_id, groupPosts.is_pinned).filter(groupPosts.deleted==False).filter(groupPosts.post_u_id==users.u_id).filter(groupPosts.group_post_id == postID).filter(groupPosts.group_post_id < lastPostID).filter(groupPosts.post_u_id==groupMembers.member_id).filter(groupPosts.group_id==groupMembers.group_id).outerjoin(groupPostUpvoted, and_(groupPostUpvoted.post_id==groupPosts.group_post_id, groupPostUpvoted.voter_id==userID)).distinct().order_by(groupPosts.group_post_id.desc()).limit(DEFAULT_LIMIT)
                    reply_check = db.session.query(groupPosts.group_post_id, users.u_id, users.firebase_id, users.u_key, users.u_name, users.u_handle, groupPosts.group_post_cont, groupPosts.date_time, groupPosts.date_time_edited, groupMembers.member_role, groupPosts.points_count, groupPosts.reply_count, groupPostUpvoted.points, groupPosts.original_post_id, groupPosts.is_pinned).filter(groupPosts.deleted==False).filter(groupPosts.post_u_id==users.u_id).filter( groupPosts.original_post_id==postID).filter(groupPosts.group_post_id < lastPostID).filter(groupPosts.post_u_id==groupMembers.member_id).filter(groupPosts.group_id==groupMembers.group_id).outerjoin(groupPostUpvoted, and_(groupPostUpvoted.post_id==groupPosts.group_post_id, groupPostUpvoted.voter_id==userID)).distinct().order_by(groupPosts.group_post_id.desc()).limit(DEFAULT_LIMIT)
                '''
                initial_post_check = db.session.query(groupPosts.group_post_id, users.u_id, users.firebase_id, users.u_key, users.u_name, users.u_handle, groupPosts.group_post_cont, groupPosts.date_time, groupPosts.date_time_edited, groupMembers.member_role, groupPosts.points_count, groupPosts.reply_count, groupPostUpvoted.points, groupPosts.original_post_id).
filter(groupPosts.original_post_id==-1).
filter(groupPosts.group_post_id == postID).
filter(groupPosts.post_u_id==users.u_id).
filter(groupPosts.group_id==groupMembers.group_id).
filter(groupPosts.post_u_id==groupMembers.member_id).
filter(groupPosts.post_u_id==groupPostUpvoted.voter_id).
filter(groupPostUpvoted.post_id==groupPosts.group_post_id).first()
                if initial_post_check != []:
                    if lastPostID==0:
                        sub_post_check = db.session.query(groupPosts.group_post_id, users.u_id, users.firebase_id, users.u_key, users.u_name, users.u_handle, groupPosts.group_post_cont, groupPosts.date_time, groupPosts.date_time_edited, groupMembers.member_role, groupPosts.points_count, groupPosts.reply_count, groupPostUpvoted.points, groupPosts.original_post_id).

filter(groupPosts.post_u_id==users.u_id).
filter(groupPosts.original_post_id==postID).
filter(groupPosts.post_u_id==groupMembers.member_id).
filter(groupMembers.group_id==groupPosts.group_id).
filter(groupPosts.post_u_id==groupPostUpvoted.voter_id).
filter(groupPosts.group_post_id==groupPostUpvoted.post_id).

order_by(groupPosts.group_post_id.desc()).distinct().limit(DEFAULT_LIMIT)
                    else:
                        sub_post_check = db.session.query(groupPosts.group_post_id, users.u_id, users.firebase_id, users.u_key, users.u_name, users.u_handle, groupPosts.group_post_cont, groupPosts.date_time, groupPosts.date_time_edited, groupMembers.member_role, groupPosts.points_count, groupPosts.reply_count, groupPostUpvoted.points, groupPosts.original_post_id).filter(groupPosts.post_u_id==users.u_id).filter(groupPosts.group_post_id < lastPostID).filter(groupPosts.original_post_id==postID).filter(groupPosts.post_u_id==groupMembers.member_id).filter(groupMembers.group_id==groupPosts.group_id).filter(groupPosts.post_u_id==groupPostUpvoted.voter_id).filter(groupPosts.group_post_id==groupPostUpvoted.post_id).order_by(groupPosts.group_post_id.desc()).distinct().limit(DEFAULT_LIMIT)
                '''
                labels = ['postID', 'userID', 'firebaseID', 'key', 'userName', 'userHandle', 'postContent', 'timestamp', 'timestampEdited', 'memberRole', 'pointsCount', 'replyCount', 'didIVote', 'cellType','isPinned']
                result['status'] = 'success'        #'pointsCount'
                if post_check is not None and post_check !=[] and reply_check is not None and reply_check != []:
                    result['message'] = 'Replies Found'
                    result['poolPosts'] = add_labels(labels, post_check, 'bucket', PROF_BUCKET, keySize=size) + add_labels(labels, reply_check, 'bucket', PROF_BUCKET, keySize=size)
                elif post_check is not None and post_check!=[]:
                    result['message'] = 'No Replies Found'
                    result['poolPosts'] = add_labels(labels, post_check, 'bucket', PROF_BUCKET, keySize=size)
                else:
                    result['status'] = 'error'
                    result['message'] = 'Error Retrieving Posts'
        else:
            result['myMemberRole']='N'
        db.session.close()
        result['status']='success'
    except Exception, e:
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Post not found'}
    return json.dumps(result)
    
@application.route('/updatePool', methods=['POST'])
def updatePool():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','poolID','action')):
            userID = request.form['myID']
            groupID = request.form['poolID']
            action = request.form['action'] #edit delete
            if action == 'edit':
                if all (l in request.form for l in ('poolName','poolHandle','latitude','longitude','city','poolDescription','isPicSet','searchable','onProfile','readable','inviteOnly','category')):
                    groupName = request.form['poolName']
                    groupHandle = request.form['poolHandle']
                    groupLat = request.form['latitude']
                    groupLong = request.form['longitude']
                    groupCity = request.form['city']
                    groupDescription = request.form['poolDescription']
                    picSet = request.form['isPicSet'] #yes, no, no_change
                    tempSearchable = request.form['searchable']
                    if tempSearchable =='yes':
                        groupSearchable = True
                    else:
                        groupSearchable = False
                    tempOnProfile = request.form['onProfile']
                    if tempOnProfile == 'yes':
                        groupOnProfile = True
                    else:
                        groupOnProfile = False
                    tempReadable = request.form['readable']
                    if tempReadable == 'yes':
                        groupReadable = True
                    else:
                        groupReadable = False
                    groupInviteOnly = (request.form['inviteOnly']).upper()
                    groupCategory = request.form['category']
                else:
                    return json.dumps(result)
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    try:
        group_member_check = db.session.query(groupMembers.member_role, groupDetails.group_key, groupMembers.member_role, groupDetails.group_active).filter(groupMembers.group_id==groupDetails.group_id).filter(groupMembers.group_id == groupID).filter(groupMembers.member_id == userID).first()
        if group_member_check != [] and group_member_check.member_role in ('O','A'):
            if action == 'delete' and group_member_check.member_role == 'O':
                db.session.query(groupDetails.group_active).filter(groupDetails.group_id==groupID).update({'group_active':'N'})
                db.session.commit()
                result['status'] = 'success'   
                result['message'] = 'Successfully deleted pool'
            elif action == 'edit':
                result['poolBucket']=GROUP_BUCKET
                if picSet == 'yes': #_iteration ???
                    if group_member_check.group_key != 'default':
                        k_1, k_2 =group_member_check.group_key.split('_',1)
                        if '_' in k_2:
                            k_2,k_3=k_2.split('_')
                            k_2 = str(int(k_2)+1)
                            key=k_1+'_'+k_2+'_'+k_3
                        else:
                            key=k_1+'_0_'+k_2
                    else:
                        key=str(groupID)+'_userProfPic'
                    result['smallPoolKey'] = key + '_small'
                    result['mediumPoolKey'] = key + '_medium'
                    result['largePoolKey'] = key + '_large'
                    result['poolKey']=key
                elif picSet=='no': #picSet == 'no'
                    result['smallPoolKey'] = 'default_small'
                    result['mediumPoolKey'] = 'default_medium'
                    result['largePoolKey'] = 'default_large'
                    result['poolKey'] = 'default'
                else:
                    result['poolKey']=group_member_check.group_key
                    result['smallPoolKey'] = group_member_check.group_key + '_small'
                    result['mediumPoolKey'] = group_member_check.group_key + '_medium'
                    result['largePoolKey'] = group_member_check.group_key + '_large'
                db.session.query(groupDetails).filter(groupDetails.group_id==groupID).update({'group_name':groupName,'group_handle':groupHandle,'group_long':groupLong, 'group_lat':groupLat, 'group_city':groupCity,'group_description':groupDescription,'group_category':groupCategory,'group_searchable':groupSearchable,'group_readable':groupReadable,'group_on_profile':groupOnProfile, 'group_invite_only':groupInviteOnly,'group_key':result['poolKey']})
                result['status'] = 'success'   
                result['message'] = 'Successfully updated pool'
                db.session.commit()
            else:
                result = {'status':'error', 'message':'Invalid Action'}
        else:
            result = {'status':'error', 'message':'Unauthorized'}
    except Exception, e:
        db.session.rollback()
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Pool not updated'}        
        pass
    finally:
        db.session.close()
    data = json.dumps(result)
    return data

#add members to group
#add members to event (invite only?), edit event, disable?

@application.route('/createChapter', methods=['POST']) #key and handle??
def createChapter():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','poolID','chapterName','chapterDescription','timestampChapterStart')):
            userID = request.form['myID']
            groupID = request.form['poolID']
            eventName = request.form['chapterName']
            eventDescription = request.form['chapterDescription']
            try:
                eventStart = datetime.strptime(request.form['timestampChapterStart'],"%b %d, %Y")
            except:
                return json.dumps({'status':'error','message':'Invalid Date'})
            if 'timestampChapterEnd' in request.form:
                try:
                    eventEnd = datetime.strptime(request.form['timestampChapterEnd'],"%b %d, %Y")
                except:
                    return json.dumps({'status':'error','message':'Invalid Date'})                
            else:
                eventEnd = eventStart
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    data_entered = groupEventDetails(group_id=groupID, event_name=eventName, event_description=eventDescription, event_start=eventStart, event_end=eventEnd)
    result={'status':'error','message':'Momen t already registered'}
    try:
        event_check = db.session.query(groupEventDetails).filter(groupEventDetails.group_id==groupID).filter(groupEventDetails.deleted == False).filter(groupEventDetails.event_name==eventName, groupEventDetails.event_description==eventDescription).filter(groupEventDetails.event_start==eventStart).filter(groupEventDetails.event_end==eventEnd).all()
        if event_check is None or event_check == []:
            member_check = db.session.query(groupMembers.member_role).filter(groupMembers.member_id==userID).filter(groupMembers.group_id==groupID).filter(groupMembers.member_role.in_(('M','H','O')))
            if member_check.first() is not None and member_check != [] and member_check[0].member_role in ('O','H'):
                try:            
                    db.session.add(data_entered)
                    db.session.commit()
                    result['chapterID']=data_entered.event_id
                    eventUserData = groupEventUsers(data_entered.event_id, userID, 'W')
                    db.session.add(eventUserData)       
                    result['status'] = 'success'
                    result['message'] = 'Event registration Complete'
                    db.session.commit()
                except:
                    result['status'] = 'Error'
                    result['message'] = 'Event registration error'
                    db.session.rollback()
                    db.session.query(groupEventDetails).filter(groupEventDetails.event_id==data_entered.event_id).delete()
                    db.session.commit()            
            else:
                result={'status':'error','message':'Unauthorized'}
        else:
            result = {'status':'error','message':' Please check to make sure the chapter does not already exist'}
    except Exception, e:
        db.session.rollback()
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'chapter not created'}
        pass    
    finally:
        db.session.close()
        db.session.close()
    data = json.dumps(result)
    return data

@application.route('/updateChapter', methods=['POST'])
def updateChapter():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','chapterID','poolID','chapterName','chapterDescription','timestampChapterStart')):
            userID = request.form['myID']
            eventID = request.form['chapterID']
            groupID = request.form['poolID']
            eventName = request.form['chapterName']
            eventDescription = request.form['chapterDescription']
            try:
                eventStart = datetime.strptime(request.form['timestampChapterStart'],"%b %d, %Y")
            except:
                return json.dumps({'status':'error','message':'Invalid Date'})
            if 'timestampChapterEnd' in request.form:
                try:
                    eventEnd = datetime.strptime(request.form['timestampChapterEnd'],"%b %d, %Y")
                except:
                    return json.dumps({'status':'error','message':'Invalid Date'})                
            else:
                eventEnd = eventStart
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    try:
        member_check = db.session.query(groupMembers.member_role).filter(groupMembers.member_id==userID).filter(groupMembers.group_id==groupID).filter(groupMembers.member_role.in_(('O','H')))
        if member_check.one() is not None:
            db.session.query(groupEventDetails).filter(groupEventDetails.deleted == False).filter(groupEventDetails.event_id==eventID).update({'event_name':eventName,'event_description':eventDescription,'event_start':eventStart,'event_end':eventEnd})
            db.session.commit()
            result['status'] = 'success'
            result['message'] = 'Chapter updated'
        else:
            result['status'] = 'error'
            result['message'] = 'Chapter not updated'
    except Exception, e:
        db.session.rollback()
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Chapter not updated'}        
        pass    
    finally:
        db.session.close()
    return json.dumps(result)
    


@application.route('/pinToScrapBook', methods=['POST'])
def pinToScrapBook():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        chapterName = None
        poolHandle = None
        if all (k in request.form for k in ('myID', 'postType', 'postID', 'action', 'postContent')):
            userHandles=[]
            if ('chapterName' in request.form and 'poolHandle' in request.form):
                chapterName = request.form['chapterName']
                poolHandle = request.form['poolHandle']
            userID = request.form['myID']
            postID = int(request.form['postID'])
            postContent = request.form['postContent']
            pinID = 0
            hasPin=False
            imageKey = 'default'
            if request.form['action'] == 'pin':
                pin = True
                addNew = True
            elif request.form['action'] == 'unpin':
                pin = False
                addNew = False
            else:
                return json.dumps(result)
            if request.form['postType'] in ('pond','anon','pool','chapterText', 'chapterImage','host'):
                postType = request.form['postType']
                if postType == 'pond':
                    postType = 'F'
                elif postType == 'anon':
                    postType = 'A'
                elif postType in ('pool','host'):
                    postType = 'G'
                elif postType == 'chapterText':
                    postType = 'M'
                elif postType == 'chapterImage':
                    postType = 'I'
                    if 'imageKey' in request.form:
                        imageKey = request.form['imageKey']
                        if imageKey[len(imageKey)-6:] == '_small': #_small
                            imageKey = imageKey[:len(imageKey)-6]
                        elif imageKey[len(imageKey)-7:] == '_medium': #_medium
                            imageKey = imageKey[:len(imageKey)-6]
                        elif imageKey[len(imageKey)-6:] == '_large': #_large
                            imageKey = imageKey[:len(imageKey)-6]
                    else: 
                        return json.dumps(result)
                else:
                    imageKey = 'default'          
            else:
                return json.dumps(result)
        elif all (l in request.form for l in ('myID','pinID','action')): 
            userHandles=[]
            userID = request.form['myID']
            pinID = int(request.form['pinID'])
            action = request.form['action']        
            addNew = False
            if action == 'unpin':
                pin = False
            else:
                pin = True
            hasPin=True
        elif all (j in request.form for j in ('myID','pinID','replyContent')):
            userHandles=[]
            if 'userHandles' in request.form:
                userHandles=parseHandles(request.form['userHandles'])
            userID = request.form['myID']
            pinID = int(request.form['pinID'])
            postContent = request.form['replyContent']
            postType = 'R'
            postID = None
            imageKey = 'default'
            pin = 'R'
            hasPin = False
            addNew = True
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    try:
        if (hasPin):
            type_check = db.session.query(pinnedPosts.pin_type, pinnedPosts.pin_post_id).filter(pinnedPosts.pin_id==pinID).first()
            postID=type_check.pin_post_id
            postType=type_check.pin_type
        if postType == 'F':
            post_check = db.session.query(forumPosts.is_pinned).filter(forumPosts.post_id==postID).filter(forumPosts.post_u_id==userID)
        elif postType == 'A':
            post_check = db.session.query(anonForumPosts.is_pinned).filter(anonForumPosts.a_post_id==postID).filter(anonForumPosts.a_post_u_id==userID)
        elif postType == 'G':
            post_check = db.session.query(groupPosts.is_pinned).filter(groupPosts.group_post_id==postID).filter(groupPosts.post_u_id==userID)
        elif postType in ('M','I'):
            post_check = db.session.query(groupEventPosts.is_pinned).filter(groupEventPosts.group_event_post_id==postID).filter(groupEventPosts.group_event_post_u_id==userID)
        if postType!='R' and post_check.first() is not None and post_check != []:
            post_check.update({'is_pinned':pin}) #update original post
            if pin == False or (not addNew and pin): #if i have to unpin, a pinnedpost entry exists already. edit it.
                db.session.query(pinnedPosts.is_pinned).filter(pinnedPosts.pin_post_id==postID).filter(pinnedPosts.pin_type==postType).update({'is_pinned':pin})
            result['message'] = ('Post pinned' if pin else 'Post un-pinned')
        if pinID == 0 and pin==True:
            pin_check = db.session.query(pinnedPosts).filter(pinnedPosts.pin_post_id==postID).filter(pinnedPosts.pin_type==postType).filter(pinnedPosts.original_post_id==pinID).filter(pinnedPosts.u_id==userID).filter(pinnedPosts.is_pinned==False)
            if pin_check.first() is not None:
                pin_check.update({'pin_post_orig_cont':postContent, 'image_key':imageKey, 'is_pinned':True, 'date_time_edited':datetime.now()})
                addNew = False
        if addNew:
            data_entered = pinnedPosts(u_id = userID, pin_type = postType, pin_post_orig_cont = postContent, pin_post_id = postID, original_post_id=pinID, image_key = imageKey, pin_post_orig_pool_handle=poolHandle, pin_post_orig_chapter_name=chapterName)
            db.session.add(data_entered)
            if postType == 'R':
                db.session.query(pinnedPosts.reply_count).filter(pinnedPosts.pin_id==pinID).update({'reply_count':pinnedPosts.reply_count+1})
        result['status'] = 'success'
        if postType == 'R':
            result['message'] = 'Reply sent'
        db.session.commit()
        if postType == 'R':  
            user_check = db.session.query(pinnedPosts.u_id, pinnedPosts.pin_type, users.u_handle, users.device_arn, users.firebase_id).filter(users.u_id==pinnedPosts.u_id).filter(pinnedPosts.pin_id == pinID).first()
            inPID = inPostID(user_check.firebase_id) # inPostID == parentPostID, do NOT send push. 
            if int(user_check.u_id) != int(userID) and inPID!=pinID:    
                my_check = db.session.query(users.u_handle).filter(users.u_id==userID).one()        
                cont = '@' + my_check.u_handle + ' replied to your scrapbook entry: ' + postContent
                subj = 'getScrapBook'
                if user_check.pin_type=='I':
                    notificType = 'T'
                else:    
                    notificType = 'S'
                notificUID = user_check.u_id
                inNot = inNotification(user_check.firebase_id)
                if inNot == True:
                    result['notificationSent']=logNotification(notificUID, cont, subj, notificType, notificPostID=pinID)      
                    firebaseNotification(user_check.firebase_id, cont)
                if user_check is not None and user_check != [] and user_check.u_id != userID:
                    if user_check.device_arn != 0 and inNot == False:         
                        result['notificationSent']=logNotification(notificUID, cont, subj, notificType, notificPostID=pinID)      
                        firebaseNotification(user_check.firebase_id, cont)
                        db.session.commit()    
                        badge = db.session.query(notific.notific_id).filter(notific.n_u_id==user_check.u_id).filter(notific.notific_seen==False).count()
                        push(user_check.device_arn, badge, cont, subj)
        last_pin_check = db.session.query(pinnedPosts.pin_id, pinnedPosts.pin_post_id).filter(pinnedPosts.u_id==userID).filter(pinnedPosts.pin_type == postType).order_by(pinnedPosts.date_time_edited.desc()).first()
        if last_pin_check is not None and last_pin_check!=[]:
            result['pinID'] = last_pin_check.pin_id
            result['postID'] = last_pin_check.pin_post_id
        else:
            result = {'status':'error', 'message':'Post not pinned'}
        if userHandles != []:
            my_check = db.session.query(users.u_handle).filter(users.u_id==userID).first()
            tagged = sendTagNotifications(userHandles, my_check.u_handle, userID, 'getScrapBook','scrapImage' if notificType == 'T' else 'scrap',postContent, (data_entered.post_id if pinID in (0, -1) else pinID))
            result['numTagged'] = len(userHandles)
            if tagged:
                result['taggedNotifications']='success'
            else:
                result['taggedNotifications']=tagged
            db.session.commit()
    except Exception, e:
        db.session.rollback()
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Post not pinned'}        
        pass    
    finally:
        db.session.close()
    return json.dumps(result)

@application.route('/getScrapBook', methods=['POST'])
def getScrapBook():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','lastPostID','userID','pinID')):
            myID = int(request.form['myID'])
            userID = int(request.form['userID']) #0=all friends, anything else for that ID (must be a friend or yourself)
            lastPostID = int(request.form['lastPostID'])
            pinID = int(request.form['pinID']) #0 for all, some num for specific post and replies
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    try:
        check = True
        scrap_check = db.session.query(pinnedPosts.pin_id, pinnedPosts.u_id, users.u_name, users.u_handle, users.u_key, users.firebase_id, pinnedPosts.pin_type, pinnedPosts.pin_post_orig_cont, pinnedPosts.date_time, pinnedPosts.reply_count, pinnedPosts.image_key, pinnedPosts.pin_post_orig_pool_handle, pinnedPosts.pin_post_orig_chapter_name, pinnedPosts.points_count, pinnedPosts.points_count, pinnedPostUpvoted.points).filter(pinnedPosts.deleted == False).filter(pinnedPosts.is_pinned == True).filter(pinnedPosts.u_id==users.u_id)
        scrap_voted = None
        if pinID !=0: # userID = 0 specific pinned post and its replies
            scrap_reply = scrap_check.filter(pinnedPosts.original_post_id == pinID)
            scrap_check = scrap_check.filter(pinnedPosts.pin_id == pinID)
        elif userID != 0: #pinID=0, my own or friends
            if userID != myID:
                friend_check = db.session.query(friends.friend_status).filter(or_(and_(friends.friend_a==myID, friends.friend_b==userID), and_(friends.friend_b==myID,friends.friend_a==userID))).distinct().first()
                if friend_check is None or friend_check.friend_status != 'F':
                    result['status'] = 'success'
                    result['message'] = 'Invalid ID'
                    check = False
                ownScrap=False
            else: #userID==myID
                scrap_voted = scrap_check.filter(or_(pinnedPostUpvoted.post_id==pinnedPosts.pin_id, pinnedPostUpvoted.post_id==pinnedPosts.original_post_id))
                ownScrap=True
            if check:
                scrap_check = scrap_check.filter(pinnedPosts.u_id == userID)
                if ownScrap: #shouldn't this be if (not) ownScrap, filter out Anon posts?
                    scrap_check = scrap_check.filter(pinnedPosts.pin_type != 'A') #should this be the other way around?
        else: #pinID==0 and userID == 0 - collection of my and my friends
            #result['status'] = 'error'
            #result['message'] = 'Invalid Request'
            friend_subq = db.session.query(users.u_id).filter(friends.friend_status=='F').filter(or_(and_(friends.friend_a==myID,friends.friend_b==users.u_id),and_(friends.friend_b==myID,friends.friend_a==users.u_id))).filter(users.u_id!=myID).distinct().subquery()
            scrap_check = scrap_check.filter(or_(pinnedPosts.u_id.in_(friend_subq),pinnedPosts.u_id==myID))
            check = True
        if lastPostID != 0:
            scrap_check = scrap_check.filter(pinned_posts.pin_id < lastPostID)
            if pinID != 0:
                scrap_reply = scrap_reply.filter(pinned_posts.pin_id < lastPostID)
        scrap_check = scrap_check.filter(pinnedPosts.pin_type != 'R').outerjoin(pinnedPostUpvoted, and_(pinnedPostUpvoted.post_id == pinnedPosts.pin_id, pinnedPostUpvoted.voter_id==myID)).order_by(pinnedPosts.pin_id.desc()).limit(DEFAULT_LIMIT)
        if pinID != 0:
            scrap_reply = scrap_reply.outerjoin(pinnedPostUpvoted, and_(pinnedPostUpvoted.post_id == pinnedPosts.pin_id, pinnedPostUpvoted.voter_id==myID)).order_by(pinnedPosts.pin_id.desc()).limit(DEFAULT_LIMIT)
        elif pinID == 0 and userID == myID:
            scrap_voted = scrap_voted.outerjoin(pinnedPostUpvoted, and_(pinnedPostUpvoted.post_id == pinnedPosts.pin_id, pinnedPostUpvoted.voter_id==myID)).order_by(pinnedPosts.pin_id.desc()).limit(DEFAULT_LIMIT)
        if check:
            label = ['pinID', 'userID', 'userName', 'userHandle', 'key', 'firebaseID', 'postType', 'postContent', 'timestamp', 'replyCount', 'imageKey', 'poolHandle','chapterName', 'points', 'pointsCount','didIVote']
            scr = add_labels(label, scrap_check, 'imageBucket', EVENT_BUCKET, add_all_label_2='bucket', add_all_2=PROF_BUCKET, keySize='small')
            if (scr is not None and scr != []) or (scrap_voted is not None and scrap_voted != []):
                for s in scr:
                    #s['key']=s['key']+'_small'
                    if s['postType']=='anon':
                        s['userName']='Default'
                        s['userHandle']='Default'
                if pinID != 0 and scrap_reply is not None and scrap_reply != []:
                    scrRep = add_labels(label, scrap_reply, 'imageBucket', EVENT_BUCKET, add_all_label_2='bucket', add_all_2=PROF_BUCKET, keySize='small')   
                    result['scrapBook'] = scr+scrRep
                elif pinID==0 and userID==myID:
                    scrVoted = add_labels(label, scrap_voted,'imageBucket', EVENT_BUCKET, add_all_label_2='bucket', add_all_2=PROF_BUCKET, keySize='small')  # need to remove duplicates?
                    result['scrapBook'] = removeDups(scr + scrVoted)
                else:
                    result['scrapBook'] = scr
                result['status'] = 'success'
                if result['scrapBook'] != []:
                    result['message'] = 'Scrapbook entries found'
                else:
                    result['message'] = 'No scrapbook entries found'                    
            else:
                result['status']='success'
                result['message'] = 'No scrapbook entries found'
    except Exception, e:
        db.session.rollback()
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Scrapbook not retrieved'}        
        pass
    finally:
        db.session.close()
    return json.dumps(result)

def removeDups(scraps): #remove duplicate posts
    return [dict(t) for t in set([tuple(d.items()) for d in scraps])] #does not preserve order
        

@application.route('/chapterProfile', methods=['POST'])
def chapterProfile():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','poolID','chapterID','size','lastPostID')):
            userID = request.form['myID']
            groupID = request.form['poolID']
            eventID = request.form['chapterID']
            lastPostID = int(request.form['lastPostID'])
            if request.form['size'] in ('small','medium','large'):
                size = request.form['size']
            else:
                return json.dumps(result)
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    try:
        user_check = db.session.query(groupMembers.member_role, groupDetails.group_num_members).filter(groupMembers.group_id == groupID).filter(groupMembers.member_id == userID).filter(groupDetails.group_id==groupMembers.group_id).first()
        if user_check is not None and user_check != [] and user_check.member_role in ('M','H','O'): 
            result['membersCount']=user_check.group_num_members
            attendee_update = db.session.query(groupEventDetails.attending_count).filter(groupEventDetails.event_id==eventID).filter(groupEventDetails.deleted == False).first()
            attendees_check = db.session.query(groupEventUsers.attendee_id).filter(groupEventUsers.event_role.in_(['M','O'])).filter(groupEventUsers.event_id==eventID).count()
            if attendee_update is not None:
                if attendees_check is None:
                    update_num = 0
                else:
                    update_num=attendees_check
                if attendee_update.attending_count != attendees_check:
                    db.session.query(groupEventDetails.attending_count).filter(groupEventDetails.deleted == False).filter(groupEventDetails.event_id==eventID).update({'attending_count':update_num})
            event_search = db.session.query(groupEventDetails.event_name, groupEventDetails.event_description, groupEventDetails.event_start, groupEventDetails.event_end, groupEventDetails.attending_count, groupEventDetails.event_post_count, groupEventUsers.event_role).filter(groupEventDetails.deleted == False).filter(groupEventDetails.event_id==eventID).outerjoin(groupEventUsers).first()
            result['status']='success'
            if event_search != []:
                label = ['chapterName','chapterDescription','timestampChapterStart','timestampChapterEnd','attendingCount','chapterPostCount','amIAttending'] 
                result['chapterInfo']=add_labels(label, event_search)
                if lastPostID == 0:
                    event_post_search = db.session.query(groupEventPosts.group_event_post_id, groupEventPosts.cell_type, groupEventPosts.image_key, groupEventPosts.group_event_post_cont, groupEventPosts.date_time, groupEventPosts.date_time_edited, users.u_id, users.u_key, users.u_name, users.u_handle, users.firebase_id, groupMembers.member_role, groupEventPosts.points_count, eventPostUpvoted.points, groupEventPosts.is_pinned).filter(groupEventPosts.deleted==False).filter(groupEventPosts.group_event_post_u_id == users.u_id).filter(groupEventPosts.event_id==eventID).filter(groupEventPosts.group_id == groupMembers.group_id).filter(groupMembers.member_id == users.u_id).filter(groupEventPosts.group_event_post_u_id==users.u_id).outerjoin(eventPostUpvoted, and_(eventPostUpvoted.post_id==groupEventPosts.group_event_post_id, eventPostUpvoted.voter_id==userID)).distinct().order_by(groupEventPosts.group_event_post_id.desc()).limit(DEFAULT_LIMIT)   
                else:
                    event_post_search = db.session.query(groupEventPosts.group_event_post_id, groupEventPosts.cell_type, groupEventPosts.image_key, groupEventPosts.group_event_post_cont, groupEventPosts.date_time, groupEventPosts.date_time_edited, users.u_id, users.u_key, users.u_name, users.u_handle, users.firebase_id, groupMembers.member_role, groupEventPosts.points_count, eventPostUpvoted.points, groupEventPosts.is_pinned).filter(groupEventPosts.deleted==False).filter(groupEventPosts.group_event_post_id < lastPostID).filter(groupEventPosts.group_event_post_u_id == users.u_id).filter(groupEventPosts.event_id==eventID).filter(groupEventPosts.group_id == groupMembers.group_id).filter(groupMembers.member_id == users.u_id).filter(groupEventPosts.group_event_post_u_id==users.u_id).outerjoin(eventPostUpvoted, and_(eventPostUpvoted.post_id==groupEventPosts.group_event_post_id, eventPostUpvoted.voter_id==userID)).distinct().order_by(groupEventPosts.group_event_post_id.desc()).limit(DEFAULT_LIMIT)
                if event_post_search != []:
                    eventLabel = ['postID', 'chapterCellType', 'imageKey', 'postContent', 'timestamp', 'timestampEdited', 'userID', 'key', 'userName', 'userHandle', 'firebaseID', 'memberRole', 'pointsCount', 'didIVote','isPinned']
                    result['chapterPosts'] = add_labels(eventLabel, event_post_search, 'bucket', PROF_BUCKET, None, 'imageBucket', EVENT_BUCKET, keySize=size) 
                    result['message'] = 'Chapter found. Chapter posts found'
                else:
                    result['message'] = 'Chapter found. Chapter posts not found'
                    result['chapterPosts'] = []
            else:
                result['message'] = 'Chapter Not Found.'
        else:
            result['message'] = 'Unauthorized'
            result['status'] = 'success'
        db.session.commit()
    except Exception, e:
        db.session.rollback()
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Chapter not found'}        
        pass
    finally:
        db.session.close()
    return json.dumps(result)

@application.route('/getChapterList', methods=['POST']) #if group is readable, events show up even to non-members bad Idea?
def getChapterList():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','poolID','lastChapterID')):
            userID = request.form['myID']
            groupID = request.form['poolID']
            lastEventID = request.form['lastChapterID']
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)    
    try:
        member_check = db.session.query(groupMembers.member_role).filter(groupMembers.member_id==userID).filter(groupMembers.group_id==groupID).filter(groupMembers.member_role.in_(('M','H','O'))).first()
        publ = db.session.query(groupDetails.group_readable).filter(groupDetails.group_id==groupID).one()
        if (member_check is not None and member_check != []) or publ==True:
            result['myMemberRole']=member_check.member_role        
            event_check = db.session.query(groupEventDetails.event_id, groupEventDetails.event_name, groupEventDetails.event_description, groupEventDetails.event_start, groupEventDetails.event_end, groupEventDetails.event_post_count).filter(groupEventDetails.group_id==groupID).filter(groupEventDetails.deleted == False).filter(groupEventDetails.event_id > lastEventID).order_by(groupEventDetails.event_start.desc()).distinct().limit(DEFAULT_LIMIT)
            #or_(groupEventUsers.attendee_id==groupMembers.member_id,
            if event_check is not None and event_check.count() !=0: 
                last_event=0
                for k in event_check:
                    if k is not None and k != []:
                        if k.event_id > last_event:
                            last_event=k.event_id 
                    else:
                        break
                if last_event != 0:    
                    db.session.query(groupMembers.last_event_seen).filter(groupMembers.member_id==userID).filter(groupMembers.group_id==groupID).filter(groupMembers.member_role.in_(('M','H','O'))).update({'last_event_seen':last_event}, synchronize_session='fetch')
                    label = ['chapterID','chapterName','chapterDescription','timestampChapterStart','timestampChapterEnd','chapterPostCount']    
                    result['chapters']= add_labels(label, event_check)
                    result['status'] = 'success'
                    result['message'] = 'Chapters Found'
                    db.session.commit()
                else:
                    result['status'] = 'error'
                    result['message'] = 'Error retrieving chapter'
            else:
                result['status'] = 'success'
                result['message'] = 'No events Found' 
        else:
            result={'status':'success','myMemberRole':'N','message':'Not a member of this pool!'} 
    except Exception, e:
        db.session.rollback()
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Chapters not found'}        
        pass
    finally:
        db.session.close()
    data = json.dumps(result)
    return data

@application.route('/sendChapterPost', methods=['POST'])
def sendChapterPost():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','poolID', 'postContent', 'chapterCellType','chapterID')):
            userID = request.form['myID']
            groupID = request.form['poolID']
            eventID = request.form['chapterID']
            tempCellType = request.form['chapterCellType']
            if tempCellType == 'image':
                cellType = 'I'
            elif tempCellType == 'text':
                cellType = 'T'
            else:
                return json.dumps(result)
            messgCont = request.form['postContent']
            userHandles=[]
            if 'userHandles' in request.form:
                userHandles=parseHandles(request.form['userHandles'])
        else:
            return json.dumps(result)
    else:    
        return json.dumps(result)
    data_entered = groupEventPosts(event_id=eventID, group_id=groupID, group_event_post_u_id=userID, group_event_post_cont=messgCont, cell_type=cellType)
    try:
        member_check = db.session.query(groupMembers.member_role, users.u_handle).filter(groupMembers.member_id==userID).filter(users.u_id==groupMembers.member_id).filter(groupMembers.group_id==groupID).filter(groupMembers.member_role.in_(('M','H','O'))).first()
        chapter_check = db.session.query(groupEventDetails.event_name, groupDetails.group_handle).filter(groupEventDetails.deleted == False).filter(groupEventDetails.event_id==eventID).filter(groupEventDetails.group_id==groupDetails.group_id).first()
        if member_check is not None and member_check != []:
            db.session.add(data_entered)
            db.session.flush()
            result['chapterName']=chapter_check.event_name
            result['postID']=data_entered.group_event_post_id
            db.session.query(groupEventDetails).filter(groupEventDetails.deleted == False).filter(groupEventDetails.event_id==eventID).update({'event_post_count':groupEventDetails.event_post_count + 1})
            db.session.commit()
            result['status'] = 'success'
            result['message'] = 'Posted'
            if cellType == 'I':
                try:
                    event_post_check = db.session.query(groupEventPosts).filter(groupEventPosts.event_id==eventID).filter(groupEventPosts.group_id==groupID).filter(groupEventPosts.group_event_post_u_id==userID).filter(groupEventPosts.cell_type=='I').distinct().order_by(groupEventPosts.group_event_post_id.desc()).first()
                    if event_post_check is not None and event_post_check != []:
                        file_name=str(result['postID'])+'_eventPostPic'
                        event_post_check.image_key = file_name
                        db.session.commit()
                        result['imageKey'] = file_name+'_small'
                        result['imageBucket'] = EVENT_BUCKET
                    else:
                        result['uploadStatus'] = 'error'
                        result['message'] = 'image not saved'
                except Exception, e:
                    result['uploadStatus'] = str(e)
                    pass    
        if userHandles != []:
            tagged = sendTagNotifications(userHandles, member_check.u_handle, userID, 'getChapterList','chapter', messgCont, data_entered.group_event_post_id, groupID=groupID, poolHandle=chapter_check.group_handle , chapterName=chapter_check.event_name, eventID=eventID)
            result['numTagged'] = len(userHandles)
            if tagged:
                result['taggedNotifications']='success'
            else:
                result['taggedNotifications']=tagged
            db.session.commit()
    except Exception, e:
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result['status'] = 'error'
            result['message'] = 'Post not sent'# + str(err)
        db.session.rollback()
        pass    
    finally:
        db.session.close()
    data = json.dumps(result)
    return data

@application.route('/poolMemberSearch', methods=['POST'])
def poolMemberSearch():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','poolID','size','lastUserName','criteria')):
            userID = request.form['myID']
            groupID = request.form['poolID']
            lastUserName = request.form['lastUserName']
            criteria = request.form['criteria']
            if request.form['size'] in ('small','medium','large'):
                size = request.form['size']
            else:
                return json.dumps(result)
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    try:
        member_check = db.session.query(groupMembers.member_role, groupDetails.group_invite_only, groupDetails.group_searchable, groupDetails.group_readable, groupDetails.group_on_profile).filter(groupMembers.member_id==userID).filter(groupDetails.group_id==groupMembers.group_id).filter(groupMembers.group_id==groupID).filter(groupMembers.member_role.in_(('M','H','O'))).first()
        if member_check is not None and member_check != []:
            search_term='%'+criteria+'%'
            member_search = db.session.query(users.u_id,users.u_name, users.u_handle, users.firebase_id, users.u_key, groupMembers.member_role).filter(or_(users.u_handle.like(search_term), users.u_name.like(search_term))).filter(users.u_id != userID).filter(users.u_id==groupMembers.member_id).filter(groupMembers.group_id==groupID).filter(groupMembers.member_role.in_(('M','H','O'))).filter(users.u_name > lastUserName).order_by(users.u_name.asc()).distinct().limit(DEFAULT_LIMIT)
            labels = ['userID','userName','userHandle','firebaseID','key','memberRole']
            result['members'] = add_labels(labels, member_search, 'bucket', PROF_BUCKET, keySize=size)
            result['status'] = 'success'
            result['message'] = 'Pool members found'
        else:
            result['status'] = 'success'
            result['message'] = 'No pool members found'
        db.session.close()        
    except Exception, e:
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Members not found'}
        pass
    data = json.dumps(result)
    return data



@application.route('/getPoolMemberList', methods=['POST']) 
def getPoolMemberList():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','poolID','size','lastUserName','showOnlyRequestList')):
            userID = request.form['myID']
            groupID = request.form['poolID']
            lastUserName = request.form['lastUserName']
            showRequested = request.form['showOnlyRequestList']
            if request.form['size'] in ('small','medium','large'):
                size = request.form['size']
            else:
                return json.dumps(result)
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    try:
        member_check = db.session.query(groupMembers.member_role, groupDetails.group_invite_only, groupDetails.group_handle).filter(groupMembers.member_id==userID).filter(groupDetails.group_id==groupMembers.group_id).filter(groupMembers.group_id==groupID).filter(groupMembers.member_role.in_(('M','H','O'))).first()
        if member_check is not None and member_check != []:
            result['myMemberRole'] = member_check.member_role
            result['poolHandle']= member_check.group_handle
            member_search = db.session.query(groupMembers.member_role, users.u_id, users.firebase_id, users.u_name, users.u_handle, users.u_key, groupMembers.member_message).filter(groupMembers.member_id == users.u_id).filter(groupMembers.group_id == groupID).filter(groupMembers.member_role.in_(['O','H','M','B','S','I'])).filter(users.u_name > lastUserName).order_by(users.u_name.asc()).all() 
            members=filter_members(member_search, keySize=size)
            if (member_check.member_role in ('O','H') or member_check.group_invite_only =='N' or (member_check.group_invite_only == 'M' and member_check.member_role == 'M')) and showRequested=='yes':
                result['receivedRequests']=members['receivedRequests'] #user sent to group
                #result['sentRequests']=members['sentRequests'] # group sent to user
                result['blocked']=members['blocked']
            elif showRequested == 'no':
                #result['test']=members
                result['owner']=[]
                result['hosts']=[]
                result['members']=[]
                for x in members['members']:
                    if x['memberRole'] == 'O':
                        result['owner'].append(x)
                    elif x['memberRole'] == 'H':
                        result['hosts'].append(x)
                    elif x['memberRole'] == 'M':
                        result['members'].append(x)
                #result['owner'] = {key:members[key] for i, key in members.iteritems() if members[key]['memberRole']=='O'}
                #result['hosts'] = {key:members[key] for i, key in members.iteritems() if members[key]['memberRole']=='H'}
                #result['members']= {key:members[key] for i, key in members.iteritems() if members[key]['memberRole']=='M'}                
            result['status'] = 'success'
            result['message'] = 'Pool members found'
            members_count = db.session.query(groupMembers.member_role).filter(groupMembers.group_id==groupID, groupMembers.member_role.in_(('M','H','O'))).count()
            db.session.query(groupDetails.group_num_members).filter(groupDetails.group_id == groupID).update({'group_num_members':members_count})
            db.session.commit()
        else:
            result['status'] = 'success'
            result['message'] = 'No pool members found'
        db.session.close()        
    except Exception, e:
        db.session.rollback()
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Members not found'}        
        pass
    data = json.dumps(result)
    return data

@application.route('/editPoolMemberList', methods=['POST']) 
def editPoolMemberList(): #must be member from member perspective
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','poolID','userID','action')):
            myID = request.form['myID']
            groupID = request.form['poolID']
            userID = request.form['userID']
            action = request.form['action']
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)    
    try:
        member_admin_check = db.session.query(groupDetails.group_invite_only, groupMembers.member_role).filter(groupMembers.member_id==myID).filter(groupMembers.group_id==groupID).filter(groupMembers.member_role.in_(('M','H','O'))).filter(groupDetails.group_id == groupID).first()
        if member_admin_check.member_role in('M','H') and action == 'leavePool' and userID==myID:
            result['status'] = 'success'
            result['message'] = 'Action complete' 
            db.session.query(groupMembers.member_role).filter(groupMembers.member_id==userID).filter(groupMembers.group_id==groupID).filter(groupMembers.member_role.in_(('M','H'))).update({'member_role':'N'}, synchronize_session='fetch')
            db.session.commit()
        elif member_admin_check.member_role in ('H','O') or member_admin_check.group_invite_only =='M':
            other_group_check = db.session.query(groupMembers.member_role).filter(groupMembers.member_id==userID, groupMembers.group_id==groupID).first()
            if other_group_check is not None and other_group_check != []:
                approver = None
                myNewRole = None
                newMemberRole = None  
                memberChange = 0
                sendNotice = False
                if other_group_check.member_role in ('S','I'):
                    result['status'] = 'success'
                    result['message'] = 'Action complete' 
                    if action == 'denyRequest': #withdraw or refuse
                        newMemberRole = 'N'
                        approver = myID
                    elif action == 'acceptRequest': # or action == 'invite':
                        newMemberRole = 'M'
                        approver = myID
                        memberChange = 1
                    elif action == 'invite':
                        if other_group_check.member_role == 'S':
                            newMemberRole = 'M'
                            approver = myID
                            memberChange = 1
                            sendNotice = True
                        else:
                            result['message'] = 'Invalid action'
                elif other_group_check.member_role in ('M','H','O','N','B'): 
                    result['status'] = 'success'
                    result['message'] = 'Action complete'         
                    approver = None
                    newMemberRole = None  
                    oneLessMember = False
                    if action == 'makeHost' and other_group_check.member_role == 'M':
                        newMemberRole = 'H'
                        approver = myID
                    elif action == 'removeHost' and other_group_check.member_role == 'H':
                        newMemberRole = 'M'
                        approver = myID
                    elif action == 'removeMember' and other_group_check.member_role != 'O':
                        newMemberRole = 'N'
                        approver = myID
                        memberChange = -1
                    elif action == 'makeOwner' and member_admin_check.member_role == 'O':
                        myNewRole = 'H'
                        newMemberRole = 'O'
                        approver = myID
                    elif action == 'invite' and other_group_check.member_role in ('N','B'):
                        newMemberRole = 'I'
                        approver = myID
                        sendNotice = True
                    elif action == 'blockUser':
                        newMemberRole = 'B'
                        approver = myID
                    else:
                        result = {'status':'error', 'message':'Invalid request'}
                        newMemberRole = None
                        approver = None
                if newMemberRole is not None and approver is not None:
                    if myNewRole is not None:
                        db.session.query(groupMembers.member_role, groupMembers.approved_by).filter(groupMembers.member_id==myID, groupMembers.group_id==groupID).update({'member_role':myNewRole, 'approved_by':approver})
                    db.session.query(groupMembers.member_role, groupMembers.approved_by).filter(groupMembers.member_id==userID, groupMembers.group_id==groupID).update({'member_role':newMemberRole, 'approved_by':approver})
                if memberChange != 0:
                    db.session.query(groupDetails.group_num_members).filter(groupDetails.group_id==groupID).update({'group_num_members':groupDetails.group_num_members + memberChange})
                db.session.commit()
            elif action == 'blockUser':
                result['status'] = 'success'
                result['message'] = 'Action complete' 
                block_data = groupMembers(groupID, userID, 'B')
                db.session.add(block_data)
            elif action == 'unblockUser':
                block_check = db.session.query(groupMembers).filter(groupMembers.group_id==groupID).filter(groupMembers.member_id==userID).first()
                if block_check is not None and block_check != []:
                    db.session.query(groupMembers).filter(groupMembers.group_id==groupID).filter(groupMembers.member_id==userID).update({'member_role':'N'})
                    result['status'] = 'success'
                    result['message'] = 'Action complete' 
            elif action == 'invite':
                result['status'] = 'success'
                result['message'] = 'Action complete' 
                member_data = groupMembers(groupID, userID, 'I')
                db.session.add(member_data)
                sendNotice = True
            elif action == 'leavePool' and member_admin_check.member_role != 'O' and userID==myID:
                result['status'] = 'success'
                result['message'] = 'Action complete'
                db.session.query(groupMembers.member_role).filter(groupMembers.member_id==userID).filter(groupMembers.group_id==groupID).filter(groupMembers.member_role.in_(('M','H'))).update({'member_role':'N'})
            else:
                result = {'status':'error', 'message':'Invalid request'}
            if sendNotice:
                user_check = db.session.query(users.device_arn, users.firebase_id).filter(users.u_id==userID).one()
                group_check = db.session.query(groupDetails.group_handle).filter(groupDetails.group_id==groupID).one()
                subj = 'getPoolList'
                cont = '.'+group_check.group_handle + ' has sent you a Pool request.'
                notificUID=userID
                notificType='M'
                inNot = inNotification(user_check.firebase_id)
                if inNot==True:
                    result['notificationSent']=logNotification(notificUID, cont, subj, notificType)
                    firebaseNotification(user_check.firebase_id, cont)
                if user_check is not None and user_check != [] and group_check is not None and group_check != []:
                    if user_check.device_arn !=0 and inNot==False:
                        result['notificationSent']=logNotification(notificUID, cont, subj, notificType)
                        firebaseNotification(user_check.firebase_id, cont)      
                        db.session.commit()
                        badge = db.session.query(notific.notific_id).filter(notific.n_u_id==userID).filter(notific.notific_seen==False).count()
                        push(user_check.device_arn, badge, cont, subj)  
        elif member_admin_check.member_role in ('M','H','O') and action == 'invite' and member_admin_check.group_invite_only == 'N' and userID != myID:
            other_group_check = db.session.query(groupMembers.member_role).filter(groupMembers.member_id==userID, groupMembers.group_id==groupID).first()
            sendNotice = False
            if other_group_check is not None and other_group_check.member_role == 'N':
                db.session.query(groupMembers.member_role).filter(groupMembers.group_id==groupID).filter(groupMembers.member_id==userID).update({'member_role':'I'}) 
                sendNotice = True               
            elif other_group_check is not None:
                result['status'] = 'error'
                result['message'] = 'Invalid Request'
            else:
                member_data = groupMembers(groupID, userID, 'I')
                db.session.add(member_data)
                sendNotice = True
            if sendNotice:
                result['status'] = 'success'
                result['message'] = 'Action complete' 
                user_check = db.session.query(users.device_arn, users.firebase_id).filter(users.u_id==userID).one()
                group_check = db.session.query(groupDetails.group_handle).filter(groupDetails.group_id==groupID).one()
                subj = 'getPoolList'
                cont = '.'+group_check.group_handle + ' has sent you a Pool request.'
                notificUID=userID
                notificType='M'
                inNot = inNotification(user_check.firebase_id)
                if inNot == True:
                    result['notificationSent']=logNotification(notificUID, cont, subj, notificType)
                    firebaseNotification(user_check.firebase_id, cont)
                if user_check is not None and user_check != [] and group_check is not None and group_check != []:
                    if user_check.device_arn !=0 and inNot == False:
                        result['notificationSent']=logNotification(notificUID, cont, subj, notificType)
                        firebaseNotification(user_check.firebase_id, cont)   
                        db.session.commit()
                        badge = db.session.query(notific.notific_id).filter(notific.n_u_id==userID).filter(notific.notific_seen==False).count()
                        push(user_check.device_arn, badge, cont, subj)     
        else:
            result = {'status':'error', 'message':'Unauthorized'}
        db.session.commit()
    except Exception, e:
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Pool membership not changed'}
        db.session.rollback()
        pass    
    finally:
        db.session.close()
    data = json.dumps(result)
    return data

@application.route('/interactPoolRequest', methods=['POST'])
def interactPoolRequest():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','poolID','action')):
            requesterID = request.form['myID']
            groupID = request.form['poolID']
            action = request.form['action'] # request, accept, deny, withdraw
            if 'userMessage' in request.form:
                userMessage = request.form['userMessage']
            else:
                userMessage = 'N/A'
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    try:
        group_check=db.session.query(groupDetails.group_invite_only).filter(groupDetails.group_id == groupID).first()
        if group_check is not None and group_check !=[]: #actions
            last_post_check = db.session.query(groupPosts.group_post_id).filter(groupPosts.group_id==groupID).order_by(groupPosts.group_post_id.desc()).first()
            last_event_check = db.session.query(groupEventDetails.event_id).filter(groupEventDetails.group_id==groupID).filter(groupEventDetails.deleted == False).order_by(groupEventDetails.event_id).first()
            if last_post_check is not None and last_post_check != []:
                lastPost = last_post_check.group_post_id
            else:      
                lastPost = None
            if last_event_check is not None and last_event_check !=[]:
                lastEvent = last_event_check.event_id
            else:       
                lastEvent = None    
            if action == 'request':
                member_check = db.session.query(groupMembers.member_role).filter(groupMembers.member_id==requesterID).filter(groupMembers.group_id==groupID).first()
                if member_check is not None and member_check.member_role != 'B':
                    if group_check.group_invite_only == 'N':
                        #db.session.query(groupMembers.member_role).filter(groupMembers.member_id==requesterID).filter(groupMembers.group_id==groupID).update({'member_role':'M', 'member_message':userMessage, 'last_post_seen':group_check.group_post_id})
                        updateData = {'member_role':'M', 'member_message':userMessage}
                        if lastPost is not None:
                            updateData.update({'last_post_seen':lastPost,'last_host_post_seen':lastPost})
                        if lastEvent is not None:
                            updateData.update({'last_event_seen':lastEvent})
                        result['status']= 'success'
                        result['message'] = 'joined pool'
                    elif member_check.member_role == 'S':
                        #db.session.query(groupMembers.member_role, groupMembers.last_post_seen).filter(groupMembers.member_id==requesterID).filter(groupMembers.group_id==groupID).update({'member_role':'M','member_message':userMessage, 'last_post_seen':group_check.group_post_id})
                        updateData = {'member_role':'M','member_message':userMessage}
                        if lastPost is not None:
                            updateData.update({'last_post_seen':lastPost,'last_host_post_seen':lastPost})
                        if lastEvent is not None:
                            updateData.update({'last_event_seen':lastEvent})
                        result['status']= 'success'
                        result['message'] = 'joined pool'
                    else:    
                        #db.session.query(groupMembers.member_role).filter(groupMembers.member_id==requesterID).filter(groupMembers.group_id==groupID).update({'member_role':'S','member_message':userMessage})
                        updateData = {'member_role':'S','member_message':userMessage}
                        result['status']='success'
                        result['message'] = 'request sent' 
                        groupInteractRequestHelper(requesterID, groupID)
                    db.session.query(groupMembers.member_role).filter(groupMembers.member_id==requesterID).filter(groupMembers.group_id==groupID).update(updateData)
                elif group_check.group_invite_only == 'N':
                    member_data = groupMembers(group_id=groupID, member_id=requesterID, member_role='M') 
                    db.session.query(groupDetails.group_num_members).filter(groupDetails.group_id == groupID).update({'group_num_members':groupDetails.group_num_members + 1})
                    db.session.add(member_data)
                    result['status']='success'
                    result['message'] = 'added to pool'
                else:
                    member_data = groupMembers(group_id=groupID, member_id=requesterID, member_role='S', member_message=userMessage)
                    db.session.add(member_data)
                    result['status']='success'
                    result['message'] = 'request sent' 
                    groupInteractRequestHelper(requesterID, groupID)
                    '''
                    user_check = db.session.query(users.u_handle, users.device_arn, users.firebase_id).filter(users.u_id==requesterID).one()
                    group_host_check = db.session.query(users.u_id, users.device_arn, groupDetails.group_handle).filter(groupMembers.group_id==groupID).filter(groupDetails.group_id == groupID).filter(or_(groupMembers.member_role=='O', groupMembers.member_role=='H')).filter(groupMembers.member_id==users.u_id).distinct().all()
                    if ((user_check is not None) and (user_check != []) and (group_host_check is not None) and (group_host_check != [])):
                        for g in group_host_check:
                            subj = 'getGroupProfile'
                            cont = '@'+user_check.u_handle + ' has sent .'+g.group_handle + ' a request'
                            notificType='R'
                            notificUID=g.u_id
                            logNotification(notificUID, cont, subj, notificType, notificGroupID=groupID)
                            firebaseNotification(user_check.firebase_id, cont)
                            if g.device_arn !=0:
                                badge = db.session.query(notific.notific_id).filter(notific.n_u_id==g.u_id).filter(notific.notific_seen==False).count()
                                push(g.device_arn, badge, cont, subj)
                    '''
            elif action in ('accept','deny','withdraw'):
                request_check = db.session.query(groupMembers.member_role).filter(groupMembers.member_id==requesterID).filter(groupMembers.group_id==groupID).first()
                #print request_check.member_role
                newRole = None
                if request_check.member_role == 'I': #invited to group (group > user)
                    if action == 'accept':
                        newRole = 'M'
                        result['status'] = 'success'
                        result['message'] = 'Request accepted'
                        db.session.query(groupDetails.group_num_members).filter(groupDetails.group_id == groupID).update({'group_num_members':groupDetails.group_num_members + 1})
                    elif action =='deny':
                        newRole = 'N'
                        result['status'] = 'success'
                        result['message'] = 'Request denied'
                    else:
                        return json.dumps(result)
                elif request_check.member_role == 'S':
                    if action == 'withdraw':
                        newRole = 'N'
                        result['status'] = 'success'
                        result['message'] = 'Request withdrawn'
                    else:
                        return json.dumps(result) 
                if newRole is not None:
                    updateData = {'member_role':newRole}
                    if lastPost is not None:
                        updateData.update({'last_post_seen':lastPost,'last_host_post_seen':lastPost})
                    if lastEvent is not None:
                        updateData.update({'last_event_seen':lastEvent})
                    db.session.query(groupMembers.member_role).filter(groupMembers.member_id==requesterID).filter(groupMembers.group_id==groupID).update(updateData) 
            else:
                return json.dumps(result)
            db.session.commit()
    except Exception, e:
        db.session.rollback()
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Request not updated'}        
        pass
    finally:
        db.session.close()
    data = json.dumps(result)
    return data

@application.route('/myInvitablePoolList', methods=['POST'])
def myInvitablePoolList():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','lastPoolName','userID')):
            user_id = request.form['myID']
            lastGroupName = request.form['lastPoolName']
            otherID = request.form['userID']
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    try:
        otherGroupMembers = aliased(groupMembers)
        group_list = db.session.query(groupDetails.group_id, users.u_id, users.u_name, users.u_handle, users.u_key, groupDetails.group_name, groupDetails.group_handle, groupDetails.group_key, groupMembers.member_role,  groupMembers.last_post_seen, otherGroupMembers.member_role.label("otherRole")).filter(groupDetails.group_active == 'Y').filter(groupMembers.member_id==users.u_id).filter(groupMembers.group_id==groupDetails.group_id).filter(groupMembers.member_id==user_id).filter(groupMembers.member_role.in_(('M','H','O'))).filter(or_(or_(groupDetails.group_invite_only == 'M', groupDetails.group_invite_only =='N'),and_(groupDetails.group_invite_only=='H',groupMembers.member_role.in_(('O','H'))))).filter(groupDetails.group_name > lastGroupName).outerjoin(otherGroupMembers, and_(otherGroupMembers.member_id==otherID,otherGroupMembers.group_id==groupDetails.group_id)).order_by(groupDetails.group_name.asc()).distinct().limit(DEFAULT_LIMIT)
        result['status']='success'
        if group_list != []:
            result['message']='Pools Found'
            groups = filter_groups(group_list, otherCheck=True)      
            result['pools'] = groups['currentGroups']
            '''            
            for a in groups:
                result[a]=groups[a]
            '''
        else:
            result['message'] = 'No groups found'
    except Exception, e:
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Pools not found'}
    finally:
        db.session.close()
    data = json.dumps(result)
    return data

@application.route('/interactChapter', methods=['POST'])
def interactChapter():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','chapterID','poolID','action')):
            userID = request.form['myID']
            groupID = request.form['poolID']
            eventID = request.form['chapterID']
            action = request.form['action'] #joinEvent, leaveEvent, getUsers, delete
            if action == 'getUsers':
                if all (j in request.form for j in ('size','lastUserName')) and request.form['size'] in ('small','medium','large'):
                    lastUserName=request.form['lastUserName']
                    size = request.form['size']
                else:
                    return json.dumps(result)
            else:
                lastUserName='0'
                size = ''
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    try:
        member_check = db.session.query(groupMembers.member_role).filter(groupMembers.member_id==userID).filter(groupMembers.group_id==groupID).filter(groupMembers.member_role.in_(('M','H','O'))).first()
        if member_check is not None and member_check != []:
            if action == 'joinChapter':            
                event_check = db.session.query(groupEventUsers.attendee_id, groupEventUsers.event_role).filter(groupEventUsers.event_id == eventID).filter(groupEventUsers.attendee_id == userID).first()
                if event_check is not None and member_check != []:
                    if event_check.event_role=='W':
                        newRole='O'
                    elif event_check.event_role=='N':
                        newRole='M'
                    else:
                        newRole=None
                    if newRole is not None:
                        db.session.query(groupEventUsers.event_role).filter(groupEventUsers.event_id==eventID).filter(groupEventUsers.attendee_id==userID).update({'event_role':newRole})
                        db.session.query(groupEventDetails.attending_count).filter(groupEventDetails.event_id==eventID).filter(groupEventDetails.deleted == False).update({'attending_count':groupEventDetails.attending_count+1})
                        result['message']='Joined Chapter'
                        result['status']='success'
                    else:
                        result['message']='Already attending chapter!'
                        result['status']='success'
                else:
                    event_member_data = groupEventUsers(event_id=eventID, attendee_id=userID, event_role='M')
                    db.session.add(event_member_data)
                    db.session.query(groupEventDetails.attending_count).filter(groupEventDetails.event_id==eventID).filter(groupEventDetails.deleted == False).update({'attending_count':groupEventDetails.attending_count+1})
                    result['message']='Joined Chapter'
                    result['status']='success'
            elif action == 'leaveChapter':
                event_check = db.session.query(groupEventUsers.attendee_id, groupEventUsers.event_role).filter(groupEventUsers.event_id == eventID).filter(groupEventUsers.attendee_id == userID).first()
                if event_check is not None and event_check !=[]:
                    if event_check.event_role=='M':
                        newRole='N'
                    elif event_check.event_role=='O':
                        newRole='W'
                    else:
                        newRole=None
                    if newRole is not None:
                        db.session.query(groupEventUsers.event_role).filter(groupEventUsers.event_id == eventID).filter(groupEventUsers.attendee_id == userID).update({'event_role':newRole})
                        db.session.query(groupEventDetails.attending_count).filter(groupEventDetails.event_id==eventID).filter(groupEventDetails.deleted == False).update({'attending_count':groupEventDetails.attending_count-1})
                        result['message']='Successfully left chapter'
                        result['status']='success'
                    else:
                        result['message']='Not attending the chapter'
                        result['status']='success'
                else:
                    result['message']='Not attending the momenbt'
                    result['status']='success'
            elif action =='getUsers':
                event_member_search = db.session.query(users.u_name, users.u_handle, users.u_key).filter(groupEventUsers.event_id==eventID).filter(groupEventUsers.attendee_id==users.u_id).filter(groupMembers.member_id==users.u_id).filter(groupMembers.member_id==userID).filter(groupMembers.member_role.in_(('M','H','O'))).filter(users.u_name > lastUserName).order_by(users.u_name.asc()).limit(DEFAULT_LIMIT)
                label = ['userName','userHandle','key']
                result['users'] = add_labels(label,event_member_search,'bucket',PROF_BUCKET, keySize=size)
                result['message']='Users found'
                result['status']='success'
            elif action == 'delete' and member_check.member_role in ('O','H'):
                event_num_check = db.session.query(groupEventUsers.attendee_id).filter(groupEventUsers.event_id==eventID).filter(groupEventUsers.event_role.in_(('M','O'))).count()
                if event_num_check == 0:
                    result['status'] = 'error'
                    result['message'] = 'Users attending Chapter'
                else:
                    db.session.query(groupEventDetails.deleted).filter(groupEventDetails.event_id==eventID).filter(groupEventDetails.group_id==groupID).update({'deleted':True})
        else:
            result = {'status':'success', 'message':'Unauthorized'}
        db.session.commit()
    except Exception, e:
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Chapter not updated'}        
        db.session.rollback()
        pass    
    finally:
        db.session.close()
    data = json.dumps(result)
    return data

@application.route('/retrievePoint', methods=['POST'])
def retrievePoint():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if 'myID' in request.form: 
            userID = request.form['myID']
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    try:
        userProf_check = db.session.query(users).filter_by(u_id=userID).first()
        if userProf_check is not None and userProf_check != []:
            result['status'] = 'success'
            result['message'] = 'successfully retrieved point information'
            '''
            if (datetime.now() - userProf_check.last_stipend_date > DEFAULT_STIPEND_TIME):
                    userProf_check.stipend_points = DEFAULT_STIPEND
                    db.session.commit()     
            '''
            result['weeklyPoints'] = userProf_check.u_stipend_points
            result['myPoints'] = userProf_check.u_personal_points
    except Exception, e:
        db.session.rollback()
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Points not found'}        
        pass
    finally:
        db.session.close()
    data = json.dumps(result)
    return data
        
@application.route('/sendPoint', methods=['POST']) #keep track of points that were added
def sendPoint():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','postType', 'postID','amount')):
            userID = request.form['myID']
            postID = request.form['postID']
            postType = request.form['postType'] #forum, anon, group, event, pinned, scrap, scrapImage
            numPoints = int(request.form['amount'])
        else:
            return json.dumps(result)
    else:    
        return json.dumps(result)
    try: #add to sent points upvoted table
        user_check = db.session.query(users.u_personal_points, users.u_stipend_points, users.u_handle).filter(users.u_id==userID).first()
        userStipendChange, userPersonalChange, postPointChange, postUserPersonalChange = 0,0,0,0
        pointsChanged = False
        votedAlready = False
        groupID = None
        eventID = None
        if postType == 'pond':
            post_check = db.session.query(forumPosts.points_count, forumPosts.post_cont, users.u_personal_points, users.u_id, users.firebase_id).filter(forumPosts.post_id == postID).filter(users.u_id==forumPosts.post_u_id).filter(users.u_id != userID).first()
            point_check = db.session.query(forumPostUpvoted).filter(forumPostUpvoted.post_id==postID).filter(forumPostUpvoted.voter_id==userID).first()
            if point_check is not None and point_check != []:
                votedAlready = True
            if post_check is not None and post_check != []:
                if user_check.u_stipend_points >= numPoints:
                    userStipendChange = -numPoints
                    postPointChange = numPoints
                    postUserPersonalChange = numPoints
                    pointsChanged=True 
                elif user_check.u_stipend_points + user_check.u_personal_points >= numPoints:
                    userPersonalChange = -numPoints + user_check.u_stipend_points
                    userStipendChange = -user_check.u_stipend_points
                    postPointChange = numPoints
                    postUserPersonalChange = numPoints
                    pointsChanged = True
                else:
                    result['status'] = 'error'
                    result['message'] = 'Points not added'
            else:
                result['status'] = 'error'
                result['message'] = 'Points not added'
        elif postType == 'anon':
            post_check = db.session.query(anonForumPosts.a_points_count, anonForumPosts.a_post_cont, users.u_personal_points,users.u_id, users.firebase_id).filter(anonForumPosts.a_post_id == postID).filter(users.u_id==anonForumPosts.a_post_u_id).filter(users.u_id != userID).first()
            point_check = db.session.query(anonForumPostUpvoted).filter(anonForumPostUpvoted.post_id==postID).filter(anonForumPostUpvoted.voter_id==userID).first()
            if point_check is not None and point_check != []:
                votedAlready = True
            if post_check is not None and post_check != []:
                if user_check.u_stipend_points >= numPoints:
                    userStipendChange = -numPoints
                    postPointChange = numPoints
                    postUserPersonalChange = numPoints
                    pointsChanged=True 
                elif user_check.u_stipend_points + user_check.u_personal_points >= numPoints:
                    userPersonalChange = -numPoints + user_check.u_stipend_points
                    userStipendChange = -user_check.u_stipend_points
                    postPointChange = numPoints
                    postUserPersonalChange = numPoints
                    pointsChanged = True
                else:
                    result['status'] = 'error'
                    result['message'] = 'Points not added'
            else:
                result['status'] = 'error'
                result['message'] = 'Points not added'
        elif postType in ('host','pool'):
            post_check = db.session.query(groupPosts.points_count, groupPosts.group_id, groupPosts.group_post_cont, users.u_personal_points,groupPosts.group_id, users.u_id, users.firebase_id).filter(groupPosts.group_post_id == postID).filter(groupPosts.post_u_id==users.u_id).filter(groupMembers.group_id==groupPosts.group_id).filter(groupMembers.member_id==users.u_id).filter(groupMembers.member_role.in_(('M','H','O'))).filter(users.u_id != userID).first()
            point_check = db.session.query(groupPostUpvoted).filter(groupPostUpvoted.post_id==postID).filter(groupPostUpvoted.voter_id==userID).first()
            if point_check is not None and point_check != []:
                votedAlready = True
            if post_check is not None and post_check !=[]:
                member_check = db.session.query(groupMembers.member_role).filter(groupMembers.group_id==post_check.group_id).filter(groupMembers.member_id==userID).first()
                if member_check is not None and member_check.member_role in ('M','H','O'):
                    if user_check.u_stipend_points >= numPoints:
                        userStipendChange = -numPoints
                        postPointChange = numPoints
                        postUserPersonalChange = numPoints
                        pointsChanged=True  
                        groupID=post_check.group_id
                    elif user_check.u_stipend_points + user_check.u_personal_points >= numPoints:
                        userPersonalChange =  -numPoints + user_check.u_stipend_points
                        userStipendChange = -user_check.u_stipend_points
                        postPointChange = numPoints
                        postUserPersonalChange = numPoints
                        pointsChanged = True
                        groupID=post_check.group_id
                    else:
                        result['status'] = 'error'
                        result['message'] = 'Points not added'
                else:
                    result['status'] = 'error'
                    result['message'] = 'Points not added'
            else:
                result['status'] = 'error'
                result['message'] = 'Points not added'
        elif postType == 'chapter':
            post_check = db.session.query(groupEventPosts.points_count, groupDetails.group_id, groupDetails.group_handle, groupEventDetails.event_id, groupEventDetails.event_name, groupEventPosts.group_event_post_cont, users.u_personal_points,groupEventPosts.group_id, users.u_id, users.firebase_id).filter(groupDetails.group_id==groupEventPosts.group_id).filter(groupEventPosts.group_event_post_id == postID).filter(groupEventPosts.group_id==groupEventDetails.group_id).filter(groupEventPosts.group_event_post_u_id==users.u_id).filter(groupMembers.group_id==groupEventPosts.group_id).filter(groupMembers.member_id==users.u_id).filter(groupMembers.member_role.in_(('M','H','O'))).filter(users.u_id != userID).first()
            point_check = db.session.query(eventPostUpvoted).filter(eventPostUpvoted.post_id==postID).filter(eventPostUpvoted.voter_id==userID).first()
            if point_check is not None and point_check != []:
                votedAlready = True
            if post_check is not None and post_check !=[]:
                member_check = db.session.query(groupMembers.member_role).filter(groupMembers.group_id==post_check.group_id).filter(groupMembers.member_id==userID).first()
                if member_check is not None and member_check.member_role in ('M','H','O'):
                    if user_check.u_stipend_points >= numPoints:
                        userStipendChange = -numPoints
                        postPointChange = numPoints
                        postUserPersonalChange = numPoints
                        pointsChanged=True 
                        eventID = post_check.event_id
                        groupID = post_check.group_id
                    elif user_check.u_stipend_points + user_check.u_personal_points >= numPoints:
                        userPersonalChange =  -numPoints + user_check.u_stipend_points
                        userStipendChange = -user_check.u_stipend_points
                        postPointChange = numPoints
                        postUserPersonalChange = numPoints
                        pointsChanged = True
                        eventID = post_check.event_id
                        groupID = post_check.group_id
                    else:
                        result['status'] = 'error'
                        result['message'] = 'Points not added'
                else:
                    result['status'] = 'error'
                    result['message'] = 'Points not added'
            else:
                result['status'] = 'error'
                result['message'] = 'Points not added'
        elif postType in ('scrap','scrapImage'):
            post_check = db.session.query(pinnedPosts.points_count, pinnedPosts.pin_post_orig_cont, users.u_personal_points,users.u_id, users.firebase_id, pinnedPosts.pin_type).filter(pinnedPosts.pin_id == postID).filter(users.u_id==pinnedPosts.u_id).filter(users.u_id != userID).first()
            if post_check.pin_type=='I':
                postType='scrapImage'
            point_check = db.session.query(pinnedPostUpvoted).filter(pinnedPostUpvoted.post_id==postID).filter(pinnedPostUpvoted.voter_id==userID).first()
            if point_check is not None and point_check != []:
                votedAlready = True
            if post_check is not None and post_check != []:
                if user_check.u_stipend_points >= numPoints:
                    userStipendChange = -numPoints
                    postPointChange = numPoints
                    postUserPersonalChange = numPoints
                    pointsChanged=True 
                elif user_check.u_stipend_points + user_check.u_personal_points >= numPoints:
                    userPersonalChange = -numPoints + user_check.u_stipend_points
                    userStipendChange = -user_check.u_stipend_points
                    postPointChange = numPoints
                    postUserPersonalChange = numPoints
                    pointsChanged = True
                else:
                    result['status'] = 'error'
                    result['message'] = 'Points not added'
            else:
                result['status'] = 'error'
                result['message'] = 'Points not added'
        if pointsChanged:
            db.session.query(users).filter(users.u_id==userID).update({'u_stipend_points':users.u_stipend_points+userStipendChange, 'u_personal_points':users.u_personal_points+userPersonalChange})
            db.session.query(users).filter(users.u_id==post_check.u_id).update({'u_personal_points':users.u_personal_points+postUserPersonalChange})
            if postType =='pond':
                db.session.query(forumPosts).filter(forumPosts.post_id==postID).update({'points_count':forumPosts.points_count+postPointChange})
                if votedAlready:
                    db.session.query(forumPostUpvoted).filter(forumPostUpvoted.post_id==postID).filter(forumPostUpvoted.voter_id==userID).update({'points':forumPostUpvoted.points + numPoints})
                else:
                    db.session.add(forumPostUpvoted(voter_id = userID, post_id = postID, points = numPoints))
            elif postType in ('pool','host'):
                db.session.query(groupPosts).filter(groupPosts.group_post_id==postID).update({'points_count':groupPosts.points_count+postPointChange})                
                if votedAlready:
                    db.session.query(forumPostUpvoted).filter(forumPostUpvoted.post_id==postID).filter(forumPostUpvoted.voter_id==userID).update({'points':forumPostUpvoted.points + numPoints})
                else:
                    db.session.add(groupPostUpvoted(voter_id = userID, post_id = postID, points = numPoints))
            elif postType == 'chapter':
                db.session.query(groupEventPosts).filter(groupEventPosts.group_event_post_id==postID).update({'points_count':groupEventPosts.points_count+postPointChange})
                if votedAlready:
                    db.session.query(forumPostUpvoted).filter(forumPostUpvoted.post_id==postID).filter(forumPostUpvoted.voter_id==userID).update({'points':forumPostUpvoted.points + numPoints})
                else:
                    db.session.add(eventPostUpvoted(voter_id = userID, post_id = postID, points = numPoints))
            elif postType == 'anon':
                db.session.query(anonForumPosts).filter(anonForumPosts.a_post_id==postID).update({'a_points_count':anonForumPosts.a_points_count+postPointChange})
                if votedAlready:
                    db.session.query(anonForumPostUpvoted).filter(anonForumPostUpvoted.post_id==postID).filter(anonForumPostUpvoted.voter_id==userID).update({'points':anonForumPostUpvoted.points + numPoints})
                else:
                    db.session.add(anonForumPostUpvoted(voter_id = userID, post_id = postID, points = numPoints))
            elif postType in ('scrap','scrapImage'):
                db.session.query(pinnedPosts).filter(pinnedPosts.pin_id==postID).update({'points_count':pinnedPosts.points_count+postPointChange})
                if votedAlready:
                    db.session.query(pinnedPostUpvoted).filter(pinnedPostUpvoted.post_id==postID).filter(pinnedPostUpvoted.voter_id==userID).update({'points':pinnedPostUpvoted.points + numPoints})
                else:
                    db.session.add(pinnedPostUpvoted(voter_id = userID, post_id = postID, points = numPoints))
            #firebase and add to getNotification
            subj = postType
            if postType=='pond':
                postCont = post_check.post_cont
                notificType = 'F'
            elif postType == 'anon':
                postCont = post_check.a_post_cont
                notificType = 'A'
            elif postType == 'pool':
                postCont = post_check.group_post_cont
                notificType = 'G'
            elif postType == 'host':
                postCont = post_check.group_post_cont
                notificType = 'H'
            elif postType == 'chapter':
                postCont = post_check.group_event_post_cont
                notificType = 'E'
            elif postType == 'scrap':
                postCont = post_check.pin_post_orig_cont
                notificType = 'S'
            elif postType == 'scrapImage':
                postCont = post_check.pin_post_orig_cont
                notificType = 'T'
            if postType == 'anon':
                cont = str(numPoints) + ' point(s) added to your ' + postType + ' post: '+ postCont
            elif postType == 'chapter':
                cont = '@' + user_check.u_handle + ' added ' + str(numPoints) + ' point(s) to your page in .' +post_check.group_handle + ', ' + post_check.event_name
            elif postType in ('scrap','scrapImage'):
                cont = '@' + user_check.u_handle + ' added ' + str(numPoints) + ' point(s) to your scrapbook entry.'
            else:
                cont = '@' + user_check.u_handle + ' added ' + str(numPoints) + ' point(s) to your ' + postType + ' post: '+ postCont
            notificUID = post_check.u_id
            if postType == 'host':
                postID = (db.session.query(groupPosts.original_post_id).filter(groupPosts.group_post_id==postID).first()).original_post_id 
            elif postType in ('scrap','scrapImage'):
                postID = (db.session.query(pinnedPosts.original_post_id).filter(pinnedPosts.pin_id==postID).first()).original_post_id
            result['notificationSent'] = logNotification(notificUID, cont, subj, notificType, notificPostID=postID, notificGroupID=groupID, notificEventID=eventID)
            firebaseNotification(post_check.firebase_id, cont)            
            result['status'] = 'success'
            result['message'] = 'Points added'
            db.session.commit()
        else:
            result['status'] = 'error'
            result['message'] = 'No Points Added'
    except Exception, e:
        db.session.rollback()
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Points not sent'}        
        pass
    finally:
        db.session.close()
    return json.dumps(result)
            
@application.route('/editPost', methods=['POST'])
def editPost():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID', 'postType', 'postID','action')):
            userID = int(request.form['myID'])
            postID = request.form['postID']
            postType = request.form['postType'] #forum, anon, group, event, scrap
            action = request.form['action']
            if action == 'edit' and 'newContent' in request.form:
                newContents = request.form['newContent']
            elif action == 'delete':
                newContents = '[deleted]'
            elif action == 'report':
                if 'reportReason' in request.form:
                    reportReason = request.form['reportReason']
                else:
                    reportReason = 'N/A'
            else:
                return json.dumps(result)
        else:
            return json.dumps(result)
    else:    
        return json.dumps(result)
    try:
        #user_check = db.session.query(users.personal_points, users.stipend_points).filter(users.u_id==user_id).first()
        if action == 'report':
            reportPost = reportedPosts(post_id = postID, post_type= postType, report_u_id = userID, report_reason = reportReason)
            db.session.add(reportPost)
            result['status'] = 'success'
            result['message'] = 'Post reported'  
        elif postType == 'pond':
            post_check = db.session.query(forumPosts).filter(forumPosts.post_id == postID).filter(forumPosts.post_u_id==userID)
            if post_check.first() is not None:
                if action == 'delete':
                    post_check.update({'deleted':True,'post_cont':newContents,'date_time_edited':datetime.now()})
                    if post_check.one().original_post_id != 0:
                        db.session.query(forumPosts).filter(forumPosts.post_id == post_check.one().original_post_id).update({'reply_count':forumPosts.reply_count - 1})
                else:
                    post_check.update({'post_cont':newContents,'date_time_edited':datetime.now()})
                result['status'] = 'success'
                result['message'] = 'Post modified'  
            else:
                result['status'] = 'error'
                result['message'] = 'Post not modified'
        elif postType in ('pool','host'):
            member_check = db.session.query(groupMembers.member_role).filter(groupPosts.group_post_id==postID).filter(groupPosts.group_id==groupMembers.group_id).filter(groupMembers.member_id==userID).filter(groupMembers.member_role.in_(('M','H','O'))).first()
            if member_check is not None:
                post_check = db.session.query(groupPosts).filter(groupPosts.group_post_id == postID)
                if post_check.first() is not None:
                    if post_check.one().post_u_id == userID or (action == 'delete' and member_check.member_role in ('H','O')):
                        if action == 'delete':
                            post_check.update({'deleted':True,'group_post_cont':newContents,'date_time_edited':datetime.now()})                        
                            if post_check.one().original_post_id != 0:
                                db.session.query(groupPosts).filter(groupPosts.group_post_id == post_check.one().original_post_id).update({'reply_count':groupPosts.reply_count - 1})
                        else:
                            post_check.update({'group_post_cont':newContents,'date_time_edited':datetime.now()})
                        result['status'] = 'success'
                        result['message'] = 'Post modified'
                    else:
                        result['status'] = 'error'
                        result['message'] = 'Post not modified'
                else:
                    result['status'] = 'error'
                    result['message'] = 'Post not modified'
            else:
                result['status'] = 'error'
                result['message'] = 'Post not modified'
        elif postType == 'chapter':
            member_check = db.session.query(groupMembers.member_role).filter(groupEventPosts.group_event_post_id==postID).filter(groupEventPosts.group_id==groupMembers.group_id).filter(groupMembers.member_id==userID).filter(groupMembers.member_role.in_(('M','H','O'))).first()
            if member_check is not None and member_check != []:
                post_check = db.session.query(groupEventPosts).filter(groupEventPosts.group_event_post_id == postID)
                if post_check.first():
                    if post_check.one().group_event_post_u_id == userID or (action == 'delete' and member_check.member_role in ('H','O')):
                        if action == 'delete':
                            post_check.update({'deleted':True,'group_event_post_cont':newContents,'date_time_edited':datetime.now()})                        
                            db.session.query(groupEventDetails.event_post_count).filter(groupEventDetails.group_id == groupEventPosts.group_id).filter(groupEventDetails.event_id==groupEventPosts.event_id).filter(groupEventPosts.group_event_post_id==postID).update({'event_post_count':groupEventDetails.event_post_count-1})
                        else:
                            post_check.update({'group_event_post_cont':newContents,'date_time_edited':datetime.now()})
                        result['status'] = 'success'
                        result['message'] = 'Post modified'
                    else:
                        result['status'] = 'error'
                        result['message'] = 'Post not modified'
                else:
                    result['status'] = 'error'
                    result['message'] = 'Post not modified'
            else:
                result['status'] = 'error'
                result['message'] = 'Post not modified'
        elif postType == 'anon':
            post_check = db.session.query(anonForumPosts).filter(anonForumPosts.a_post_id == postID).filter(anonForumPosts.a_post_u_id==userID)
            if post_check.first() is not None:
                if action == 'delete':
                    post_check.update({'deleted':True,'a_post_cont':newContents,'a_date_time_edited':datetime.now()})                        
                    if post_check.one().a_original_post_id != 0:
                        db.session.query(anonForumPosts).filter(anonForumPosts.a_post_id == post_check.one().a_original_post_id).update({'a_reply_count':anonForumPosts.a_reply_count - 1})
                else:
                    post_check.update({'a_post_cont':newContents,'a_date_time_edited':datetime.now()})               
                result['status'] = 'success'
                result['message'] = 'Post modified'  
            else:
                result['status'] = 'error'
                result['message'] = 'Post not modified'
        elif postType == 'scrap': #only replies
            post_check = db.session.query(pinnedPosts).filter(pinnedPosts.pin_id==postID).filter(pinnedPosts.u_id==userID).filter(pinnedPosts.original_post_id != 0)
            if post_check.first() is not None:
                if action == 'delete':
                    post_check.update({'deleted':True,'pin_post_orig_cont':newContents,'date_time_edited':datetime.now()})
                    db.session.query(pinnedPosts).filter(pinnedPosts.pin_id == post_check.one().original_post_id).update({'reply_count':pinnedPosts.reply_count - 1})
                else:
                    post_check.update({'pin_post_orig_cont':newContents, 'date_time_edited':datetime.now()})
                result['status'] = 'success'
                result['message'] = 'Post modified'  
            else:
                result['status'] = 'error'
                result['message'] = 'Post not modified'
        db.session.commit()
    except Exception, e:
        db.session.rollback()
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Post not updated'}        
        pass
    finally:
        db.session.close()
    data = json.dumps(result)
    return data  
        
@application.route('/getNotifications', methods=['POST'])
def getNotifications():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','lastNotificationID')):
            myID = request.form['myID']
            lastNot = int(request.form['lastNotificationID'])
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    try:
        if lastNot == 0:
            notifications = db.session.query(notific.notific_id, notific.date_time, notific.notific_cont, notific.notific_subject, notific.notific_type, notific.notific_post_id, notific.notific_group_id, notific.notific_other_id, notific.notific_event_id, notific.notific_seen, groupDetails.group_handle, groupMembers.member_role, users.firebase_id, users.u_handle, users.u_key).filter(notific.n_u_id==myID).outerjoin(groupDetails, notific.notific_group_id==groupDetails.group_id).outerjoin(groupMembers, and_(groupMembers.member_id==myID,groupMembers.group_id==notific.notific_group_id)).outerjoin(users, notific.notific_other_id == users.u_id).order_by(notific.notific_id.desc()).limit(SECONDARY_LIMIT)
            #notifications = db.session.query(notific.notific_id, notific.date_time, notific.notific_cont, notific.notific_subject, notific.notific_type, notific.notific_post_id, notific.notific_group_id, notific.notific_other_id, notific.notific_seen).filter(notific.n_u_id==myID).order_by(notific.notific_id.desc()).limit(SECONDARY_LIMIT)
        else:
            notifications = db.session.query(notific.notific_id, notific.date_time, notific.notific_cont, notific.notific_subject, notific.notific_type, notific.notific_post_id, notific.notific_group_id, notific.notific_other_id, notific.notific_event_id, notific.notific_seen, groupDetails.group_handle, groupMembers.member_role, users.firebase_id, users.u_handle, users.u_key).filter(notific.n_u_id==myID).outerjoin(groupDetails, notific.notific_group_id==groupDetails.group_id).outerjoin(groupMembers, and_(groupMembers.member_id==myID,groupMembers.group_id==notific.notific_group_id)).outerjoin(users, notific.notific_other_id == users.u_id).filter(notific.notific_id < lastNot).order_by(notific.notific_id.desc()).limit(SECONDARY_LIMIT)
        if notifications is not None and (notifications.count() > 0):
            end = notifications[0].date_time
            for i in notifications:
                start = i.date_time
            if start == end:
                globalNotifications = db.session.query(globalNotific.g_notific_id, globalNotific.date_time, globalNotific.g_notific_cont, globalNotific.g_notific_subject, globalNotific.g_notific_type, globalNotific.g_notific_type).filter(users.u_id==myID).filter(or_(globalNotific.g_notific_id > users.last_global_notific, globalNotific.date_time > datetime.now()-timedelta(days=14))).order_by(globalNotific.g_notific_id.desc()).all()
            else:
                globalNotifications = globalNotifications = db.session.query(globalNotific.g_notific_id, globalNotific.date_time, globalNotific.g_notific_cont, globalNotific.g_notific_subject, globalNotific.g_notific_type, globalNotific.g_notific_type).filter(users.u_id==myID).filter(or_(globalNotific.g_notific_id > users.last_global_notific, globalNotific.date_time.between(start-timedelta(days=1),end+timedelta(days=1)), globalNotific.date_time > datetime.now()-timedelta(days=14))).order_by(globalNotific.g_notific_id.desc()).all()
        else:
            globalNotifications = db.session.query(globalNotific.g_notific_id, globalNotific.date_time, globalNotific.g_notific_cont, globalNotific.g_notific_subject, globalNotific.g_notific_type, globalNotific.g_notific_type).filter(users.u_id==myID).filter(or_(globalNotific.g_notific_id > users.last_global_notific, globalNotific.date_time > datetime.now()-timedelta(days=14))).order_by(globalNotific.g_notific_id.desc()).all()
        labels = ['notificationID','timestamp','contents','subject','notificationType','postID','poolID','userID', 'chapterID','notificationSeen', 'poolHandle','myMemberRole', 'firebaseID', 'userHandle', 'key']
        g_labels = ['notificationID','timestamp','contents','subject','notificationType', 'notificationSeen']
        notifics=[]
        globalNotifics=[]
        if notifications is not None or globalNotifications is not None:
            result['status'] = 'success'
            result['message'] = 'Notifications retrieved'
            if notifications != [] and globalNotifications != []:
                notifics = add_labels(labels,notifications, 'bucket', PROF_BUCKET, keySize='small')
                globalNotifics = add_labels(g_labels,globalNotifications)
                if notifics != [] and globalNotifics != []:                
                    try:    
                        db.session.query(users.last_global_notific).filter(users.u_id==myID).update({'last_global_notific':globalNotifications[0].g_notific_id})
                        db.session.query(notific.notific_seen).filter(notific.n_u_id==myID).update({'notific_seen':True})
                    except:      
                        pass
            elif notifications != []:
                notifics = add_labels(labels,notifications, 'bucket', PROF_BUCKET, keySize='small')
                if notifics !=[]:
                    try:
                        db.session.query(notific.notific_seen).filter(notific.n_u_id==myID).update({'notific_seen':True})
                    except:
                        pass
            elif globalNotifications != []:
                globalNotifics = add_labels(g_labels,globalNotifications)
                if globalNotifics != []:
                    try:
                        db.session.query(users.last_global_notific).filter(users.u_id==myID).update({'last_global_notific':globalNotifications[0].g_notific_id})
                    except:
                        pass
        else:
            result['message'] = 'Error retrieving notifications'
        result['notifications']=merge_notifications(notifics, globalNotifics)
        db.session.commit()
        if result['notifications']==[]:
            result['status'] = 'success'
            result['message'] = 'No Notifications'
    except Exception, e:
        db.session.rollback()
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Notifications not found'}        
        pass    
    finally:
        db.session.close()
    return json.dumps(result)    


@application.route('/handleCheck', methods=['POST'])
def handleCheck():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('handle','handleType')):
            handle = request.form['handle']
            handleType = request.form['handleType'] #pool, user
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    try:
        handle_check = None
        if handleType == 'pool':
            handle_check = db.session.query(groupDetails.group_handle).filter(groupDetails.group_handle == handle).first()
        elif handleType == 'user':
            handle_check = db.session.query(users.u_handle).filter(users.u_handle==handle).first()
        if handle_check is not None and handle_check != []:
            result = {'status':'success','handleExists':'yes'}
        else:
            result = {'status':'success','handleExists':'no'}
    except:
        result = {'status':'error','message':'Invalid request'}
    finally:
        db.session.close()
    return json.dumps(result)

@application.route('/newDeviceID', methods=['POST'])
def newDeviceID():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('deviceID','userID')):
            myID = request.form['userID']
            devID = request.form['deviceID']
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    try:
        user_check = db.session.query(users).filter(users.u_id==myID).one() 
        if user_check is not None and user_check != []:
            db.session.query(users).filter(users.u_id==user_check.u_id).update({'device_arn':register_device(devID,user_check.u_id)})
            result['status'] = 'success'
            result['message'] = 'Device registered'
        else:
            result['status'] = 'error'
            result['message'] = 'Device registration failed'            
        db.session.commit()
    except Exception, e:
        db.session.rollback()
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error', 'message':'Device registration failed'}
    finally:
        db.session.close()
    return json.dumps(result)

@application.route('/reportBug', methods=['POST'])
def reportBug():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('subject','message')):
            subj = request.form['subject']
            mess = request.form['message']
        else:
            return json.dumps(result)
    else:    
        return json.dumps(result)
    try:
        data_entered = bugReport(subject=subj, messg=mess)
        db.session.add(data_entered)
        db.session.commit()
        result = {'status':'success','message':'Bug report submitted'}
    except Exception, e:
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result={'status':'error','message':'Bug not reported'}
    finally:
        db.session.close()
    return json.dumps(result)

@application.route('/sendGlobalMessage', methods=['POST'])
def sendGlobalMessage():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('contents','subject','secret')):
            contents = request.form['contents']
            subject = request.form['subject']
            secret = request.form['secret']
        else:
            return json.dumps(result)
        if secret != 'stupid':
            return json.dumps(result)
    else:
        return json.dumps(result)
    notificType = 'X'
    data_entered = globalNotific(g_notific_cont=contents, g_notific_subject = subject, g_notific_type = notificType)
    try:
        db.session.add(data_entered)
        db.session.commit()
        fb = firebaseNotification('*', contents)
        result = {'status':'success','message':'Global Notification added','firebase':fb}
    except Exception, e:
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result={'status':'error','message':'Global Notification not added'}
    finally:
        db.session.close()
    return json.dumps(result)

@application.route('/getBugReports', methods=['POST','GET'])
def getBugReports():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('id','secret', 'update')):
            bugID = int(request.form['id'])
            secret = request.form['secret']
            update = request.form['update']
            if update == 'yes':
                if 'newStatus' in request.form:
                    newStatus = request.form['newStatus']
                else:
                    return json.dumps(result)
        else:
            return json.dumps(result)
        if secret != 'stupid':
            return json.dumps(result)
    elif request.method == 'GET':
        bugID = int(request.args.get('id'))
        secret = str(request.args.get('secret'))
        update = request.args.get('update')
        if bugID is None or secret is None or update is None:
            return json.dumps(result)
        if update == 'yes':
            if 'newStatus' in request.form:
                newStatus = request.args.get('newStatus')
            else:
                return json.dumps(result)
        if secret != 'stupid':
            return json.dumps(result)
    else:
        return json.dumps(result)
    try:
        if bugID==0:
            bugs = db.session.query(bugReport.bug_report_id, bugReport.date_time, bugReport.subject, bugReport.messg, bugReport.status).all()
        elif update != 'yes':
            bugs = db.session.query(bugReport.bug_report_id, bugReport.date_time, bugReport.subject, bugReport.messg, bugReport.status).filter(bugReport.bug_report_id==bugID).first()
        elif update == 'yes':
            db.session.query(bugReport.status).filter(bugReport.bug_report_id==bugID).update({'status':newStatus})
            db.session.commit()
            result['message']='Bug status update'
        if update == 'no' and bugs is not None and bugs !=[]:
            labels = ['bugID','timestamp','subject','message','status']
            result['bugs'] = add_labels(labels, bugs)
            result['message']='Found'
        else:
            result['message']='None found'
        result['status'] = 'success'
    except Exception, e:
        if ENABLE_ERRORS:
            result['status'] = 'error'
            result['message'] = str(e)
        else:
            result = {'status':'error','message':'Bug report error'}
    return json.dumps(result)

@application.route('/resetStipend', methods=['POST','GET'])
def resetStipend():
    try:
        if 'secret' in request.form:
            secret = request.form['secret']
        else:
            return json.dumps(result)
        if secret != 'stupid':
            return json.dumps(result)
        resetStipendPoints()
        result = {'status':'success','message':'Points Reset'}
    except Exception, e:
        result = {'status':'error','message':str(e)}
    return json.dumps(result)

@application.route('/test', methods=['GET','POST'])
def test():
    try:
        '''
        sns = boto3.client('sns',region_name='us-west-1')
        device_arn = 'arn:aws:sns:us-west-1:554061732115:endpoint/APNS_SANDBOX/hostPostDev/0db06b83-5361-3b06-82b2-864f027c52dc'    
        apns_dict = {'aps':{'alert':'inner message','sound':'mySound.caf'}}
        apns_string = json.dumps(apns_dict,ensure_ascii=False)
        message = {'default':'default message','APNS_SANDBOX':apns_string}
        messageJSON = json.dumps(message,ensure_ascii=False)
        sns.publish(Message=messageJSON, TargetArn=device_arn)#,message_structure='json')
        '''
        innerMessage = str(datetime.now()) + 'test push' #request.form['message']
        badge = 1 #request.form['badge']
        category = 'testcategory' #request.form['category']
        device_arn = 'arn:aws:sns:us-west-1:554061732115:endpoint/APNS/.native/d16c21b4-e198-3411-93fb-3c03436044b1' 
        result = push(device_arn, badge, innerMessage, category)
        #resetStipendPoints()
    except Exception, e:
        return json.dumps({'status':'error', 'message':str(e)})
    return json.dumps(str(result))

@application.route('/test2', methods=['GET','POST'])
def test2():
    sns = boto3.client('sns',region_name='us-west-1', aws_access_key_id="AKIAIAWLQ6C2HQNAFCOA", aws_secret_access_key="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")
    deviceID='5e944b672ecb126f6fd6c76fca1bba56b54c9c3e663a9889fdfe4580808a123f'
    try:
        endpoint_response = sns.create_platform_endpoint(
            PlatformApplicationArn = 'arn:aws:sns:us-west-1:554061732115:app/APNS_SANDBOX/hostPostDev',
            Token = deviceID,
            CustomUserData = 'Test'
        )
        endpoint_arn = endpoint_response['EndpointArn']
        return endpoint_arn
    except Exception, err:    
        result_re = re.compile(r'Endpoint(.*)already', re.IGNORECASE)
        res = result_re.search(err.message)
        if res:
            endpoint_arn = res.group(0).replace('Endpoint ','').replace(' already','')
        else:
            raise
    return False


@application.route('/test3', methods=['GET','POST'])
def test3():
    try:
        fbID = 'P5U0caXruLUCYycKvAuY3PupnHH3'
        mess = 'test ' + str(datetime.utcnow())
        expiration = datetime.utcnow() + timedelta(minutes=30)
        auth_payload = {"uid": "1", "auth_data": "foo", "other_auth_data": "bar"}
        options = {"expires":expiration}
        token = create_token(FIREBASE_SECRET, auth_payload, options)
        payload='"'+mess+'"'
        print str(token)
        r = requests.post(FIREBASE_URL + '/users/'+str(fbID)+'/notifications.json?auth='+str(token), data=payload)
        print r
        print 'here now'
    except Exception, err:    
        return str(err)
    return 'Test successful\n'


@application.route('/test4', methods=['GET','POST'])
def test4():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('sendID','recipID','recipFBID')):
            sendID = request.form['sendID']
            recipID = request.form['recipID']
            recipFBID = request.form['recipFBID']
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    res = checkInChat(sendID, recipID,recipFBID)
    return str(res) + '\n'


@application.route('/test5', methods=['GET','POST'])
def test5():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if 'recipFBID' in request.form:
            recipFBID = request.form['recipFBID']
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    res = inNotification(recipFBID)
    return str(res) + '\n'


@application.route('/test6', methods=['GET','POST'])
def test6():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if 'reg' in request.form:
            reg = request.form['reg']
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    try:
        result['res']=re.match(r"_small$|_medium$|_large$", reg)
    except Exception, e:
        result = {'error':str(e)}
    return json.dumps(result)

                

#iv=wExMGMCtvrhXqil5&token=[65, 171, 188, 48, 15, 101, 147, 222, 124, 211, 110, 108, 55, 183, 223, 21, 135, 44, 184, 48, 103, 121, 81, 132, 20, 33, 160, 246, 197, 157, 32, 126]
@application.route('/testEncrypt', methods=['GET','POST'])
def testEncrypt():
    result = {'status':'error','message':'Invalid request'}
    return json.dumps({'result':str(validate())})
    #if request.method == 'POST':
    '''    
    try:
        if all (k in request.form for k in ('iv','token')):
            iv = str(request.form['iv'])
            s = str(request.form['token'])
            s = s[1:len(s)-1];
            r = s.split(', ')
            r = map(int, r)
            print 'iv', iv
            token = "".join(map(chr, r)) 
            test = False
        else:
            test = True
            iv = None
            token = None
            print 'continue\n'
            #return json.dumps(result)
        SECRET = "12345678901234567890123456789012"
        if test:
            iv = "1234567890123456"#os.urandom(16) 
            data =  "HRGef1LKiqV76lVct3MuFkxuubF20123"
            print 'data: ', data
            print 'iv: ', iv
            token = str(bytearray([183, 230, 34, 116, 213, 65, 86, 85, 145, 224, 122, 97, 127, 55, 58, 126, 185, 28, 67, 80, 172, 154, 239, 35, 162, 122, 144, 72, 13, 236, 79, 219, 54, 162, 250, 221, 119, 127, 197, 151, 17, 132, 0, 163, 36, 179, 51, 229]))
            cipher = AES.new(SECRET, MODE, iv)    
            #token = '8c9add63f5ee41ad5c746a249f946fb23b455797ac394e66b5cdc26933718c88c17e636e5e2579b15abb2c19678d5ce0'
            #token = "".join(map(chr, token)) 
            print 'token:\n',token
            s = cipher.encrypt(data)     
            print 'Encrypted string:\n', base64.b64encode(s)    
            print 'data: ', data
        print 'iv: ', iv
        decryptor = AES.new(SECRET, MODE, iv)
        decoded1 = decryptor.decrypt(token)
        #decryptor = AES.new(SECRET, MODE, iv)
        #decoded2 = decryptor.decrypt(s)
        #decoded = base64.b64encode(decoded1)
        print 'Decrypted string1: ', decoded1
        #print 'Decrypted string2: ', decoded2
        result = {'status':'success','message':decoded1}
    except Exception, e:
        result['errorMess']=str(e)
    return json.dumps(result)
    '''    


'''


if all (k in request.form for k in ('iv','token')):
    iv = request.form['iv']
    token = "".join(map(chr, request.form['token']))
else:
    return result
if !validate(token, iv):
    return result

def validate(token, iv):
    decryptor = AES.new(SECRET, MODE, iv)
    decoded = decryptor.decrypt(token)
    #print 'Decrypted string: ', decoded
    firebaseID, tokenTime = [stuff with decoded]
    if datetime.now() < tokenTime:
        userExists = db.session.query(users.firebase_id).filter(users.firebase_id==firebaseID).first()
        if userExists != None:
            return True
    return false

'''

'''
#functions...private?        

@application.route('/attendeeList', methods=['GET','POST'])
def attendeeList():
    result = {'status':'error','message':'Invalid request'}
    result = {'status':'error', 'message':'Invalid'}  
    if request.method == 'GET':
        user_id = request.args.get('myID')
        group_id = request.args.get('groupID')
        event_id = request.args.get('eventID')
    elif request.method == 'POST':
        if all (k in request.form for k in ('myID','groupID','eventID')):
            user_id = request.form['myID']
            group_id = request.form['groupID']
            event_id = request.form['eventID']
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    try:
        member_check = db.session.query(groupMembers.member_status, groupMembers.member_role).filter(groupMembers.member_id==user_id).filter(groupMembers.group_id==group_id).filter(groupMembers.member_status == 'M').first()
        
        if member_check is not None and member_check != []:
            result['myMemberRole'] = member_check.member_role
            attendee_search = db.session.query(users.u_id, users.u_name, users.handle, users.key).filter(groupEventUsers.event_id==event_id).filter(groupEventUsers.attendee_id == users.u_id).filter(groupMembers.member_id==users.u_id).filter(groupMembers.group_id == group_id).filter(groupMembers.member_status=='M').distinct().order_by(case((groupMembers.member_role == "O", 1),(groupMembers.member_role == "H", 2),(groupMembers.member_role == "M", 3))).all()
            attendeeLabel = ('memberRole','userID','userName','handle','key')
            result['attendees']=add_labels(attendeeLabel, attendee_search, 'bucket', PROF_BUCKET)
            result['status'] = 'success'
            result['message'] = 'Group members found'
        else:
            result['status'] = 'success'
            result['message'] = 'No group members found'
        db.session.close()        
    except Exception, e:
        result = {'status':'error', 'message':str(e)}
        pass
    return json.dumps(result)



def order_group_dist(group_list, long, lat):
    for g in group_list:
        dist = sqrt((g.group_long-long)-(g.group_lat-lat))
'''

#user_check = db.session.query(users.u_id, users.u_handle, users.device_arn, users.firebase_id, groupDetails.group_handle).filter(groupDetails.group_id==groupMembers.group_id).filter(users.u_id == groupMembers.member_id).filter(groupMembers.group_id==groupID).filter(groupMembers.member_role.in_(('M','H','O'))).all()
def notifyPool(user_check, myHandle, messgCont, originalPostID, groupID, myID):
    try:
        for u in user_check:
            subj = 'getPoolPost'
            cont = '.' + u.group_handle + ', @' + myHandle +': ' + messgCont
            notificType = 'G'
            notificUID = u.u_id
            #result['notificationSent' + str(u.u_id)]=
            logNotification(notificUID, cont, subj, notificType, notificPostID=originalPostID, notificGroupID=groupID)
            firebaseNotification(u.firebase_id, cont)
            if u is not None and u != [] and u.u_id != myID:
                if u.device_arn != 0 and not inNotification(u.firebase_id) and not (inPool(u.firebase_id)==groupID) and inPool(u.firebase_id)>=0:
                    badge = db.session.query(notific.notific_id).filter(notific.n_u_id==u.u_id).filter(notific.notific_seen==False).count()
                    push(u.device_arn, badge, cont, subj)
    except Exception, e:
        #print str(e)
        pass
    finally:
        db.session.close()

def notifyChat(recip_dev_arn, sendID, recipID, recip_fb_id, subj, cont, notificType, notificUID):
    try:    
        if recip_dev_arn != 0:
            if not checkInChat(sendID, recipID, recip_fb_id): #checkInChat -> true if in chat, false if not. 
                logNotification(notificUID, cont, subj, notificType, notificOtherID=sendID)
                firebaseNotification(recip_fb_id, cont) 
                if not inNotification(recip_fb_id):
                    badge = db.session.query(notific.notific_id).filter(notific.n_u_id==recipID).filter(notific.notific_seen==False).count()
                    push(recip_dev_arn, badge, cont, subj)
    except Exception, e:
        #print '\n\nasdf\n'
        #print str(e)
        pass
    finally:
        db.session.close()
                

def merge_notifications(notifics, globalNotifics):
    temp = notifics + globalNotifics
    res = sorted(temp, key=lambda noti: noti['timestamp'], reverse=True)
    return res

def filter_groups(group_list, new_host_posts=None, new_posts=None, new_events=None, keySize=None, otherCheck=False):
    currentGroups=[]
    sentRequests=[]
    receivedInvites=[]
    try:
        for g in group_list:
            if g.member_role in ('M','H','O'):
                if otherCheck:
                    currentGroups.append([g.group_id, g.group_name, g.group_key, g.group_handle, g.otherRole])
                elif new_host_posts is not None and new_posts is not None and new_events is not None: #and g.group_id in new_host_posts and g.group_id in new_posts and g.group_id in new_events:
                    currentGroups.append([g.group_id, g.group_name, g.group_key, g.group_handle, g.member_role, new_host_posts[g.group_id],new_posts[g.group_id],new_events[g.group_id]]) #neweventreplies
                else:
                    currentGroups.append([g.group_id, g.group_name, g.group_key, g.group_handle, g.member_role, None, None, None])   
            elif g.member_role == 'S':
                sentRequests.append([g.group_id, g.group_name, g.group_key, g.group_handle])
            elif g.member_role == 'I':
                receivedInvites.append([g.group_id, g.group_name, g.group_key,g.group_handle])
        label = ['poolID','poolName','poolKey','poolHandle','memberRole']
        if new_events is not None:
            current_label =  ['poolID','poolName','poolKey','poolHandle','memberRole','newHostPostsCount','newPostsCount','newChaptersCount']
        else:
            current_label = label
        add_all = 'poolBucket'
        labelCurrentGroups = add_labels(current_label, currentGroups, add_all, GROUP_BUCKET, keySize=keySize)
        labelSentRequests = add_labels(label, sentRequests, add_all, GROUP_BUCKET, keySize=keySize)      
        labelReceivedInvites = add_labels(label, receivedInvites, add_all, GROUP_BUCKET, keySize=keySize)
    except Exception, e:
        return {'errorMessageGroups':str(e)}   
    return {'currentGroups':labelCurrentGroups, 'sentRequests':labelSentRequests, 'receivedRequests':labelReceivedInvites}

def filter_friends(friend_list, kSize):
    sentRequests=[]
    receivedRequests=[]
    currentFriends=[]
    for f in friend_list:
        if f.friend_status == 'F':
            currentFriends.append([f.u_id, f.u_name, f.u_handle,f.firebase_id, f.u_key,'F'])
        elif int(f.requester) != int(f.u_id):
            sentRequests.append([f.u_id, f.u_name, f.u_handle, f.firebase_id, f.u_key,'S'])
        elif int(f.requester) == int(f.u_id):
            receivedRequests.append([f.u_id,f.u_name, f.u_handle, f.firebase_id, f.u_key,'R'])
    label=['userID','userName','userHandle','firebaseID','key','isFriend']
    add_all='bucket'
    labelCurrentFriends = add_labels(label,currentFriends, add_all, PROF_BUCKET, keySize=kSize) 
    labelSentRequests = add_labels(label,sentRequests, add_all, PROF_BUCKET, True, keySize=kSize)
    labelReceivedRequests = add_labels(label,receivedRequests, add_all, PROF_BUCKET, keySize=kSize)
    return {'currentFriends':labelCurrentFriends,'sentRequests':labelSentRequests,'receivedRequests':labelReceivedRequests}

def filter_members(member_list, keySize):
    sentRequests=[]
    receivedRequests=[]
    currentMembers=[]
    blocked=[]
    for m in member_list:
        if m.member_role in ('M','H','O'):
            if len(currentMembers) < DEFAULT_LIMIT:
                currentMembers.append([m.member_role, m.u_id, m.firebase_id, m.u_name, m.u_handle, m.u_key])
        elif m.member_role == 'S': #request from user to group
            if len(receivedRequests) < DEFAULT_LIMIT:
                receivedRequests.append([m.u_id, m.firebase_id, m.u_name, m.u_handle, m.member_message, m.u_key])
        elif m.member_role == 'I': #request from group to user
            if len(sentRequests) < DEFAULT_LIMIT:
                sentRequests.append([m.u_id, m.firebase_id, m.u_name, m.u_handle, m.member_message, m.u_key])
        elif m.member_role == 'B':
            blocked.append([m.u_id, m.u_name, m.u_handle, m.member_message, str(m.u_id)+'_userProfPic'])
    currentLabel=['memberRole','userID', 'firebaseID','userName','userHandle','key']
    label=['userID','firebaseID','userName','userHandle','userMessage','key']
    add_all='bucket'
    labelCurrentMembers = add_labels(currentLabel, currentMembers, add_all, PROF_BUCKET, keySize=keySize)
    labelSentRequests = add_labels(label, sentRequests, add_all, PROF_BUCKET, keySize=keySize)
    labelReceivedRequests = add_labels(label, receivedRequests, add_all, PROF_BUCKET, keySize=keySize)
    labelBlocked = add_labels(label, blocked, add_all, PROF_BUCKET)
    return {'members':labelCurrentMembers, 'sentRequests':labelSentRequests, 'receivedRequests':labelReceivedRequests,'blocked':labelBlocked}

def add_labels(labels, list_to_add, add_all_label=None, add_all=None, first_initial = False, add_all_label_2=None, add_all_2=None, keySize=None):
    temp=[]
    try:
        for k in list_to_add:
            k_temp={}
            if len(k) < len (labels):
                use_labels = labels[:len(k)]
            else:
                use_labels = labels
            for j,x in zip(k, use_labels):
                #print 'j: ', j
                #print 'x: ', x
                #print 'k: ', k
                k_temp[x]=add_labels_helper(j,x,k, first_initial,keySize)
            if (add_all is not None):
                k_temp[add_all_label]=add_all
            if (add_all_2 is not None):
                k_temp[add_all_label_2]=add_all_2
            temp.append(k_temp)
    except Exception, e:    
        #print str(e)
        k_temp={}    
        for i in range(len(labels)):#j,x in k,labels:
            #print 'i: ', i
            x=labels[i] 
            #print 'x: ', x    
            k_temp[x]=add_labels_helper(list_to_add[i],x,k, first_initial,keySize)         
        if (add_all is not None):
            k_temp[add_all_label]=add_all
        if (add_all_2 is not None):
            k_temp[add_all_label_2]=add_all_2
        temp.append(k_temp)
    return temp

def add_labels_helper(j,x,k, first_initial,keySize):   
    if 'timestamp' in x:
        res = json_serial(j)
    elif 'didIVote' in x:
        if j is 'NULL' or j is None:
            res = 'no'
        else:
            res = 'yes'
    elif first_initial and 'userName' in x:
        res=first_and_initial(j)
    elif 'chapterCellType' in x:
        if j == 'I':
            res = 'image'
        elif j== 'T':
            res = 'text'
    elif 'cellType' in x:
        if j == 0:
            res = 'host'
        elif j== -1:
            res = 'pool'
        else:
            res = 'post'
    elif 'amIAttending' in x:
        if j is None or j=='N' or j=='W':
            res = 'no'
        elif j =='M' or j=='O':
            res = 'yes'
    elif 'Chat' in x:
        if j is None:
            res = 'None'
        else:
            res = j
    elif 'readable' in x or 'onProfile' in x or 'searchable' in x:
        if j:
            res = 'yes'
        elif not j:
            res = 'no'
    elif ('key' in x or 'Key' in x) and keySize is not None and j is not None:
        res = j+'_'+keySize
    elif 'isFriend' in x:
        if j is None:
            res = 'N'
        else:
            res = j
    elif 'memberRole' in x:
        if j is None:
            res = 'N'
        else:
            res = j
    elif 'notificationType' in x:
        if j in ('P','F'):
            res = 'pond'
        elif j == 'A':
            res = 'anon'
        elif j == 'G':
            res = 'pool'
        elif j == 'H':
            res = 'host'
        elif j == 'M':
            res = 'myPoolRequest'
        elif j == 'R':
            res = 'poolPoolRequest'
        elif j == 'S':
            res = 'scrap'
        elif j == 'T':
            res = 'scrapImage'
        elif j =='D':
            res = 'friendRequest'
        elif j == 'C':
            res = 'chat'
        elif j == 'X':
            res = 'global'
        elif j == 'E':
            res = 'chapter'
        else:
            res = j
    elif 'notificationSeen' in x:
        if j == True:
            res = 'Y'
        elif j == False:
            res = 'N'
        elif j == 'X':
            res = 'X'
    elif 'longitude' in x or 'latitude' in x:
        res = str(j)
    elif 'memberRole' in x:
        if j is None:
            res = 'N'
        else:
            res = j
    elif 'isPinned' in x:
        if j==True:
            res = 'Y'
        elif j== False:
            res = 'N'
        else:
            res = j
    elif 'postType' in x:
        if j == 'F':
            res = 'pond'
        elif j == 'A':
            res = 'anon'
        elif j == 'G':
            res = 'pool'
        elif j == 'M':
            res = 'chapterText'
        elif j == 'I':
            res = 'chapterImage'
        elif j == 'R':
            res = 'reply'
    elif 'poolHandle' in x:
        if j is None:
            res = 'pool'
        else:
            res = j
    elif 'chapterName' in x:
        if j is None:
            res = 'chapter'
        else:
            res = j
    else:
        res=j
    return res
            

def original_getMinMaxLongLat(my_long, my_lat, dist):
    #364173 feet * cos(long) = 1 degree of long
    #dist in miles
    delta = (dist * Decimal(5280)) / Decimal(364173 * cos(my_long))
    minLong = my_long - delta
    maxLong = my_long + delta
    maxLat = my_lat + (dist * Decimal(0.01447315953478432289213674551561))
    minLat = my_lat - (dist * Decimal(0.01447315953478432289213674551561))
    if minLong > maxLong == Decimal('1'):
        minLong,maxLong = maxLong,minLong
    if minLat > minLong == Decimal('1'):
        minLat, maxLat = maxLat, minLat        
    return minLong, maxLong, minLat, maxLat
    
def getMinMaxLongLat(my_long, my_lat, dist):
    #364173 feet * cos(long) = 1 degree of long
    #dist in miles
    delta = abs((dist * 5280) / (364173 * cos(my_long)))
    minLong = my_long - delta
    maxLong = my_long + delta
    maxLat = my_lat + (dist * (0.01447315953478432289213674551561))
    minLat = my_lat - (dist * (0.01447315953478432289213674551561))   
    return minLong, maxLong, minLat, maxLat

#not necessary
def hash_password(password):
    pwhash = bcrypt.hashpw(password, bcrypt.gensalt())
    return pwhash

def json_serial(obj):
    if isinstance(obj, datetime):
        serial = obj.isoformat()
        return serial
    elif isinstance(obj, date):
        serial = obj.isoformat()
    raise TypeError ("Type not serializable" + str(obj))

def first_and_initial(name):
    if " " in name:
        first, space, last = name.partition(" ")
        return first + space + last[0]
    else:
        return name

def validate_phone(phone):
    return re.sub("[^0-9]", "", phone)

def format_phone(phone):
    if len(phone) == 10:
        phone = '('+phone[:-7] + ') '+ phone[-7:-4] + '-'+phone[-4:]
    return phone

def validate_email(email):
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return False
    return True

def validate_handle(handle):
    if not re.match(r"[a-zA-Z]", handle):
        return False
    return True

def resetStipendPoints(userID=0): #0 means all IDs
    db.session.query(users.u_stipend_points, users.last_stipend_date).update({'u_stipend_points':DEFAULT_STIPEND,'last_stipend_date':datetime.now()})
    db.session.commit()

def push(deviceARN, badge, innerMessage, subject):
    try:
        sns = boto3.client('sns',region_name='us-west-1')
        device_arn = deviceARN  
        apns_dict = {'aps':{'alert':innerMessage,'badge':badge,'category':subject,'content-available':1}}
        apns_string = json.dumps(apns_dict,ensure_ascii=False)
        message = {'APNS':apns_string}
        messageJSON = json.dumps(message,ensure_ascii=False)
        sns.publish(Message=messageJSON, TargetArn=device_arn, MessageStructure='json')
    except Exception, e:
        return json.dumps({'status':'error', 'message':str(e)})
    return True
    '''
    publish_result = sns.publish(
        target_arn=endpoint_arn,
        message=body,
    )
    '''

def checkInChat(sendID, recipID, recipFBID):
    node = str(sendID) + '_' +str(recipID) if sendID < recipID else str(recipID)+'_'+str(sendID)
    auth_payload = {'uid':'1'}
    expiration = datetime.utcnow() + timedelta(minutes=30)
    options = {"expires":expiration}
    token = create_token(FIREBASE_SECRET, auth_payload, options)
    inConvo = (requests.get(FIREBASE_URL + '/chats/'+node+'/'+str(recipID)+'_inConversation.json?auth=' + str(token))).text
    #print inConvo == 'null'
    #inFriends = (requests.get(FIREBASE_URL + '/users/' + recipFBID + '/inFriendList.json?auth=' + str(token))).text
    #print inFriends
    if (inConvo == 'false' or inConvo =='null'):# and inFriends=='false':
        return False #send
    else: 
        return True

def inNotification(recipFBID):
    auth_payload = {'uid':'1'}
    expiration = datetime.utcnow() + timedelta(minutes=30)
    options = {"expires":expiration}
    token = create_token(FIREBASE_SECRET, auth_payload, options)
    inNotific = (requests.get(FIREBASE_URL + '/users/'+recipFBID+'/inNotifications.json?auth=' + str(token))).text
    if inNotific == 'null':
        requests.put(FIREBASE_URL + '/users/'+recipFBID+'/inPool.json?auth=' + str(token), data="false")
        return False
    elif inNotific == 'true':
        return True
    else:
        return False

def inPool(recipFBID):
    auth_payload = {'uid':'1'}
    expiration = datetime.utcnow() + timedelta(minutes=30)
    options = {"expires":expiration}
    token = create_token(FIREBASE_SECRET, auth_payload, options)
    inNotific = (requests.get(FIREBASE_URL + '/users/'+recipFBID+'/inPool.json?auth=' + str(token))).text
    if inNotific == 'null':
        requests.put(FIREBASE_URL + '/users/'+recipFBID+'/inPool.json?auth=' + str(token), data="-1")
        return -1
    return int(inNotific) #0 or poolID

def inPostID(recipFBID):
    auth_payload = {'uid':'1'}
    expiration = datetime.utcnow() + timedelta(minutes=30)
    options = {"expires":expiration}
    token = create_token(FIREBASE_SECRET, auth_payload, options)
    inNotific = (requests.get(FIREBASE_URL + '/users/'+recipFBID+'/inPostID.json?auth=' + str(token))).text
    if inNotific == 'null':
        requests.put(FIREBASE_URL + '/users/'+recipFBID+'/inPostID.json?auth=' + str(token), data="0")
        return 0
    return int(inNotific) #postID

def firebaseNotification(fbID, mess):
    expiration = datetime.utcnow() + timedelta(minutes=30)
    auth_payload = {'uid':'1'}
    options = {"expires":expiration}
    token = create_token(FIREBASE_SECRET, auth_payload, options)
    payload='"'+mess+'"'
    r = requests.post(FIREBASE_URL + '/users/'+str(fbID)+'/notifications.json?auth='+str(token), data=payload)
    return r.status_code

def logNotification(userID, contents, subject, notificType, notificPostID=None, notificGroupID=None, notificOtherID=None, notificEventID=None):
    '''
    print 'userID', userID
    print 'contents',contents
    print 'subject',subject
    print 'notificType',notificType
    print 'notificPostID',notificPostID
    print 'notificGroupID', notificGroupID
    print 'notificOtherID', notificOtherID
    print 'notificEventID',notificEventID
    '''
    data_entered = notific(n_u_id=userID, notific_cont=contents, notific_subject = subject, notific_type = notificType, notific_post_id = notificPostID, notific_group_id = notificGroupID, notific_other_id = notificOtherID, notific_event_id=notificEventID)
    result = True
    try:
        db.session.add(data_entered)
        db.session.commit()
    except Exception, e:
        #print str(e)
        db.session.rollback()
        result=False
    finally:
        db.session.close()
    #print 'log notific done', result
    #print '\ncont', contents
    return result

def register_device(device_id, user_id = 'N/A'):
    sns = boto3.client('sns',region_name='us-west-1', aws_access_key_id = AWS_ACCESS_KEY_ID, aws_secret_access_key = AWS_SECRET_ACCESS_KEY)
    try:
        endpoint_response = sns.create_platform_endpoint(
            PlatformApplicationArn = PLATFORM_APPLICATION_ARN,
            Token = device_id,
            CustomUserData = str(user_id)
        )
        endpoint_arn = endpoint_response['EndpointArn']
        return endpoint_arn
    except Exception, err: 
        result_re = re.compile(r'Endpoint(.*)already', re.IGNORECASE)
        res = result_re.search(err.message)
        e=str(err.message)
        if res:
            try:
                ind = e.find('arn:aws:sns')
                if ind != -1:
                    devARN = e[ind:].split()[0]
                    endpoint_response = sns.set_endpoint_attributes(
                        EndpointArn=devARN,
                        Attributes = {'CustomUserData':str(user_id), 'Enabled':'True'}
                    )
                    endpoint_arn = endpoint_arn = endpoint_response['EndpointArn']
                    return endpoint_arn
                else:
                    return False
            except Exception, inEx:
                return str(inEx)
        else:
            raise
    return False

def anonValidate():
    result = False
    try:
        if 'myID' in request.form:
            myID = int(request.form['myID'])
            if myID == 0:
                result=True
    except Exception, e:
        result=str(e)
    return result

def validate():
    result = False
    try:
        if all (k in request.form for k in ('iv','token')):
            iv = str(request.form['iv'])
            s = str(request.form['token'])
            s = s[1:len(s)-1];
            r = s.split(', ')
            r = map(int, r)
            token = "".join(map(chr, r)) 
        else:
            return result
        SECRET = "vLhLbQexoJ9D2WVUJcH18tvYw7IxcgNF"
        decryptor = AES.new(SECRET, MODE, iv)
        decoded = decryptor.decrypt(token)
        firebaseLength = 28
        firebaseID = decoded[:firebaseLength]
        tokenTime = decoded[firebaseLength:firebaseLength+19]
        tokenTime = datetime.strptime(tokenTime, '%Y-%m-%dT%H:%M:%S')
        if datetime.now() < tokenTime:
            if request.endpoint == 'register':
                result = True
            else:
                userExists = db.session.query(users.firebase_id).filter(users.firebase_id==firebaseID).first()
                if userExists != None:
                    result=True
    except Exception, e:
        result=str(e)
    finally:
        db.session.close()
    return result

def groupInteractRequestHelper(requesterID, groupID):
    user_check = db.session.query(users.u_handle, users.device_arn, users.firebase_id).filter(users.u_id==requesterID).one()
    group_host_check = db.session.query(users.u_id, users.device_arn, groupDetails.group_handle).filter(groupMembers.group_id==groupID).filter(groupDetails.group_id == groupID).filter(or_(groupMembers.member_role=='O', groupMembers.member_role=='H')).filter(groupMembers.member_id==users.u_id).distinct().all()
    if ((user_check is not None) and (user_check != []) and (group_host_check is not None) and (group_host_check != [])):
        for g in group_host_check:
            subj = 'getGroupProfile'
            cont = '@'+user_check.u_handle + ' has sent .'+g.group_handle + ' a request'
            notificType='R'
            notificUID=g.u_id
            inNot = inNotification(user_check.firebase_id)
            if inNot==True:
                logNotification(notificUID, cont, subj, notificType, notificGroupID=groupID)
                firebaseNotification(user_check.firebase_id, cont)
            if g.device_arn !=0 and inNot == False:
                logNotification(notificUID, cont, subj, notificType, notificGroupID=groupID)
                firebaseNotification(user_check.firebase_id, cont)
                db.session.commit()
                badge = db.session.query(notific.notific_id).filter(notific.n_u_id==g.u_id).filter(notific.notific_seen==False).count()
                push(g.device_arn, badge, cont, subj)



def dynamicRadiusHelper(myLong, myLat, postType, sort, myRad, td, lastPostID):
    if myRad > MAX_RADIUS:
        radius = MAX_RADIUS
    else:
        radius = myRad
    try:
        min_long, max_long, min_lat, max_lat = getMinMaxLongLat(myLong, myLat, radius)
        timeCut = datetime.now() - timedelta(hours = td)
        if postType == 'pond':
            if sort == 'new':
                if lastPostID == 0:
                    get_post_check = db.session.query(forumPosts.post_id).filter(forumPosts.deleted==False).filter(forumPosts.original_post_id==0).filter(forumPosts.date_time > timeCut).filter(forumPosts.post_lat.between(min_lat, max_lat)).filter(forumPosts.post_long.between(min_long, max_long)).order_by(forumPosts.date_time.desc()).distinct().count()
                else:                         
                    get_post_check = db.session.query(forumPosts.post_id).filter(forumPosts.deleted==False).filter(forumPosts.original_post_id==0).filter(forumPosts.date_time > timeCut).filter(forumPosts.post_id < lastPostID).filter(forumPosts.post_lat.between(min_lat, max_lat)).filter(forumPosts.post_long.between(min_long, max_long)).order_by(forumPosts.date_time.desc()).distinct().count()
            elif sort == 'hot':
                if lastPostID == 0:    
                    get_post_check = db.session.query(forumPosts.post_id).filter(forumPosts.deleted==False).filter(forumPosts.date_time > timeCut).filter(forumPosts.original_post_id==0).filter(forumPosts.post_lat.between(min_lat, max_lat)).filter(forumPosts.post_long.between(min_long, max_long)).order_by(forumPosts.points_count.desc()).distinct().count()
                else:
                    get_post_check = db.session.query(forumPosts.post_id).filter(forumPosts.deleted==False).filter(forumPosts.date_time > timeCut).filter(forumPosts.original_post_id==0).filter(forumPosts.post_id < lastPostID).filter(forumPosts.post_lat.between(min_lat, max_lat)).filter(forumPosts.post_long.between(min_long, max_long)).order_by(forumPosts.points_count.desc()).distinct().count()
        elif postType == 'anon':
            if sort == 'new':  
                if lastPostID==0:
                    get_post_check = db.session.query(anonForumPosts.a_post_id).filter(anonForumPosts.deleted==False).filter(anonForumPosts.a_date_time > timeCut).filter(anonForumPosts.a_original_post_id==0).filter(anonForumPosts.a_post_lat.between(min_lat, max_lat)).filter(anonForumPosts.a_post_long.between(min_long, max_long)).order_by(anonForumPosts.a_date_time.desc()).distinct().count()
                else:
                    get_post_check = db.session.query(anonForumPosts.a_post_id).filter(anonForumPosts.deleted==False).filter(anonForumPosts.a_date_time > timeCut).filter(anonForumPosts.a_post_id < lastPostID).filter(anonForumPosts.a_original_post_id==0).filter(anonForumPosts.a_post_lat.between(min_lat, max_lat)).filter(anonForumPosts.a_post_long.between(min_long, max_long)).order_by(anonForumPosts.a_date_time.desc()).distinct().count()
            elif sort == 'hot': # adjust time range?
                if lastPostID == 0:
                    get_post_check = db.session.query(anonForumPosts.a_post_id).filter(anonForumPosts.deleted==False).filter(anonForumPosts.a_date_time > timeCut).filter(anonForumPosts.a_original_post_id==0).filter(anonForumPosts.a_post_lat.between(min_lat, max_lat)).filter(anonForumPosts.a_post_long.between(min_long, max_long)).order_by(anonForumPosts.a_points_count.desc()).distinct().count()
                else:                        
                    get_post_check = db.session.query(anonForumPosts.a_post_id).filter(anonForumPosts.deleted==False).filter(anonForumPosts.a_date_time > timeCut).filter(anonForumPosts.a_post_id < lastPostID).filter(anonForumPosts.a_original_post_id==0).filter(anonForumPosts.a_post_lat.between(min_lat, max_lat)).filter(anonForumPosts.a_post_long.between(min_long, max_long)).order_by(anonForumPosts.a_points_count.desc()).distinct().count()
    except Exception, e:
        print str(e)
    finally:
        db.session.close()
    '''
    print int(get_post_check)
    print 'radius: ', radius
    print 'td: ',td
    print '\n\n'
    '''
    if (int(get_post_check) < DEFAULT_LIMIT) and (radius < MAX_RADIUS):
        radius, td = dynamicRadiusHelper(myLong, myLat, postType, sort, radius * 1.5, td, lastPostID)
    elif (int(get_post_check) < DEFAULT_LIMIT) and (sort != 'hot') and (radius == MAX_RADIUS) and (td < MAX_TIME):
        radius, td = dynamicRadiusHelper(myLong, myLat, postType, sort, radius, td * 1.5, lastPostID)
    return radius, td
        



#@application.route('/', methods=['GET','POST'])

from front.front import front_test

application.register_blueprint(front_test)

if __name__ == '__main__':
    if ENABLE_ERRORS:
        application.debug = True
    else:
        application.debug = False
    application.run(host='0.0.0.0')
    
