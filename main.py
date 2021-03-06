import os
from praw import Reddit
from praw.models import Submission, Subreddit, Comment
from dotenv import load_dotenv
from stellar_sdk import Keypair, Asset, exceptions
import logging
import sqlite3
import mysql.connector
import sys  

"""
logging.basicConfig(filename='app.log', filemode='w', format='%(name)s - %(levelname)s - %(message)s')
logging.getLogger().addHandler(logging.StreamHandler())
logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))
"""

load_dotenv()
#  Reddit
CLIENT = os.getenv("CLIENT_ID")
SECRET = os.getenv("CLIENT_SECRET")
USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")

# MariaDB
USE_SQLITE3 = os.getenv("USE_SQLITE3")
MARIA_DB_HOST = os.getenv("MARIA_DB_HOST")
MARIA_DB_USER = os.getenv("MARIA_DB_USER")
MARIA_DB_PASSWORD = os.getenv("MARIA_DB_PASSWORD")
MARIA_DB_PORT = os.getenv("MARIA_DB_PORT")
MARIA_DB_DATABASE = os.getenv("MARIA_DB_DATABASE")

# Website
SIGNING_URL = os.getenv("SIGNING_URL")

if USE_SQLITE3 == "True":
    conn = sqlite3.connect('accounts.db')
else:
    try:
        conn = mysql.connector.connect(
            user=MARIA_DB_USER,
            password=MARIA_DB_PASSWORD,
            host=MARIA_DB_HOST,
            port=int(MARIA_DB_PORT),
            database=MARIA_DB_DATABASE
        )

    except Exception as e:
        print(f"Error connecting to Mysql Database: {e}")
        sys.exit(1)

c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS accounts (id INTEGER AUTO_INCREMENT PRIMARY KEY, username text, account text)''')
c.execute('''CREATE TABLE IF NOT EXISTS to_notify (id INTEGER AUTO_INCREMENT PRIMARY KEY, person_to_be_notified text, persons_account text, amount int, asset_name text, asset_issuer text)''')
conn.commit()

# Create the reddit object instance using Praw
reddit = Reddit(
    user_agent="Stellar Tip Bot v0.0.1",
    client_id=CLIENT,
    client_secret=SECRET,
    username=USERNAME,
    password=PASSWORD,
)

def statementForDB(statement):
    if USE_SQLITE3 == "False":
        return statement.replace('?', '%s')
    return statement

def create_account(username, public_key):
    # Check if Valid key
    try:
        Keypair.from_public_key(public_key)
    except exceptions.Ed25519PublicKeyInvalidError:
        return "The provided Public Key is invalid!"

    # Create Account or replace
    try:
        statement = "REPLACE INTO accounts (username, account) VALUES(?,?)"
        c.execute(statementForDB(statement), (str(username), str(public_key)))
        conn.commit()
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return f"There was an error creating your account: {str(e)}"

    # Check if user was wanted
    try: 
        statement = "SELECT person_to_be_notified, amount, id from to_notify WHERE persons_account=?"
        c.execute(statementForDB(statement), (str(username), ))
        rows = c.fetchall()
    except Exception as e:
        print(f"ERROR: {str(e)}")

    # Notify everyone else
    if rows is []:
        pass
    else:
        for row in rows:
            try:
                reddit.redditor(row[0]).message(f'{username} opened an account!', f'The person in the subject setup their Stellar Wallet! Visit the following url to proceed with tipping: {SIGNING_URL}/payment?user={username}&amount={row[1]}.')
                statement = "DELETE FROM to_notify WHERE id=?"
                c.execute(statementForDB(statement), (int(row[2]), ))
                conn.commit()
            except Exception as e:
                print(f"Error deleting from table: {str(e)}")

    return "Account has been succesfully created!"

def payment(user, amount, original_poster, asset_code=None, asset_issuer=None):
    # Check if User Exists
    user = user.replace('/u/', '').replace('u/', '').replace('/U/', '')
    try:
        statement = "SELECT account from accounts WHERE username=?"
        c.execute(statementForDB(statement), (str(user), ))
        public_key = c.fetchone()
    except Exception as e:
        print(f"ERROR with Payment: {str(e)}")
        return f"There was an error finding the account for the recepient: {str(e)}"

    # Check if it's custom asset
    if asset_code == None and asset_issuer == None:
        asset_name = "XLM"
    else:
        try:
            asset = Asset(asset_code, asset_issuer)
            asset_name = asset_code
        except Exception as e:
            return f"There was an error processing the custom asset: {str(e)}"

    if public_key is None:
        # Inform user
        reddit.redditor(user).message(f'{original_poster} wants to tip you!', f'Hey there! The user in the subject wants to tip you {amount} {asset_name}. In order to accept the tip create an account by replying to this message with: `setaddress [ADDRESS]` where `[ADDRESS]` is the Stellar Wallet where you want to receive the tip.')
        
        # Add user for later notification
        try:
            statement = "INSERT INTO to_notify (person_to_be_notified, persons_account, amount, asset_name, asset_issuer) VALUES(?,?,?,?,?)"
            c.execute(statementForDB(statement), (str(original_poster), str(user), int(amount), str(asset_name), str(asset_issuer)))
            conn.commit()
        except Exception as e:
            print(f"ERROR with Payment: {str(e)}")
        return "The user does not have a Stellar Account setten up with me. They have been notified you want to tip them."
    else:
        if asset_name == "XLM":
            url = f"{SIGNING_URL}/payment?user={user}&amount={amount}"
        else:
            url = f"{SIGNING_URL}/create-claimable-balance?user={user}&amount={amount}&asset_name={asset_name}&asset_issuer={asset_issuer}"
        return f"Hi there! In order to tip the following person visit the following page: {url}"
    

def main():
    print('Started!')
    try:
        # Parse messages that it receives
        for mention in reddit.inbox.stream():
            if mention.new:
                mention.mark_read()
                print(f"{mention.author} - {mention.body}")

                # Parse commands
                message = mention.body.split(' ')
                if 'tipbot_stellar' in message[0]:
                    message.pop(0)
                command = message[0].lower()
                arguments = message [1::]

                print(command)

                if command == "help":
                    mention.reply("""
                    Hello! This are the commands I currently support:
                    `help` <- You ran this! ????

                    `tip [USER] [AMOUNT]` <- Pay a certain reddit user `[AMOUNT]` XLM

                    `tip [USER] [AMOUNT] [ASSET_NAME] [ASSET_ISSUER]` <- Creates a Claimable balance for a certain asset to a user

                    `setAddress [STELLAR_ADDRESS]` <- Set your Stellar Public Key so others can tip you.

                    The bot uses [Albedo](https://albedo.link/) for signing transactions so make sure you have it installed.
                    """)
                    continue
                if command == "tip":
                    if len(arguments) == 4:
                        message = payment(arguments[0], arguments[1], mention.author, arguments[2], arguments[3])
                    elif len(arguments) == 2:
                        message = payment(arguments[0], arguments[1], mention.author)
                    else:
                        message = 'Invalid number of arguments'
                    mention.reply(message)
                    continue
                if command == "setaddress":
                    message = create_account(mention.author, arguments[0])
                    print(message)
                    mention.reply(message)
                    continue
                else:
                    mention.reply("The command you wrote does not exist. Try replying with `help`")
    except Exception as e:
        print(str(e))


if __name__ == '__main__':
    main()
