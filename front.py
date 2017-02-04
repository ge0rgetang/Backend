from flask import Blueprint, render_template

front_test = Blueprint('front', __name__)

@front_test.route('/', methods=['POST','GET'])
@front_test.route('/home', methods=['POST','GET'])
def front():
    return render_template("index.html")

@front_test.route('/FBAppLink', methods=['POST','GET'])
def FBAppLink():
    return render_template("FBAppLink.html")

@front_test.route('/job/appTester', methods=['POST','GET'])
def appTester():
    return render_template("submissionForm.html")