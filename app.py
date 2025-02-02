import discord
from discord.ext import commands
from spotipy.oauth2 import SpotifyOAuth
import psycopg2  # Bibliothèque pour PostgreSQL
import threading
from flask import Flask, request, redirect
import time
import os
from urllib.parse import urlparse  # Pour parser l'URL de la base de données

# Configuration du bot Discord
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Configuration de Spotify
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
SCOPE = "user-library-read"

def get_db_connection():
    db_url = os.getenv("DATABASE_URL")  # Récupérer l'URL de la base de données depuis les variables d'environnement
    
    # Parser l'URL
    parsed_url = urlparse(db_url)
    
    # Extraire les informations de connexion
    db_config = {
        'dbname': parsed_url.path[1:],  # Supprimer le premier "/"
        'user': parsed_url.username,
        'password': parsed_url.password,
        'host': parsed_url.hostname,
        'port': parsed_url.port,
    }
    
    # Se connecter à la base de données
    conn = psycopg2.connect(**db_config, sslmode="require")
    return conn

# Créer la table si elle n'existe pas
def create_db():
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS tokens (
                user_id TEXT PRIMARY KEY,
                access_token TEXT NOT NULL,
                refresh_token TEXT NOT NULL,
                token_expiry INTEGER NOT NULL
            )
        ''')
        conn.commit()
        conn.close()
        print("Base de données initialisée avec succès.")
    except Exception as e:
        print(f"Erreur lors de l'initialisation de la base de données : {e}")

# Insérer ou mettre à jour le token dans la base de données
def insert_or_update_token(user_id, access_token, refresh_token, token_expiry):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO tokens (user_id, access_token, refresh_token, token_expiry)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE
        SET access_token = EXCLUDED.access_token,
            refresh_token = EXCLUDED.refresh_token,
            token_expiry = EXCLUDED.token_expiry
    ''', (user_id, access_token, refresh_token, token_expiry))
    conn.commit()
    conn.close()

# Flask serveur pour gérer la redirection OAuth
app = Flask(__name__)

@app.route("/callback")
def callback():
    code = request.args.get('code')
    user_id = request.args.get('state')  # L'état contient l'ID de l'utilisateur Discord

    if code and user_id:
        sp_oauth = SpotifyOAuth(client_id=CLIENT_ID,
                                client_secret=CLIENT_SECRET,
                                redirect_uri=REDIRECT_URI,
                                scope=SCOPE)

        try:
            token_info = sp_oauth.get_access_token(code)
            access_token = token_info['access_token']
            refresh_token = token_info['refresh_token']
            token_expiry = int(time.time()) + token_info['expires_in']  # Calcul de l'heure d'expiration du token
            print(f"Tokens reçus pour {user_id}")

            # Stocker les tokens dans la base de données
            insert_or_update_token(user_id, access_token, refresh_token, token_expiry)
            return "Authentification réussie ! Tu peux fermer cette page."
        except Exception as e:
            print(f"Erreur lors de l'échange du code : {e}")
            return "Une erreur est survenue lors de l'authentification."
    else:
        return "Code ou state manquant dans la requête."

# Démarrer Flask dans un thread séparé
def run_flask():
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))

threading.Thread(target=run_flask, daemon=True).start()

# Commande Discord pour lancer l'authentification Spotify
@bot.command()
async def connect(ctx):
    user_id = str(ctx.author.id)
    
    # Générer l'URL d'authentification Spotify
    sp_oauth = SpotifyOAuth(client_id=CLIENT_ID,
                            client_secret=CLIENT_SECRET,
                            redirect_uri=REDIRECT_URI,
                            scope=SCOPE,
                            state=user_id)  # Utiliser l'ID de l'utilisateur comme state
    auth_url = sp_oauth.get_authorize_url()
    
    # Envoyer le lien d'authentification à l'utilisateur
    await ctx.send(f"Clique sur ce lien pour te connecter à Spotify : {auth_url}")

# Créer la base de données au démarrage
create_db()

# Démarrer le bot Discord
bot.run(os.getenv("DISCORD_BOT_TOKEN"))