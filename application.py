'''
Created on May 30, 2016

@author: Michael Tam


        Fields={"acl": "public-read", "Content-Type": file_type},
        Conditions=[
          {"acl": "public-read"},
          {"Content-Type": file_type}
        ],

need to add validation to post variables and email etc
still need to validate
'''

from flask import Flask, request
from application.models import users, chats, friends, forumPosts, groupDetails, groupMembers, groupPosts, groupEventDetails, groupEventPosts, groupEventUsers, forumPostUpvoted, groupPostUpvoted, eventPostUpvoted, systemMessages
from application import db
import json, bcrypt, boto3, os
from sqlalchemy import or_, update, and_, case, in_
from sqlalchemy.orm import load_only
from math import cos
from decimal import Decimal
from datetime import datetime, timedelta

PROF_BUCKET = 'hostpostuserprof'
GROUP_BUCKET = 'hostpostgroups'
EVENT_BUCKET = 'hostposteventimage'

DEFAULT_STIPEND = 42
DEFAULT_STIPEND_TIME = timedelta(days=7)


application = Flask(__name__)
application.debug = True

application.secret_key = 'cC1YCIWOj9GgWspgNEo2'

#@application.route('/', methods=['GET','POST'])

@application.route('/login', methods=['POST'])
def login():
    result = json.dumps({'status':'error','message':'Invalid request'})
    if request.method == 'POST':
        if all (k in request.form for k in ('userEmail','userPassword')):
            userEmail = request.form['userEmail']        
            userPass = request.form['userPassword']
            login_method = 0 #login via email
        elif all (k in request.form for k in ('userHandle','userPassword')):
            userHandle = request.form['userHandle']
            userPass = request.form['userPassword']
            login_method = 1 #login via handle
        else:
            return result
    else:
        return result
    result = {'status':'error', 'message':'Invalid User Name or Password'}
    try:
        if login_method == 0:
            login_check = db.session.query(users.u_id).filter_by(email=userEmail).first() 
        else: #login via handle
            login_check = db.session.query(users.u_id).filter_by(handle=userHandle).first() 
        if login_check != []:
            if login_check.verify_password(userPass):
                result['status'] = 'success'
                result['message'] = 'successful Login'
                result['myID'] = login_check.u_id
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
    result = json.dumps({'status':'error','message':'Invalid request'})
    if request.method == 'POST':
        if all (k in request.form for k in ('userEmail','userName','userHandle','userPassword','isPicSet')):
            userEmail = request.form['userEmail']
            userHandle = request.form['userHandle']
            userName = request.form['userName']
            hashpaswrd = hash_password(request.form['userPassword'].encode('utf-8'))
            picSet = request.form['isPicSet']
        else:
            return result
    else:
        return result
    data_entered = users(u_email = userEmail, u_name=userName, u_paswd = hashpaswrd, u_handle = userHandle, stipend_points = DEFAULT_STIPEND)
    result={'status':'error','message':'Email already registered'}
    try:
        db.session.add(data_entered)
        try:
            user_check = db.session.query(users).filter_by(email=userEmail).first()
            user_id = user_check.u_id
            result['myID']=user_id
            result['key'] = 'default'
            result['bucket']= PROF_BUCKET
            if picSet == 'yes':
                file_name=str(user_id)+'_userProfPic'
                result['key'] = file_name
                db.session.query(users).filter_by(u_id=user_id).update({'key':result['key']})
            else: #pic not set ( = 'no')
                db.session.query(users).filter_by(u_id=user_id).update({'key':'default'})
        except Exception, e:
            result = {'uploadStatus':'error', 'error_message':str(e)}
            pass
        db.session.commit()       
        result['status'] = 'success'
        try:
            message_check = db.query(systemMessages.message_contents).filter(systemMessages.message_name == 'welcome').first()
            result['message'] = message_check.message_contents
        except:
            result['message'] = 'Welcome to .native - please tell your friends!' 
            pass
    except Exception, e:
        db.session.rollback()
        result = {'status':'error', 'message':str(e)}
        pass
    finally:
        db.session.close()
    return json.dumps(result)

@application.route('/getForumPost', methods=['POST']) #sort hot=all posts in last 24 hours ordered by points
def getForumPost():
    result = json.dumps({'status':'error','message':'Invalid request'})
    if request.method == 'POST':
        if all (k in request.form for k in ('myID', 'postID')):
            myID = request.form['myID']
            postID = request.form['postID']
            if postID == 0: #get parent posts or get my posts
                if 'isMine' in request.form:
                    isMine = request.form['isMine']
                    if isMine is 'no':
                        if all (m in request.form for m in ('longitude','latitude','sort','isExact')):
                            isExact = request.form['isExact']
                            if isExact == 'yes':
                                radius = Decimal(1.5)
                            else:
                                radius = Decimal(5.0)
                            myLong = Decimal(request.form['longitude'])
                            myLat = Decimal(request.form['latitude'])
                            sort = request.form['sort']
                        else:
                            return result
                else:
                        return result
            else: #post ID == actual post ID - get replies
                isMine = None
                isExact = None
                radius = None
                sort = None
        else:
            return result
    else:    
        return result
    
    result = {'status':'error', 'message':'No posts found'}
    try:
        if postID == 0: #get parent posts or get my posts 
            if isMine == 'yes': #get parent posts you created and parent posts you replied to
                subq = db.session.query(forumPosts.original_post_id).filter(forumPosts.post_u_id == myID).filter(forumPosts.original_post_id != 0).distinct().subquery()
                get_my_posts = db.session.query(users.u_id, users.u_name, users.u_handle,users.u_key, forumPosts.post_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points).filter(forumPosts.post_u_id==users.u_id).filter(forumPosts.post_u_id==myID).filter(or_(forumPosts.original_post_id==0, forumPosts.post_id.in_(subq.original_post_id))).outerJoin(forumPostUpvoted, users.u_id == forumPostUpvoted.voter_id, forumPosts.post_id == forumPostUpvoted.post_id).order_by(forumPosts.date_time).distinct().all()
                if get_my_posts is not None:    
                    #query for post count
                    result['status'] = 'success'        
                    if get_my_posts == []:
                        result['message'] = 'No results found'
                    else:
                        result['message'] = 'Results Found'
                        labels = ['userID','userName','userHandle','key','bucket','postID','postContent','pointsCount','replyCount','timestamp','timestampEdited','didIVote']
                        add_all = 'bucket'
                        result['forumPosts'] = add_labels(labels,get_my_posts,add_all,PROF_BUCKET)
            elif isMine == 'no':
                max_long, min_long, max_lat, min_lat = getMinMaxLongLat(myLong, myLat, radius)
                if sort == 'new':         
                    get_post_check = db.session.query(users.u_id, users.u_name, users.u_handle,users.u_key, forumPosts.post_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points).filter(forumPosts.post_u_id==users.u_id).filter(forumPosts.original_post_id==0).filter(forumPosts.post_lat.between(min_lat, max_lat)).filter(forumPosts.post_long.between(min_long, max_long)).outerJoin(forumPostUpvoted, users.u_id == forumPostUpvoted.voter_id, forumPosts.post_id == forumPostUpvoted.post_id).order_by(forumPosts.date_time).distinct().all()
                elif sort == 'hot':
                    get_post_check = db.session.query(users.u_id, users.u_name, users.u_handle,users.u_key, forumPosts.post_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points).filter(forumPosts.post_u_id==users.u_id).filter(forumPosts.original_post_id==0).filter(forumPosts.post_lat.between(min_lat, max_lat)).filter(forumPosts.post_long.between(min_long, max_long)).outerJoin(forumPostUpvoted, users.u_id == forumPostUpvoted.voter_id, forumPosts.post_id == forumPostUpvoted.post_id).distinct().all() #restrict by date
                else:
                    return result
                if get_post_check is not None:
                    result['status'] = 'success'        
                    if get_post_check == []:
                        result['message'] = 'No results found'
                    else:
                        result['message'] = 'Results Found'
                        labels = ['userID','userName','userHandle','key','bucket','postID','postContent','pointsCount','replyCount','timestamp','timestampEdited','didIVote']
                        add_all = 'bucket'
                        result['forumPosts'] = add_labels(labels,get_post_check,add_all,PROF_BUCKET)
        else: #actual postID
            get_posts = db.session.query(users.u_id, users.u_name, users.u_handle,users.u_key, forumPosts.post_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points).filter(forumPosts.post_u_id==users.u_id).filter(forumPosts.post_id==postID).outerJoin(forumPostUpvoted, users.u_id == forumPostUpvoted.voter_id, forumPosts.post_id == forumPostUpvoted.post_id).distinct().first()
            get_replies = db.session.query(users.u_id, users.u_name, users.u_handle,users.u_key, forumPosts.post_id, forumPosts.post_cont, forumPosts.points_count, forumPosts.reply_count, forumPosts.date_time, forumPosts.date_time_edited, forumPostUpvoted.points).filter(forumPosts.post_u_id==users.u_id).filter(forumPosts.original_post_id==postID).outerJoin(forumPostUpvoted, users.u_id == forumPostUpvoted.voter_id, forumPosts.post_id == forumPostUpvoted.post_id).order_by(forumPosts.post_id).distinct().all() 
            if get_posts is not None:
                if get_posts == []:
                        result['message'] = 'No results found'
                else:
                    result['message'] = 'Results Found'
                    labels = ['userID','userName','userHandle','key','postID','postContent','pointsCount','timestamp','timestampEdited','didIVote']
                    add_all = 'bucket'
                    result['parentPost'] = add_labels(labels,get_posts,add_all,PROF_BUCKET)
                    result['replies'] = add_labels(labels,get_replies,add_all,PROF_BUCKET)
        db.session.close()
    except Exception, e:
        result = {'status':'error', 'message':str(e)}
        pass
    data = json.dumps(result)
    return data

@application.route('/sendForumPost', methods=['POST'])
def sendForumPost():
    result = json.dumps({'status':'error','message':'Invalid request'})
    if request.method == 'POST':
        if all (k in request.form for k in ('myID', 'postContent', 'postID')):
            myID = request.form['myID']
            postCont = request.form['postContent']
            postID = request.form['postID']
            if postID == 0:
                if all (l in request.form for l in ('longitude','latitude')):
                    postLong = request.form['longitude']
                    postLat = request.form['latitude']
                else:
                    return result
        else:
            return result
    else:    
        return result
    result = {'status':'error', 'message':'Invalid'}
    if postID == 0:
        data_entered = forumPosts(post_u_id = myID, post_cont = postCont, post_long = postLong, post_lat = postLat)
    else:
        data_entered = forumPosts(post_u_id = myID, post_cont = postCont, original_post_id = postID)
    try:
        db.session.add(data_entered)
        db.session.commit()
        result['status'] = 'success'
        result['message'] = 'Posted'
    except:
        db.session.rollback()
        pass    
    finally:
        db.session.close()
    data = json.dumps(result)
    return data

@application.route('/getFriendList', methods=['POST'])
def getFriendList():
    result = json.dumps({'status':'error','message':'Invalid request'})
    if request.method == 'POST':        
    #if all (k in request.form for k in ('myID')):
        if 'myID' in request.form:
            userID = request.form['myID']
            #attribute = request.form['attribute']
        else:
            return result
    else:    
        return result
    result = {'status':'error', 'message':'No results found'}
    try:
        friend_list = db.session.query(users.u_id, users.u_name, users.u_handle, friends.friend_a, friends.friend_b, friends.requester, friends.friend_status, users.u_key, friends.last_chat).filter(users.u_id==userID).filter(or_(users.u_id==friends.friend_a, users.u_id==friends.friend_b)).filter(or_(friends.friend_status == 'F',friends.friend_status == 'P')).distinct().all()
        db.session.close()
        result['status']='success'
        if friend_list !=[]:
            result['message']='Friends Found'
            groupsFriends = filter_friends(friend_list)          
            for a in groupsFriends:
                result[a]=groupsFriends[a]
    except Exception, e:
        result = {'status':'error', 'message':str(e)}
        pass
    data = json.dumps(result)
    return data

@application.route('/searchFriend', methods=['POST'])
def searchFriend():
    result = json.dumps({'status':'error','message':'Invalid request'})
    if request.method == 'POST':
        if all (k in request.form for k in ('criteria','myID')): 
            criteria = request.form['criteria']
            myID = request.form['myID']
        else:
            return result
    else:
        return result
    #handle
    search_term = '%' + criteria + '%'
    result = {'status':'error', 'message':'No results found'}
    try:
        search_check = db.session.query(users.u_id,users.u_name, users.u_handle, users.key).filter(or_(users.u_handle.like(search_term), users.u_name.like(search_term))).filter(users.u_id != myID).distinct().all() 
        block_check = db.session.query(friends.friend_a, friends.friend_b).filter(or_(friends.friend_a == myID, friends.friend_b == myID)).filter(friends.friend_status=='B').distinct().all()    
        db.session.close()
        if search_check is not None:
            result['status'] = 'success'        
            if search_check == []:
                result['message'] = 'No results found'
            else:
                labels =['userID','userName','userHandle','key']
                add_all = 'bucket'
                if block_check != []:
                    search_list = []
                    for f in search_check:
                        for b in block_check:
                            if not (f.u_id == b.friend_a or f.u_id == b.friend_b):
                                search_list.append(f)
                    result['users']= add_labels(labels,search_list,add_all,PROF_BUCKET)
                    if search_list == None:
                        result['message'] = 'No Results Found'
                else:
                    result['users']= add_labels(labels,search_check,add_all, PROF_BUCKET, True)
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
    result = json.dumps({'status':'error','message':'Invalid request'})
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','otherID','action')):
            requester_ID = request.form['myID']
            friend_ID = request.form['userID']
            action = request.form['action']
        else:
            return result
    else:
        return result
    try:
        #see if friend request has been made already
        friend_check = db.session.query(friends).filter(or_(friends.requester==requester_ID, friends.requester==friend_ID)).first() #first? or all? case to handle that?
        #if friends > 1 ? should never happen error
        if friend_check is not None and friend_check != []:
            f_status=friend_check.friend_status
            req = friend_check.requested(requester_ID)
            if action == 'block' and f_status != 'B':
                friend_check.friend_status = 'B'
                friend_check.requester = requester_ID
                db.session.commit()
                result['status']='success'
                result['message']='Blocked'
            elif f_status == 'F': #friends already
                if action == 'unfriend': #unfriend
                    friend_check.friend_status='U'
                    db.session.commit()
                    result['status']='success'
                    result['message']='Friend un-friended'                  
            elif f_status == 'P': #pending
                if req and action == 'withdraw':
                    friend_check.friend_status='W'
                    db.session.commit()
                    result['status']='success'
                    result['message']='Friend request withdrawn'
                elif not req:
                    if action == 'accept': #accept
                        friend_check.friend_status='F'
                        db.session.commit()
                        result['status']='success'
                        result['message']='Friend request accepted'        
                        #update status to F
                    elif action == 'deny': #deny
                        friend_check.friend_status='D'
                        db.session.commit()
                        result['status']='success'
                        result['message']='Friend request denied'
                        #update status to D
            elif f_status == 'B' and req:
                if action == 'unblock': 
                    friend_check.friend_status='U'
                    db.session.commit()             
                    result['status']='success'
                    result['message']='Unblocked'            
            elif action == 'request': #anything else, update as to a new request
                friend_check.friend_status='P'
                db.session.commit()
                result['status']='success'
                result['message']='Friend request sent'
            else:
                result['status']='error'
                result['message']='Invalid Request'
        elif action == 'request': #new request
            friend_entered = friends(requester_ID, friend_ID, requester_ID, 'P')
            db.session.add(friend_entered)
            db.session.commit()
            result['status']='success'
            result['message']='Friend request sent'
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
    result = json.dumps({'status':'error','message':'Invalid request'})
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','userID','limitInfo')):
            userID = request.form['myID']
            otherID = request.form['userID']
            limitInfo = request.form['limitInfo']
        else:
            return result
    else:
        return result
    if userID == otherID:
        return result
    try:
        userProf_check = db.session.query(users.key, users.u_name, users.u_handle, users.u_description, users.u_stipend_points, users.u_personal_points).filter_by(u_id=otherID).first()
        if userProf_check != []:
            result['status'] = 'success'
            result['message'] = 'successfully retrieved profile information.' 
            if limitInfo == 'no':
                result['key'] = userProf_check.key
                result['bucket'] = PROF_BUCKET
                other_groups = db.session.query(groupDetails.group_id, groupDetails.group_handle,groupDetails.group_name, groupDetails.group_key,groupDetails.group_city, groupDetails.group_description).filter(groupMembers.member_id==otherID).filter(groupDetails.group_id==groupMembers.group_id).filter(groupMembers.member_status=='M').distinct().all() 
            else:
                other_groups = db.session.query(groupDetails.group_id, groupDetails.group_handle,groupDetails.group_name, groupDetails.group_city, groupDetails.group_description).filter(groupMembers.member_id==otherID).filter(groupDetails.group_id==groupMembers.group_id).filter(groupMembers.member_status=='M').distinct().all()
            result['userName'] = userProf_check.u_name 
            result['userHandle'] = userProf_check.handle
            result['userDescription'] = userProf_check.user_description
            result['pointsCount'] = userProf_check.personal_points
            is_Friends = db.session.query(friends).filter(or_(friends.friend_a==userID, friends.friend_b==userID)).filter(or_(friends.friend_a==otherID,friends.friend_b==otherID)).first()          
            db.session.close()
            result['isFriend'] = 'N'
            if is_Friends is not None and is_Friends != []:
                if is_Friends.friend_status == 'F':
                    result['isFriend']= 'F'
                elif is_Friends.friend_status == 'P':
                    if is_Friends.requested(userID):
                        result['isFriend']='S' #sent
                    elif is_Friends.requested(otherID):
                        result['isFriend']='R' #requested
                elif is_Friends.friend_status == 'B': #blocked
                    result['isFriend']='B' #if B don't send 
                    result['key'] = 'default'
                    result['name'] = 'default'
            if other_groups is not None and other_groups != []:
                add_all = 'groupBucket'
                if limitInfo == 'no':
                    group_labels = ['groupID','groupHandle','groupName','groupKey','city','groupDescription']
                    result['groups'] = add_labels(group_labels, other_groups, add_all, GROUP_BUCKET)
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
    result = json.dumps({'status':'error','message':'Invalid request'})
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','userID')):
            myID = request.form['myID']
            otherID = request.form['userID']
        elif 'userID' not in request.form and 'myID' in request.form:
            myID = request.form['myID']
            otherID = myID
        else:
            return result
    else:
        return result
    result = {'status':'error', 'message':'No Chats Available'}  
    try:
        chat_check = db.session.query(chats.send_id, chats.messg_cont, chats.date_time).filter(or_(myID==chats.send_id,myID==chats.recip_id)).filter(or_(otherID==chats.send_id,otherID==chats.recip_id)).order_by(chats.date_time.desc()).all()
        db.session.close()
        if chat_check != []:
            result['status'] = 'success'        
            if chat_check == []:
                result['message'] = 'No Chats Found'
            else:
                result['message'] = 'Chats Found'
                label = ['userID', 'chatMessage','timestamp'] #senderID
                result['chats'] = add_labels(label, chat_check)
        else:
            result['status'] = 'error'
            result['message'] = 'Error Retrieving Chats'
    except Exception, e:
        result = {'status':'error', 'message':str(e)}
    data = json.dumps(result)
    return data

@application.route('/sendChat', methods=['POST'])
def sendChat():
    result = json.dumps({'status':'error','message':'Invalid request'})
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','otherID','chatMessage')):
            sendID = request.form['myID']
            recipID = request.form['userID']
            mess = request.form['chatMessage']
        else:
            return result
    else:
        return result
    data_entered = chats(sendID, recipID, mess)
    try:
        db.session.add(data_entered)
        db.session.commit()
        result['status'] = 'success'
        result['message'] = 'Chat Sent'
    except:
        db.session.rollback()
        pass    
    finally:
        db.session.close()
    data = json.dumps(result)
    return data

@application.route('/getMyProfile', methods=['POST'])
def getMyProfile():
    result = json.dumps({'status':'error','message':'Invalid request'})
    if request.method == 'POST':
        if 'myID' in request.form: 
            userID = request.form['myID']
        else:
            return result
    else:
        return result
    try:
        userProf_check = db.session.query(users.u_name, users.u_email, users.u_handle, users.u_key, users.u_dob, users.u_description, users.u_phone, users.u_personal_points, users.u_stipend_points).filter(users.u_id==userID).first()
        if userProf_check is not None and userProf_check != []:
            result['status'] = 'success'
            result['message'] = 'successfully retrieved profile information'
            result['key'] = userProf_check.u_key
            result['bucket'] = PROF_BUCKET
            result['myName'] = userProf_check.u_name
            result['myHandle'] = userProf_check.u_handle
            result['myDescription'] = userProf_check.u_description
            result['myEmail'] = userProf_check.u_email
            '''
            if (datetime.now() - userProf_check.last_stipend_date > DEFAULT_STIPEND_TIME):
                    userProf_check.stipend_points = DEFAULT_STIPEND
                    db.session.commit()
            '''
            result['weeklyPoints'] = userProf_check.stipend_points
            result['myPoints'] = userProf_check.personal_points
            if (userProf_check.u_dob == datetime.date(1901,1,1)):
                result['myBirthday'] = 'Need to set'
            else:
                result['myBirthday'] = userProf_check.dob
            if (userProf_check.u_phone == 'N/A'):
                result['myPhoneNumber'] = 'Need to set'
            else:
                result['myPhoneNumber'] = userProf_check.phone
    except Exception, e:
        db.session.rollback()
        result = {'status':'error', 'message':str(e)}
        pass
    finally:
        db.session.close()
    data = json.dumps(result)
    return data

@application.route('/updateMyProfile', methods=['POST'])
def updateMyProfile():
    result = json.dumps({'status':'error','message':'Invalid request'})
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
                picSet = request.form['isPicSet'] #yes no
                if all (m in request.form for m in ('myPassword','newPassword')):
                    myPass = request.form['myPassword']
                    newPass = request.form['newPassword']
        else:
            return result
    else:
        return result
    try:
        if action == 'edit':
            if myPass is not None and newPass is not None:
                if picSet == 'yes':
                    result['key'] = str(user_id)+'_userProfPic'
                else: #picSet == 'no'
                    result['key'] = 'default'
                result['bucket'] = PROF_BUCKET
                login_check = db.session.query(users.u_id).filter(u_id==userID).first() 
                if login_check is not None and login_check != []:
                    if login_check.verify_password(myPass):                         
                        db.session.query(users).filter(users.u_id==userID).update({'u_name':newName,'u_handle':newHandle,'u_description':newDescription,'u_dob':newBirthday,'u_phone':newPhoneNumber,'u_email':newEmail,'u_passwd':hash_password(newPass.encode('utf-8')),'key':result['key']})
                    else:
                        return result
            else:
                db.session.query(users).filter(users.u_id==userID).update({'u_name':newName,'u_handle':newHandle,'u_description':newDescription,'u_dob':newBirthday,'u_phone':newPhoneNumber,'u_email':newEmail,'key':result['key']}) 
            result['status'] = 'success'
            result['message'] = 'successfully updated profile information'
        else:
            return json.dumps({'status':'error','message':'Invalid request'})
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
    result = json.dumps({'status':'error','message':'Invalid request'})
    if request.method == 'POST':
        if 'myID' in request.form:
            myID = request.form['myID']
        else:
            return result
    else:
        return result
    try:
        subq = db.session.query(groupPosts.original_post_id).filter(groupPosts.post_u_id == myID).filter(groupPosts.original_post_id != 0).distinct().subquery()
        get_my_posts = db.session.query(users.u_id, users.u_name, users.u_handle,users.u_key, groupPosts.group_post_id, groupPosts.group_post_cont, groupMembers.member_role, groupDetails.group_name, groupPosts.points_count, groupPosts.reply_count, groupPosts.date_time, groupPosts.date_time_edited, groupPostUpvoted.points, groupPosts.original_post_id).filter(groupPosts.post_u_id==users.u_id).filter(groupMembers.member_id == users.u_id).filter(groupMembers.group_id==groupPosts.group_id).filter(groupPosts.post_u_id==myID).filter(groupDetails.group_id==groupPosts.group_id).filter(or_(groupPosts.original_post_id==0, groupPosts.group_post_id.in_(subq.original_post_id))).outerJoin(groupPostUpvoted, users.u_id == groupPostUpvoted.voter_id, groupPosts.group_post_id == groupPostUpvoted.post_id).distinct().all()
        if get_my_posts is not None:    
            result['status'] = 'success'        
            if get_my_posts == []:
                result['message'] = 'No results found'
            else:
                result['message'] = 'Results Found'
                labels = ['userID','userName','userHandle','key','bucket','postID','postContent','memberRole','groupName', 'pointsCount','replyCount','timestamp','timestampEdited','didIVote','cellType']
                add_all = 'bucket'
                result['groupPosts'] = add_labels(labels,get_my_posts,add_all,PROF_BUCKET)
    except Exception, e:
        result = {'status':'error', 'message':str(e)}
        pass
    data = json.dumps(result)
    return data

@application.route('/getMyGroupList', methods=['POST'])
def getMyGroupList():
    result = json.dumps({'status':'error','message':'Invalid request'})
    if request.method == 'POST':
        if 'myID' in request.form:
            user_id = request.form['myID']
        else:
            return result
    else:
        return result    
    try:
        group_list = db.session.query(users.u_id, users.u_name, users.u_handle, users.u_key, groupDetails.group_id, groupDetails.group_name, groupDetails.group_key, groupMembers.member_role, groupMembers.member_status, groupMembers.last_post_seen).filter(users.u_id==user_id).filter(groupMembers.member_id==users.u_id).filter(groupMembers.group_id==groupDetails.group_id).filter(groupMembers.member_status != "B").distinct().all()
        num_host_posts={}
        num_posts = {}
        num_events = {}
        for k in group_list: #number new group Posts, new event,  new host post
            if k.member_status == 'M':
                new_host_posts = db.session.query(groupPosts.group_post_id).filter(k.group_id == groupPosts.group_id).filter(groupPosts.original_post_id==0).filter(groupPosts.group_post_id > k.last_host_post_seen).count()
                new_posts= db.session.query(groupPosts.group_post_id).filter(k.group_id == groupPosts.group_id).filter(groupPosts.original_post_id==-1).filter(groupPosts.group_post_id > k.last_post_seen).count()
                new_events = db.session.query(groupEventDetails.event_id).filter(k.group_id == groupEventDetails.group_id).filter(groupEventDetails.event_id > k.last_event_seen).count()
                num_host_posts[k.group_id]=new_host_posts.group_post_id
                num_posts[k.group_id]=new_posts.group_post_id
                num_events[k.group_id]=new_events.event_id
        db.session.close()
        result['status']='success'
        if group_list != []:
            result['message']='Groups Found'
            groupsFriends = filter_groups(group_list, num_host_posts, num_posts, num_events)        
            for a in groupsFriends:
                result[a]=groupsFriends[a]
        else:
            result['message'] = 'No groups found'
    except Exception, e:
        result = {'status':'error', 'message':str(e)}
        pass
    data = json.dumps(result)
    return data

@application.route('/searchGroup', methods=['POST'])
def searchGroup():
    result = json.dumps({'status':'error','message':'Invalid request'})
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','criteria','longitude','latitude','isExact','groupSize','category')):
            user_id = request.form['myID']
            criteria = request.form['criteria']
            searchLong = request.form['longitude']
            searchLat = request.form['latitude']
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
                return result
            isExact = request.form['isExact']
            if isExact == 'yes':
                radius = 5
            else:
                radius = 10
            category = request.form['category']
        else:
            return result
    else:
        return result
    maxLong, minLong, maxLat, minLat = getMinMaxLongLat(searchLong, searchLat, radius)
    #distance
    criteria = '%'+criteria+'%'
    try: #search by size
        if groupSize in ('large','any'):
            group_search = db.session.query(groupDetails.group_id, groupDetails.group_handle, groupDetails.group_name, groupDetails.group_num_members, groupDetails.group_key, groupDetails.group_city, groupDetails.group_description, groupDetails.invite_only).filter(groupDetails.group_long >= minLong).filter(groupDetails.group_long <= maxLong).filter(groupDetails.group_lat >= minLat).filter(groupDetails.group_lat <= maxLat).filter(groupDetails.searchable == 'Y').filter(groupDetails.group_num_members >= minSize).filter(groupDetails.group_category ==category).filter(or_(groupDetails.group_handle.like(criteria),groupDetails.group_name.like(criteria),groupDetails.group_description.like(criteria))).distinct().all()
        else: #small or medium
            group_search = db.session.query(groupDetails.group_id, groupDetails.group_handle, groupDetails.group_name, groupDetails.group_num_members, groupDetails.group_key, groupDetails.group_city, groupDetails.group_description, groupDetails.invite_only).filter(groupDetails.group_long >= minLong).filter(groupDetails.group_long <= maxLong).filter(groupDetails.group_lat >= minLat).filter(groupDetails.group_lat <= maxLat).filter(groupDetails.searchable == 'Y').filter(groupDetails.group_num_members >= minSize).filter(groupDetails.group_num_members <= maxSize).filter(groupDetails.group_category == category).filter(or_(groupDetails.group_handle.like(criteria),groupDetails.group_name.like(criteria),groupDetails.group_description.like(criteria))).distinct().all()
        blocked_search = db.session.query(groupDetails.group_id).filter(groupMembers.member_id == user_id).filter(groupMembers.group_id==groupDetails.group_id).filter(groupMembers.member_status=='B').all()
        db.session.close()
        if blocked_search != []:
            group_list = []
            for k in group_search:
                temp = True
                for i in blocked_search:
                    if k.group_id == i.group_id:
                        temp = False
                if (temp): #append upcoming events count
                    group_list.append(k)
        else:
            group_list = group_search
        result['status']='success'
        if group_list != []:
            result['message']='Groups Found'
            label = ['groupID','groupHandle','groupName','membersCount','groupKey','city','groupDescription','inviteOnly'] #upcomingeventsCount
            result['groups']=add_labels(label, group_list,'groupBucket',GROUP_BUCKET)
            #membersCount
            #UpcomingEventsCount
    except Exception, e:
        result = {'status':'error', 'message':str(e)}
        pass
    data = json.dumps(result)
    return data

@application.route('/createGroup', methods=['POST'])
def createGroup():
    result = json.dumps({'status':'error','message':'Invalid request'})
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','groupName','groupHandle','latitude','longitude','city','groupDescription','isPicSet','searchable','onProfile','readable','inviteOnly','category')):
            userID = request.form['myID']
            groupName = request.form['groupName']
            groupHandle = request.form['groupHandle']
            groupLat = request.form['latitude']
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
            return result
    else:
        return result
    data_entered = groupDetails(group_name=groupName, group_handle=groupHandle, group_description=groupDescription, group_city=groupCity, group_lat=groupLat, group_long=groupLong, group_category=category, group_searchable=searchable, group_readable=readable, group_on_profile=onProfile, group_invite_only=inviteOnly)
    result={'status':'error','message':'Group already registered'}
    try:
        db.session.add(data_entered)
        group_check = db.session.query(groupDetails).filter(groupDetails.group_handle==groupHandle).first()
        user_check = db.session.query(users).filter(users.u_id == userID).first()
        if group_check != [] and user_check != []:
            memberData = groupMembers(group_id=group_check.group_id,member_id=user_check.u_id,member_role='O',members_status='M')
            db.session.add(memberData)
        else:
            result['status'] = 'Error'
            result['message'] = 'Group registration error'
            db.session.rollback()
            pass
        try:
            group_check_2 = db.session.query(groupDetails).filter_by(groupDetails.group_id == group_check.group_id).first()
            
            result['groupKey'] = 'default'
            result['groupBucket']= GROUP_BUCKET
            if picSet == 'yes':
                file_name=str(group_check_2.group_id)+'_groupPic'
                group_check.key = file_name
                result['groupKey'] = file_name
        except Exception, e:
            result = {'uploadStatus':'error', 'error_message':str(e)}
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
    result = json.dumps({'status':'error','message':'Invalid request'})
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','groupID')):
            userID = request.form['myID']
            groupID = request.form['groupID']
        else:
            return result
    else:
        return result  
    try: #if group is public do something else < invite_only is 'N'
        group_search = db.session.query(groupDetails.group_id, groupDetails.group_handle, groupDetails.group_name, groupDetails.group_key, groupDetails.group_city, groupDetails.group_description, groupMembers.member_role, groupDetails.group_readable, groupDetails.group_num_members, groupDetails.group_invite_only).filter(groupDetails.group_id==groupID).filter(groupMembers.member_id==userID).filter(groupMembers.group_id==groupID).distinct().first()
        blocked_search = db.session.query(groupDetails.group_id).filter(groupMembers.member_id == userID).filter(groupMembers.group_id==groupDetails.group_id).filter(groupMembers.member_status!='B').all()        
        if blocked_search != []:
            group_list = []
            for k in group_search:
                temp = True
                for i in blocked_search:               
                    if k.group_id == i.group_id:
                        temp = False
                if(temp):
                    group_list.append(k)
        else:
            group_list= group_search
        if(group_list == []):
            result['status']='success'
            result['message']='No Groups Found'
        elif group_list != []:
            #if group is public do something else
            result['message']='Group found'
            label = ['groupID','groupHandle','groupName','groupKey','city','groupDescription', 'myMemberRole','readable','membersCount','inviteOnly'] #upcomingeventsCount, groupsRequestsCount
            result['groupInfo']=add_labels(label, group_list,'groupBucket',GROUP_BUCKET)
            #get most recent host post and regular group posts            
            hostPostSearch =  db.session.query(groupPosts.group_post_id, users.u_id, groupMembers.member_role, users.u_name, users.u_handle, users.u_key, groupPosts.date_time, groupPosts.date_time_edited, groupPosts.group_post_cont, groupPosts.reply_count).filter(groupPosts.group_id == group_search.group_id).filter(groupPosts.post_u_id == users.u_id).filter(groupMembers.group_id==group_search.group_id).filter(groupMembers.member_id==users.u_id).distinct().order_by(groupPosts.group_post_id.desc()).first()
            subq = db.session.query(groupPosts.original_post_id).filter(groupPosts.post_u_id==userID).filter(groupPosts.original_post_id == -1).distinct().subquery()
            postSearch = db.session.query(groupPosts.group_post_id, users.u_id, groupMembers.member_role, users.u_name, users.u_handle, users.u_key, groupPosts.date_time, groupPosts.date_time_edited, groupPosts.group_post_cont, groupPosts.reply_count, groupPosts.points_count, groupPostUpvoted.points).filter(groupPosts.post_u_id == users.u_id).filter(groupPosts.post_u_id==groupMembers.member_id).filter(or_(groupPosts.original_post_id==-1, forumPosts.post_id.in_(subq.original_post_id))).outerJoin(groupPostUpvoted, users.u_id == groupPostUpvoted.voter_id, groupPosts.group_post_id == groupPostUpvoted.post_id).distinct().all()
            if hostPostSearch != [] and postSearch != []:
                hostPostLabel = ['postID','userID','memberRole','userName','userHandle','key','timestamp','timestampEdited','postContent','replyCount']
                result['hostPost']=add_labels(hostPostLabel,hostPostSearch, 'bucket', PROF_BUCKET) 
                result['message'] = 'Group Found. Posts.'
                postLabel = ['postID','userID','memberRole','userName','userHandle','key','timestamp','timestampEdited','postContent','replyCount','pointsCount','didIVote']
                result['groupPosts'] = add_labels(postLabel, postSearch,'bucket',PROF_BUCKET)
                result['status']=success
            else:
                result['message'] = 'Group found. No Host Post'
                result['status']=success
            user_count = db.session.query(groupMembers.member_id).filter(groupMembers.group_id==group_search.group_id).distinct().count()
            result['members']=user_count
            #upcomingEventsCount'
        db.session.close()        
    except Exception, e:
        result = {'status':'error', 'message':str(e)}
        pass
    data = json.dumps(result)
    return data

@application.route('/sendGroupPost', methods=['POST'])
def sendGroupPost():
    result = json.dumps({'status':'error','message':'Invalid request'})
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','groupID', 'postContent', 'postID')):
            myID = request.form['myID']
            groupID = request.form['groupID']
            originalPostID = request.form['postID'] #checking on client side
            messgCont = request.form['postContent']
        else:
            return result
    else:    
        return result
    result = {'status':'error', 'message':'Invalid'}
    data_entered = groupPosts(group_id=groupID, post_u_id=myID, group_post_cont=messgCont, original_post_id=originalPostID)
    try:
        db.session.add(data_entered)
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
    result = json.dumps({'status':'error','message':'Invalid request'})
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','postID')):
            userID = request.form['myID']
            postID = request.form['postID']  #0=hostPost,  else parent postID XXX-1=groupPost,
            groupID = request.form['groupID']
        else:
            return result
    else:    
        return result
    result = {'status':'error', 'message':'No posts found'}
    try:
        member_check = db.session.query(groupMembers.member_role, groupMembers.member_status).filter(groupMembers.member_id==userID).filter(groupMembers.member_id==users.u_id).filter(groupMembers.group_id == groupID).filter(groupMembers.member_status == 'M').first()
        group_check = db.session.query(groupDetails.group_readable).filter(groupDetails.group_id == groupID).first()
        if group_check.group_readable or member_check.member_status == 'M':
            result['myMemberRole']=member_check.member_role
            if postID == 0:
                host_post_check = db.session.query(groupPosts.group_post_id, users.u_id, users.u_key, users.u_name, users.u_handle, groupPosts.group_post_cont, groupPosts.date_time, groupPosts.date_time_edited, groupMembers.member_role, groupPosts.reply_count).filter(groupPosts.group_id==groupID).filter(groupPosts.original_post_id==0).filter(groupPosts.post_u_id==users.u_id).filter(groupPosts.group_id==group_check.group_id).filter(groupMembers.member_id==users.u_id).distinct().all()
                hostPostLabels = ['postID','userID','key','userName','userHandle','postContent','timestamp','timestampEdited','memberRole','replyCount']
                result['hostPosts'] = add_labels(hostPostLabels, host_post_check, 'bucket', PROF_BUCKET)
                result['status'] = 'success'
                result['message'] = 'Posts Found'
            else:
                initial_post_check = db.session.query(groupPosts.group_post_id, users.u_id, users.u_key, users.u_name, users.u_handle, groupPosts.group_post_cont, groupPosts.date_time, groupPosts.date_time_edited, groupMembers.member_role, groupPosts.points_count, groupPosts.reply_count, groupPostUpvoted.points, groupPosts.original_post_id).filter(groupPosts.original_post_id==-1).filter(groupPosts.group_post_id == postID).filter(groupPosts.post_u_id==users.u_id).filter(groupPosts.group_id==groupMembers.group_id).filter(groupPosts.post_u_id==groupMembers.member_id).filter(groupPosts.post_u_id==groupPostUpvoted.voter_id).filter(groupPostUpvoted.post_id==groupPosts.group_post_id).first()
                if initial_post_check != []:
                    sub_post_check = db.session.query(groupPosts.group_post_id, users.u_id, users.u_key, users.u_name, users.u_handle, groupPosts.group_post_cont, groupPosts.date_time, groupPosts.date_time_edited, groupMembers.member_role, groupPosts.points_count, groupPosts.reply_count, groupPostUpvoted.points, groupPosts.original_post_id).filter(groupPosts.post_u_id==users.u_id).filter(groupPosts.original_post_id==postID).filter(groupPosts.post_u_id==groupMembers.member_id).filter(groupMembers.group_id==groupPosts.group_id).filter(groupPosts.post_u_id==groupPostUpvoted.voter_id).filter(groupPosts.group_post_id==groupPostUpvoted.post_id).order_by(groupPosts.group_post_id.desc()).distinct().all()
                    labels = ['postID','userID','key','userName','userHandle','postContent','timestamp','timestampedited','memberRole','pointsCount','replyCount','didIVote','cellType']
                    result['status'] = 'success'        
                    if sub_post_check == []:
                        result['message'] = 'No Replies Found'
                    else:
                        result['message'] = 'Replies Found'
                        result['replies'] = add_labels(labels, sub_post_check, 'bucket', PROF_BUCKET)
                        result['parentPost'] = add_labels(labels, initial_post_check, 'bucket', PROF_BUCKET) #cellType = HostPost or GroupPost
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
    result = json.dumps({'status':'error','message':'Invalid request'})
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
                    isPicSet = request.form['isPicSet']
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
            return result
    else:
        return result
    try:
        group_member_check = db.session.query(groupMembers.member_role).filter(groupMembers.group_id==groupDetails.group_id).filter(groupMembers.group_id == groupID).filter(groupMembers.member_id == userID).first()
        if group_member_check != [] and group_member_check.member_role in ('O','A'):
            if action == 'delete' and group_member_check.member_role == 'O':
                group_member_check.group_active = 'N'
            elif action == 'edit':
                if isPicSet == 'yes':
                    result['key']=str(groupID)+'_groupPic'
                else:
                    result['key']='default'
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
    result = json.dumps({'status':'error','message':'Invalid request'})
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
            return result
    else:
        return result
    data_entered = groupEventDetails(group_id=groupID, event_name=eventName, event_description=eventDescription, event_start=eventStart, event_end=eventEnd)
    result={'status':'error','message':'Group already registered'}
    try:
        member_check = db.session.query(groupMembers.member_role).filter(groupMembers.member_id==userID).filter(groupMembers.group_id==groupID).filter(groupMembers.member_status=='M')
        if member_check != [] and member_check.member_role in ('O','H'):
            db.session.add(data_entered)
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
    result = json.dumps({'status':'error','message':'Invalid request'})
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
            return result
    else:
        return result
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
    result = json.dumps({'status':'error','message':'Invalid request'})
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','groupID','eventID')):
            userID = request.form['myID']
            groupID = request.form['groupID']
            eventID = request.form['eventID']
        else:
            return result
    else:
        return result
    try:
        user_check = db.session.query(groupMembers).filter(groupMembers.group_id == groupID).filter(groupMembers.member_id == userID).first()
        if user_check != [] and user_check.member_role == 'M' and user_check.member_status != 'B': #allow others to see?
            event_search = db.session.query(groupEventDetails.event_name, groupEventDetails.event_description, groupEventDetails.event_start, groupEventDetails.event_end, groupEventDetails.attending_count, groupEventDetails.event_post_count, groupEventUsers.event_role).filter(groupEventDetails.event_id==eventID).outerJoin(groupEventUsers, groupEventDetails.event_id==groupEventUsers.event_id, groupEventusers==userID).first()
            result['status']='success'
            if event_search != []:
                label = ['eventName','eventDescription','timestampEventStart','timestampEventEnd','attendingCount','eventPostCount','amIAttending'] 
                result['eventInfo']=add_labels(label, event_search)
                event_post_search = db.session.query(groupEventPosts.group_event_post_id, groupEventPosts.cell_type, groupEventPosts.image_key, groupEventPosts.group_event_post_cont, groupEventPosts.date_time, groupEventPosts.date_time_edited, users.u_id, users.u_key, users.u_name, users.u_handle, groupMembers.member_role, groupEventPosts.points_count, eventPostUpvoted.points).filter(groupEventPosts.group_event_post_u_id == userID).filter(groupEventPosts.event_id==eventID).filter(groupEventPosts.group_id == groupMembers.group_id).filter(groupMembers.member_id == users.u_id).filter(groupEventPosts.group_post_user_id==users.u_id).filter(eventPostUpvoted.voter_id ==users.u_id).filter(eventPostUpvoted.post_id == groupEventPosts.group_event_post_id).distinct().order_by(groupEventPosts.group_event_post_id.desc()).all()
                if event_post_search != []:
                    eventLabel = ['postID','eventCellType','imageKey','postContent','timestamp','timestampEdited','userID','key','userName','userHandle','memberRole','pointsCount','didIVote']
                    result['eventPosts'] = add_labels(eventLabel, event_post_search, 'bucket', PROF_BUCKET, None, 'imageBucket', EVENT_BUCKET) 
                    result['message'] = 'Event found. Event posts found'
                else:
                    result['message'] = 'Event found. Event posts not found'
                    result['eventPosts'] = []
            else:
                result['message'] = 'Event Not Found.'
        else:
            result['message'] = 'Unauthorized'
            result['status'] = 'error'
        db.session.close()        
    except Exception, e:
        result = {'status':'error', 'message':str(e)}
        pass
    data = json.dumps(result)
    return data

@application.route('/getEventList', methods=['POST']) #if group is readable, events show up even to non-members bad Idea?
def getEventList():
    result = json.dumps({'status':'error','message':'Invalid request'})
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','groupID')):
            userID = request.form['myID']
            groupID = request.form['groupID']
        else:
            return result
    else:
        return result    
    try:
        event_check = db.session.query(groupEventDetails.event_id, groupEventDetails.event_name, groupEventDetails.event_description, groupEventDetails.event_start, groupEventDetails.event_end, groupEventUsers.event_role, groupEventDetails.attending_count, groupEventDetails.event_post_count).filter(groupEventDetails.group_id==groupID).outerJoin(groupEventUsers, groupMembers.member_id==groupEventUsers.attendee_id, groupEventDetails.event_id == groupEventUsers.event_id).filter(groupEventUsers.attendee_id==userID).distinct().all()
        if event_check is not None:
            if event_check != []:
                member_check = db.session.query(groupMembers.member_role).filter(groupMembers.member_id==userID).filter(groupMembers.group_id==groupID).filter(groupMembers.member_status=='M').first()
                request['myMemberRole']=member_check.member_role
                label = ['eventID','eventName','eventDescription','timestampEventStart','timestampEventEnd','amIAttending','attendingCount','eventPostCount']
                request['events']= add_labels(label, event_check)
                request['status'] = 'success'
                request['message'] = 'Events Found'
            else:
                request['status'] = 'success'
                request['message'] = 'No events Found'
        db.session.close()        
    except Exception, e:
        result = {'status':'error', 'message':str(e)}
        pass
    data = json.dumps(result)
    return data

@application.route('/sendEventPost', methods=['POST'])
def sendEventPost():
    result = json.dumps({'status':'error','message':'Invalid request'})
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','groupID', 'postContent', 'eventCellType','postID')):
            userID = request.form['myID']
            groupID = request.form['groupID']
            eventID = request.form['eventID']
            cellType = request.form['eventCellType']
            messgCont = request.form['postContent']
        else:
            return result
    else:    
        return result
    data_entered = groupEventPosts(event_id=eventID, group_id=groupID, group_post_u_id=userID, group_event_post_cont=messgCont, cell_type=cellType)
    try:
        member_check = db.session.query(groupMembers.member_status, groupEventUsers.event_role).filter(groupMembers.member_id==userID).filter(groupMembers.group_id==groupID).filter(groupEventUsers.event_id == eventID).filter(groupEventUsers.attendee_id==groupMembers.member_id).filter(groupMembers.member_status == 'M').first()
        if member_check is not None and member_check != []:
            db.session.add(data_entered)
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
                        result['imageKey'] = file_name
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

@application.route('/getGroupMemberList', methods=['POST']) 
def getGroupMemberList():
    result = json.dumps({'status':'error','message':'Invalid request'})
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','groupID')):
            user_id = request.form['myID']
            group_id = request.form['groupID']
            showRequested = request.form['showOnlyRequestList']
        else:
            return result
    else:
        return result
    try:
        member_check = db.session.query(groupMembers.member_status, groupMembers.member_role, groupDetails.group_invite_only).filter(groupMembers.member_id==user_id).filter(groupDetails.group_id==groupMembers.group_id).filter(groupMembers.group_id==group_id).filter(groupMembers.member_status == 'M').first()
        if member_check is not None and member_check != []:
            result['myMemberRole'] = member_check.member_role
            member_search = db.session.query(groupMembers.member_role, users.u_id, users.u_name, users.u_handle, users.u_key, groupMembers.member_message).filter(groupMembers.member_id == users.u_id).filter(groupMembers.group_id == group_id).filter(groupMembers.member_status in ('M','B','S','I')).all()
            members=filter_members(member_search)
            if (member_check.memberRole in ('O','H') or member_check.group_invite_only =='N' or (member_check.group_invite_only == 'M' and member_check.member_role == 'M')) and showRequested=='yes':
                result['receivedRequests']=members['receivedRequests'] #group sent to user
                result['sentRequests']=members['sentRequests'] # user set to group
                result['blocked']=members['blocked']
            elif showRequested == 'no':
                result['members']=members['members']
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

@application.route('/editGroupMemberList', methods=['POST']) 
def editGroupMemberList(): #must be member from member perspective
    result = json.dumps({'status':'error','message':'Invalid request'})
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','groupID','userID','action')):
            myID = request.form['myID']
            groupID = request.form['groupID']
            userID = request.form['userID']
            action = request.form['action']
        else:
            return result
    else:
        return result    
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
    result = json.dumps({'status':'error','message':'Invalid request'})
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
            return result
    else:
        return result
    try:
        group_check=db.session.query(groupDetails.invite_only).filter(groupDetails.group_id == groupID).first()
        if group_check is not None and group_check !=[]: #actions
            if action == 'request':
                if group_check.invite_only == 'N':
                    member_data = groupMembers(group_id=groupID, requester_id=requesterID, member_role='M', member_status='M') 
                else:
                    member_data = groupMembers(group_id=groupID, requester_id=requesterID, member_role='M', member_status='S', member_message=userMessage)
                db.session.add(member_data)     
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
                        return result
                elif request_check.member_status == 'S':
                    if action == 'withdraw':
                        request_check.member_status = 'N'
                        result['status'] = 'success'
                        result['message'] = 'Request withdrawn'
                    else:
                        return result  
            else:
                return result
            db.session.commit()
    except Exception, e:
        db.session.rollback()
        result = {'status':'error', 'message':str(e)}
        pass
    finally:
        db.session.close()
    data = json.dumps(result)
    return data

@application.route('/myInivtableGroupList', methods=['POST'])
def myInvitableGroupList():
    result = json.dumps({'status':'error','message':'Invalid request'})
    if request.method == 'POST':
        if 'myID' in request.form:
            user_id = request.form['myID']
        else:
            return result
    else:
        return result
    try:
        group_list = db.session.query(users.u_id, users.u_name, users.u_handle, users.u_key, groupDetails.group_id, groupDetails.group_name, groupDetails.group_key, groupMembers.member_role, groupMembers.member_status, groupMembers.last_post_seen).filter(users.u_id==user_id).filter(groupMembers.member_id==user_id).filter(groupMembers.group_id==groupDetails.group_id).filter(groupMembers.member_status == 'M').filter(or_(groupDetails.invite_only in ('M','N'), groupMembers.member_role in ('H','O'))).distinct().all()
        db.session.close()
        result['status']='success'
        if group_list != []:
            result['message']='Groups Found'
            groups = filter_groups(group_list)        
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
    result = json.dumps({'status':'error','message':'Invalid request'})
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','eventID','groupID','action')):
            userID = request.form['myID']
            groupID = request.form['groupID']
            eventID = request.form['eventID']
            action = request.form['action'] #joinEvent, leaveEvent, getUsers
        else:
            return result
    else:
        return result
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
            elif action == 'leaveEvent':
                event_check = db.session.query(groupEventUsers.attendee_id, groupEventUsers.event_role).filter(groupEventUsers.event_id == eventID).filter(groupEventUsers.attendee_id == userID).first()
                event_check.event_role = 'N'
            elif action =='getUsers': #attendee list???
                event_member_search = db.session.query(users.u_name, users.u_handle, users.u_key).filter(groupEventUsers.event_id==eventID).filter(groupEventUsers.attendee_id==users.u_id).filter(groupMembers.member_id==users.u_id).filter(groupMembers.member_id==userID).filter(groupMembers.member_status=='M').all()
                label = ['userName','userHandle','key']
                result['users'] = add_labels(label,event_member_search,'bucket',PROF_BUCKET)
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

@application.route('/retrievePoint', methods=['POST'])
def retrievePoint():
    result = json.dumps({'status':'error','message':'Invalid request'})
    if request.method == 'POST':
        if 'myID' in request.form: 
            userID = request.form['myID']
        else:
            return result
    else:
        return result
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
            result['weeklyPoints'] = userProf_check.stipend_points
            result['myPoints'] = userProf_check.personal_points
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
    result = json.dumps({'status':'error','message':'Invalid request'})
    if request.method == 'POST':
        if all (k in request.form for k in ('myID','postType', 'postID','amount')):
            userID = request.form['myID']
            postID = request.form['postID']
            postType = request.form['postType']
            numPoints = request.form['amount']
        else:
            return result
    else:    
        return result
    try: #add to sent points upvoted table
        user_check = db.session.query(users.u_personal_points, users.u_stipend_points).filter(users.u_id==userID).first()
        if postType == 'forum':
            post_check = db.session.query(forumPosts.points_count, users.u_personal_points).filter(forumPosts.post_id == postID).filter(users.u_id==forumPosts.post_u_id).first()
            if post_check is not None and post_check != []:
                if user_check.u_stipend_points >= numPoints:
                    user_check.u_stipend_points -= numPoints
                    post_check.points_count += numPoints
                    post_check.u_personal_points += numPoints
                    result['status'] = 'success'
                    result['message'] = 'Points added'  
                elif user_check.u_stipend_points + user_check.u_personal_points >= numPoints:
                    user_check.u_personal_points = user_check.u_personal_points - numPoints + user_check.u_stipend_points
                    user_check.u_stipend_points = 0
                    post_check.points_count += numPoints
                    post_check.u_personal_points += numPoints
                    result['status'] = 'success'
                    result['message'] = 'Points added'
                else:
                    result['status'] = 'error'
                    result['message'] = 'Points not added'
            else:
                result['status'] = 'error'
                result['message'] = 'Points not added'
        elif postType == 'group':
            post_check = db.session.query(groupPosts.points_count, users.u_personal_points,groupPosts.group_id).filter(groupPosts.group_post_id == postID).filter(groupPosts.post_u_id==users.u_id).filter(groupMembers.group_id==groupPosts.group_id).filter(groupMembers.member_id==users.u_id).filter(groupMembers.member_status=='M').first()
            if post_check is not None and post_check !=[]:
                member_check = db.session.query(groupMembers.member_status).filter(groupMembers.group_id==post_check.group_id).filter(groupMembers.member_id==userID).first()
                if member_check is not None and member_check.member_status=='M':
                    if user_check.u_stipend_points >= numPoints:
                        user_check.u_stipend_points -= numPoints
                        post_check.points_count += numPoints
                        post_check.u_personal_points += numPoints
                        result['status'] = 'success'
                        result['message'] = 'Points added'  
                    elif user_check.u_stipend_points + user_check.u_personal_points >= numPoints:
                        user_check.u_personal_points = user_check.u_personal_points - numPoints + user_check.u_stipend_points
                        user_check.u_stipend_points = 0
                        post_check.points_count += numPoints
                        post_check.u_personal_points += numPoints
                        result['status'] = 'success'
                        result['message'] = 'Points added'
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
            if post_check is not None and post_check !=[]:
                member_check = db.session.query(groupMembers.member_status).filter(groupMembers.group_id==post_check.group_id).filter(groupMembers.member_id==userID).first()
                if member_check is not None and member_check.member_status=='M':
                    if user_check.stipend_points >= numPoints:
                        user_check.u_stipend_points -= numPoints
                        post_check.points_count += numPoints
                        post_check.u_personal_points += numPoints
                        result['status'] = 'success'
                        result['message'] = 'Points added'  
                    elif user_check.stipend_points + user_check.u_personal_points >= numPoints:
                        user_check.u_personal_points = user_check.u_personal_points - numPoints + user_check.u_stipend_points
                        user_check.u_stipend_points = 0
                        post_check.points_count += numPoints
                        post_check.u_personal_points += numPoints
                        result['status'] = 'success'
                        result['message'] = 'Points added'
                    else:
                        result['status'] = 'error'
                        result['message'] = 'Points not added'
                else:
                    result['status'] = 'error'
                    result['message'] = 'Points not added'
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
    return json.dumps(result)
            
@application.route('/editPost', methods=['POST'])
def editPost():
    result = json.dumps({'status':'error','message':'Invalid request'})
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
            else:
                return json.dumps(result)
        else:
            return json.dumps(result)
    else:    
        return json.dumps(result)
    try:
        #user_check = db.session.query(users.personal_points, users.stipend_points).filter(users.u_id==user_id).first()
        if postType == 'forum':
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
                        post_check.group_post_cont = new_contents
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
        
        


'''
#functions...private?        

@application.route('/attendeeList', methods=['GET','POST'])
def attendeeList():
    result = json.dumps({'status':'error','message':'Invalid request'})
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
def filter_groups(group_list, new_host_posts=None, new_posts=None, new_events=None):
    currentGroups=[]
    sentRequests=[]
    receivedInvites=[]
    for g in group_list:
        if g.member_status == "M":
            if new_host_posts is not None and new_posts is not None and new_events is not None:
                currentGroups.append([g.group_id, g.group_name, g.group_key, g.handle, g.member_role, new_host_posts[g.group_id],new_posts[g.group_id],new_events[g.group_id]]) #neweventreplies
            else:
                currentGroups.append([g.group_id, g.group_name, g.group_key, g.handle])
        elif g.member_status == 'S':
            sentRequests.append([g.group_id, g.group_name, g.group_key, g.handle])
        elif g.member_status == 'I':
            receivedInvites.append([g.group_id, g.group_name, g.group_key,g.handle])
    label = ['groupID','groupName','groupKey','groupHandle']
    if new_events is not None:
        current_label =  ['groupID','groupName','groupKey','groupHandle','memberRole','newHostPostsCount','newPostsCount','newEventsCount']
    else:
        current_label = label
    add_all = 'groupBucket'
    labelCurrentGroups = add_labels(current_label, currentGroups, add_all, GROUP_BUCKET)
    labelSentRequests = add_labels(label, sentRequests, add_all, GROUP_BUCKET)
    labelReceivedInvites = add_labels(label, receivedInvites, add_all, GROUP_BUCKET)
    return {'currentGroups':labelCurrentGroups,'sentRequests':labelSentRequests,'receivedRequests':labelReceivedInvites}

def filter_friends(friend_list):
    sentRequests=[]
    receivedRequests=[]
    currentFriends=[]
    for f in friend_list:
        if f.friend_status == 'F':
            currentFriends.append([f.u_id,f.u_name,f.u_handle, f.last_chat, str(f.u_id)+'_userProfPic'])
        elif f.requested(f.u_id):
            sentRequests.append([f.u_id,f.u_name, f.u_handle, str(f.u_id)+'_userProfPic'])
        elif not f.requested(f.u_id):
            receivedRequests.append([f.u_id,f.u_name, f.u_handle, str(f.u_id)+'_userProfPic'])
    currentLabel=['userID','userName','userHandle','lastChatMessage','key']
    label=['userID','userName','userHandle','key']
    add_all='bucket'
    labelCurrentFriends = add_labels(currentLabel,currentFriends, add_all, PROF_BUCKET) 
    labelSentRequests = add_labels(label,sentRequests, add_all, PROF_BUCKET, True)
    labelReceivedRequests = add_labels(label,receivedRequests, add_all, PROF_BUCKET)
    return {'currentFriends':labelCurrentFriends,'sentRequests':labelSentRequests,'receivedRequests':labelReceivedRequests}

def filter_members(member_list):
    sentRequests=[]
    receivedRequests=[]
    currentMembers=[]
    blocked=[]
    for m in member_list:
        if m.member_status == 'M':
            currentMembers.append([m.member_role, m.u_id, m.u_name, m.u_handle, str(m.u_id)+'_userProfPic'])
        elif m.member_status == 'S': #request from user to group
            receivedRequests.append([m.u_id, m.u_name, m.u_handle, m.member_message, str(m.u_id)+'_userProfPic'])
        elif m.member_status == 'I': #request from group to user
            sentRequests.append([m.u_id, m.u_name, m.u_handle, m.member_message, str(m.u_id)+'_userProfPic'])
        elif m.member_status == 'B':
            blocked.append([m.u_id, m.u_name, m.u_handle, m.member_message, str(m.u_id)+'_userProfPic'])
    currentLabel=['memberRole','userID','userName','userHandle','key']
    label=['userID','userName','userHandle','userMessage','key']
    add_all='bucket'
    labelCurrentMembers = add_labels(currentLabel, currentMembers, add_all, PROF_BUCKET)
    labelSentRequests = add_labels(label, sentRequests, add_all, PROF_BUCKET)
    labelReceivedRequests = add_labels(label, receivedRequests, add_all, PROF_BUCKET)
    labelBlocked = add_labels(label, blocked, add_all, PROF_BUCKET)
    return {'members':labelCurrentMembers, 'sentRequests':labelSentRequests, 'receivedRequests':labelReceivedRequests,'blocked':labelBlocked}

def add_labels(labels, list_to_add, add_all_label=None, add_all=None, first_initial = False, add_all_label_2=None, add_all_2=None):
    temp=[]
    for k in list_to_add:
        k_temp={}
        for j,x in zip(k, labels):
            if 'timestamp' in x:
                k_temp[x]=json_serial(j)
            elif 'didIVote' in x:
                if j is not None:
                    k_temp[x] = 'no'
                else:
                    k_temp[x] = 'yes'
            elif first_initial and x =='userName':
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
                    k_temp[X] = 'yes'
            else:
                k_temp[x]=j
        if (add_all is not None):
            k_temp[add_all_label]=add_all_2
        if (add_all_2 is not None):
            k_temp[add_all_label_2]=add_all_2
    temp.append(k_temp)
    return temp
    
def getMinMaxLongLat(my_long, my_lat, dist):
    #364173 feet * cos(long) = 1 degree of long
    #dist in miles
    delta = (dist * Decimal(5280)) / Decimal(364173 * cos(my_long))
    minLong = my_long - delta
    maxLong = my_long + delta
    maxLat = my_lat + (dist * Decimal(0.01447315953478432289213674551561))
    minLat = my_lat - (dist * Decimal(0.01447315953478432289213674551561))
    return minLong, maxLong, minLat, maxLat

def hash_password(password):
    pwhash = bcrypt.hashpw(password, bcrypt.gensalt())
    return pwhash

def json_serial(obj):
    if isinstance(obj, datetime):
        serial = obj.isoformat()
        return serial
    raise TypeError ("Type not serializable")

def first_and_initial(name):
    first, space, last = name.partition(" ")
    return first + space + last[0]

if __name__ == '__main__':
    application.run(host='0.0.0.0')
    
