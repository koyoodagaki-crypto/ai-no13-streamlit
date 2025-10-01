import streamlit as st

import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from google.cloud import firestore
from openai import AzureOpenAI
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
import json


#環境ファイルの読み込み
#load_dotenv()

#firebaseの初期化
if not firebase_admin._apps:
   cred = credentials.Certificate(json.loads(st.secrets["firebase"]["firebase_key"]))
   app = firebase_admin.initialize_app(cred)

#ユーザの質問の要約生成用
AOAI_API_KEY = st.secrets["api_keys"]["AOAI_API_KEY"]
AOAI_API_VERSION = st.secrets["api_keys"]["AOAI_API_VERSION"]
AOAI_ENDPOINT = st.secrets["api_keys"]["AOAI_ENDPOINT"]
AOAI_MODEL_NAME = st.secrets["api_keys"]["AOAI_MODEL_NAME"]


#ユーザー質問をAI Searchに投げる用
SEARCH_SERVICE_ENDPOINT = st.secrets["api_keys"]["SEARCH_SERVICE_ENDPOINT"] # Azure AI Searchのエンドポイント
SEARCH_SERVICE_API_KEY = st.secrets["api_keys"]["SEARCH_SERVICE_API_KEY"] # Azure AI SearchのAPIキー
SEARCH_SERVICE_INDEX_NAME = st.secrets["api_keys"]["SEARCH_SERVICE_INDEX_NAME"] # Azure AI Searchのインデックス名


#RAG回答生成用
AOAI2_ENDPOINT = st.secrets["api_keys"]["AOAI2_ENDPOINT"] # Azure OpenAI Serviceのエンドポイント
AOAI2_API_VERSION = st.secrets["api_keys"]["AOAI2_API_VERSION"] # Azure OpenAI ServiceのAPIバージョン
AOAI2_API_KEY = st.secrets["api_keys"]["AOAI2_API_KEY"] # Azure OpenAI ServiceのAPIキー
AOAI2_EMBEDDING_MODEL_NAME = st.secrets["api_keys"]["AOAI2_EMBEDDING_MODEL_NAME"] # Azure OpenAI Serviceの埋め込みモデル名
AOAI2_CHAT_MODEL_NAME = st.secrets["api_keys"]["AOAI2_CHAT_MODEL_NAME"] # Azure OpenAI Serviceのチャットモデル名

#
NEW_CHAT_TITLE = "New Chat"
#CHATBOT_USER = "user1"
GCP_PROJECT = "fas-ai-no13-chathistory"

# AIのキャラクターを決めるためのシステムメッセージを定義する。 =================================================================
system_message_chat_conversation = "与えられた情報に従って正確で具体的な回答をして下さい。手順についての質問が来た場合、なるべく詳細にユーザーに伝えるように心がけてください"

# 定義ここまで ------------------------------------------------------------------------------------------------------------------------------

#ユーザー名チェック

username = st.secrets.api_keys.USER_NAMES.split(",")
#print(username)

#セッションステートでログイン状態を保持
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

# ===================
#　ログイン画面
# ===================
if not st.session_state.logged_in:
    st.title('ログイン画面')
    st.session_state.username = st.text_input('ユーザー名を入力してください')

    if st.button("ログイン"):
        if st.session_state.username in username:
            st.session_state.logged_in = True
            st.success('ログイン成功')
            print('ログイン成功')
            st.rerun()
        else:
            st.error('ユーザー名がありません')

    

# ===========================
#　ログイン後ページ (チャット画面)
# ===========================
else:
    
    st.write("JSONキー一覧:" ,st.secrets["firebase"]["firebase_key"])

    #タイトル表示
    st.title('設備技術 RAGアプリ（プロト）')
    st.write(f"ようこそ {st.session_state.username}さん!")

    #注意点の表記
    st.subheader('※注意点※')
    st.text('①質問を送信してから、5秒~10秒のタイムラグがあります。')
    st.text('②まったく同じ質問でも回答が返る場合と返らない場合が稀に有ります。')
    st.text('③同じ意図の質問でも、質問の仕方によって回答に若干の変化があります')
    st.write('ここまでは描画可能')

    #新しいチャットを作成するための関数 -----------------------------------------------------------------------------------------------
    def create_new_chat():
        st.session_state.displayed_chat_title = NEW_CHAT_TITLE #現在表示されているチャットのタイトルを保持する
        st.session_state.displayed_chat_messages = [] #新しいチャットが作成された際にメッセージが表示されない状態にリセットする

    # ------------------------------------------------------------------------------------------------------------------------------


    #表示するチャットを変更する為の関数 -----------------------------------------------------------------------------------------------------------------------
    def change_displayed_chat(chat_doc):
        # Update titles
        st.session_state.titles = [
            doc.to_dict()["title"] for doc in st.session_state.chats_ref.stream()  #すべてのチャットのタイトルをストリーム形式で取得する
        ]

        st.session_state.displayed_chat_ref = chat_doc.reference #引数として渡された 'chat_doc'のリファレンスを設定する➡現在表示されているチャットが特定される
        st.session_state.displayed_chat_title = chat_doc.to_dict()["title"] #chat_docのタイトルを取得する
        st.session_state.displayed_chat_messages = [  #選択されたチャットのメッセージを取得して設定する メッセージコレクションを参照し、timestampで並べる
            msg.to_dict()
            for msg in chat_doc.reference.collection("messages").stream()
        ]

    # --------------------------------------------------------------------------------------------------------------------------------------------------------


    #主要部分 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    st.write('dbの宣言開始')
    db = firestore.Client(project=GCP_PROJECT)
    st.write('dbの設定終了')

    try:
        users_ref = db.collection('users')
        docs = users_ref.stream()
        for doc in docs:
            st.write(doc.id)
    except Exception as e:
        st.error(f"firestore接続エラー:{e}")
        

    #ユーザーのセッション状態の初期化
    #if "user" not in st.session_state: #セッションに'user'というキーが存在しない場合、デフォルトのユーザー名をCHATBOT_USERに設定する
        #A   st.session_state.user = CHATBOT_USER 

    #チャットリファレンスの初期化
    if "chats_ref" not in st.session_state:# 'chat_ref'がセッションに存在しない場合、firestoreのデータベースからユーザーのチャットコレクションへのリファレンスを取得する
        st.write('usersを取得開始')#エラーロギング
        users_ref = db.collection("users") #ユーザーのドキュメントを取得
        st.write('usersの取得終了')#エラーロギング

        st.write('queryの取得開始')#エラーロギング
        user_ref = users_ref.document(st.session_state.username)
        st.write('queryの設定完了')
        #doc = user_ref.get()
        st.session_state.chats_ref = user_ref.collection("chats") #そのユーザーに関連するチャットのコレクションをchat_refとして保存する

    #チャットタイトルの取得
    if "titles" not in st.session_state:
        #st.session_state.titles = [   #firestoreからチャットを作成日時順に取得し、それぞれのチャットのタイトルをリストとして格納する
         #       doc.to_dict()["title"]
          #      for doc in st.session_state.chats_ref.get()
           #     ]
        st.session_state.titles = 'test'
        st.write('チャットタイトルの取得完了')

    #表示中のチャットリファレンスの初期化
    if "displayed_chat_ref" not in st.session_state:
        st.session_state.displayed_chat_ref = None #初回アクセス時には表示するチャットがないため、displayed_chat_refをnoneに設定する

    #表示中のチャットタイトルの初期化
    if "displayed_chat_title" not in st.session_state:
        st.session_state.displayed_chat_title = "New Chat" 

    #表示中のメッセージの初期化
    if "displayed_chat_messages" not in st.session_state: #現在表示中のチャットメッセージを格納するリストを初期化する
        st.session_state.displayed_chat_messages = []
    
    # Sidebarの構築
    #サイドバーに新しいチャットを開始するボタンと過去のチャットのリストを表示する
    st.write('サイドバー処理開始')

    with st.sidebar:
        #チャットボット使用ユーザーの表示
        st.subheader(f"ユーザー : {st.session_state.username}")

        #現在表示されているチャットが新しいチャットであるかどうかを確認し、ボタンを無効化するかどうかを決定する
        new_chat_disable = st.session_state.displayed_chat_title == NEW_CHAT_TITLE 
    
        #新しいチャットのボタンを配置し、クリック時にcreate_new_chatを呼び出す
        st.button("新しい会話を始める", on_click=create_new_chat, disabled=new_chat_disable, type="primary") 

        st.title("過去の会話履歴")

        #過去のチャット履歴のタイトルをボタンとして表示し、クリック時にchange_displayed_chat関数を呼び出して選択されたチャットを表示する
        for doc in st.session_state.chats_ref.stream():
            data = doc.to_dict()
            st.button(data["title"], on_click=change_displayed_chat, args=(doc, ))

    print('サイドバー処理終了')

    #メッセージの表示
    # displayed_chat_messagesに格納されたメッセージをループし、各メッセージのロール（ユーザーまたはチャットボット）に応じて表示
    for message in st.session_state.displayed_chat_messages:
        with st.chat_message(message["role"]):
            st.markdown(message["contents"])


    if user_input_text := st.chat_input("質問を入力してください"):

        # ユーザーのメッセージを追加
        with st.chat_message("user"):
            st.markdown(user_input_text)

        # チャットの初回処理
        if len(st.session_state.displayed_chat_messages) == 0:

            # Create new chat title
            chat_title_prompt = f"""
            ChatBotとの会話を開始するためにユーザーが入力した文を与えるので、その内容を要約し会話のタイトルを考えてもらいます。
            出力は、会話のタイトルのみにしてください。
            ユーザーの入力文: {user_input_text} """

            #azure open ai client(ユーザー質問要約用)の初期化
            openai_client = AzureOpenAI(
                azure_endpoint=AOAI_ENDPOINT, 
                api_key=AOAI_API_KEY,
                api_version=AOAI_API_VERSION
            )

            #チャットのタイトルを決めるために、OpenAIの機能でユーザーの入力文を要約する
            response = openai_client.chat.completions.create(
                model=AOAI_MODEL_NAME,
                messages=[{'role': 'system', 'content': chat_title_prompt}]
            )

            st.session_state.displayed_chat_title = response.choices[0].message.content


            # firestoreにtitelとcreatedの値を追加する
            _, st.session_state.displayed_chat_ref = st.session_state.chats_ref.add(
                {
                'title': st.session_state.displayed_chat_title,
                'created': firestore.SERVER_TIMESTAMP,
                }
            )

        user_input_data = {
            "role": "user",
            "contents": user_input_text,
            "timestamp": firestore.SERVER_TIMESTAMP
        }
        st.session_state.displayed_chat_messages.append(user_input_data) #ユーザーの質問をチャット履歴に追加する
        st.session_state.displayed_chat_ref.collection("messages").add(user_input_data) #ユーザーの質問をfirestoreに追加する


        with st.spinner("回答を生成中です..."):

            #azure open ai client(RAG回答生成用)の初期化
            openai_client2 = AzureOpenAI(
                azure_endpoint=AOAI2_ENDPOINT, 
                api_key=AOAI2_API_KEY,
                api_version=AOAI2_API_VERSION
            )

            # Azure OpenAI Serviceの埋め込み用APIを用いて、ユーザーからの質問をベクトル化する。
            response = openai_client2.embeddings.create(
                input = user_input_text,
                model = AOAI2_EMBEDDING_MODEL_NAME            
            )

            # ベクトル化された質問をAzure AI Searchに対して検索するためのクエリを生成する。
            vector_query = VectorizedQuery(
                vector=response.data[0].embedding,
                k_nearest_neighbors=3,
                fields="text_vector"
            )

               # Azure AI SearchのAPIに接続するためのクライアントを生成する
            search_client = SearchClient(
                endpoint=SEARCH_SERVICE_ENDPOINT, 
                index_name=SEARCH_SERVICE_INDEX_NAME, 
                credential=AzureKeyCredential(SEARCH_SERVICE_API_KEY) 
            )

            # ベクトル化された質問を用いて、Azure AI Searchに対してベクトル検索を行う。
            results = search_client.search(
                vector_queries=[vector_query],
                select=['chunk_id', 'chunk']
            )

            # チャット履歴の中からユーザーの質問に対する回答を生成するためのメッセージを生成する。
            messages = []


            # 先頭にAIのキャラ付けを行うシステムメッセージを追加する。
            messages.insert(0, {"role": "system", "content": system_message_chat_conversation})


            # 回答を生成するためにAzure AI Searchから取得した情報を整形する。
            sources = ["[Source" + result["chunk_id"] + "]: " + result["chunk"] for result in results]
            source = "\n".join(sources)


            # ユーザーの質問と情報源を含むメッセージを生成する。
            user_message = """
            {query}

            Sources:
            {source}
            """.format(query=user_input_text, source=source)

            # メッセージを追加する。
            messages.append({"role": "user", "content": user_message})

            # OpenAIのLLMに質問に対する回答を依頼する
            response = openai_client2.chat.completions.create(
                model=AOAI2_CHAT_MODEL_NAME,
                messages=messages
            )
            
            assistant_output_text = response.choices[0].message.content #LLMによる回答を格納する

            # Assistant
            with st.chat_message("assistant"):
                st.markdown(assistant_output_text)
            assistant_output_data = {
                "role": "assistant",
                "contents": assistant_output_text,
                "timestamp": firestore.SERVER_TIMESTAMP
            }
            st.session_state.displayed_chat_messages.append(assistant_output_data) #LLMの回答を会話履歴に追加する
            st.session_state.displayed_chat_ref.collection("messages").add(assistant_output_data) #firestoreにLLMの回答を追加する
