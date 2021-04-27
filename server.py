from flask import Flask, render_template, request, g
from dotenv import load_dotenv
from praw import Reddit
from stellar_sdk import Server
import sqlite3
import mysql.connector
import os

app = Flask(__name__)


DATABASE = 'accounts.db'

load_dotenv()
CLIENT = os.getenv("CLIENT_ID")
SECRET = os.getenv("CLIENT_SECRET")
USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")

reddit = Reddit(
    user_agent="Stellar Tip Bot v0.0.1",
    client_id=CLIENT,
    client_secret=SECRET,
    username=USERNAME,
    password=PASSWORD,
)

HORIZON_URL = os.getenv("HORIZON_URL")
server = Server(HORIZON_URL)

USE_SQLITE3 = os.getenv("USE_SQLITE3")
MARIA_DB_HOST = os.getenv("MARIA_DB_HOST")
MARIA_DB_USER = os.getenv("MARIA_DB_USER")
MARIA_DB_PASSWORD = os.getenv("MARIA_DB_PASSWORD")
MARIA_DB_PORT = os.getenv("MARIA_DB_PORT")
MARIA_DB_DATABASE = os.getenv("MARIA_DB_DATABASE")

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        if USE_SQLITE3 == "True":
            db = g._database = sqlite3.connect(DATABASE)
        else:
            db = g._database = mysql.connector.connect(
            user=MARIA_DB_USER,
            password=MARIA_DB_PASSWORD,
            host=MARIA_DB_HOST,
            port=int(MARIA_DB_PORT),
            database=MARIA_DB_DATABASE
        )
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

@app.route('/payment', methods=['GET', 'POST'])
def payment():
    user = request.args.get('user')
    amount = request.args.get('amount')

    if request.method == 'POST':
        data = request.form
        transaction = data["signed_envelope_xdr"]

        try:
            response = server.submit_transaction(transaction)
            reddit.redditor(user).message("You have been tipped!",f"A user has tipped you {amount} XLM! You can view the transaction at the following url: https://stellar.expert/explorer/testnet/tx/{response['id']}")
            return "Success!"
        except Exception as e:
            return str(e)



    else:
        c = get_db().cursor()
        statement = "SELECT account from accounts WHERE username=?"
        
        if USE_SQLITE3 == "False":
            statement = statement.replace('?', '%s')

        c.execute(statement, (str(user), ))
        rows = cursor.fetchone()

        if rows == None:
            return "404, not found"

    return render_template("payment.html", amount=amount, public_key=rows[0], username=user)