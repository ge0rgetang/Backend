'''
Created on May 30, 2016

@author: Michael Tam

'''

from flask import Flask, request
from application.models import users, chats, friends, forumPosts, groupDetails, groupMembers, groupPosts, groupEventDetails, groupEventPosts, groupEventUsers, forumPostUpvoted, groupPostUpvoted, eventPostUpvoted, systemMessages, reportedPosts, notific, anonForumPosts, anonForumPostUpvoted
from application import db
import json, bcrypt, boto3, os, re, time, re, requests
import boto.sns
from email.utils import parseaddr
from sqlalchemy import or_, update, and_, case, func #in_
from sqlalchemy.orm import load_only
from math import cos
from decimal import Decimal
from datetime import datetime, timedelta, time, date
from firebase import firebase
from firebase_token_generator import create_token

PROF_BUCKET = 'hostpostuserprof'
GROUP_BUCKET = 'hostpostgroup'
EVENT_BUCKET = 'hostposteventimage'
PLATFORM_APPLICATION_ARN = 'arn:aws:sns:us-west-1:554061732115:app/APNS_SANDBOX/hostPostDev'
AWS_ACCESS_KEY_ID = "AKIAIAWLQ6C2HQNAFCOA"
AWS_SECRET_ACCESS_KEY = "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"
DEFAULT_LIMIT = 42


DEFAULT_STIPEND = 42
DEFAULT_STIPEND_TIME = timedelta(days=7)


application = Flask(__name__)
application.debug = True

application.secret_key = 'cC1YCIWOj9GgWspgNEo2'

@application.route('/login', methods=['POST'])
def login():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('deviceID','userEmail','userPassword')):
            userEmail = request.form['userEmail']        
            userPass = request.form['userPassword']
            login_method = 0 #login via email
            devID = request.form['deviceID']
        elif all (k in request.form for k in ('deviceID','userHandle','userPassword')):
            userHandle = request.form['userHandle']
            userPass = request.form['userPassword']
            login_method = 1 #login via handle
            devID = request.form['deviceID']
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    result = {'status':'error', 'message':'Invalid User Name or Password'}
    try:
        if login_method == 0:
            login_check = db.session.query(users).filter(users.u_email==userEmail).first() 
        else: #login via handle
            login_check = db.session.query(users).filter(users.u_handle==userHandle).first() 
        if login_check != []:
            if login_check.verify_password(userPass):
                db.session.query(users).filter(users.u_id==login_check.u_id).update({'device_arn':register_device(devID,login_check.u_id)})
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
                '''
                if (datetime.now() - login_check.last_stipend_date > DEFAULT_STIPEND_TIME):
                    login_check.stipend_points = DEFAULT_STIPEND
                '''
        db.session.close()
    except Exception, e:
        result = {'status':'error', 'message':str(e)}
        pass    
    return json.dumps(result)

@application.route('/register', methods=['POST'])
def register():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myIDFIR','deviceID','userEmail','userName','userHandle','userPassword','isPicSet')):
            userEmail = request.form['userEmail']
            userHandle = request.form['userHandle']
            userName = request.form['userName']
            hashpaswrd = hash_password(request.form['userPassword'].encode('utf-8'))
            picSet = request.form['isPicSet']
            devID = request.form['deviceID']
            fireBID = request.form['myIDFIR']
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    if not (validate_email(userEmail) or validate_handle(userHandle)):
        return json.dumps(result)    

    data_entered = users(u_email = userEmail, u_name=userName, u_paswd = hashpaswrd, u_handle = userHandle, stipend_points = DEFAULT_STIPEND, firebase_id=fireBID, device_arn = register_device(devID))
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
    print handle_exist
    print email_exist
    if handle_exist != 0:
        result['message'] = 'User handle already exists'
        return json.dumps(result)
    elif email_exist !=0:
        result['message'] = 'User email already exists'
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
            result['smallKey'] = 'default'
            result['mediumKey'] = 'default'
            result['largeKey'] = 'default'
        result['bucket']= PROF_BUCKET
        result['status'] = 'success'
        db.session.commit()
    except Exception, e:
        db.session.rollback()
        result = {'status':'error', 'message':str(e)}
    finally:
        db.session.close()
    return json.dumps(result)

@application.route('/getMixedPost', methods=['POST']) #sort new, hot=all posts in last 24 hours ordered by points
def getMixedPost():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID', 'postID','lastPostID','size')):
            myID = request.form['myID']
            postID = int(request.form['postID'])
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
            if lastPostID==0:
                get_forum_check = db.session.query(forumPosts.post_id, users.u_id, users.u_name, users.u_handle,users.u_key, users.firebase_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points).filter(forumPosts.post_u_id==users.u_id).filter(forumPosts.original_post_id==0).filter(forumPosts.post_lat.between(min_lat, max_lat)).filter(forumPosts.post_long.between(min_long, max_long)).outerjoin(forumPostUpvoted, and_(forumPostUpvoted.post_id==forumPosts.post_id, forumPostUpvoted.voter_id==myID)).order_by(forumPosts.date_time.desc()).distinct().limit(DEFAULT_LIMIT)
                get_anon_check = db.session.query(anonForumPosts.a_post_id, users.u_id, users.u_name, users.u_handle,users.u_key, anonForumPosts.a_post_cont, anonForumPosts.a_points_count, anonForumPosts.a_reply_count, anonForumPosts.a_date_time, anonForumPosts.a_date_time_edited, anonForumPostUpvoted.points).filter(anonForumPosts.a_post_u_id==users.u_id).filter(anonForumPosts.a_original_post_id==0).filter(anonForumPosts.a_post_lat.between(min_lat, max_lat)).filter(anonForumPosts.a_post_long.between(min_long, max_long)).outerjoin(anonForumPostUpvoted, and_(anonForumPostUpvoted.post_id==anonForumPosts.a_post_id, anonForumPostUpvoted.voter_id==myID)).order_by(anonForumPosts.a_date_time.desc()).distinct().limit(DEFAULT_LIMIT)
            else:      
                get_forum_check = db.session.query(forumPosts.post_id, users.u_id, users.u_name, users.u_handle,users.u_key, users.firebase_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points).filter(forumPosts.post_u_id==users.u_id).filter(forumPosts.original_post_id==0).filter(forumPosts.post_id < lastPostID).filter(forumPosts.post_lat.between(min_lat, max_lat)).filter(forumPosts.post_long.between(min_long, max_long)).outerjoin(forumPostUpvoted, and_(forumPostUpvoted.post_id==forumPosts.post_id, forumPostUpvoted.voter_id==myID)).order_by(forumPosts.date_time.desc()).distinct().limit(DEFAULT_LIMIT)
                get_anon_check = db.session.query(anonForumPosts.a_post_id, users.u_id, users.u_name, users.u_handle,users.u_key, anonForumPosts.a_post_cont, anonForumPosts.a_points_count, anonForumPosts.a_reply_count, anonForumPosts.a_date_time, anonForumPosts.a_date_time_edited, anonForumPostUpvoted.points).filter(anonForumPosts.a_post_u_id==users.u_id).filter(anonForumPosts.a_post_id < lastPostID).filter(anonForumPosts.a_original_post_id==0).filter(anonForumPosts.a_post_lat.between(min_lat, max_lat)).filter(anonForumPosts.a_post_long.between(min_long, max_long)).outerjoin(anonForumPostUpvoted, and_(anonForumPostUpvoted.post_id==anonForumPosts.a_post_id, anonForumPostUpvoted.voter_id==myID)).order_by(anonForumPosts.a_date_time.desc()).distinct().limit(DEFAULT_LIMIT)
                #return json.dumps({'status':'error','message':'got here'})
        if sort == 'hot':
            timeCut = datetime.now() - timedelta(hours = 48) # adjust time range?
            if lastPostID == 0:
                '''
                Do not know why I did an outerjoin. Think straight 3-way join works. Need to test
                '''
                get_forum_check = db.session.query(forumPosts.post_id, users.u_id, users.u_name, users.u_handle,users.u_key, users.firebase_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points).filter(forumPosts.date_time > timeCut).filter(forumPosts.post_u_id==users.u_id).filter(forumPosts.original_post_id==0).filter(forumPosts.post_lat.between(min_lat, max_lat)).filter(forumPosts.post_long.between(min_long, max_long)).outerjoin(forumPostUpvoted, and_(forumPostUpvoted.post_id==forumPosts.post_id, forumPostUpvoted.voter_id==myID)).order_by(forumPosts.points_count.desc()).distinct().limit(DEFAULT_LIMIT) #restrict by date
                get_anon_check = db.session.query(anonForumPosts.a_post_id, users.u_id, users.u_name, users.u_handle,users.u_key, anonForumPosts.a_post_cont, anonForumPosts.a_points_count, anonForumPosts.a_reply_count, anonForumPosts.a_date_time, anonForumPosts.a_date_time_edited, anonForumPostUpvoted.points).filter(anonForumPosts.a_date_time > timeCut).filter(anonForumPosts.a_post_u_id==users.u_id).filter(anonForumPosts.a_original_post_id==0).filter(anonForumPosts.a_post_lat.between(min_lat, max_lat)).filter(anonForumPosts.a_post_long.between(min_long, max_long)).outerjoin(anonForumPostUpvoted, and_(anonForumPostUpvoted.post_id==anonForumPosts.a_post_id, anonForumPostUpvoted.voter_id==myID)).order_by(anonForumPosts.a_points_count.desc()).distinct().limit(DEFAULT_LIMIT) #restrict by date
                '''
                get_forum_check = db.session.query(forumPosts.post_id, users.u_id, users.u_name, users.u_handle,users.u_key, users.firebase_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points).filter(forumPosts.date_time > timeCut).filter(forumPosts.post_u_id==users.u_id).filter(forumPosts.original_post_id==0).filter(forumPosts.post_lat.between(min_lat, max_lat)).filter(forumPosts.post_long.between(min_long, max_long)).filter(forumPostUpvoted.post_id==forumPosts.post_id).filter(forumPostUpvoted.voter_id==myID).order_by(forumPosts.points_count.desc()).distinct().limit(DEFAULT_LIMIT)
                get_anon_check = db.session.query(anonForumPosts.a_post_id, users.u_id, users.u_name, users.u_handle,users.u_key, anonForumPosts.a_post_cont, anonForumPosts.a_points_count, anonForumPosts.a_reply_count, anonForumPosts.a_date_time, anonForumPosts.a_date_time_edited, anonForumPostUpvoted.points).filter(anonForumPosts.a_date_time > timeCut).filter(anonForumPosts.a_post_u_id==users.u_id).filter(anonForumPosts.a_original_post_id==0).filter(anonForumPosts.a_post_lat.between(min_lat, max_lat)).filter(anonForumPosts.a_post_long.between(min_long, max_long)).filter(anonForumPostUpvoted.post_id==anonForumPosts.a_post_id).filter(anonForumPostUpvoted.voter_id==myID).order_by(anonForumPosts.a_points_count.desc()).distinct().limit(DEFAULT_LIMIT) #restrict by date
            '''
            else:
                '''
                get_forum_check = db.session.query(forumPosts.post_id, users.u_id, users.u_name, users.u_handle,users.u_key, users.firebase_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points).filter(forumPosts.date_time > timeCut).filter(forumPosts.post_u_id==users.u_id).filter(forumPosts.original_post_id==0).filter(forumPosts.post_id < lastPostID).filter(forumPosts.post_lat.between(min_lat, max_lat)).filter(forumPosts.post_long.between(min_long, max_long)).filter(and_(forumPostUpvoted.post_id==forumPosts.post_id, forumPostUpvoted.voter_id==myID)).order_by(forumPosts.points_count.desc()).distinct().limit(DEFAULT_LIMIT) #restrict by date
                get_anon_check = db.session.query(anonForumPosts.a_post_id, users.u_id, users.u_name, users.u_handle,users.u_key, anonForumPosts.a_post_cont, anonForumPosts.a_points_count, anonForumPosts.a_reply_count, anonForumPosts.a_date_time, anonForumPosts.a_date_time_edited, anonForumPostUpvoted.points).filter(anonForumPosts.a_date_time > timeCut).filter(anonForumPosts.a_post_u_id==users.u_id).filter(anonForumPosts.a_post_id < lastPostID).filter(anonForumPosts.a_original_post_id==0).filter(anonForumPosts.a_post_lat.between(min_lat, max_lat)).filter(anonForumPosts.a_post_long.between(min_long, max_long)).filter(and_(anonForumPostUpvoted.post_id==anonForumPosts.a_post_id, anonForumPostUpvoted.voter_id==myID)).order_by(anonForumPosts.a_points_count.desc()).distinct().limit(DEFAULT_LIMIT) #restrict by date
                '''
                get_forum_check = db.session.query(forumPosts.post_id, users.u_id, users.u_name, users.u_handle,users.u_key, users.firebase_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points).filter(forumPosts.date_time > timeCut).filter(forumPosts.post_u_id==users.u_id).filter(forumPosts.original_post_id==0).filter(forumPosts.post_id < lastPostID).filter(forumPosts.post_lat.between(min_lat, max_lat)).filter(forumPosts.post_long.between(min_long, max_long)).outerjoin(forumPostUpvoted, and_(forumPostUpvoted.post_id==forumPosts.post_id, forumPostUpvoted.voter_id==myID)).order_by(forumPosts.points_count.desc()).distinct().limit(DEFAULT_LIMIT) #restrict by date
                get_anon_check = db.session.query(anonForumPosts.a_post_id, users.u_id, users.u_name, users.u_handle,users.u_key, anonForumPosts.a_post_cont, anonForumPosts.a_points_count, anonForumPosts.a_reply_count, anonForumPosts.a_date_time, anonForumPosts.a_date_time_edited, anonForumPostUpvoted.points).filter(anonForumPosts.a_date_time > timeCut).filter(anonForumPosts.a_post_u_id==users.u_id).filter(anonForumPosts.a_post_id < lastPostID).filter(anonForumPosts.a_original_post_id==0).filter(anonForumPosts.a_post_lat.between(min_lat, max_lat)).filter(anonForumPosts.a_post_long.between(min_long, max_long)).outerjoin(anonForumPostUpvoted, and_(anonForumPostUpvoted.post_id==anonForumPosts.a_post_id, anonForumPostUpvoted.voter_id==myID)).order_by(anonForumPosts.a_points_count.desc()).distinct().limit(DEFAULT_LIMIT) #restrict by date
        else:
            result={'status':'error', 'message':'Invalid Sort'}
        if get_forum_check is not None and get_anon_check is not None:
            result['status'] = 'success'        
            if get_forum_check == [] and get_anon_check==[]:
                result['message'] = 'No results found'
            else:
                result['message'] = 'Results Found'
                anon_labels = ['postID','userID','userName','userHandle','key','postContent','pointsCount','replyCount','timestamp','timestampEdited','didIVote']
                add_all = 'bucket'
                anonForumPostsList = add_labels(anon_labels,get_anon_check,add_all,PROF_BUCKET, True)
                forum_labels = ['postID','userID','userName','userHandle','key','firebaseID','postContent','pointsCount','replyCount','timestamp','timestampEdited','didIVote']
                forumPostsList = add_labels(forum_labels,get_forum_check,add_all,PROF_BUCKET, True, keySize=size)
                result['posts']=[]
                print 'here'
                if sort == 'new':
                    a=0
                    a_max = len(anonForumPostsList)-1
                    f=0
                    f_max = len(forumPostsList)-1
                    for i in range(0,DEFAULT_LIMIT):
                        if f >= f_max or anonForumPostsList[a]['timestamp'] > forumPostsList[f]['timestamp']:
                            result['posts'].append(anonForumPostsList[a])
                            a+=1
                        elif a >= a_max or anonForumPostsList[a]['timestamp'] < forumPostsList[f]['timestamp']:
                            result['posts'].append(forumPostsList[f])
                            f+=1
                elif sort =='hot':
                    a=0
                    a_max = len(anonForumPostsList)-1
                    f=0
                    f_max = len(forumPostsList)-1
                    for i in range(0,DEFAULT_LIMIT):
                        if f < f_max and a < a_max:
                            if anonForumPostsList[a]['pointsCount'] > forumPostsList[f]['pointsCount']:
                                result['posts'].append(anonForumPostsList[a])
                                a+=1
                            elif anonForumPostsList[a]['pointsCount'] < forumPostsList[f]['pointsCount']:
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
    except Exception, e:
        db.session.rollback()
        result = {'status':'error', 'message':str(e)}
    finally:
        db.session.close()   
    return json.dumps(result) 


@application.route('/getForumPost', methods=['POST']) #sort hot=all posts in last 24 hours ordered by points
def getForumPost():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID', 'postID','lastPostID','size')):
            myID = request.form['myID']
            postID = int(request.form['postID'])
            lastPostID = int(request.form['lastPostID'])
            size = request.form['size']
            if postID == 0: #get parent posts or get my posts
                if 'isMine' in request.form:
                    isMine = str(request.form['isMine'])
                    if isMine == 'no':
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
                #result = json.dumps({'status':'error','message':'wrong place'})
                subq = db.session.query(forumPosts.original_post_id).filter(forumPosts.post_u_id == myID).filter(forumPosts.original_post_id != 0).distinct().subquery()
                subq2 = db.session.query(forumPostUpvoted.post_id).filter(forumPostUpvoted.voter_id == myID).distinct().subquery()
                if lastPostID == 0:
                    '''
                    get_my_posts = db.session.query(forumPosts.post_id, users.u_id, users.u_name, users.u_handle,users.u_key,users.firebase_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points).filter(forumPosts.post_u_id==users.u_id).filter(forumPosts.post_u_id==myID).filter(or_(forumPosts.original_post_id==0, forumPosts.post_id.in_(subq))).outerjoin(forumPostUpvoted, and_(forumPostUpvoted.post_id==forumPosts.post_id, forumPostUpvoted.voter_id==myID)).order_by(forumPosts.date_time.desc()).distinct().limit(DEFAULT_LIMIT)
                    '''
                    get_my_posts = db.session.query(forumPosts.post_id, users.u_id, users.u_name, users.u_handle,users.u_key,users.firebase_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points).filter(forumPosts.post_u_id==users.u_id).filter(or_(forumPosts.post_u_id==myID, forumPosts.post_id.in_(subq2))).filter(or_(forumPosts.original_post_id==0, forumPosts.post_id.in_(subq))).outerjoin(forumPostUpvoted, and_(forumPostUpvoted.post_id==forumPosts.post_id, forumPostUpvoted.voter_id==myID)).order_by(forumPosts.date_time.desc()).distinct().limit(DEFAULT_LIMIT)
                else:
                    get_my_posts = db.session.query(forumPosts.post_id, users.u_id, users.u_name, users.u_handle,users.u_key,users.firebase_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points).filter(forumPosts.post_u_id==users.u_id).filter(or_(forumPosts.post_u_id==myID, forumPosts.post_id.in_(subq2))).filter(forumPosts.post_id < lastPostID).filter(or_(forumPosts.original_post_id==0, forumPosts.post_id.in_(subq))).outerjoin(forumPostUpvoted, and_(forumPostUpvoted.post_id==forumPosts.post_id, forumPostUpvoted.voter_id==myID)).order_by(forumPosts.date_time.desc()).distinct().limit(DEFAULT_LIMIT)
                if get_my_posts is not None:    
                    #query for post count
                    #return json.dumps({'result':'here'})
                    result['status'] = 'success'        
                    if get_my_posts == []:
                        result['message'] = 'No results found'
                    else:
                        result['message'] = 'Results Found'
                        labels = ['postID','userID','userName','userHandle','key','firebaseID','postContent','pointsCount','replyCount','timestamp','timestampEdited','didIVote']
                        add_all = 'bucket'
                        result['forumPosts'] = add_labels(labels,get_my_posts,add_all,PROF_BUCKET, True, keySize=size)
            elif isMine == 'no':
                min_long, max_long, min_lat, max_lat = getMinMaxLongLat(myLong, myLat, radius)
                if sort == 'new':
                    if lastPostID == 0:
                        get_post_check = db.session.query(forumPosts.post_id, users.u_id, users.u_name, users.u_handle,users.u_key, users.firebase_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points).filter(forumPosts.post_u_id==users.u_id).filter(forumPosts.original_post_id==0).filter(forumPosts.post_lat.between(min_lat, max_lat)).filter(forumPosts.post_long.between(min_long, max_long)).outerjoin(forumPostUpvoted, and_(forumPostUpvoted.post_id==forumPosts.post_id, forumPostUpvoted.voter_id==myID)).order_by(forumPosts.date_time.desc()).distinct().limit(DEFAULT_LIMIT)
                    else:                         
                        get_post_check = db.session.query(forumPosts.post_id, users.u_id, users.u_name, users.u_handle,users.u_key, users.firebase_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points).filter(forumPosts.post_u_id==users.u_id).filter(forumPosts.original_post_id==0).filter(forumPosts.post_id < lastPostID).filter(forumPosts.post_lat.between(min_lat, max_lat)).filter(forumPosts.post_long.between(min_long, max_long)).outerjoin(forumPostUpvoted, and_(forumPostUpvoted.post_id==forumPosts.post_id, forumPostUpvoted.voter_id==myID)).order_by(forumPosts.date_time.desc()).distinct().limit(DEFAULT_LIMIT)
                    #return json.dumps({'status':'error','message':'got here'})
                elif sort == 'hot':
                    timeCut = datetime.now() - timedelta(hours = 48) # adjust time range?
                    if lastPostID == 0:    
                        get_post_check = db.session.query(forumPosts.post_id, users.u_id, users.u_name, users.u_handle,users.u_key, users.firebase_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points).filter(forumPosts.date_time > timeCut).filter(forumPosts.post_u_id==users.u_id).filter(forumPosts.original_post_id==0).filter(forumPosts.post_lat.between(min_lat, max_lat)).filter(forumPosts.post_long.between(min_long, max_long)).outerjoin(forumPostUpvoted, and_(forumPostUpvoted.post_id==forumPosts.post_id, forumPostUpvoted.voter_id==myID)).order_by(forumPosts.points_count.desc()).distinct().limit(DEFAULT_LIMIT) #restrict by date
                    else:
                        get_post_check = db.session.query(forumPosts.post_id, users.u_id, users.u_name, users.u_handle,users.u_key, users.firebase_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points).filter(forumPosts.date_time > timeCut).filter(forumPosts.post_u_id==users.u_id).filter(forumPosts.original_post_id==0).filter(forumPosts.post_id < lastPostID).filter(forumPosts.post_lat.between(min_lat, max_lat)).filter(forumPosts.post_long.between(min_long, max_long)).outerjoin(forumPostUpvoted, and_(forumPostUpvoted.post_id==forumPosts.post_id, forumPostUpvoted.voter_id==myID)).order_by(forumPosts.points_count.desc()).distinct().limit(DEFAULT_LIMIT) #restrict by date
                else:
                    return json.dumps(result)
                if get_post_check is not None:
                    result['status'] = 'success'        
                    if get_post_check == []:
                        result['message'] = 'No results found'
                    else:
                        result['message'] = 'Results Found'
                        labels = ['postID','userID','userName','userHandle','key','firebaseID','postContent','pointsCount','replyCount','timestamp','timestampEdited','didIVote']
                        add_all = 'bucket'
                        result['forumPosts'] = add_labels(labels,get_post_check,add_all,PROF_BUCKET, True, keySize=size)
        else: #actual postID sort by desc but send parent in first position
            if lastPostID==0:
                #get_posts = db.session.query(forumPosts.post_id, users.u_id, users.u_name, users.u_handle,users.u_key, users.firebase_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points).outerjoin(forumPostUpvoted, and_(forumPostUpvoted.post_id==forumPosts.post_id, forumPostUpvoted.voter_id==myID)).filter(forumPosts.post_u_id==users.u_id).filter(or_(forumPosts.post_id==postID,forumPosts.original_post_id==postID)).distinct().order_by(forumPosts.post_id).limit(DEFAULT_LIMIT)                
                get_posts = db.session.query(forumPosts.post_id, users.u_id, users.u_name, users.u_handle,users.u_key, users.firebase_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points).outerjoin(forumPostUpvoted, and_(forumPostUpvoted.post_id==forumPosts.post_id, forumPostUpvoted.voter_id==myID)).filter(forumPosts.post_u_id==users.u_id).filter(forumPosts.post_id==postID).distinct().limit(DEFAULT_LIMIT)
                get_replies = db.session.query(forumPosts.post_id, users.u_id, users.u_name, users.u_handle, users.u_key, users.firebase_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points).filter(forumPosts.post_u_id==users.u_id).filter(forumPosts.original_post_id==postID).outerjoin(forumPostUpvoted, and_(forumPostUpvoted.post_id==forumPosts.post_id, forumPostUpvoted.voter_id==myID)).order_by(forumPosts.post_id.desc()).distinct().limit(DEFAULT_LIMIT) 
            else:
                #get_posts = db.session.query(forumPosts.post_id, users.u_id, users.u_name, users.u_handle,users.u_key, users.firebase_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points).filter(forumPosts.post_id < lastPostID).outerjoin(forumPostUpvoted, and_(forumPostUpvoted.post_id==forumPosts.post_id, forumPostUpvoted.voter_id==myID)).filter(forumPosts.post_u_id==users.u_id).filter(or_(forumPosts.post_id==postID, forumPosts.original_post_id==postID)).order_by(forumPosts.post_id).distinct().limit(DEFAULT_LIMIT)
                get_posts = db.session.query(forumPosts.post_id, users.u_id, users.u_name, users.u_handle,users.u_key, users.firebase_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points).filter(forumPosts.post_id < lastPostID).outerjoin(forumPostUpvoted, and_(forumPostUpvoted.post_id==forumPosts.post_id, forumPostUpvoted.voter_id==myID)).filter(forumPosts.post_u_id==users.u_id).filter(forumPosts.post_id==postID).distinct().limit(DEFAULT_LIMIT)
                get_replies = db.session.query(forumPosts.post_id, users.u_id, users.u_name, users.u_handle, users.u_key, users.firebase_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points).filter(forumPosts.post_id < lastPostID).filter(forumPosts.post_u_id==users.u_id).filter(forumPosts.original_post_id==postID).outerjoin(forumPostUpvoted, and_(forumPostUpvoted.post_id==forumPosts.post_id, forumPostUpvoted.voter_id==myID)).order_by(forumPosts.post_id.desc()).distinct().limit(DEFAULT_LIMIT) 
            if get_posts is not None:
                if get_posts == []:
                    result['message'] = 'No results found'
                else:
                    print get_posts
                    result['status'] = 'success' 
                    result['message'] = 'Results Found'
                    labels = ['postID','userID','userName','userHandle','key','firebaseID','postContent','pointsCount','replyCount','timestamp','timestampEdited','didIVote']
                    add_all = 'bucket'
                    result['forumPosts'] = add_labels(labels,get_posts,add_all,PROF_BUCKET, first_initial=True, keySize=size) + add_labels(labels,get_replies,add_all,PROF_BUCKET, first_initial=True, keySize=size)
                    '''
                    if get_replies is not None:
                        if get_replies == []:
                            result['message'] = result['message'] + '. No replies found'
                        else:
                            result['forumPosts'] = add_labels(labels,get_replies,add_all,PROF_BUCKET)
                            result['message'] = result['message'] + '. Replies found'
                    '''
        db.session.close()
    except Exception, e:
        result = {'status':'error', 'message':str(e)}
        pass
    data = json.dumps(result)
    return data

@application.route('/sendForumPost', methods=['POST'])
def sendForumPost():
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
        data_entered = forumPosts(post_u_id = myID, post_cont = postCont, post_long = postLong, post_lat = postLat)
    else:
        data_entered = forumPosts(post_u_id = myID, post_cont = postCont, original_post_id = postID)
    try:
        db.session.add(data_entered)
        db.session.flush()
        result['postID']=data_entered.post_id
        db.session.commit()
        if postID not in (0, -1):
            db.session.query(forumPosts).filter(forumPosts.post_id==postID).update({'reply_count':forumPosts.reply_count + 1})
            db.session.commit()
            user_check = db.session.query(users.u_handle, users.device_arn, forumPosts.post_cont, users.firebase_id).filter(users.u_id==forumPosts.post_u_id).filter(forumPosts.post_id==postID).one()
            cont = '@' + user_check.u_handle + ' replied to your forum post! ' + user_check.post_cont
            subj = 'getMyForumPost'
            logNotification(forumPosts.post_u_id, cont, subj)
            firebaseNotification(user_check.firebase_id, cont)
            if user_check is not None and user_check != []:
                if user_check.device_arn != 0:                      
                    push(user_check.device_arn, 1, cont, subj)
        result['status'] = 'success'
        result['message'] = 'Posted'
    except Exception, e:
        db.session.rollback()
        result = {'status':'error', 'message':str(e)}
        pass
    finally:
        db.session.close()
    data = json.dumps(result)
    return data

@application.route('/getAnonForumPost', methods=['POST']) #sort hot=all posts in last 24 hours ordered by points
def getAnonForumPost():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID', 'postID', 'lastPostID')):
            myID = request.form['myID']
            postID = int(request.form['postID'])
            lastPostID = int(request.form['lastPostID'])
            if postID == 0: #get parent posts or get my posts
                if 'isMine' in request.form:
                    isMine = str(request.form['isMine'])
                    if isMine == 'no':
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
                if lastPostID ==0:
                    get_my_posts = db.session.query(users.u_id, users.u_name, users.u_handle,users.u_key, users.firebase_id, anonForumPosts.a_post_id, anonForumPosts.a_post_cont, anonForumPosts.a_points_count, anonForumPosts.a_reply_count, anonForumPosts.a_date_time, anonForumPosts.a_date_time_edited, anonForumPostUpvoted.points).filter(anonForumPosts.a_post_u_id==users.u_id).filter(or_(anonForumPosts.a_post_u_id==myID,anonForumPosts.a_post_id.in_(subq2))).filter(or_(anonForumPosts.a_original_post_id==0, anonForumPosts.a_post_id.in_(subq))).outerjoin(anonForumPostUpvoted, and_(anonForumPostUpvoted.post_id==anonForumPosts.a_post_id, anonfForumPostUpvoted.voter_id==myID)).order_by(anonForumPosts.a_date_time.desc()).distinct().limit(DEFAULT_LIMIT)
                else:                
                    get_my_posts = db.session.query(users.u_id, users.u_name, users.u_handle,users.u_key, users.firebase_id, anonForumPosts.a_post_id, anonForumPosts.a_post_cont, anonForumPosts.a_points_count, anonForumPosts.a_reply_count, anonForumPosts.a_date_time, anonForumPosts.a_date_time_edited, anonForumPostUpvoted.points).filter(anonForumPosts.a_post_id < lastPostID).filter(anonForumPosts.a_post_u_id==users.u_id).filter(or_(anonForumPosts.a_post_u_id==myID,anonForumPosts.a_post_id.in_(subq2))).filter(or_(anonForumPosts.a_original_post_id==0, anonForumPosts.a_post_id.in_(subq))).outerjoin(anonForumPostUpvoted, and_(anonForumPostUpvoted.post_id==anonForumPosts.a_post_id, anonfForumPostUpvoted.voter_id==myID)).order_by(anonForumPosts.a_date_time.desc()).distinct().limit(DEFAULT_LIMIT)
                if get_my_posts is not None:    
                    #query for post count
                    
                    #return json.dumps({'result':'here'})
                
                    result['status'] = 'success'        
                    result['message'] = 'Results Found'
                    labels = ['userID','userName','userHandle','key', 'firebaseID', 'postID','postContent','pointsCount','replyCount','timestamp','timestampEdited','didIVote']
                    add_all = 'bucket'
                    result['anonForumPosts'] = add_labels(labels,get_my_posts,add_all,PROF_BUCKET, True)
                    if result['anonForumPosts'] == []:
                        result['message'] = 'No results found'
            elif isMine == 'no':
                min_long, max_long, min_lat, max_lat = getMinMaxLongLat(myLong, myLat, radius)
                if sort == 'new':  
                    if lastPostID==0:
                        get_post_check = db.session.query(anonForumPosts.a_post_id, users.u_id, users.u_name, users.u_handle, users.u_key, users.firebase_id, anonForumPosts.a_post_cont, anonForumPosts.a_points_count, anonForumPosts.a_reply_count, anonForumPosts.a_date_time, anonForumPosts.a_date_time_edited, anonForumPostUpvoted.points).filter(anonForumPosts.a_post_u_id==users.u_id).filter(anonForumPosts.a_original_post_id==0).filter(anonForumPosts.a_post_lat.between(min_lat, max_lat)).filter(anonForumPosts.a_post_long.between(min_long, max_long)).outerjoin(anonForumPostUpvoted, and_(anonForumPostUpvoted.post_id==anonForumPosts.a_post_id, anonForumPostUpvoted.voter_id==myID)).order_by(anonForumPosts.a_date_time.desc()).distinct().limit(DEFAULT_LIMIT)  
                    else:
                        get_post_check = db.session.query(anonForumPosts.a_post_id, users.u_id, users.u_name, users.u_handle, users.u_key, users.firebase_id, anonForumPosts.a_post_cont, anonForumPosts.a_points_count, anonForumPosts.a_reply_count, anonForumPosts.a_date_time, anonForumPosts.a_date_time_edited, anonForumPostUpvoted.points).filter(anonForumPosts.a_post_u_id==users.u_id).filter(anonForumPosts.a_post_id < lastPostID).filter(anonForumPosts.a_original_post_id==0).filter(anonForumPosts.a_post_lat.between(min_lat, max_lat)).filter(anonForumPosts.a_post_long.between(min_long, max_long)).outerjoin(anonForumPostUpvoted, and_(anonForumPostUpvoted.post_id==anonForumPosts.a_post_id, anonForumPostUpvoted.voter_id==myID)).order_by(anonForumPosts.a_date_time.desc()).distinct().limit(DEFAULT_LIMIT)
                    #return json.dumps({'status':'error','message':'got here'})
                elif sort == 'hot':
                    timeCut = datetime.now() - timedelta(hours = 48) # adjust time range?
                    if lastPostID == 0:
                        get_post_check = db.session.query(anonForumPosts.a_post_id, users.u_id, users.u_name, users.u_handle,users.u_key, users.firebase_id, anonForumPosts.a_post_cont, anonForumPosts.a_points_count, anonForumPosts.a_reply_count, anonForumPosts.a_date_time, anonForumPosts.a_date_time_edited, anonForumPostUpvoted.points).filter(anonForumPosts.a_date_time > timeCut).filter(anonForumPosts.a_post_u_id==users.u_id).filter(anonForumPosts.a_original_post_id==0).filter(anonForumPosts.a_post_lat.between(min_lat, max_lat)).filter(anonForumPosts.a_post_long.between(min_long, max_long)).outerjoin(anonForumPostUpvoted, and_(anonForumPostUpvoted.post_id==anonForumPosts.a_post_id, anonForumPostUpvoted.voter_id==myID)).order_by(anonForumPosts.a_points_count.desc()).distinct().limit(DEFAULT_LIMIT) #restrict by date
                    else:                        
                        get_post_check = db.session.query(anonForumPosts.a_post_id, users.u_id, users.u_name, users.u_handle,users.u_key, users.firebase_id, anonForumPosts.a_post_cont, anonForumPosts.a_points_count, anonForumPosts.a_reply_count, anonForumPosts.a_date_time, anonForumPosts.a_date_time_edited, anonForumPostUpvoted.points).filter(anonForumPosts.a_date_time > timeCut).filter(anonForumPosts.a_post_u_id==users.u_id).filter(anonForumPosts.a_post_id < lastPostID).filter(anonForumPosts.a_original_post_id==0).filter(anonForumPosts.a_post_lat.between(min_lat, max_lat)).filter(anonForumPosts.a_post_long.between(min_long, max_long)).outerjoin(anonForumPostUpvoted, and_(anonForumPostUpvoted.post_id==anonForumPosts.a_post_id, anonForumPostUpvoted.voter_id==myID)).order_by(anonForumPosts.a_points_count.desc()).distinct().limit(DEFAULT_LIMIT) #restrict by date
                else:
                    return json.dumps(result)
                if get_post_check is not None:
                    result['status'] = 'success'        
                    result['message'] = 'Results Found'
                    labels = ['postID','userID','userName','userHandle','key', 'firebaseID', 'postContent','pointsCount','replyCount','timestamp','timestampEdited','didIVote']
                    add_all = 'bucket'
                    result['anonForumPosts'] = add_labels(labels,get_post_check,add_all,PROF_BUCKET, True)
                    if result['anonForumPosts'] == []:
                        result['message'] = 'No results found'
        else: #actual postID
            if lastPostID==0:
                get_posts = db.session.query(anonForumPosts.a_post_id, users.u_id, users.u_name, users.u_handle,users.u_key, users.firebase_id, anonForumPosts.a_post_cont, anonForumPosts.a_points_count, anonForumPosts.a_reply_count, anonForumPosts.a_date_time, anonForumPosts.a_date_time_edited, anonForumPostUpvoted.points).filter(anonForumPosts.a_post_u_id==users.u_id).filter(or_(anonForumPosts.a_post_id==postID, anonForumPosts.a_original_post_id==postID)).outerjoin(anonForumPostUpvoted, and_(anonForumPostUpvoted.post_id==anonForumPosts.a_post_id, anonForumPostUpvoted.voter_id==myID)).distinct().order_by(anonForumPosts.a_post_id).limit(DEFAULT_LIMIT)
                '''
                get_posts = db.session.query(anonForumPosts.a_post_id, users.u_id, users.u_name, users.u_handle,users.u_key, anonForumPosts.a_post_cont, anonForumPosts.a_points_count, anonForumPosts.a_reply_count, anonForumPosts.a_date_time, anonForumPosts.a_date_time_edited, anonForumPostUpvoted.points).filter(anonForumPosts.a_post_u_id==users.u_id).filter(anonForumPosts.a_post_id==postID).outerjoin(anonForumPostUpvoted, and_(anonForumPostUpvoted.post_id==anonForumPosts.a_post_id, anonForumPostUpvoted.voter_id==myID)).distinct().limit(DEFAULT_LIMIT)
                get_replies = db.session.query(anonForumPost.a_post_id, users.u_id, users.u_name, users.u_handle, users.u_key, anonForumPosts.a_post_cont, anonForumPosts.a_points_count, anonForumPosts.a_reply_count, anonForumPosts.a_date_time, anonForumPosts.a_date_time_edited, anonForumPostUpvoted.points).filter(anonForumPosts.a_post_u_id==users.u_id).filter(anonForumPosts.a_original_post_id==postID).outerjoin(anonForumPostUpvoted, and_(anonForumPostUpvoted.post_id==anonForumPosts.a_post_id, anonForumPostUpvoted.voter_id==myID)).order_by(anonForumPosts.a_post_id).distinct().limit(DEFAULT_LIMIT)
                '''
            else:
                get_posts = db.session.query(anonForumPosts.a_post_id, users.u_id, users.u_name, users.u_handle,users.u_key, users.firebase_id, anonForumPosts.a_post_cont, anonForumPosts.a_points_count, anonForumPosts.a_reply_count, anonForumPosts.a_date_time, anonForumPosts.a_date_time_edited, anonForumPostUpvoted.points).filter(anonForumPosts.a_post_id < lastPostID).filter(anonForumPosts.a_post_u_id==users.u_id).filter(or_(anonForumPosts.a_post_id==postID, anonForumPosts.a_original_post_id==postID)).outerjoin(anonForumPostUpvoted, and_(anonForumPostUpvoted.post_id==anonForumPosts.a_post_id, anonForumPostUpvoted.voter_id==myID)).distinct().order_by(anonForumPosts.a_post_id).limit(DEFAULT_LIMIT)                
                '''
                get_posts = db.session.query(anonForumPosts.a_post_id, users.u_id, users.u_name, users.u_handle,users.u_key, anonForumPosts.a_post_cont, anonForumPosts.a_points_count, anonForumPosts.a_reply_count, anonForumPosts.a_date_time, anonForumPosts.a_date_time_edited, anonForumPostUpvoted.points).filter(anonForumPosts.a_post_id < lastPostID).filter(anonForumPosts.a_post_u_id==users.u_id).filter(anonForumPosts.a_post_id==postID).outerjoin(anonForumPostUpvoted, and_(anonForumPostUpvoted.post_id==anonForumPosts.a_post_id, anonForumPostUpvoted.voter_id==myID)).distinct().limit(DEFAULT_LIMIT)
            get_replies = db.session.query(anonForumPost.a_post_id, users.u_id, users.u_name, users.u_handle, users.u_key, anonForumPosts.a_post_cont, anonForumPosts.a_points_count, anonForumPosts.a_reply_count, anonForumPosts.a_date_time, anonForumPosts.a_date_time_edited, anonForumPostUpvoted.points).filter(anonForumPosts.a_post_id < lastPostID).filter(anonForumPosts.a_post_u_id==users.u_id).filter(anonForumPosts.a_original_post_id==postID).outerjoin(anonForumPostUpvoted, and_(anonForumPostUpvoted.post_id==anonForumPosts.a_post_id, anonForumPostUpvoted.voter_id==myID)).order_by(anonForumPosts.a_post_id).distinct().limit(DEFAULT_LIMIT) 
                '''
            if get_posts is not None:
                result['status'] = 'success' 
                result['message'] = 'Results Found'
                labels = ['postID','userID','userName','userHandle','key', 'firebaseID', 'postContent','pointsCount','replyCount','timestamp','timestampEdited','didIVote']
                add_all = 'bucket'
                result['anonForumPosts'] = add_labels(labels,get_posts,add_all,PROF_BUCKET, first_initial=True)
                if result['anonForumPosts'] == []:
                    result['message'] = 'No results found'
                    '''
                    if get_replies is not None:
                        if get_replies == []:
                            result['message'] = result['message'] + '. No replies found'
                        else:
                            result['anonForumPosts'] = add_labels(labels,get_replies,add_all,PROF_BUCKET)
                            result['message'] = result['message'] + '. Replies found'
                    '''
        db.session.close()
    except Exception, e:
        result = {'status':'error', 'message':str(e)}
        pass
    data = json.dumps(result)
    return data

@application.route('/sendAnonForumPost', methods=['POST'])
def sendAnonForumPost():
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
            db.session.query(anonForumPosts).filter(anonForumPosts.a_post_id==postID).update({'reply_count':anonForumPosts.a_reply_count + 1})
            db.session.commit()
        result['status'] = 'success'
        result['message'] = 'Posted'
    except Exception, e:
        db.session.rollback()
        result = {'status':'error', 'message':str(e)}
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
        friend_list_last_chat = db.session.query(users.u_id, users.u_name, users.u_handle, users.firebase_id, friends.friend_a, friends.friend_b, friends.requester, friends.friend_status, users.u_key, friends.last_chat, friends.last_chat_timestamp).filter(users.u_id!=userID).filter(or_(users.u_id==friends.friend_a, users.u_id==friends.friend_b)).filter(or_(friends.friend_a==userID,friends.friend_b==userID)).filter(or_(friends.friend_status == 'F',friends.friend_status == 'P')).distinct().order_by(friends.last_chat_timestamp, users.u_name).limit(DEFAULT_LIMIT) #only if chats exist
        friend_list = db.session.query(users.u_id, users.u_name, users.u_handle, users.firebase_id, friends.friend_a, friends.friend_b, friends.requester, friends.friend_status, users.u_key, friends.last_chat, friends.last_chat_timestamp).filter(users.u_id!=userID).filter(or_(users.u_id==friends.friend_a, users.u_id==friends.friend_b)).filter(or_(friends.friend_a==userID,friends.friend_b==userID)).filter(or_(friends.friend_status == 'F',friends.friend_status == 'P')).filter(users.u_name > lastUserName).distinct().order_by(users.u_name).limit(DEFAULT_LIMIT)
        db.session.close()
        result['status']='success'
        if friend_list !=[]:
            result['message']='Friends Found'
            groupsFriends = filter_friends(friend_list,size)
            result['currentFriends']=groupsFriends['currentFriends']
            result['receivedRequests']=groupsFriends['receivedRequests']
            '''
            for a in groupsFriends:
                result[a]=groupsFriends[a]
            '''
    except Exception, e:
        result = {'status':'error', 'message':str(e)}
        pass
    data = json.dumps(result)
    return data

@application.route('/searchFriend', methods=['POST'])
def searchFriend():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('criteria','myID','size','lastUserName')): 
            criteria = request.form['criteria']
            myID = request.form['myID']
            lastUserName = request.form['lastUserName']
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
        search_check = db.session.query(users.u_id,users.u_name, users.u_handle, users.firebase_id, users.u_key, friends.friend_status).filter(or_(users.u_handle.like(search_term), users.u_name.like(search_term))).filter(users.u_id != myID).filter(users.u_name > lastUserName).outerjoin(friends, or_(and_(friends.friend_a==users.u_id, friends.friend_b==myID),and_(friends.friend_b==users.u_id,friends.friend_a==myID))).order_by(users.u_name.asc()).distinct().limit(DEFAULT_LIMIT) #might have issues if a lot of blocked? probably not though
        block_check = db.session.query(friends.friend_a, friends.friend_b).filter(or_(friends.friend_a == myID, friends.friend_b == myID)).filter(friends.friend_status=='B').distinct().all()    
        db.session.close()
        if search_check is not None:
            result['status'] = 'success'      
            if search_check == []:
                result['message'] = 'No results found'
            else:
                labels =['userID','userName','userHandle','firebase_id','key','isFriend']
                add_all = 'bucket'
                if block_check != []:
                    search_list = []
                    for f in search_check:
                        for b in block_check:
                            if not (f.u_id == b.friend_a or f.u_id == b.friend_b):
                                search_list.append(f)
                    result['users']= add_labels(labels,search_list,add_all,PROF_BUCKET,keySize=size)
                    if search_list == None:
                        result['message'] = 'No Results Found'
                else:
                    result['users']= add_labels(labels,search_check,add_all, PROF_BUCKET, True,keySize=size)
                    result['message'] = 'Results Found'              
        else:
            result['status'] = 'error'
            result['message'] = 'Error Retrieving Search Results'
    except Exception, e:
        result = {'status':'error', 'message':str(e)}
        pass    
        # remove error sending
        # check best practices for error handling
    data = json.dumps(result)
    return data

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
        friend_check = db.session.query(friends).filter(or_(friends.requester==requester_ID, friends.requester==friend_ID)).first() #first? or all? case to handle that?
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
                    if action == 'accept': #accept
                        db.session.query(friends).filter(friends.friend_id==f_id).update({'friend_status':'F'})
                        db.session.commit()
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
                    db.session.query(friends).filter(friends.friend_id==f_id).update({'friend_status':'U'})                    
                    db.session.commit()
                    result['status']='success'
                    result['message']='Unblocked'            
            elif action == 'request': #anything else, update as to a new request
                db.session.query(friends).filter(friends.friend_id==f_id).update({'friend_status':'P'})                 
                db.session.commit()
                result['status']='success'
                result['message']='Friend request sent'
                user_check = db.session.query(users.u_handle, users.device_arn).filter(users.u_id==friend_ID).one()
                subj = 'getFriendList'
                cont = '@' + user_check.u_handle + ' has sent you a friend request'
                logNotifification(friend_ID, cont, subj)
                if user_check is not None and user_check != []:
                    if user_check.device_arn != 0:                 
                        push(user_check.device_arn, 1, cont, subj)
            else:
                result['status']='error'
                result['message']='Invalid Request'
        elif action == 'request': #new request
            friend_entered = friends(requester_ID, friend_ID, requester_ID, 'P')
            db.session.add(friend_entered)
            db.session.commit()
            result['status']='success'
            result['message']='Friend request sent'
            user_check = db.session.query(users.u_handle, users.device_arn, users.firebase_id).filter(users.u_id==friend_ID).one()
            subj='getFriendList'
            cont = '@' + user_check.u_handle + ' has sent you a friend request'
            logNotification(friend_ID, cont, subj)
            firebaseNotification(user_check.firebase_id, cont)
            if user_check is not None and user_check != []:
                if user_check.device_arn != 0:
                    push(user_check.device_arn, 1, cont, subj)
        else:
            result['status']='error'
            result['message']='Invalid Request'
    except Exception, e:
        db.session.rollback()
        result = {'status':'error', 'message':str(e)}
        pass
    finally:
        db.session.close()
    data = json.dumps(result)
    return data

@application.route('/getUserProfile', methods=['POST'])
def getUserProfile():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','userID','limitInfo','lastGroupName')):
            userID = request.form['myID']
            otherID = request.form['userID']
            limitInfo = request.form['limitInfo']
            lastGroupName = request.form['lastGroupName']
            if limitInfo is 'no' and all (j in request.form for j in ('userPicSize','groupPicSize')):
                if request.form['groupPicSize'] in ('small','medium','large'):
                    groupPicSize = request.form['groupPicSize']                
                if (request.form['userPicSize'] in ('small','medium','large')):
                    userPicSize = request.form['userPicSize']
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
                result['userName'] = userProf_check.u_name
                result['key'] = userProf_check.u_key+'_'+userPicSize
                result['bucket'] = PROF_BUCKET
                other_groups = db.session.query(groupDetails.group_id, groupDetails.group_handle,groupDetails.group_name, groupDetails.group_key,groupDetails.group_city, groupDetails.group_description).filter(groupMembers.member_id==otherID).filter(groupDetails.group_id==groupMembers.group_id).filter(groupMembers.member_status=='M').filter(groupDetails.group_name > lastGroupName).order_by(groupDetails.group_name.asc()).limit(DEFAULT_LIMIT)
            else:
                result['userName'] = first_and_initial(userProf_check.u_name)
                other_groups = db.session.query(groupDetails.group_id, groupDetails.group_handle,groupDetails.group_name, groupDetails.group_city, groupDetails.group_description).filter(groupMembers.member_id==otherID).filter(groupDetails.group_id==groupMembers.group_id).filter(groupMembers.member_status=='M').filter(groupDetails.group_name > lastGroupName).order_by(groupDetails.group_name.asc()).limit(DEFAULT_LIMIT)
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
                elif is_Friends.friend_status == 'B': #blocked
                    result['isFriend']='B' #if B don't send 
                    result['key'] = 'default'
                    result['name'] = 'default'
            if other_groups is not None and other_groups != []:
                add_all = 'groupBucket'
                if limitInfo == 'no':
                    group_labels = ['groupID','groupHandle','groupName','groupKey','city','groupDescription']
                    result['groups'] = add_labels(group_labels, other_groups, add_all, GROUP_BUCKET, keySize= groupPicSize)
                else:
                    group_labels = ['groupID','groupHandle','groupName','city','groupDescription']
                    result['groups'] = add_labels(group_labels, other_groups)
            else: 
                result['message'] = 'successfully retrieved profile information. No groups found' 
        else:
            result = {'status':'error', 'message':'Profile not found'}
            db.session.close()
    except Exception, e:
        result = {'status':'error', 'message':str(e)}
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
        elif 'userID' not in request.form and 'myID' in request.form:
            myID = request.form['myID']
            otherID = myID
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    result = {'status':'error', 'message':'No Chats Available'}  
    try:
        chat_check = db.session.query(chats.messg_id, chats.send_id, chats.messg_cont, chats.date_time).filter(or_(myID==chats.send_id,myID==chats.recip_id)).filter(or_(otherID==chats.send_id,otherID==chats.recip_id)).filter(chats.messg_id > lastChatID).order_by(chats.date_time.desc()).limit(DEFAULT_LIMIT)
        db.session.close()
        if chat_check is not None:
            if chat_check != []:
                result['status'] = 'success'        
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
        result = {'status':'error', 'message':str(e)}
    data = json.dumps(result)
    return data

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
    data_entered = chats(sendID, recipID, mess)
    try:
        db.session.add(data_entered)
        #push
        db.session.commit()
        db.session.query(friends).filter(or_(friends.friend_a==sendID, friends.friend_b==sendID)).filter(or_(friends.friend_a==recipID,friends.friend_b==recipID)).distinct().one().update({"lastChat":mess,"last_chat_timestamp":datetime.utcnow()})
        result['status'] = 'success'
        result['message'] = 'Chat Sent'
        user_check = db.session.query(users.u_handle, users.device_arn, users.firebase_id).filter(users.u_id==recipID).one()
        subj = 'getFriendList'
        cont =  '@' + user_check.u_handle + ': ' + mess
        logNotification(recipID, cont, subj) 
        firebaseNotification(user_check.firebase_id, cont)       
        if user_check is not None and user_check != []:
            if user_check.device_arn != 0:
                push(user_check.device_arn, 1, cont, subj)
    except:
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
            print userProf_check.u_dob
            print date(1901,1,1)
            if (userProf_check.u_dob == date(1901,1,1)):
                result['myBirthday'] = 'Need to set'
            else:
                result['myBirthday'] = json_serial(datetime.combine(userProf_check.u_dob,time()))
            if (userProf_check.u_phone == 'N/A'):
                result['myPhoneNumber'] = 'Need to set'
            else:
                result['myPhoneNumber'] = userProf_check.phone
    except Exception, e:
        result['status']='error'
        result['message']=str(e)
        pass
    finally:
        db.session.close()
    data = json.dumps(result)
    return data

@application.route('/updateMyProfile', methods=['POST'])
def updateMyProfile():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','action','item')):
            userID = request.form['myID']
            action = request.form['action']
            if action =='edit' and all (l in request.form for l in ('myName','myHandle','myDescription','myBirthday','myPhoneNumber','myEmail','isPicSet')):
                newName = request.form['myName']
                newHandle = request.form['myHandle']
                newDescription = request.form['myDescription']
                newBirthday = request.form['myBirthday']
                newPhoneNumber = request.form['myPhoneNumber']
                newEmail = request.form['myEmail'] #check
                picSet = request.form['isPicSet'] #yes, no, no_change
                if all (m in request.form for m in ('myPassword','newPassword')):
                    myPass = request.form['myPassword']
                    newPass = request.form['newPassword']
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    try:
        user_check = db.sesion.query(users.u_key).filter(users.u_id==userID).one()
        if user_check is not None and user_check !=[]:
        
            if action == 'edit':
                if myPass is not None and newPass is not None:
                    if picSet == 'yes':
                        if user_check.u_key != 'default':
                            k_1, k_2 =user_check.u_key.split('_',1)
                            if '_' in k_2:
                                k_2,k_3=k_2.split('_')
                                k_2 = str(int(k_2)+1)
                                key=k1+'_'+k2+'_'+k3
                            else:
                                key=k1+'_0_'+k2
                        else:
                            key=str(user_id)+'_userProfPic'
                        result['smallKey'] = key + '_small'
                        result['mediumKey'] = key + '_medium'
                        result['largeKey'] = key + '_large'
                    elif picSet == 'no':
                        result['smallKey'] = 'default'
                        result['mediumKey'] = 'default'
                        result['largeKey'] = 'default'
                    result['bucket'] = PROF_BUCKET
                    login_check = db.session.query(users.u_id).filter(u_id==userID).first() 
                    if login_check is not None and login_check != []:
                        if login_check.verify_password(myPass):                         
                            db.session.query(users).filter(users.u_id==userID).update({'u_name':newName,'u_handle':newHandle,'u_description':newDescription,'u_dob':newBirthday,'u_phone':newPhoneNumber,'u_email':newEmail,'u_passwd':hash_password(newPass.encode('utf-8')),'key':result['key']}) 
                        else:
                            return json.dumps(result)
                else:
                    db.session.query(users).filter(users.u_id==userID).update({'u_name':newName,'u_handle':newHandle,'u_description':newDescription,'u_dob':newBirthday,'u_phone':newPhoneNumber,'u_email':newEmail,'key':result['key']}) 
                result['status'] = 'success'
                result['message'] = 'successfully updated profile information'
            else:
                return json.dumps(result)
        else:
            return json.dumps(result)
    except Exception, e:
        db.session.rollback()
        result = {'status':'error', 'message':str(e)}
        pass
    finally:
        db.session.close()
    data = json.dumps(result)
    return data

@application.route('/getMyGroupPost', methods=['POST'])
def getMyGroupPost():
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
        subq = db.session.query(groupPosts.original_post_id).filter(groupPosts.post_u_id == myID).filter(groupPosts.original_post_id != 0).distinct().subquery()
        get_my_posts = db.session.query(groupPosts.group_post_id, users.u_id, users.u_name, users.u_handle,users.u_key, groupPosts.group_post_cont, groupMembers.member_role, groupDetails.group_name, groupPosts.points_count, groupPosts.reply_count, groupPosts.date_time, groupPosts.date_time_edited, groupPostUpvoted.points, groupPosts.original_post_id).filter(groupPosts.post_u_id==users.u_id).filter(groupMembers.member_id == users.u_id).filter(groupMembers.group_id==groupPosts.group_id).filter(groupPosts.post_u_id==myID).filter(groupDetails.group_id==groupPosts.group_id).filter(or_(groupPosts.original_post_id==0, groupPosts.group_post_id.in_(subq))).outerjoin(groupPostUpvoted, and_(groupPostUpvoted.post_id==groupPosts.group_post_id, groupPostUpvoted.voter_id==myID)).distinct().all()
        if get_my_posts is not None:    
            result['status'] = 'success'        
            if get_my_posts == []:
                result['message'] = 'No results found'
            else:
                result['message'] = 'Results Found'
                labels = ['postID','userID','userName','userHandle','key','bucket','postContent','memberRole','groupName', 'pointsCount','replyCount','timestamp','timestampEdited','didIVote','cellType']
                add_all = 'bucket'
                result['groupPosts'] = add_labels(labels,get_my_posts,add_all,PROF_BUCKET,keySize=size)
    except Exception, e:
        result = {'status':'error', 'message':str(e)}
        pass
    data = json.dumps(result)
    return data

@application.route('/getMyGroupList', methods=['POST'])
def getMyGroupList():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','size', 'lastGroupName')):
            user_id = request.form['myID']
            lastGroupName = request.form['lastGroupName']
            if request.form['size'] in ('small','medium','large'):
                size = request.form['size']
            else:
                return json.dumps(result)
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)    
    try:
        group_list = db.session.query(users.u_id, users.u_name, users.u_handle, users.u_key, groupDetails.group_id, groupDetails.group_name, groupDetails.group_handle, groupDetails.group_key, groupMembers.member_role, groupMembers.member_status, groupMembers.last_post_seen, groupMembers.last_host_post_seen, groupMembers.last_event_seen).filter(users.u_id==user_id).filter(groupMembers.member_id==users.u_id).filter(groupMembers.group_id==groupDetails.group_id).filter(groupMembers.member_status != "B").filter(groupDetails.group_name > lastGroupName).order_by(groupDetails.group_name.asc()).distinct().limit(DEFAULT_LIMIT)
        num_host_posts={}
        num_posts = {}
        num_events = {}
        for k in group_list: #number new group Posts, new event,  new host post
            if k.member_status == 'M':
                print k
                new_host_posts = db.session.query(groupPosts.group_post_id).filter(k.group_id == groupPosts.group_id).filter(groupPosts.original_post_id==0).filter(groupPosts.group_post_id > 0 if (k.last_host_post_seen is not None) else k.last_host_post_seen).count()
                new_posts= db.session.query(groupPosts.group_post_id).filter(k.group_id == groupPosts.group_id).filter(groupPosts.original_post_id==-1).filter(groupPosts.group_post_id > 0 if (k.last_post_seen is not None) else k.last_post_seen).count()
                new_events = db.session.query(groupEventDetails.event_id).filter(k.group_id == groupEventDetails.group_id).filter(groupEventDetails.event_id > 0 if (k.last_event_seen is not None) else k.last_event_seen).count()
                num_host_posts[k.group_id]=new_host_posts
                num_posts[k.group_id]=new_posts
                num_events[k.group_id]=new_events
        db.session.close()
        result['status']='success'
        if group_list != []:
            result['message']='Groups Found'
            groupsFriends = filter_groups(group_list, num_host_posts, num_posts, num_events, keySize=size)  
            result['receivedRequests'] = groupsFriends['receivedRequests']
            result['currentGroups'] = groupsFriends['currentGroups']
            '''      
            for a in groupsFriends:
                result[a]=groupsFriends[a]
            '''
        else:
            result['message'] = 'No groups found'
    except Exception, e:
        result = {'status':'error', 'message':str(e)}
        pass
    data = json.dumps(result)
    return data

@application.route('/searchGroup', methods=['POST'])
def searchGroup():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','criteria','longitude','latitude','isExact','groupSize','category','size','lastGroupName')):
            user_id = request.form['myID']
            criteria = request.form['criteria']
            searchLong = float(request.form['longitude'])
            searchLat = float(request.form['latitude'])
            lastGroupName = request.form['lastGroupName']
            groupSize = request.form['groupSize'] #small <15 medium 15-50 large 50+ any
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
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    maxLong, minLong, maxLat, minLat = getMinMaxLongLat(searchLong, searchLat, radius)
    #distance
    criteria = '%'+criteria+'%'
    try: #search by size
        if groupSize in ('large','any'):
            group_search = db.session.query(groupDetails.group_id, groupDetails.group_handle, groupDetails.group_name, groupDetails.group_num_members, groupDetails.group_key, groupDetails.group_city, groupDetails.group_description, groupDetails.group_invite_only, groupMembers.member_role).filter(groupDetails.group_active=='Y').filter(groupDetails.group_long >= minLong).filter(groupDetails.group_long <= maxLong).filter(groupDetails.group_lat >= minLat).filter(groupDetails.group_lat <= maxLat).filter(groupDetails.group_searchable == 'Y').filter(groupDetails.group_num_members >= minSize).filter(groupDetails.group_category ==category).filter(or_(groupDetails.group_handle.like(criteria),groupDetails.group_name.like(criteria),groupDetails.group_description.like(criteria))).outerjoin(groupMembers, groupMembers.group_id==groupDetails.group_id).filter(groupMembers.member_id==user_id).filter(groupDetails.group_name > lastGroupName).order_by(groupDetails.group_name.asc()).distinct().limit(DEFAULT_LIMIT)
        else: #small or medium
            group_search = db.session.query(groupDetails.group_id, groupDetails.group_handle, groupDetails.group_name, groupDetails.group_num_members, groupDetails.group_key, groupDetails.group_city, groupDetails.group_description, groupDetails.group_invite_only, groupMembers.member_role).filter(groupDetails.group_active=='Y').filter(groupDetails.group_long >= minLong).filter(groupDetails.group_long <= maxLong).filter(groupDetails.group_lat >= minLat).filter(groupDetails.group_lat <= maxLat).filter(groupDetails.group_searchable == 'Y').filter(groupDetails.group_num_members >= minSize).filter(groupDetails.group_num_members <= maxSize).filter(groupDetails.group_category == category).filter(or_(groupDetails.group_handle.like(criteria),groupDetails.group_name.like(criteria),groupDetails.group_description.like(criteria))).outerjoin(groupMembers, groupMembers.group_id==groupDetails.group_id).filter(groupMembers.member_id==user_id).filter(groupDetails.group_name > lastGroupName).order_by(groupDetails.group_name).distinct().limit(DEFAULT_LIMIT)
        if group_search is not None and group_search !=[]:        
            blocked_search = db.session.query(groupDetails.group_id).filter(groupMembers.member_id == user_id).filter(groupMembers.group_id==groupDetails.group_id).filter(groupMembers.member_status=='B').all()
            if blocked_search != []:
                group_list = []
                for k in group_search:
                    temp = True
                    for i in blocked_search:
                        if k.group_id == i.group_id:
                            temp = False
                    if (temp): #append upcoming events count
                        k.append(db.session.query(groupEventDetails.event_id).filter(groupEventDetails.group_id == k.group_id).filter(groupEventDetails.event_start > datetime.now()).distinct().count())
                        group_list.append(k)
            else:
                group_list = group_search
        else:
            group_list = []
        db.session.close()
        result['status']='success'
        if group_list != []:
            result['message']='Groups Found'
            label = ['groupID','groupHandle','groupName','membersCount','groupKey','city','groupDescription','inviteOnly','upcomingEventsCount'] 
            result['groups']=add_labels(label, group_list,'groupBucket',GROUP_BUCKET,keySize=size)
            #membersCount
            #UpcomingEventsCount
        else:
            result['message']='No Groups Found'
    except Exception, e:
        result = {'status':'error', 'message':str(e)}
        pass
    data = json.dumps(result)
    return data

@application.route('/createGroup', methods=['POST'])
def createGroup():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','groupName','groupHandle','latitude','longitude','city','groupDescription','isPicSet','searchable','onProfile','readable','inviteOnly','category')):
            userID = request.form['myID']
            groupName = request.form['groupName']
            groupHandle = request.form['groupHandle']
            request = groupLat.form['latitude']
            groupLong = request.form['longitude']
            groupCity = request.form['city']
            groupDescription = request.form['groupDescription']
            picSet = request.form['isPicSet'] 
            tempSearchable = request.form['searchable']
            if tempSearchable is 'yes':
                searchable = True
            else:
                searchable = False
            tempOnProfile = request.form['onProfile']
            if tempOnProfile is 'yes':
                onProfile = True
            else:
                onProfile = False
            tempReadable = request.form['readable']
            if tempReadable is 'yes':
                readable = True
            else:
                readable = False
            inviteOnly = request.form['inviteOnly']
            category = request.form['category']
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    data_entered = groupDetails(group_name=groupName, group_handle=groupHandle, group_description=groupDescription, group_city=groupCity, group_lat=groupLat, group_long=groupLong, group_category=category, group_searchable=searchable, group_readable=readable, group_on_profile=onProfile, group_invite_only=inviteOnly)
    result={'status':'error','message':'Group already registered'}
    try:
        db.session.add(data_entered)
        db.session.flush()
        result['groupID']=data_entered.group_id
        group_check = db.session.query(groupDetails).filter(groupDetails.group_handle==groupHandle).first()
        user_check = db.session.query(users).filter(users.u_id == userID).first()
        if group_check != [] and user_check != []:
            memberData = groupMembers(group_id=group_check.group_id,member_id=user_check.u_id,member_role='O',member_status='M')
            db.session.add(memberData)
            db.session.commit()
        else:
            result['status'] = 'Error'
            result['message'] = 'Group registration error'
            db.session.rollback()
            pass
        try:
            group_check_2 = db.session.query(groupDetails.group_id).filter(groupDetails.group_id == group_check.group_id).first()
            result['smallKey'] = 'default'
            result['mediumKey'] = 'default'
            result['largeKey'] = 'default'
            result['groupBucket']= GROUP_BUCKET
            if picSet == 'yes':
                file_name=str(group_check_2.group_id)+'_groupPic'
                key = file_name
                db.session.query(groupDetails.group_key).filter(groupDetails.group_id==group_check_2.group_id).update({"group_key":result['groupKey']})
                db.session.commit()
                result['smallKey'] = key + '_small'
                result['mediumKey'] = key + '_medium'
                result['largeKey'] = key + '_large'
        except Exception, f:
            result = {'uploadStatus':'error', 'error_message':str(f)}
            pass
        db.session.commit()
        result['status'] = 'success'
        result['message'] = 'Group created!'
    except Exception, e:
        db.session.rollback()
        result = {'status':'error', 'message':str(e)}
        pass
    finally:
        db.session.close()
    data = json.dumps(result)
    return data

@application.route('/getGroupProfile', methods=['POST'])
def getGroupProfile():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','groupID','size')):
            userID = request.form['myID']
            groupID = request.form['groupID']
            if all(x in ([request.form['userPicSize'],request.form['groupPicSize']]) for x in ['small','medium','large']):
                userPicSize = request.form['userPicSize']
                groupPicSize = request.form['groupPicSize']
            else:
                return json.dumps(result)
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)  
    try: #if group is public do something else < invite_only is 'N'
        group_search = db.session.query(groupDetails.group_id, groupDetails.group_handle, groupDetails.group_name, groupDetails.group_key, groupDetails.group_city, groupDetails.group_description, groupDetails.group_readable, groupDetails.group_num_members, groupDetails.group_invite_only, groupDetails.group_searchable, groupDetails.group_readable, groupDetails.group_on_profile,groupMembers.member_role).filter(groupDetails.group_id==groupID).outerjoin(groupMembers, groupMembers.member_id==userID).distinct().all()
        print group_search
        blocked_search = db.session.query(groupDetails.group_id).filter(groupMembers.member_id == userID).filter(groupMembers.group_id==groupDetails.group_id).filter(groupMembers.member_status=='B').all()  
        blocked=False        
        if blocked_search != []:
            for i in blocked_search:
                if i.group_id==group_search.group_id:
                    blocked=True
        if(blocked or group_search is None or group_search == []):
            result['status']='success'
            result['message']='No Groups Found'
        elif group_search != []:
            print group_search
            result['upcomingEventsCount']=db.session.query(groupEventDetails.event_id).filter(groupEventDetails.group_id == groupID).filter(groupEventDetails.event_start > datetime.now()).distinct().count()
            if group_search[0].member_role in ('O','H'):
                result['groupsRequestsCount']=db.session.query(groupMembers.member_id).filter(groupMembers.group_id == groupID).filter(groupMembers.member_status == 'S').distinct().count()
            else:
                result['groupsRequestsCount']=-1
            #if group is public do something else
            result['message']='Group found'
            label = ['groupID', 'groupHandle', 'groupName', 'groupKey', 'city', 'groupDescription', 'readable', 'membersCount', 'inviteOnly', 'searchable', 'readable', 'onProfile', 'memberRole']
            result['groupInfo']=add_labels(label, group_search,'groupBucket',GROUP_BUCKET, keySize=groupPicsize)
            print result['groupInfo']
            #get most recent host post and regular group posts            
            hostPostSearch =  db.session.query(groupPosts.group_post_id, users.u_id, groupMembers.member_role, users.u_name, users.u_handle, users.u_key, groupPosts.date_time, groupPosts.date_time_edited, groupPosts.group_post_cont, groupPosts.reply_count).filter(groupPosts.group_id == groupID).filter(groupPosts.post_u_id == users.u_id).filter(groupMembers.group_id==groupID).filter(groupMembers.member_id==users.u_id).distinct().order_by(groupPosts.group_post_id.desc()).first()
            subq = db.session.query(groupPosts.original_post_id).filter(groupPosts.post_u_id==userID).filter(groupPosts.original_post_id == -1).distinct().subquery()
            postSearch = db.session.query(groupPosts.group_post_id, users.u_id, users.firebase_id, groupMembers.member_role, users.u_name, users.u_handle, users.u_key, groupPosts.date_time, groupPosts.date_time_edited, groupPosts.group_post_cont, groupPosts.reply_count, groupPosts.points_count, groupPostUpvoted.points).filter(groupPosts.post_u_id == users.u_id).filter(groupPosts.post_u_id==groupMembers.member_id).filter(or_(groupPosts.original_post_id==-1, forumPosts.post_id.in_(subq))).outerjoin(groupPostUpvoted, and_(groupPostUpvoted.post_id==groupPosts.group_post_id, groupPostUpvoted.voter_id==userID)).distinct().all()
            if hostPostSearch != [] and postSearch != []:
                hostPostLabel = ['postID','userID','firebaseID','memberRole','userName','userHandle','key','timestamp','timestampEdited','postContent','replyCount']
                result['hostPost']=add_labels(hostPostLabel,hostPostSearch, 'bucket', PROF_BUCKET, keySize=userPicSize) 
                result['message'] = 'Group Found. Posts.'
                postLabel = ['postID','userID','firebaseID','memberRole','userName','userHandle','key','timestamp','timestampEdited','postContent','replyCount','pointsCount','didIVote']
                result['groupPosts'] = add_labels(postLabel, postSearch,'bucket',PROF_BUCKET, keySize=userPicSize)
                result['status']='success'
                groupMemberCheck = db.session.query(groupMembers.last_host_post_seen, groupmembers.last_post_seen).filter(groupMembers.member_id==userID, groupMembers.group_id==groupID).first()
                groupMemberCheck.last_host_post_seen = hostPostSearch.group_post_id
                groupMemberCheck.last_post_seen = postSearch.first().group_post_id
            else:
                result['message'] = 'Group found. No Host Post'
                result['status']='success'
        db.session.commit()       
    except Exception, e:
        db.session.rollback()
        result = {'status':'error', 'message':str(e)}
        pass
    finally:
        db.session.close() 
    data = json.dumps(result)
    return data

@application.route('/sendGroupPost', methods=['POST'])
def sendGroupPost():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','groupID', 'postContent', 'postID')):
            myID = request.form['myID']
            groupID = request.form['groupID']
            originalPostID = request.form['postID'] #checking on client side
            messgCont = request.form['postContent']
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
        if originalPostID not in (0, -1):
            post_check = db.session.query(groupPosts.reply_count).filter(groupPosts.group_post_id==originalPostID).first()
            post_check.reply_count += 1
            user_check = db.session.query(users.u_id, users.u_handle, users.device_arn, groupPosts.group_post_cont, users.firebase_id).filter(users.u_id==groupPosts.post_u_id).filter(groupPosts.group_post_id == originalPostID).one()
            subj = 'getFriendList'
            cont = '@' + user_check.u_handle + ' replied to your post: ' + user_check.group_post_cont
            logNotification (user_check.u_id, cont, subj)
            firebaseNotification(user_check.firebase_id, cont)
            if user_check is not None and user_check != []:
                if user_check.device_arn != 0:
                    push(user_check.device_arn, 1, cont, subj)
        db.session.query(groupPosts)
        db.session.commit()
        result['status'] = 'success'
        result['message'] = 'Posted'
    except:
        result['status'] = 'Error'
        result['message'] = 'Not Posted'
        db.session.rollback()
        pass    
    finally:
        db.session.close()
    data = json.dumps(result)
    return data

@application.route('/getGroupPost', methods=['POST'])
def getGroupPost():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','postID','size','lastPostID')):
            userID = request.form['myID']
            lastPostID = int(request.form['lastPostID'])
            postID = request.form['postID']  #0=hostPost,  else parent postID XXX-1=groupPost,
            groupID = request.form['groupID']
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
        member_check = db.session.query(groupMembers.member_role, groupMembers.member_status).filter(groupMembers.member_id==userID).filter(groupMembers.member_id==users.u_id).filter(groupMembers.group_id == groupID).filter(groupMembers.member_status == 'M').first()
        group_check = db.session.query(groupDetails.group_readable).filter(groupDetails.group_id == groupID).first()
        if group_check.group_readable or member_check.member_status == 'M':
            result['myMemberRole']=member_check.member_role
            if postID == 0:
                if lastPostID ==0:
                    host_post_check = db.session.query(groupPosts.group_post_id, users.u_id, users.firebase_id, users.u_key, users.u_name, users.u_handle, groupPosts.group_post_cont, groupPosts.date_time, groupPosts.date_time_edited, groupMembers.member_role, groupPosts.reply_count).filter(groupPosts.group_id==groupID).filter(groupPosts.original_post_id==0).filter(groupPosts.post_u_id==users.u_id).filter(groupPosts.group_id==group_check.group_id).filter(groupMembers.member_id==users.u_id).distinct().limit(DEFAULT_LIMIT)
                else:                
                    host_post_check = db.session.query(groupPosts.group_post_id, users.u_id, users.firebase_id, users.u_key, users.u_name, users.u_handle, groupPosts.group_post_cont, groupPosts.date_time, groupPosts.date_time_edited, groupMembers.member_role, groupPosts.reply_count).filter(groupPosts.group_post_id < lastPostID).filter(groupPosts.group_id==groupID).filter(groupPosts.original_post_id==0).filter(groupPosts.post_u_id==users.u_id).filter(groupPosts.group_id==group_check.group_id).filter(groupMembers.member_id==users.u_id).distinct().limit(DEFAULT_LIMIT)
                hostPostLabels = ['postID','userID','firebaseID','key','userName','userHandle','postContent','timestamp','timestampEdited','memberRole','replyCount']
                result['hostPosts'] = add_labels(hostPostLabels, host_post_check, 'bucket', PROF_BUCKET,keySize=size)
                result['status'] = 'success'
                result['message'] = 'Posts Found'
            else:
                if lastPostID==0:
                    post_check = db.session.query(groupPosts.group_post_id, users.u_id, users.firebase_id, users.u_key, users.u_name, users.u_handle, groupPosts.group_post_cont, groupPosts.date_time, groupPosts.date_time_edited, groupMembers.member_role, groupPosts.points_count, groupPosts.reply_count, groupPostUpvoted.points, groupPosts.original_post_id).filter(groupPosts.post_u_id==users.u_id).filter(groupPosts.group_post_id == postID, groupPosts.original_post_id==postID).filter(groupPosts.post_u_id==groupMembers.member_id).filter(groupPosts.group_id==groupMembers.group_id).filter(groupPosts.post_u_id==groupPostUpvoted.voter_id).filter(groupPostUpvoted.post_id==groupPosts.group_post_id).distinct().order_by(groupPosts.group_post_id.desc()).limit(DEFAULT_LIMIT)
                else:
                    post_check = db.session.query(groupPosts.group_post_id, users.u_id, users.firebase_id, users.u_key, users.u_name, users.u_handle, groupPosts.group_post_cont, groupPosts.date_time, groupPosts.date_time_edited, groupMembers.member_role, groupPosts.points_count, groupPosts.reply_count, groupPostUpvoted.points, groupPosts.original_post_id).filter(groupPosts.post_u_id==users.u_id).filter(groupPosts.group_post_id == postID, groupPosts.original_post_id==postID).filter(groupPosts.group_post_id < lastPostID).filter(groupPosts.post_u_id==groupMembers.member_id).filter(groupPosts.group_id==groupMembers.group_id).filter(groupPosts.post_u_id==groupPostUpvoted.voter_id).filter(groupPostUpvoted.post_id==groupPosts.group_post_id).distinct().order_by(groupPosts.group_post_id.desc()).limit(DEFAULT_LIMIT)
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
                labels = ['postID','userID','firebaseID','key','userName','userHandle','postContent','timestamp','timestampedited','memberRole','pointsCount','replyCount','didIVote','cellType']
                result['status'] = 'success'        
                if post_check is not none and post_check !=[]:
                    result['message'] = 'No Replies Found'
                    result['groupPosts'] = add_labels(labels, initial_post_check, 'bucket', PROF_BUCKET, keySize=size) #cellType = HostPost or GroupPost
                else:
                    result['status'] = 'error'
                    result['message'] = 'Error Retrieving Posts'
        db.session.close()
    except Exception, e:
        result = {'status':'error', 'message':str(e)}
    data = json.dumps(result)
    return data

@application.route('/updateGroup', methods=['POST'])
def updateGroup():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','groupID','action','item')):
            userID = request.form['myID']
            groupID = request.form['groupID']
            action = request.form['action'] #edit delete
            if action == 'edit':
                if all (l in request.form for l in ('groupName','groupHandle','latitude','longitude','city','groupDescription','isPicSet','searchable','onProfile','readable','inviteOnly','category')):
                    groupName = request.form['groupName']
                    groupHandle = request.form['groupHandle']
                    groupLong = request.form['latitude']
                    groupLat = request.form['longitude']
                    groupCity = request.form['city']
                    groupDescription = request.form['groupDescription']
                    picSet = request.form['isPicSet'] #yes, no, no_change
                    groupSearchable = request.form['searchable']
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
                    groupInviteOnly = request.form['inviteOnly']
                    groupCategory = request.form['category']
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    try:
        group_member_check = db.session.query(groupMembers.member_role, groupDetails.group_key).filter(groupMembers.group_id==groupDetails.group_id).filter(groupMembers.group_id == groupID).filter(groupMembers.member_id == userID).first()
        if group_member_check != [] and group_member_check.member_role in ('O','A'):
            if action == 'delete' and group_member_check.member_role == 'O':
                group_member_check.group_active = 'N'
            elif action == 'edit':
                if picSet == 'yes': #_iteration ???
                    if group_member_check.group_key != 'default':
                        k_1, k_2 =group_member_check.group_key.split('_',1)
                        if '_' in k_2:
                            k_2,k_3=k_2.split('_')
                            k_2 = str(int(k_2)+1)
                            key=k1+'_'+k2+'_'+k3
                        else:
                            key=k1+'_0_'+k2
                    else:
                        key=str(groupid)+'_userProfPic'
                    result['smallKey'] = key + '_small'
                    result['mediumKey'] = key + '_medium'
                    result['largeKey'] = key + '_large'
                elif picSet=='no': #picSet == 'no'
                    result['smallKey'] = 'default'
                    result['mediumKey'] = 'default'
                    result['largeKey'] = 'default'
                db.session.query(groupDetails).filter_by(groupDetails.group_id==groupID).update({'groupName':groupName,'group_handle':groupHandle,'group_long':groupLong, 'group_lat':groupLat, 'group_city':groupCity,'group_description':groupDescription,'group_category':groupCategory,'group_searchable':groupSearchable,'group_readable':groupReadable,'group_on_profile':groupOnProfile, 'group_invite_only':groupInviteOnly,'group_key':result['key']})
                result['status'] = 'success'   
                result['message'] = 'Successfully updated group'
            else:
                result = {'status':'error', 'message':'Invalid Action'}
        else:
            result = {'status':'error', 'message':'Unauthorized'}
    except Exception, e:
        db.session.rollback()
        result = {'status':'error', 'message':str(e)}
        pass
    finally:
        db.session.close()
    data = json.dumps(result)
    return data

#add members to group
#add members to event (invite only?), edit event, disable?

@application.route('/createEvent', methods=['POST']) #key and handle??
def createEvent():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','groupID','eventName','eventDescription','timestampEventStart')):
            userID = request.forms['myID']
            groupID = request.forms['groupID']
            eventName = request.forms['eventName']
            eventDescription = request.forms['eventDescription']
            eventStart = request.forms['timestampEventStart']
            if 'timestampEventEnd' in request.form:
                eventEnd = request.forms['timestampEventEnd']
            else:
                eventEnd = eventStart
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    data_entered = groupEventDetails(group_id=groupID, event_name=eventName, event_description=eventDescription, event_start=eventStart, event_end=eventEnd)
    result={'status':'error','message':'Group already registered'}
    try:
        member_check = db.session.query(groupMembers.member_role).filter(groupMembers.member_id==userID).filter(groupMembers.group_id==groupID).filter(groupMembers.member_status=='M')
        if member_check != [] and member_check.member_role in ('O','H'):
            db.session.add(data_entered)
            db.session.flush()
            result['eventID']=data_entered.event_id
            event_check = db.session.query(groupEventDetails).filter(groupEventDetails.group_id==groupID).filter(groupEventDetails.event_name == eventName).filter(groupEventDetails.event_start == eventStart).filter(groupEventDetails.event_end == eventEnd).first()
            user_check = db.session.query(users).filter(users.u_id == userID).first()
            if event_check != [] and user_check != []:
                eventUserData = groupEventUsers(event_check.event_id, userID, 'O')
                try:
                    db.session.add(eventUserData)
                    db.session.commit()       
                    result['status'] = 'success'
                    result['message'] = 'Event registration Complete'
                except:
                    result['status'] = 'Error'
                    result['message'] = 'Event registration error'
                    db.session.rollback()
        else:
            result={'status':'error','message':'Unauthorized'}
    except Exception, e:
        db.session.rollback()
        result = {'status':'error', 'message':str(e) + ' Please check to make sure the event does not already exist'}
        pass    
    finally:
        db.session.close()
    data = json.dumps(result)
    return data

@application.route('/updateEvent', methods=['POST'])
def updateEvent():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','eventID','groupID','eventName','eventDescription','timestampEventStart')):
            userID = request.forms['myID']
            eventID = request.forms['eventID']
            groupID = request.forms['groupID']
            eventName = request.forms['eventName']
            eventDescription = request.forms['eventDescription']
            eventStart = request.forms['timestampEventStart']
            if 'timestampEventEnd' in request.form:
                eventEnd = request.forms['timestampEventEnd']
            else:
                eventEnd = eventStart
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    try:
        member_check = db.session.query(groupMembers.member_role).filter(groupMembers.member_id==userID).filter(groupMembers.group_id==groupID).filter(groupMembers.member_status=='M')
        if member_check != [] and member_check.member_role in ('O','H'):
            db.session.query(groupEventDetails).filter(groupEventDetails.event_id==eventID).update({'event_name':eventName,'event_description':eventDescription,'event_start':eventStart, 'event_end':eventEnd})
            db.session.commit()
            result['status'] = 'success'
            result['message'] = 'Event updated'
        else:
            result['status'] = 'error'
            result['message'] = 'Event not updated'
    except Exception, e:
        db.session.rollback()
        result = {'status':'error', 'message':str(e)}
        pass    
    finally:
        db.session.close()
    data = json.dumps(result)
    return data

@application.route('/eventProfile', methods=['POST'])
def eventProfile():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','groupID','eventID','size','lastPostID')):
            userID = request.form['myID']
            groupID = request.form['groupID']
            eventID = request.form['eventID']
            lastPostID = request.form['lastPostID']
            if request.form['size'] in ('small','medium','large'):
                size = request.form['size']
            else:
                return json.dumps(result)
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    try:
        user_check = db.session.query(groupMembers).filter(groupMembers.group_id == groupID).filter(groupMembers.member_id == userID).first()
        if user_check != [] and user_check.member_role == 'M' and user_check.member_status != 'B': #allow others to see?
            event_search = db.session.query(groupEventDetails.event_name, groupEventDetails.event_description, groupEventDetails.event_start, groupEventDetails.event_end, groupEventDetails.attending_count, groupEventDetails.event_post_count, groupEventUsers.event_role).filter(groupEventDetails.event_id==eventID).outerjoin(groupEventUsers).first()
            result['status']='success'
            if event_search != []:
                label = ['eventName','eventDescription','timestampEventStart','timestampEventEnd','attendingCount','eventPostCount','amIAttending'] 
                result['eventInfo']=add_labels(label, event_search)
                if lastPostID == 0:
                    event_post_search = db.session.query(groupEventPosts.group_event_post_id, groupEventPosts.cell_type, groupEventPosts.image_key, groupEventPosts.group_event_post_cont, groupEventPosts.date_time, groupEventPosts.date_time_edited, users.u_id, users.u_key, users.u_name, users.u_handle, groupMembers.member_role, groupEventPosts.points_count, eventPostUpvoted.points).filter(groupEventPosts.group_event_post_u_id == userID).filter(groupEventPosts.event_id==eventID).filter(groupEventPosts.group_id == groupMembers.group_id).filter(groupMembers.member_id == users.u_id).filter(groupEventPosts.group_post_user_id==users.u_id).filter(eventPostUpvoted.voter_id ==users.u_id).filter(eventPostUpvoted.post_id == groupEventPosts.group_event_post_id).distinct().order_by(groupEventPosts.group_event_post_id.desc()).limit(DEFAULT_LIMIT)    
                else:
                    event_post_search = db.session.query(groupEventPosts.group_event_post_id, groupEventPosts.cell_type, groupEventPosts.image_key, groupEventPosts.group_event_post_cont, groupEventPosts.date_time, groupEventPosts.date_time_edited, users.u_id, users.u_key, users.u_name, users.u_handle, groupMembers.member_role, groupEventPosts.points_count, eventPostUpvoted.points).filter(groupEventPosts.group_event_post_u_id == userID).filter(groupEventPosts.group_event_post_id < lastPostID).filter(groupEventPosts.event_id==eventID).filter(groupEventPosts.group_id == groupMembers.group_id).filter(groupMembers.member_id == users.u_id).filter(groupEventPosts.group_post_user_id==users.u_id).filter(eventPostUpvoted.voter_id ==users.u_id).filter(eventPostUpvoted.post_id == groupEventPosts.group_event_post_id).distinct().order_by(groupEventPosts.group_event_post_id.desc()).limit(DEFAULT_LIMIT)
                if event_post_search != []:
                    eventLabel = ['postID','eventCellType','imageKey','postContent','timestamp','timestampEdited','userID','key','userName','userHandle','memberRole','pointsCount','didIVote']
                    result['eventPosts'] = add_labels(eventLabel, event_post_search, 'bucket', PROF_BUCKET, None, 'imageBucket', EVENT_BUCKET, keySize=size) 
                    result['message'] = 'Event found. Event posts found'
                else:
                    result['message'] = 'Event found. Event posts not found'
                    result['eventPosts'] = []
            else:
                result['message'] = 'Event Not Found.'
        else:
            result['message'] = 'Unauthorized'
            result['status'] = 'error'
        db.session.commit()
    except Exception, e:
        db.session.rollback()
        result = {'status':'error', 'message':str(e)}
        pass
    finally:
        db.session.close()
    data = json.dumps(result)
    return data

@application.route('/getEventList', methods=['POST']) #if group is readable, events show up even to non-members bad Idea?
def getEventList():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','groupID', 'size','lastEventID')):
            userID = request.form['myID']
            groupID = request.form['groupID']
            lastEventID = request.form['lastEventID']
            if request.form['size'] in ('small','medium','large'):
                size = request.form['size']
            else:
                return json.dumps(result)
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)    
    try:
        event_check = db.session.query(groupEventDetails.event_id, groupEventDetails.event_name, groupEventDetails.event_description, groupEventDetails.event_start, groupEventDetails.event_end, groupEventUsers.event_role, groupEventDetails.attending_count, groupEventDetails.event_post_count).filter(groupEventDetails.group_id==groupID).outerjoin(groupEventUsers, groupMembers.member_id==groupEventUsers.attendee_id, groupEventDetails.event_id == groupEventUsers.event_id).filter(groupEventUsers.attendee_id==userID).filter(groupEventDetails.event_id > lastEventID).order_by(groupEventDetails.event_id.asc()).distinct().limit(DEFAULT_LIMIT)
        if event_check is not None:
            if event_check != []:
                member_check = db.session.query(groupMembers.member_role,groupMembers.last_event_seen, groupMembers.member_id==userID, groupMembers.group_id==groupID, groupMembers.member_status=='M').first()
                member_check.last_event_seen = event_check.first().event_id
                request['myMemberRole']=member_check.member_role
                label = ['eventID','eventName','eventDescription','timestampEventStart','timestampEventEnd','amIAttending','attendingCount','eventPostCount']
                request['events']= add_labels(label, event_check, keySize=size)
                request['status'] = 'success'
                request['message'] = 'Events Found'
            else:
                request['status'] = 'success'
                request['message'] = 'No events Found'
        db.session.commit()      
    except Exception, e:
        db.session.rollback()
        result = {'status':'error', 'message':str(e)}
        pass
    finally:
        db.session.close()
    data = json.dumps(result)
    return data

@application.route('/sendEventPost', methods=['POST'])
def sendEventPost():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','groupID', 'postContent', 'eventCellType','postID')):
            userID = request.form['myID']
            groupID = request.form['groupID']
            eventID = request.form['eventID']
            cellType = request.form['eventCellType']
            messgCont = request.form['postContent']
        else:
            return json.dumps(result)
    else:    
        return json.dumps(result)
    data_entered = groupEventPosts(event_id=eventID, group_id=groupID, group_post_u_id=userID, group_event_post_cont=messgCont, cell_type=cellType)
    try:
        member_check = db.session.query(groupMembers.member_status, groupEventUsers.event_role).filter(groupMembers.member_id==userID).filter(groupMembers.group_id==groupID).filter(groupEventUsers.event_id == eventID).filter(groupEventUsers.attendee_id==groupMembers.member_id).filter(groupMembers.member_status == 'M').first()
        if member_check is not None and member_check != []:
            db.session.add(data_entered)
            db.session.flush()
            result['postID']=data_entered.group_event_post_id
            db.session.query(groupEventDetails).filter(groupEventDetails.event_id==eventID).update({'event_post_count':groupEventDetails.event_post_count + 1})
            db.session.commit()
            result['status'] = 'success'
            result['message'] = 'Posted'
            if cellType == 'image':
                try:
                    event_post_check = db.session.query(groupEventPosts).filter(groupEventPosts.event_id==eventID).filter(groupEventPosts.group_id==groupID).filter(groupEventPosts.group_event_post_u_id==userID).filter(groupEventPosts.cell_type=='image').distinct().order_by(groupEventPosts.group_event_post_id.desc()).first()
                    if event_post_check is not None and event_post_check != []:
                        file_name=str(userID)+'_eventPostPic'
                        event_post_check.image_key = file_name
                        db.session.commit()
                        result['smallImageKey'] = file_name+'_small'
                        result['mediumImageKey'] = file_name+'_medium'
                        result['largeImageKey'] = file_name+'_large'
                        result['imageBucket'] = EVENT_BUCKET
                    else:
                        result['uploadStatus'] = 'error'
                        result['message'] = 'image not saved'
                except Exception, e:
                    result['uploadStatus'] = str(e)
                    pass    
    except:
        result['status'] = 'Error'
        result['message'] = 'Not Posted'
        db.session.rollback()
        pass    
    finally:
        db.session.close()
    data = json.dumps(result)
    return data

@application.route('/groupMemberSearch', methods=['POST'])
def groupMemberSearch():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','groupID','size','lastUserName','criteria')):
            userID = request.form['myID']
            groupID = request.form['groupID']
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
        member_check = db.session.query(groupMembers.member_status, groupMembers.member_role, groupDetails.group_invite_only, groupDetails.group_searchable, groupDetails.group_readable, groupDetails.group_on_profile).filter(groupMembers.member_id==userID).filter(groupDetails.group_id==groupMembers.group_id).filter(groupMembers.group_id==groupID).filter(groupMembers.member_status == 'M').first()
        if member_check is not None and member_check != []:
            search_term='%'+criteria+'%'
            member_search = db.session.query(users.u_id,users.u_name, users.u_handle, users.firebase_id, users.u_key, groupMembers.member_role).filter(or_(users.u_handle.like(search_term), users.u_name.like(search_term))).filter(users.u_id != myID).filter(users.u_id==groupMembers.member_id).filter(groupMembers.group_id==groupID).filter(groupMembers.member_status=='M').filter(users.u_name > lastUserName).order_by(users.u_name.asc()).distinct().limit(DEFAULT_LIMIT)
            labels = ['userID','userName','userHandle','firebaseID','key','memberRole']
            result['members'] = add_labels(labels, member_search, 'groupBucket',GROUP_BUCKET, keySize=size)
            result['status'] = 'success'
            result['message'] = 'Group members found'
        else:
            result['status'] = 'success'
            result['message'] = 'No group members found'
        db.session.close()        
    except Exception, e:
        result = {'status':'error', 'message':str(e)}
        pass
    data = json.dumps(result)
    return data



@application.route('/getGroupMemberList', methods=['POST']) 
def getGroupMemberList():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','groupID','size','lastUserName','showOnlyRequestList')):
            userID = request.form['myID']
            groupID = request.form['groupID']
            lastUserNane = request.form['lastUserName']
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
        member_check = db.session.query(groupMembers.member_status, groupMembers.member_role, groupDetails.group_invite_only).filter(groupMembers.member_id==userID).filter(groupDetails.group_id==groupMembers.group_id).filter(groupMembers.group_id==groupID).filter(groupMembers.member_status == 'M').first()
        if member_check is not None and member_check != []:
            result['myMemberRole'] = member_check.member_role
            member_search = db.session.query(groupMembers.member_role, users.u_id, users.firebase_id, users.u_name, users.u_handle, users.u_key, groupMembers.member_message).filter(groupMembers.member_id == users.u_id).filter(groupMembers.group_id == groupID).filter(groupMembers.member_status in ('M','B','S','I')).filter(users.u_name > lastUserName).order_by(users.u_name.asc()).all()
            members=filter_members(member_search, keySize=size)
            if (member_check.memberRole in ('O','H') or member_check.group_invite_only =='N' or (member_check.group_invite_only == 'M' and member_check.member_role == 'M')) and showRequested=='yes':
                #result['receivedRequests']=members['receivedRequests'] #group sent to user
                result['sentRequests']=members['sentRequests'] # user sent to group
                result['blocked']=members['blocked']
            elif showRequested == 'no':
                result['owner'] = {key:members[key] for i, key in members.iteritems() if members[key]['memberRole']=='O'}
                result['hosts'] = {key:members[key] for i, key in members.iteritems() if members[key]['memberRole']=='H'}
                result['members']= {key:members[key] for i, key in members.iteritems() if members[key]['memberRole']=='M'}                
            result['status'] = 'success'
            result['message'] = 'Group members found'
            members_count = db.session.query(groupMembers.member_status).filter(groupMembers.group_id==groupID, groupMembers.member_status =='M').count()
            group_check = db.session.query(groupDetails.group_num_members).filter(groupDetails.group_id == groupID).first()
            group_check.group_num_members = members_count
            db.session.commit()
        else:
            result['status'] = 'success'
            result['message'] = 'No group members found'
        db.session.close()        
    except Exception, e:
        result = {'status':'error', 'message':str(e)}
        pass
    data = json.dumps(result)
    return data

@application.route('/editGroupMemberList', methods=['POST']) 
def editGroupMemberList(): #must be member from member perspective
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','groupID','userID','action')):
            myID = request.form['myID']
            groupID = request.form['groupID']
            userID = request.form['userID']
            action = request.form['action']
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)    
    try:
        member_admin_check = db.session.query(groupDetails.invite_only, groupMembers.member_status, groupMembers.member_role).filter(groupMembers.member_id==userID).filter(groupMembers.group_id==groupID).filter(groupMembers.member_status == 'M').filter(groupDetails.group_id == groupID).first()
        if member_admin_check.member_role in ('H','O') or member_admin_check.invite_only =='M':
            other_group_check = db.session.query(groupMembers.member_status, groupMembers.member_role, groupEventUsers.event_role).filter(groupMembers.member_id==userID, groupMembers.group_id==groupID).filter(groupEventUsers.attendee_id==groupMembers.member_id).first()
            if other_group_check is not None and other_group_check != []:
                if other_group_check.member_status in ('S','I'):
                    result['status'] = 'success'
                    result['message'] = 'Action complete' 
                    if action == 'denyRequest': #withdraw or refuse
                        other_group_check.member_status = 'N'
                    elif action == 'acceptRequest':
                        other_group_check.member_status = 'M'
                        other_group_check.approved_by = myID
                        group_members = db.session.query(groupDetails.group_num_members).filter(groupDetails.group_id==groupID).first()
                        group_members.group_num_mumebers += 1
                elif other_group_check.member_status == 'M': 
                    result['status'] = 'success'
                    result['message'] = 'Action complete'           
                    if action == 'makeHost' and other_group_check.member_role == 'M':
                        other_group_check.member_role = 'H'
                        other_group_check.approved_by = myID
                    elif action == 'removeHost' and other_group_check.member_role == 'H':
                        other_group_check.member_role = 'M'
                    elif action == 'removeMember':
                        other_group_check.member_status = 'N'
                        other_group_check.approved_by = myID
                        group_members = db.session.query(groupDetails.group_num_members).filter(groupDetails.group_id==groupID).first()
                        group_members.group_num_mumebers -= 1
                    elif action == 'makeOwner' and member_admin_check.member_role == 'O':
                        member_admin_check.member_role = 'H'
                        other_group_check.member_role = 'O'
                        other_group_check.approved_by = myID
                    elif action == 'blockUser':
                        other_group_check.member_status = 'B'
                        other_group_check.approved_by = myID
                    else:
                        result = {'status':'error', 'message':'Invalid request'}
            elif action == 'blockUser':
                result['status'] = 'success'
                result['message'] = 'Action complete' 
                block_data = groupMembers(groupID, userID, 'M', 'B')
                db.session.add(block_data)
            elif action == 'unblockUser':
                block_check = db.session.query(groupMembers).filter(groupMembers.group_id==groupID).filter(groupMembers.member_id==userID).first()
                if block_check is not None and block_check != []:
                    block_check.member_status='M'
                    result['status'] = 'success'
                    result['message'] = 'Action complete' 
            elif action == 'invite':
                result['status'] = 'success'
                result['message'] = 'Action complete' 
                member_data = groupMembers(groupID, userID, 'M', 'I')
                db.session.add(member_data)
                user_check = db.session.query(users.device_arn, users.firebase_id).filter(users.u_id==userID).one()
                group_check = db.sesion.query(groupDetails.group_handle).filter(groupDetails.group_id==groupID).one()
                subj = 'getGroupList'
                cont = '.'+group_check.group_handle + ' has sent you a group request.'
                logNotification(userID, cont, subj)
                firebaseNotification(user_check.firebase_id, cont)
                if user_check is not None and user_check != [] and group_check is not None and group_check != []:
                    if user_check.device_arn !=0:
                        push(g.device_arn, 1, cont, subj)    
            elif action == 'leaveGroup' and member_admin_check.member_role != 'O' and userID==myID:
                result['status'] = 'success'
                result['message'] = 'Action complete' 
                member_admin_check.member_status = 'N'
            else:
                result = {'status':'error', 'message':'Invalid request'}
            db.session.commit()
        elif member_admin_check.member_status == 'M' and action == 'leaveGroup' and userID==myID and member_admin_check != 'O':
            result['status'] = 'success'
            result['message'] = 'Action complete' 
            member_admin_check.member_status = 'N'
        else:
            result = {'status':'error', 'message':'Unauthorized'}
    except:
        result['status'] = 'Error'
        result['message'] = 'Changes not made'
        db.session.rollback()
        pass    
    finally:
        db.session.close()
    data = json.dumps(result)
    return data

@application.route('/interactGroupRequest', methods=['POST'])
def interactGroupRequest():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','groupID','action')):
            requesterID = request.form['myID']
            groupID = request.form['groupID']
            action = request.form['action'] # request, accept, deny, withdraw
            if action == 'request' and 'userMessage' in request.form:
                userMessage = request.form['userMessage']
            else:
                userMessage = 'N/A'
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    try:
        group_check=db.session.query(groupDetails.invite_only).filter(groupDetails.group_id == groupID).first()
        if group_check is not None and group_check !=[]: #actions
            if action == 'request':
                if group_check.invite_only == 'N':
                    member_data = groupMembers(group_id=groupID, requester_id=requesterID, member_role='M', member_status='M') 
                else:
                    member_data = groupMembers(group_id=groupID, requester_id=requesterID, member_role='M', member_status='S', member_message=userMessage)
                    db.session.add(member_data) 
                    user_check = db.session.query(users.u_handle, users.device_arn, users.firebase_id).filter(users.u_id==requesterID).one()
                    group_host_check = db.sesion.query(users.u_id, users.device_arn, groupDetails.group_handle).filter(groupMembers.group_id==groupID).filter(groupDetails.group_id == groupID).filter(or_(groupMembers.member_role=='O', groupMembers.member_role=='H')).filter(groupMembers.member_id==users.u_id).distinct().all()
                    if ((user_check is not None) and (user_check != []) and (group_host_check is not None) and (group_host_check != [])):
                        for g in group_host_check:
                            subj = 'getGroupProfile'
                            cont = '@'+user_check.u_handle + ' has sent .'+g.group_handle + ' a request'
                            logNotification(g.u_id, cont, subj)
                            firebaseNotification(user_check.firebase_id, cont)
                            if g.device_arn !=0:
                                push(g.device_arn, 1, cont, subj)
            elif action in ('accept','deny','withdraw'):
                request_check = db.session.query(groupMembers.member_status).filter(groupMembers.member_id==requesterID).filter(groupMembers.group_id==groupID).first()
                if request_check.member_status== 'I': #invited to group (group > user)
                    if action == 'accept':
                        request_check.member_status = 'M'
                        result['status'] = 'success'
                        result['message'] = 'Request accepted'
                    elif action =='deny':
                        request_check.member_status = 'N'
                        result['status'] = 'success'
                        result['message'] = 'Request denied'
                    else:
                        return json.dumps(result)
                elif request_check.member_status == 'S':
                    if action == 'withdraw':
                        request_check.member_status = 'N'
                        result['status'] = 'success'
                        result['message'] = 'Request withdrawn'
                    else:
                        return json.dumps(result)  
            else:
                return json.dumps(result)
            db.session.commit()
    except Exception, e:
        db.session.rollback()
        result = {'status':'error', 'message':str(e)}
        pass
    finally:
        db.session.close()
    data = json.dumps(result)
    return data

@application.route('/myInvitableGroupList', methods=['POST'])
def myInvitableGroupList():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','size','lastGroupName')):
            user_id = request.form['myID']
            lastGroupName = request.form['lastGroupName']
            if request.form['size'] in ('small','medium','large'):
                size = request.form['size']
            else:
                return json.dumps(result)
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    try:
        group_list = db.session.query(users.u_id, users.u_name, users.u_handle, users.u_key, groupDetails.group_id, groupDetails.group_name, groupDetails.group_handle, groupDetails.group_key, groupMembers.member_role, groupMembers.member_status, groupMembers.last_post_seen).filter(groupDetails.group_active == 'Y').filter(groupMembers.member_id==users.u_id).filter(groupMembers.group_id==groupDetails.group_id).filter(groupMembers.member_status == 'M').filter(or_(or_(groupDetails.group_invite_only == 'M', groupDetails.group_invite_only =='N'), or_(groupMembers.member_role == 'H', groupMembers.member_role == 'O'))).filter(groupDetails.group_name > lastGroupName).order_by(groupDetails.group_name.asc()).distinct().limit(DEFAULT_LIMIT)
        db.session.close()
        result['status']='success'
        if group_list != []:
            result['message']='Groups Found'
            groups = filter_groups(group_list, keySize=size)        
            result['groups'] = groups['currentGroups']
        else:
            result['message'] = 'No groups found'
    except Exception, e:
        result = {'status':'error', 'message':str(e)}
        pass
    data = json.dumps(result)
    return data

@application.route('/interactEvent', methods=['POST'])
def interactEvent():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','eventID','groupID','action','size')):
            userID = request.form['myID']
            groupID = request.form['groupID']
            eventID = request.form['eventID']
            action = request.form['action'] #joinEvent, leaveEvent, getUsers
            if action == 'getUsers':
                if 'lastUserName' in request.form:
                    lastUserName=request.form['lastUserName']
                else:
                    return json.dumps(result)
            else:
                lastUserName='0'
            if request.form['size'] in ('small','medium','large'):
                size = request.form['size']
            else:
                return json.dumps(result)    
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    try:
        member_check = db.session.query(groupMembers.member_status, groupMembers.member_role).filter(groupMembers.member_id==userID).filter(groupMembers.group_id==groupID).filter(groupMembers.member_status == 'M').first()
        if member_check is not None and member_check != []:
            if action == 'joinEvent':            
                event_check = db.session.query(groupEventUsers.attendee_id, groupEventUsers.event_role).filter(groupEventUsers.event_id == eventID).filter(groupEventUsers.attendee_id == userID).first()
                if event_check is not None and member_check != []:
                    event_check.event_role = 'M'
                else:
                    event_member_data = groupEventUsers(event_id=eventID, attendee_id=userID, event_role='M')
                    db.session.add(event_member_data)
                event_attendee = db.session.query(groupEventDetails.attending_count).filter(groupEventDetails.event_id==eventID).first()
                event_attendee.attending_count += 1
            elif action == 'leaveEvent':
                event_check = db.session.query(groupEventUsers.attendee_id, groupEventUsers.event_role).filter(groupEventUsers.event_id == eventID).filter(groupEventUsers.attendee_id == userID).first()
                event_check.event_role = 'N'
                event_attendee = db.session.query(groupEventDetails.attending_count).filter(groupEventDetails.event_id==eventID).first()
                event_attendee.attending_count -= 1
            elif action =='getUsers':
                event_member_search = db.session.query(users.u_name, users.u_handle, users.u_key).filter(groupEventUsers.event_id==eventID).filter(groupEventUsers.attendee_id==users.u_id).filter(groupMembers.member_id==users.u_id).filter(groupMembers.member_id==userID).filter(groupMembers.member_status=='M').filter(users.u_name > lastUserName).order_by(users.u_name.asc()).limit(DEFAULT_LIMIT)
                label = ['userName','userHandle','key']
                result['users'] = add_labels(label,event_member_search,'bucket',PROF_BUCKET, keySize=size)
        else:
            result = {'status':'error', 'message':'Unauthorized'}
        db.session.commit()
    except:
        result['status'] = 'Error'
        result['message'] = 'Changes not made'
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
        result = {'status':'error', 'message':str(e)}
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
            postType = request.form['postType']
            numPoints = int(request.form['amount'])
        else:
            return json.dumps(result)
    else:    
        return json.dumps(result)
    try: #add to sent points upvoted table
        user_check = db.session.query(users.u_personal_points, users.u_stipend_points).filter(users.u_id==userID).first()
        userStipendChange, userPersonalChange, postPointChange, postUserPersonalChange = 0,0,0,0
        pointsChanged = False
        votedAlready = False
        if postType == 'forum':
            post_check = db.session.query(forumPosts.points_count, users.u_personal_points,users.u_id).filter(forumPosts.post_id == postID).filter(users.u_id==forumPosts.post_u_id).first()
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
                    userStipendChange = -user_check.u_personal_points
                    postPointChange = numPoints
                    poserUserPersonalChange = numPoints
                    pointsChanged = True
                else:
                    result['status'] = 'error'
                    result['message'] = 'Points not added'
            else:
                result['status'] = 'error'
                result['message'] = 'Points not added'
        elif postType == 'anon':
            post_check = db.session.query(anonForumPosts.a_points_count, users.u_personal_points,users.u_id).filter(anonForumPosts.a_post_id == postID).filter(users.u_id==anonForumPosts.a_post_u_id).first()
            point_check = db.session.query(anonForumPostUpvoted).filter(anonForumPostUpvoted.post_id==postID).filter(anonForumPostUpvoted.voter_id==userID).first()
            if point_check is not None and point_check != []:
                votedAlready = True
                print 'asdf'
            if post_check is not None and post_check != []:
                if user_check.u_stipend_points >= numPoints:
                    userStipendChange = -numPoints
                    postPointChange = numPoints
                    postUserPersonalChange = numPoints
                    pointsChanged=True 
                elif user_check.u_stipend_points + user_check.u_personal_points >= numPoints:
                    userPersonalChange = -numPoints + user_check.u_stipend_points
                    userStipendChange = -user_check.u_personal_points
                    postPointChange = numPoints
                    poserUserPersonalChange = numPoints
                    pointsChanged = True
                else:
                    result['status'] = 'error'
                    result['message'] = 'Points not added'
            else:
                result['status'] = 'error'
                result['message'] = 'Points not added'
        elif postType == 'group':
            post_check = db.session.query(groupPosts.points_count, users.u_personal_points,groupPosts.group_id).filter(groupPosts.group_post_id == postID).filter(groupPosts.post_u_id==users.u_id).filter(groupMembers.group_id==groupPosts.group_id).filter(groupMembers.member_id==users.u_id).filter(groupMembers.member_status=='M').first()
            point_check = db.session.query(groupPostsUpvoted).filter(groupPostsUpvoted.post_id==postID).filter(groupPostsUpvoted.voter_id==userID).one()
            if point_check is not None and point_check != []:
                votedAlready = True
            if post_check is not None and post_check !=[]:
                member_check = db.session.query(groupMembers.member_status).filter(groupMembers.group_id==post_check.group_id).filter(groupMembers.member_id==userID).first()
                if member_check is not None and member_check.member_status=='M':
                    if user_check.u_stipend_points >= numPoints:
                        userStipendChange = -numPoints
                        postPointChange = numPoints
                        postUserPersonalChange = numPoints
                        pointsChanged=True  
                    elif user_check.u_stipend_points + user_check.u_personal_points >= numPoints:
                        userPersonalChange =  -numPoints + user_check.u_stipend_points
                        userStipendChange = -user_check.u_personal_points
                        postPointChange = numPoints
                        poserUserPersonalChange = numPoints
                        pointsChanged = True
                    else:
                        result['status'] = 'error'
                        result['message'] = 'Points not added'
                else:
                    result['status'] = 'error'
                    result['message'] = 'Points not added'
            else:
                result['status'] = 'error'
                result['message'] = 'Points not added'
        elif postType == 'event':
            post_check = db.session.query(groupEventPosts.points_count, users.u_personal_points,groupEventPosts.group_id).filter(groupEventPosts.group_event_post_id == postID).filter(groupEventPosts.group_event_post_u_id==users.u_id).filter(groupMembers.group_id==groupEventPosts.group_id).filter(groupMembers.member_id==users.u_id).filter(groupMembers.member_status=='M').first()
            point_check = db.session.query(groupEventPostsUpvoted).filter(eventPostsUpvoted.post_id==postID).filter(eventPostsUpvoted.voter_id==userID).one()
            if point_check is not None and point_check != []:
                votedAlready = True
            if post_check is not None and post_check !=[]:
                member_check = db.session.query(groupMembers.member_status).filter(groupMembers.group_id==post_check.group_id).filter(groupMembers.member_id==userID).first()
                if member_check is not None and member_check.member_status=='M':
                    if user_check.stipend_points >= numPoints:
                        userStipendChange = -numPoints
                        postPointChange = numPoints
                        postUserPersonalChange = numPoints
                        pointsChanged=True 
                    elif user_check.stipend_points + user_check.u_personal_points >= numPoints:
                        userPersonalChange =  -numPoints + user_check.u_stipend_points
                        userStipendChange = -user_check.u_personal_points
                        postPointChange = numPoints
                        poserUserPersonalChange = numPoints
                        pointsChanged = True
                    else:
                        result['status'] = 'error'
                        result['message'] = 'Points not added'
                else:
                    result['status'] = 'error'
                    result['message'] = 'Points not added'
            else:
                result['status'] = 'error'
                result['message'] = 'Points not added'
        if pointsChanged:
            db.session.query(users).filter(users.u_id==userID).update({'u_stipend_points':users.u_stipend_points+userStipendChange, 'u_personal_points':users.u_personal_points+userPersonalChange})
            db.session.query(users).filter(users.u_id==post_check.u_id).update({'u_personal_points':users.u_personal_points+postUserPersonalChange})
            if postType =='forum':
                db.session.query(forumPosts).filter(forumPosts.post_id==postID).update({'points_count':forumPosts.points_count+postPointChange})
                if votedAlready:
                    db.session.query(forumPostUpvoted).filter(forumPostUpvoted.post_id==postID).filter(forumPostUpvoted.voter_id==userID).update({'points':forumPostUpvoted.points + numPoints})
                else:
                    db.session.add(forumPostUpvoted(voter_id = userID, post_id = postID, points = numPoints))
            elif postType == 'group':
                db.session.query(groupPosts).filter(groupPosts.group_post_id==postID).update({'points_count':groupPosts.points_count+postPointChange})                
                if votedAlready:
                    db.session.query(forumPostUpvoted).filter(forumPostUpvoted.post_id==postID).filter(forumPostUpvoted.voter_id==userID).update({'points':forumPostUpvoted.points + numPoints})
                else:
                    db.session.add(groupPostUpvoted(voter_id = userID, post_id = postID, points = numPoints))
            elif postType == 'event':
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
            result['status'] = 'success'
            result['message'] = 'Points added'
            db.session.commit()
        else:
            result['status'] = 'error'
            result['message'] = 'No Points Added'
    except Exception, e:
        db.session.rollback()
        result = {'status':'error', 'message':str(e)}
        pass
    finally:
        db.session.close()
    return json.dumps(result)
            
@application.route('/editPost', methods=['POST'])
def editPost():
    result = {'status':'error','message':'Invalid request'}
    if request.method == 'POST':
        if all (k in request.form for k in ('myID', 'postType', 'postID','action')):
            userID = request.form['myID']
            postID = request.form['postID']
            postType = request.form['postType'] #forum, group, event
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
        elif postType == 'forum':
            post_check = db.session.query(forumPosts).filter(forumPosts.post_id == postID).filter(forumPosts.post_u_id==userID).first()
            if post_check is not None and post_check != []:
                post_check.initial_post_cont = new_contents
                post_check.date_time_edited = datetime.now()
                result['status'] = 'success'
                result['message'] = 'Post modified'  
            else:
                result['status'] = 'error'
                result['message'] = 'Post not modified'
        elif postType == 'group':
            member_check = db.session.query(groupMembers.member_role).filter(groupPosts.group_post_id==postID).filter(groupPosts.group_id==groupMembers.group_id).filter(groupMembers.member_id==userID).filter(groupMembers.member_status == 'M').first()
            if member_check is not None and member_check != []:
                post_check = db.session.query(groupPosts).filter(groupPosts.group_post_id == postID).first()
                if post_check is not None and post_check != []:
                    if post_check.post_u_id == userID or (action == 'delete' and member_check.member_role in ('H','O')):
                        post_check.group_post_cont = newContents
                        post_check.date_time_edited = datetime.now()
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
                result['message'] = 'Points not added'
        elif postType == 'event':
            member_check = db.session.query(groupMembers.member_role).filter(groupEventPosts.group_event_post_id==postID).filter(groupEventPosts.group_id==groupMembers.group_id).filter(groupMembers.member_id==userID).filter(groupMembers.member_status == 'M').first()
            if member_check is not None and member_check != []:
                post_check = db.session.query(groupEventPosts).filter(groupEventPosts.group_event_post_id == postID).first()
                if post_check is not None and post_check != []:
                    if post_check.group_event_post_u_id == userID or (action == 'delete' and member_check.member_role in ('H','O')):
                        post_check.group_event_post_cont = newContents
                        post_check.date_time_edited = datetime.now()
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
                result['message'] = 'Points not added'
        db.session.commit()
    except Exception, e:
        db.session.rollback()
        result = {'status':'error', 'message':str(e)}
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
            lastNot = request.form['lastNotificationID']
        else:
            return json.dumps(result)
    else:
        return json.dumps(result)
    try:
        if lastNot != 0:
            notifications = db.session.query(notific.notific_id, notific.date_time, notific.notific_cont, notific.notific_subject).filter(notific.n_u_id==myID).order_by(notific.notific_id.desc()).limit(DEFAULT_LIMIT)
        else:
            notifications = db.session.query(notific.notific_id, notific.date_time, notific.notific_cont, notific.notific_subject).filter(notific.n_u_id==myID).filter(notific.notific_id < lastNot).order_by(notific.notific_id.desc()).limit(DEFAULT_LIMIT)            
        if notifications is not None:
            if notifications != []:
                labels = ['notify_id','timestamp','contents','subject']
                result['notifications'] = add_labels(labels,notifications)
                result['status'] = 'success'
                result['message'] = 'Notifications retrieved'
            else:
                result['status'] = 'success'
                result['message'] = 'No Notifications'
        else:
            result['message'] = 'Error retrieving notifications'
    except Exception, e:
        result = {'status':'error', 'message':str(e)}
        pass    
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
        result = {'status':'error', 'message':str(e)}
    finally:
        db.session.close()
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
        innerMessage = str(datetime.now()) #request.form['message']
        badge = 1 #request.form['badge']
        category = 'testcategory' #request.form['category']
        device_arn = 'arn:aws:sns:us-west-1:554061732115:endpoint/APNS_SANDBOX/hostPostDev/0db06b83-5361-3b06-82b2-864f027c52dc'    
        result = push(device_arn, badge, innerMessage, category)
        resetStipendPoints()
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
def filter_groups(group_list, new_host_posts=None, new_posts=None, new_events=None, keySize=None):
    currentGroups=[]
    sentRequests=[]
    receivedInvites=[]
    for g in group_list:
        if g.member_status == "M":
            if new_host_posts is not None and new_posts is not None and new_events is not None:
                currentGroups.append([g.group_id, g.group_name, g.group_key, g.group_handle, g.member_role, new_host_posts[g.group_id],new_posts[g.group_id],new_events[g.group_id]]) #neweventreplies
            else:
                currentGroups.append([g.group_id, g.group_name, g.group_key, g.group_handle])
        elif g.member_status == 'S':
            sentRequests.append([g.group_id, g.group_name, g.group_key, g.group_handle])
        elif g.member_status == 'I':
            receivedInvites.append([g.group_id, g.group_name, g.group_key,g.group_handle])
    label = ['groupID','groupName','groupKey','groupHandle']
    if new_events is not None:
        current_label =  ['groupID','groupName','groupKey','groupHandle','memberRole','newHostPostsCount','newPostsCount','newEventsCount']
    else:
        current_label = label
    add_all = 'groupBucket'
    labelCurrentGroups = add_labels(current_label, currentGroups, add_all, GROUP_BUCKET, keySize=keySize)
    labelSentRequests = add_labels(label, sentRequests, add_all, GROUP_BUCKET, keySize=keySize)
    labelReceivedInvites = add_labels(label, receivedInvites, add_all, GROUP_BUCKET, keySize=keySize)
    return {'currentGroups':labelCurrentGroups,'sentRequests':labelSentRequests,'receivedRequests':labelReceivedInvites}

def filter_friends(friend_list, kSize):
    sentRequests=[]
    receivedRequests=[]
    currentFriends=[]
    for f in friend_list:
        if f.friend_status == 'F':
            currentFriends.append([f.u_id, f.u_name, f.u_handle,f.firebase_id, f.last_chat,f.last_chat_timestamp, str(f.u_id)+'_userProfPic'])
        elif f.requester == f.u_id:
            sentRequests.append([f.u_id, f.u_name, f.u_handle, f.firebase_id, str(f.u_id)+'_userProfPic'])
        elif f.requester != f.u_id:
            receivedRequests.append([f.u_id,f.u_name, f.u_handle, f.firebase_id, str(f.u_id)+'_userProfPic'])
    currentLabel=['userID','userName','userHandle','firebaseID','lastChatMessage','lastChatTimestamp','key',]
    label=['userID','userName','userHandle','firebaseID','key']
    add_all='bucket'
    labelCurrentFriends = add_labels(currentLabel,currentFriends, add_all, PROF_BUCKET, keySize=kSize) 
    labelSentRequests = add_labels(label,sentRequests, add_all, PROF_BUCKET, True, keySize=kSize)
    labelReceivedRequests = add_labels(label,receivedRequests, add_all, PROF_BUCKET, keySize=kSize)
    return {'currentFriends':labelCurrentFriends,'sentRequests':labelSentRequests,'receivedRequests':labelReceivedRequests}

def filter_members(member_list, keySize):
    sentRequests=[]
    receivedRequests=[]
    currentMembers=[]
    blocked=[]
    for m in member_list:
        if m.member_status == 'M':
            if len(currentMembers) < DEFAULT_LIMIT:
                currentMembers.append([m.member_role, m.u_id, m.firebase_id, m.u_name, m.u_handle, str(m.u_id)+'_userProfPic'])
        elif m.member_status == 'S': #request from user to group
            if len(receivedRequests) < DEFAULT_LIMIT:
                receivedRequests.append([m.u_id, m.firebase_id, m.u_name, m.u_handle, m.member_message, str(m.u_id)+'_userProfPic'])
        elif m.member_status == 'I': #request from group to user
            if len(sentRequests) < DEFAULT_LIMIT:
                sentRequests.append([m.u_id, m.firebase_id, m.u_name, m.u_handle, m.member_message, str(m.u_id)+'_userProfPic'])
        elif m.member_status == 'B':
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
    for k in list_to_add:
        k_temp={}
        for j,x in zip(k, labels):
            if 'timestamp' in x:
                k_temp[x]=json_serial(j)
            elif 'didIVote' in x:
                if j is 'NULL' or j is None:
                    k_temp[x] = 'no'
                else:
                    k_temp[x] = 'yes'
            elif first_initial and 'userName' in x:
                k_temp[x]=first_and_initial(j)
            elif 'eventCellType' in x:
                if j == 'I':
                    k_temp[x] = 'image'
                elif j== 'T':
                    k_temp[x] = 'text'
            elif 'cellType' in x:
                if j == 0:
                    k_temp[x] = 'hostPost'
                elif j== -1:
                    k_temp[x] = 'groupPost'
                else:
                    k_temp[x] = 'post'
            elif 'amIAttending' in x:
                if j is None or j=='N':
                    k_temp[x] = 'no'
                elif j =='M':
                    k_temp[x] = 'yes'
            elif 'Chat' in x:
                if j is None:
                    k_temp[x] = 'None'
                else:
                    k_temp[x] = j
            elif 'key' in x and keySize is not None:
                k_temp[x] = j+'_'+keySize
            else:
                k_temp[x]=j
        if (add_all is not None):
            k_temp[add_all_label]=add_all
        if (add_all_2 is not None):
            k_temp[add_all_label_2]=add_all_2
        temp.append(k_temp)
    return temp
    
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

def hash_password(password):
    pwhash = bcrypt.hashpw(password, bcrypt.gensalt())
    return pwhash

def json_serial(obj):
    if isinstance(obj, datetime):
        serial = obj.isoformat()
        return serial
    elif isinstance(obj, date):
        serial = obj.isoformat()
    raise TypeError ("Type not serializable")

def first_and_initial(name):
    first, space, last = name.partition(" ")
    return first + space + last[0]

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
        apns_dict = {'aps':{'alert':innerMessage,'badge':badge,'category':subject}}
        apns_string = json.dumps(apns_dict,ensure_ascii=False)
        message = {'APNS_SANDBOX':apns_string}
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

def firebaseNotification(fbID, mess):
    expiration = datetime.utcnow() + timedelta(minutes=30)
    auth_payload = {"uid": "1", "auth_data": "foo", "other_auth_data": "bar"}
    options = {"expires":expiration}
    token = create_token(AWS_SECRET_ACCESS_KEY, auth_payload, options)
    payload='"'+mess+'"'
    r = requests.post('https://dotnative-2ec5a.firebaseio.com/users/'+str(fbID)+'/notifications.json?auth='+str(token), data=payload)
    return r.status_code

def logNotification(userID, contents, subject):
    data_entered = notific(n_u_id=userID,notific_cont=contents, notific_subject = subject)
    result = True    
    try:
        db.session.add(data_entered)
        db.session.commit()
    except Exception, e:
        result=False
    finally:
        db.session.close()
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
        if res:
            endpoint_arn = res.group(0).replace('Endpoint ','').replace(' already','')
        else:
            raise
    return False

#@application.route('/', methods=['GET','POST'])


if __name__ == '__main__':
    application.run(host='0.0.0.0')
    
