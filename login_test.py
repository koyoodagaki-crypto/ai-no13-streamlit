import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore


GCP_PROJECT = "fas-ai-no13-chathistory"

 #firebaseの初期化
if not firebase_admin._apps:
    cred = credentials.Certificate({
        "type": st.secrets['firebase']['type'],
        "project_id": st.secrets['firebase']['project_id'],
        "private_key_id": st.secrets['firebase']['private_key_id'],
        "private_key": st.secrets['firebase']['private_key'],
        "client_email": st.secrets['firebase']['client_email'],
        "client_id": st.secrets['firebase']['client_id'],
        "auth_uri": st.secrets['firebase']['auth_uri'],
        "token_uri": st.secrets['firebase']['token_uri'],
        "auth_provider_x509_cert_url": st.secrets['firebase']['auth_provider_x509_cert_url'],
        "client_x509_cert_url": st.secrets['firebase']['client_x509_cert_url'],
        "universe_domain": st.secrets['firebase']['universe_domain']
    })
    firebase_admin.initialize_app(cred)

db = firestore.client()

# usersコレクションの参照を取得
users_ref = db.collection('users')

# ドキュメントを取得し、IDを表示
docs = users_ref.stream()

st.title("Users Collection Document IDs")
for doc in docs:
    st.write(doc.id)  # ドキュメントのIDを表示