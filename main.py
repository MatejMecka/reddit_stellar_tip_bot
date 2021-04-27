import os
from praw import Reddit
from praw.models import Submission, Subreddit, Comment
from dotenv import load_dotenv
from stellar_sdk import Keypair, exceptions
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
c.execute('''CREATE TABLE IF NOT EXISTS to_notify (id INTEGER AUTO_INCREMENT PRIMARY KEY, person_to_be_notified text, persons_account text)''')
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
        return "Account has been succesfully created!"
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return f"There was an error creating your account: {str(e)}"

    # Check if user was wanted
    try: 
        statement = "SELECT person_to_be_notified from to_notify WHERE persons_account=?"
        c.execute(statementForDB(statement), (str(user), ))
        rows = c.fetchone()
    except Exception as e:
        print(f"ERROR: {str(e)}")

    if rows is None:
        pass
    else:
        reddit.redditor(user).message(f'{rows[0]} opened an account!', f'The person in the subject setup their Stellar Wallet! You can now reissue the same command.')


def payment(amount, user, original_poster):
    # Check if User Exists
    user = user.replace('/u/', '').replace('u/', '').replace('/U/', '')
    try:
        statement = "SELECT account from accounts WHERE username=?"
        c.execute(statementForDB(statement), (str(user), ))
        public_key = c.fetchone()
    except Exception as e:
        print(f"ERROR with Payment: {str(e)}")
        return f"There was an error finding the account for the recepient: {str(e)}"

    if public_key is None:
        # Inform user
        reddit.redditor(user).message(f'{original_poster} wants to tip you!', f'Hey there! The user in the subject wants to tip you {amount} XLM. In order to accept the tip create an account using `setaddress [ADDRESS]`')
        
        # Add user for later notification
        try:
            statement = "REPLACE INTO to_notify (person_to_be_notified, persons_account) VALUES(?,?)"
            c.execute(statementForDB(statement), (str(original_poster), str(user)))
            conn.commit()
        except Exception as e:
                print(f"ERROR with Payment: {str(e)}")
        return "The user does not have a Stellar Account setten up with me. They have been notified you want to tip them."
    else:
        return f"Hi there! In order to tip the following person visit the following page: {SIGNING_URL}/payment?user={user}&amount={amount}"
    

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
                        Hello! This are the commands I currently support
                        `help` <- You ran this! 😎

                        `tip [AMOUNT] [USER]` <- Pay a certain reddit user `[AMOUNT]` XLM

                        `tip [AMOUNT] [ASSET_NAME] [ASSET_ISSUER] [USER]` <- Creates a Claimable balance for a certain asset to a user

                        `setAddress [STELLAR_ADDRESS]` <- Set your Stellar Public Key so others can tip you.

                        The bot uses [Albedo](https://albedo.link/) for signing transactions so make sure you have it installed.
                    """)
                    continue
                if command == "tip":
                    if len(arguments) == 4:
                        pass
                    else:
                        message = payment(arguments[0], arguments[1], mention.author)
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
