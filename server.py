from flask import Flask, render_template, request, g
from dotenv import load_dotenv
from praw import Reddit
from stellar_sdk import Server, Asset, TransactionBuilder, Network
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

SIGNING_URL = os.getenv("SIGNING_URL")
NETWORK = os.getenv("NETWORK")

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

def getAccount(user):
    c = get_db().cursor()
    statement = "SELECT account from accounts WHERE username=?"

    if USE_SQLITE3 == "False":
        statement = statement.replace('?', '%s')

    c.execute(statement, (str(user), ))
    rows = c.fetchone()
    return rows

def getAssets(public_key: str) -> list:
    """
    Get all the balances an account has.
    """
    balances = server.accounts().account_id(public_key).call()['balances']
    balances_to_return = [ {"asset_code": elem.get("asset_code"), "issuer": elem.get("asset_issuer"), "balance": elem.get("balance")} for elem in balances ]
    balances_to_return[-1]["asset_code"] = "XLM"
    return balances_to_return

def verifyItExists(asset: str, available_assets: list) -> bool:
    """
    Check if in the balances of the account an asset like that alredy exists to establish a trustline
    """
    asset_name = asset.split(':')[0]
    asset_issuer = asset.split(':')[1]
    for elem in available_assets:
        if elem["asset_code"] == asset_name and elem["asset_issuer"] == asset_issuer:
            return True
    return False

def generateTransaction(balance, balances, id):
    # Check if asset is trusted
    print(balances)
    establish_trustline = verifyItExists(balance.get('asset'), balances)
    print(balance)

    if NETWORK == "TESTNET":
        passphrase = Network.TESTNET_NETWORK_PASSPHRASE
    else:
        passphrase = Network.PUBLIC_NETWORK_PASSPHRASE

    account = server.load_account(balance['claimants'][0]['destination'])
    base_fee = server.fetch_base_fee()
    if establish_trustline:
        transaction = TransactionBuilder(
            source_account=account,
            network_passphrase=passphrase
        ).append_claim_claimable_balance_op(
            balance_id=id,
        ).build()
    else:
        asset = Asset(asset_name, asset_issuer)
        transaction = TransactionBuilder(
            source_account=account,
            network_passphrase=passphrase
        ).append_change_trust_op(
            asset_code=asset, 
            asset_issuer=asset_issuer
        ).append_claim_claimable_balance_op(
            balance_id=id,
            source=user_pub_key
        ).build()

    print(transaction.to_xdr())
    return transaction.to_xdr()
    



@app.route('/claim-claimable-balance', methods=['GET', 'POST'])
def claim_claimable_balances():
    id = request.args.get('id')

    # Retrieve Claimable Balance
    try:
        balance = server.claimable_balances().claimable_balance(id).call()
    except Exception as e:
        return str(e)


    # Retrieve Balance
    try:
        balances = server.accounts().account_id(balance['claimants'][0]['destination']).order(desc=False).call()['balances']
    except Exception as e:
        return str(e)

    xdr = generateTransaction(balance, balances, id)

    return render_template("claim_balance.html", xdr=xdr, asset_name=balance.get('asset').split(':')[0], amount=round(float(balance.get('amount'))))
    


@app.route('/create-claimable-balance', methods=['GET', 'POST'])
def claimable_balances():
    user = request.args.get('user')
    amount = request.args.get('amount')
    asset_name = request.args.get('asset_name')
    asset_issuer = request.args.get('asset_issuer')

    rows = getAccount(user)

    if rows == None:
        return "404, not found"

    if request.method == 'POST':
        data = request.form
        transaction = data["signed_envelope_xdr"]
        submitters_public_key = data["pubkey"]
        print(data)
        try:
            response = server.submit_transaction(transaction)
            data = server.claimable_balances().for_claimant(rows[0]).for_sponsor(submitters_public_key).call()['_embedded']['records'][0]['id']
            reddit.redditor(user).message("You have been tipped!",f"A user has tipped you {amount} {asset_name}! You can view the transaction at the following url: https://stellar.expert/explorer/testnet/tx/{response['id']} .In order to claim the fund visit the following url: {SIGNING_URL}/claim-claimable-balance?id={data} ")
            return "Success!"
        except Exception as e:
            return str(e)

    else:
        try:
            asset = Asset(asset_name, asset_issuer)
        except Exception as e:
            return str(e)

    return render_template("claimable_balance.html", amount=amount, public_key=rows[0], username=user, asset_name=asset_name, asset_issuer=asset_issuer, horizon_url=HORIZON_URL)



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
        rows = getAccount(user)

        if rows == None:
            return "404, not found"

    return render_template("payment.html", amount=amount, public_key=rows[0], username=user)