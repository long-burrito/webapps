from google_auth_oauthlib.flow import Flow
from flask import Flask, send_from_directory, render_template, request, session, redirect, url_for, make_response, jsonify, abort
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import requests
from google.oauth2 import id_token
import os
import google.auth.transport.requests
from pip._vendor import cachecontrol
import yfinance as yf
from decimal import Decimal
import cv2
import csv
app = Flask(__name__)
app.secret_key = b'\x829a\x89g\xddl\xe1\xc6\x8e\xa0~\x1fAz\x1a\xbb\xeb\xb6\xd5\xc9\x94d\x16'
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1" #REMOVE THIS WHEN YOU DEPLOY

GOOGLE_CLIENT_ID = "897888035020-2vdd9g62ncv72be90lmut7oa6hgds1sp.apps.googleusercontent.com"
GOOGLE_CLIENT_ID2 = "897888035020-6g5i0otamnsulni820jvstvdocvrcqud.apps.googleusercontent.com"
cred = credentials.Certificate(r"C:\Users\Rene Ramirez\Desktop\Web Apps\ToDo_List\final\creds.json")
firebase_admin.initialize_app(cred)
db = firestore.client()
user_id = ""

flow2 = Flow.from_client_secrets_file(
	client_secrets_file=r"C:\Users\Rene Ramirez\Desktop\Web Apps\ToDo_List\final\oauth2.json",
	scopes=["https://www.googleapis.com/auth/userinfo.profile", "https://www.googleapis.com/auth/userinfo.email", "openid"],
	redirect_uri="http://localhost:80/final/callback" #FIX THIS WHEN YOU DEPLOY http://localhost:80
	)

def login_is_required(function):  #a function to check if the user is authorized or not
    def wrapper(*args, **kwargs):
        if "sub" not in session:  #authorization required
            return redirect("/loginpage")
        else:
            return function()

@app.route('/')
def default():
    return send_from_directory(directory=app.static_folder, path='index.html')

@app.route('/user_info')
def user_info():
    out=f"<p>ip:{request.remote_addr}</p>"
    for key,value in request.headers:
        out+=f"<p>{key}:{value}</p>"
    return out

@app.route('/api/user/<user_id>')
def get_user_data(user_id):
    users_ref = db.collection('users2')
    user_doc = users_ref.document(user_id).get()

    if user_doc.exists:
        return jsonify(user_doc.to_dict())
    else:
        return jsonify({"error": "User not found"}), 404

@app.route('/final')
def thefinal():
    return render_template("final.html",session=session,user_id=user_id)

@app.route("/final/callback")  #this is the page that will handle the callback process meaning process after the authorization
def finalcallback():
    flow2.fetch_token(authorization_response=request.url)

    if not session["state"] == request.args["state"]:
        abort(500)  #state does not match!

    credentials = flow2.credentials
    request_session = requests.session()
    cached_session = cachecontrol.CacheControl(request_session)
    token_request = google.auth.transport.requests.Request(session=cached_session)

    id_info = id_token.verify_oauth2_token(
        id_token=credentials._id_token,
        request=token_request,
        audience=GOOGLE_CLIENT_ID2
    )
    global user_id

    user_id = id_info.get('sub')
    if user_id:
        users_ref = db.collection('users2')
        user_doc = users_ref.document(user_id)
        # Retrieve the document
        doc = user_doc.get()
        if not doc.exists:  # Check if the document does not exist
            # Create or update the document with the specified fields
            user_doc.set({
                "money": 500,
                "ticks": {
                    "gme": 10,
                    "aapl": 10,
                }
            }, merge=True)

    session.update(id_info)  # Update session with the user's information

    return redirect("/final")

@app.route("/final/login")  #the page where the user can login
def finallogin():
    authorization_url, state = flow2.authorization_url()  #asking the flow class for the authorization (login) url
    session["state"] = state
    return redirect(authorization_url)

@app.route("/final/logout")  #the page where the user can login
def finallogout():
    session.clear()
    return redirect("/final")
#hop on vc

@app.route("/final/get_stocks/<ticker>")
def get_stocks(ticker):
    stock = yf.Ticker(ticker)
    current_price = stock.history(period='1d')['Close'][0]
    all_info = stock.info
    return jsonify(all_info)

@app.route("/final/my_stocks")
def get_the_stocks():
    return render_template('stocks.html', user_id=user_id)

@app.route("/final/tickers")
def tickers():
    return render_template("tickers.html")



@app.route('/final/purchase', methods=['POST'])
def handle_purchase():
    data = request.json
    ticker = data['ticker']
    shares = int(data['shares'])
    total_cost = Decimal(str(data['totalCost']))
    user_id = data['user_id']  # Assuming user_id is sent in the request

    # Reference to the user's document
    user_doc_ref = db.collection('users2').document(user_id)

    # Fetch the user's document
    user_doc = user_doc_ref.get()
    if user_doc.exists:
        user_data = user_doc.to_dict()
        current_money = Decimal(str(user_data.get('money', 0)))
        ticks = user_data.get('ticks', {})

        if current_money >= total_cost:
            # Deduct the total cost from user's money
            new_money = current_money - total_cost

            # Update the ticker's share count in the 'ticks' dictionary
            ticks[ticker] = ticks.get(ticker, 0) + shares

            # Update the user's document with new money and ticks values
            user_doc_ref.update({
                'money': float(new_money),
                'ticks': ticks
            })

            return jsonify({'status': 'success', 'message': 'Purchase completed'})
        else:
            return jsonify({'status': 'failed', 'message': 'Insufficient funds'}), 400
    else:
        return jsonify({'status': 'failed', 'message': 'User not found'}), 404

@app.route('/final/sell', methods=['POST'])
def handle_sell():
    data = request.json
    shares_to_sell = int(data['shares'])
    user_id = data['user_id']  # Assuming user_id is sent in the request
    ticker = data['ticker']  # Ensuring ticker symbol is in upper case for consistency
    amount = float(data['money'])

    # Reference to the user's document
    user_doc_ref = db.collection('users2').document(user_id)

    # Fetch the user's document
    user_doc = user_doc_ref.get()
    if user_doc.exists:
        user_data = user_doc.to_dict()
        current_money = float(str(user_data.get('money', 0)))
        ticks = user_data.get('ticks', {})

        if ticker not in ticks or ticks[ticker] < shares_to_sell:
            return jsonify({'status': 'failed', 'message': 'Not enough shares to sell'}), 400

        # If sufficient shares are available, proceed with selling
        new_money = current_money + amount
        ticks[ticker] -= shares_to_sell
        if ticks[ticker] == 0:
            del ticks[ticker]  # Remove ticker from the dictionary if the share count goes to zero

        user_doc_ref.update({
            'money': float(new_money),
            'ticks': ticks
        })

        return jsonify({'status': 'success', 'message': 'Sale completed'})
    else: 
        return jsonify({'status': 'failed', 'message': 'User not found'}), 404


@app.route('/final/upload_csv', methods=['POST'])
def upload_csv():
    # Check if the request has a file in the 'csvFile' field
    if 'csvFile' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    csv_file = request.files['csvFile']
    
    # Check if no file is selected
    if csv_file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    try:
        # Assuming you want to save the CSV data to a Firestore collection called 'tickersdb'
        tickers_ref = db.collection('tickersdb')  # Firestore collection reference

        # Read the CSV data
        csv_data = csv_file.read().decode('utf-8').splitlines()
        csv_reader = csv.DictReader(csv_data)
        
        # Iterate through the CSV rows and upload each row as a separate document in Firestore
        for idx, row in enumerate(csv_reader, start=2):
            # Prepare data for Firestore document
            firestore_data = {
                'symbol': row['symbol'],
                'name': row['name'],
                'exchange': row['exchange'],
                'assetType': row['assetType'],
                'ipoDate': row['ipoDate'],
                'delistingDate': row['delistingDate'],
                'status': row['status']
            }

            # Set the Firestore document in the 'tickersdb' collection
            document_name = row['symbol']  # Use the 'symbol' field as the document name
            print(f"Document Name: {document_name}")
            tickers_ref.document(document_name).set(firestore_data)
        return jsonify({'status': 'success', 'message': 'CSV data uploaded to Firestore'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

app.run(debug=True,host="0.0.0.0",port=80) 