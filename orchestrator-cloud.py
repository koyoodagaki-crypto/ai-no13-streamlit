#ライブラリのインポート =================================================
import os
from azure.search.documents import SearchClient
from openai import AzureOpenAI
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.models import VectorizedQuery
import streamlit as st
from dotenv import load_dotenv



# .envファイルから環境変数を読み込む。 =====================================================================================
load_dotenv(verbose=True)

###
# streamlit cloundのsecretsに記述したキーを参照する ======================================================================
SEARCH_SERVICE_ENDPOINT = st.secrets.AzureAPIkey.SEARCH_SERVICE_ENDPOINT # Azure AI Searchのエンドポイント
SEARCH_SERVICE_API_KEY = st.secrets.AzureAPIkey.SEARCH_SERVICE_API_KEY # Azure AI SearchのAPIキー
SEARCH_SERVICE_INDEX_NAME = st.secrets.AzureAPIkey.SEARCH_SERVICE_INDEX_NAME # Azure AI Searchのインデックス名
AOAI_ENDPOINT = st.secrets.AzureAPIkey.AOAI_ENDPOINT # Azure OpenAI Serviceのエンドポイント
AOAI_API_VERSION = st.secrets.AzureAPIkey.AOAI_API_VERSION # Azure OpenAI ServiceのAPIバージョン
AOAI_API_KEY = st.secrets.AzureAPIkey.AOAI_API_KEY # Azure OpenAI ServiceのAPIキー
AOAI_EMBEDDING_MODEL_NAME = st.secrets.AzureAPIkey.AOAI_EMBEDDING_MODEL_NAME # Azure OpenAI Serviceの埋め込みモデル名
AOAI_CHAT_MODEL_NAME = st.secrets.AzureAPIkey.AOAI_CHAT_MODEL_NAME # Azure OpenAI Serviceのチャットモデル名
###

# AIのキャラクターを決めるためのシステムメッセージを定義する。 =================================================================
system_message_chat_conversation = "与えられた情報に従って正確な回答をして下さい。作業手順についての質問があった際には、出来るだけ詳細に伝えるようにしてください。"

#テスト
#st.secrets.AzureAPIkey.○○
print(SEARCH_SERVICE_ENDPOINT)
print(SEARCH_SERVICE_API_KEY)
print(SEARCH_SERVICE_INDEX_NAME)
print(AOAI_ENDPOINT)
print(AOAI_API_VERSION)

# ユーザーの質問に対して回答を生成するための関数を定義する。###################################################################################
# 引数はチャット履歴を表すJSON配列とする。
def search(history):
    # [{'role': 'user', 'content': '有給は何日取れますか？'},{'role': 'assistant', 'content': '10日です'},
    # {'role': 'user', 'content': '一日の労働上限時間は？'}...]というJSON配列から
    # 最も末尾に格納されているJSONオブジェクトのcontent(=ユーザーの質問)を取得する。
    question = history[-1].get('content')

    # Azure AI SearchのAPIに接続するためのクライアントを生成する
    search_client = SearchClient(
        endpoint=SEARCH_SERVICE_ENDPOINT, 
        index_name=SEARCH_SERVICE_INDEX_NAME, 
        credential=AzureKeyCredential(SEARCH_SERVICE_API_KEY) 
    )


    # Azure OpenAI ServiceのAPIに接続するためのクライアントを生成する
    openai_client = AzureOpenAI(
        azure_endpoint=AOAI_ENDPOINT, 
        api_key=AOAI_API_KEY,
        api_version=AOAI_API_VERSION
    )


    # Azure OpenAI Serviceの埋め込み用APIを用いて、ユーザーからの質問をベクトル化する。
    response = openai_client.embeddings.create(
        input = question,
        model = AOAI_EMBEDDING_MODEL_NAME 
    )


    # ベクトル化された質問をAzure AI Searchに対して検索するためのクエリを生成する。
    vector_query = VectorizedQuery(
        vector=response.data[0].embedding,
        k_nearest_neighbors=3,
        fields="text_vector"
    )


    # ベクトル化された質問を用いて、Azure AI Searchに対してベクトル検索を行う。
    results = search_client.search(
        vector_queries=[vector_query],
        select=['chunk_id', 'chunk'])
    

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
    """.format(query=question, source=source)

    # メッセージを追加する。
    messages.append({"role": "user", "content": user_message})


    # Azure OpenAI Serviceに回答生成を依頼する。
    response = openai_client.chat.completions.create(
        model=AOAI_CHAT_MODEL_NAME, 
        messages=messages,
        max_tokens=6500,
        top_p = 0.2
    )
    answer = response.choices[0].message.content

    # 回答を返す。
    return answer

# ###############################################################################################################################


# ここからは画面を構築するためのコード  ###########################################################################

# チャット履歴を初期化する。
if "history" not in st.session_state:
   st.session_state["history"] = []

#タイトル表示
st.title('設備技術 RAGアプリ（プロト）')

# チャット履歴を表示する。
for message in st.session_state.history:
    with st.chat_message(message["role"]):
        st.write(message["content"])

# ユーザーが質問を入力したときの処理を記述する。
if prompt := st.chat_input("質問を入力してください"):

    # ユーザーが入力した質問を表示する。
    with st.chat_message("user"):
        st.write(prompt)

    # ユーザの質問をチャット履歴に追加する
    st.session_state.history.append({"role": "user", "content": prompt})

    # ユーザーの質問に対して回答を生成するためにsearch関数を呼び出す。
    response = search(st.session_state.history)

    # 回答を表示する。
    with st.chat_message("assistant"):
        st.write(response)

    # 回答をチャット履歴に追加する。
    st.session_state.history.append({"role": "assistant", "content": response})