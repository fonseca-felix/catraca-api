import sys
import io
import os
import json
import re
from datetime import datetime
from pathlib import Path

# Garante que o terminal aceite caracteres especiais (acentos)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from flask import Flask, jsonify, request
from flask_cors import CORS
from flasgger import Swagger
from dotenv import load_dotenv
from auth import token_obrigatorio, gerar_token

# Carrega variáveis de ambiente
load_dotenv()

# Importação do Firebase
import firebase_admin
from firebase_admin import credentials, firestore

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "catraca123")
CORS(app, origins="*")

# Configuração do Swagger
app.config['SWAGGER'] = {'openapi': '3.0.3'}

# ==================== CONEXÃO FIREBASE ====================
db = None
FIREBASE_CONNECTED = False

def init_firebase():
    """Inicializa a conexão com o Firebase"""
    global db, FIREBASE_CONNECTED
    
    print("[INFO] Iniciando configuração do Firebase...")
    print(f"[INFO] Diretório atual: {os.getcwd()}")
    
    # Lista arquivos JSON na pasta para debug
    json_files = list(Path().glob("*.json"))
    print(f"[INFO] Arquivos JSON encontrados: {[f.name for f in json_files]}")
    
    # 1. Tenta carregar do ambiente Vercel
    firebase_creds = os.getenv("FIREBASE_CREDENTIALS")
    if firebase_creds:
        try:
            print("[INFO] Tentando carregar credenciais da variável de ambiente...")
            cred_dict = json.loads(firebase_creds)
            cred = credentials.Certificate(cred_dict)
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)
            db = firestore.client()
            FIREBASE_CONNECTED = True
            print("[OK] Firebase conectado via variável de ambiente")
            return True
        except Exception as e:
            print(f"[ERRO] Falha ao carregar credenciais do ambiente: {e}")
    
    # 2. Tenta carregar do arquivo local
    arquivo_credencial = "teste-catraca-firebase-adminsdk-fbsvc-e8860cef87.json"
    if os.path.exists(arquivo_credencial):
        try:
            print(f"[INFO] Tentando carregar arquivo: {arquivo_credencial}")
            cred = credentials.Certificate(arquivo_credencial)
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)
            db = firestore.client()
            FIREBASE_CONNECTED = True
            print(f"[OK] Firebase conectado via arquivo: {arquivo_credencial}")
            return True
        except Exception as e:
            print(f"[ERRO] Falha ao carregar {arquivo_credencial}: {e}")
    
    # 3. Tenta qualquer outro JSON na pasta
    for json_file in json_files:
        if json_file.name != arquivo_credencial:
            try:
                print(f"[INFO] Tentando arquivo alternativo: {json_file.name}")
                cred = credentials.Certificate(str(json_file))
                if not firebase_admin._apps:
                    firebase_admin.initialize_app(cred)
                db = firestore.client()
                FIREBASE_CONNECTED = True
                print(f"[OK] Firebase conectado via arquivo: {json_file.name}")
                return True
            except Exception as e:
                print(f"[ERRO] Falha ao carregar {json_file.name}: {e}")
    
    print("[ERRO] ❌ Não foi possível conectar ao Firebase!")
    print("[SOLUÇÃO] Coloque o arquivo de credenciais JSON na pasta do projeto")
    
    return False

# Inicializa Firebase
init_firebase()

# Tentar carregar Swagger
try:
    openapi_path = os.path.join(os.path.dirname(__file__), "openapi.yaml")
    if os.path.exists(openapi_path):
        swagger = Swagger(app, template_file=openapi_path)
        print("[OK] Swagger carregado")
    else:
        print("[AVISO] Arquivo openapi.yaml não encontrado")
except Exception as e:
    print(f"[AVISO] Erro ao carregar Swagger: {e}")

# ==================== FUNÇÕES DE APOIO ====================

def limpar_cpf(cpf):
    return re.sub(r"[^0-9]", "", str(cpf))

def validar_cpf_simples(cpf):
    """Apenas verifica se tem 11 dígitos para facilitar o cadastro."""
    return len(limpar_cpf(cpf)) == 11

def obter_proximo_id():
    """Gera ID sequencial (1, 2, 3...) via transação."""
    if db is None:
        return 1
    
    try:
        contador_ref = db.collection("configuracoes").document("contador_alunos")
        
        @firestore.transactional
        def transacao_id(transaction):
            snapshot = contador_ref.get(transaction=transaction)
            if not snapshot.exists:
                novo_id = 1
                transaction.set(contador_ref, {"ultimo_id": novo_id})
            else:
                novo_id = snapshot.get("ultimo_id") + 1
                transaction.update(contador_ref, {"ultimo_id": novo_id})
            return novo_id
        
        return transacao_id(db.transaction())
    except Exception as e:
        print(f"[ERRO] obter_proximo_id: {e}")
        return 1

# ==================== ROTAS ====================

@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "status": "online",
        "api": "API da Catraca",
        "mensagem": "A API está rodando perfeitamente!",
        "firebase_conectado": FIREBASE_CONNECTED,
        "firebase_db": db is not None
    }), 200

@app.route("/health", methods=["GET"])
def health():
    """Endpoint para verificar saúde da API"""
    return jsonify({
        "status": "healthy",
        "firebase": FIREBASE_CONNECTED,
        "timestamp": datetime.now().isoformat()
    }), 200

# -------------------- ROTAS DE ALUNOS (CRUD) --------------------

# LISTAR TODOS
@app.route("/alunos", methods=["GET"])
@token_obrigatorio
def listar_todos_alunos():
    if not FIREBASE_CONNECTED or db is None:
        return jsonify({"error": "Banco de dados não conectado. Configure as credenciais do Firebase primeiro.", "modo": "offline"}), 503
    
    try:
        alunos = []
        for doc in db.collection("alunos").stream():
            d = doc.to_dict()
            if "data_cadastro" in d and d["data_cadastro"]:
                if hasattr(d["data_cadastro"], 'isoformat'):
                    d["data_cadastro"] = d["data_cadastro"].isoformat()
            alunos.append(d)
        return jsonify(alunos), 200
    except Exception as e:
        return jsonify({"error": f"Erro ao listar alunos: {str(e)}"}), 500

# ROTA PARA OBTER O ÚLTIMO ID GERADO
@app.route("/alunos/ultimo_id", methods=["GET"])
@token_obrigatorio
def obter_ultimo_id_cadastrado():
    if db is None:
        return jsonify({"ultimo_id": 0}), 200
    
    try:
        contador_ref = db.collection("configuracoes").document("contador_alunos").get()
        if contador_ref.exists:
            return jsonify({"ultimo_id": contador_ref.get("ultimo_id")}), 200
        return jsonify({"ultimo_id": 0}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# BUSCAR UM ESPECÍFICO
@app.route("/alunos/<string:cpf>", methods=["GET"])
@token_obrigatorio
def buscar_aluno_por_cpf(cpf):
    if not FIREBASE_CONNECTED or db is None:
        return jsonify({"error": "Sistema funcionando em modo offline - Firebase não configurado"}), 503

    try:
        cpf_limpo = limpar_cpf(cpf)
        doc = db.collection("alunos").document(cpf_limpo).get()
        
        if not doc.exists:
            return jsonify({"error": "Usuário não está cadastrado"}), 404
            
        aluno = doc.to_dict()
        if "data_cadastro" in aluno and aluno["data_cadastro"]:
            if hasattr(aluno["data_cadastro"], 'isoformat'):
                aluno["data_cadastro"] = aluno["data_cadastro"].isoformat()
                
        return jsonify(aluno), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# CADASTRAR ALUNO
@app.route("/alunos", methods=["POST"])
@token_obrigatorio
def cadastrar_aluno():
    if not FIREBASE_CONNECTED or db is None:
        return jsonify({"error": "Sistema funcionando em modo offline - Firebase não configurado"}), 503

    dados = request.get_json()
    
    if not dados:
        return jsonify({"error": "Dados inválidos ou corpo da requisição vazio"}), 400
        
    cpf_limpo = limpar_cpf(dados.get("cpf", ""))

    if not validar_cpf_simples(cpf_limpo):
        return jsonify({"error": "CPF deve ter 11 números"}), 400
    
    # Verifica se já existe
    doc_ref = db.collection("alunos").document(cpf_limpo)
    if doc_ref.get().exists:
        return jsonify({"error": "CPF já cadastrado no sistema"}), 409

    try:
        novo_id = obter_proximo_id()
        status = dados.get("status", "liberado")
        
        aluno_data = {
            "id": novo_id,
            "nome": dados.get("nome", "Sem Nome").strip(),
            "cpf": cpf_limpo,
            "status": status,
            "data_cadastro": firestore.SERVER_TIMESTAMP
        }
        
        doc_ref.set(aluno_data)
        return jsonify({"message": "Aluno cadastrado com sucesso!", "id": novo_id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ALTERAR STATUS DO ALUNO
@app.route("/alunos/<string:cpf>/status", methods=["PUT", "PATCH"])
@token_obrigatorio
def alterar_status_aluno(cpf):
    if not FIREBASE_CONNECTED or db is None:
        return jsonify({"error": "Sistema funcionando em modo offline - Firebase não configurado"}), 503

    try:
        cpf_limpo = limpar_cpf(cpf)
        dados = request.get_json()
        
        aluno_ref = db.collection("alunos").document(cpf_limpo)
        if not aluno_ref.get().exists:
            return jsonify({"error": "Usuário não está cadastrado"}), 404

        novo_status = dados.get("status")
        if novo_status not in ["liberado", "bloqueado"]:
            return jsonify({"error": "Status inválido. Use 'liberado' ou 'bloqueado'."}), 400

        aluno_ref.update({"status": novo_status})
        return jsonify({"message": f"Status atualizado para {novo_status}"}), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# EDITAR NOME DO ALUNO
@app.route("/alunos/<string:cpf>", methods=["PUT"])
@token_obrigatorio
def editar_aluno(cpf):
    if not FIREBASE_CONNECTED or db is None:
        return jsonify({"error": "Sistema funcionando em modo offline - Firebase não configurado"}), 503

    try:
        cpf_limpo = limpar_cpf(cpf)
        dados = request.get_json()
        
        aluno_ref = db.collection("alunos").document(cpf_limpo)
        aluno_snap = aluno_ref.get()
        if not aluno_snap.exists:
            return jsonify({"error": "Usuário não está cadastrado"}), 404

        campos_permitidos = ["nome", "status", "cpf"]
        dados_seguros = {k: v for k, v in dados.items() if k in campos_permitidos}

        if not dados_seguros:
            return jsonify({"error": "Nenhum dado válido fornecido para atualização"}), 400

        # Validação de status, se presente
        if "status" in dados_seguros and dados_seguros["status"] not in ["liberado", "bloqueado"]:
            return jsonify({"error": "Status inválido. Use 'liberado' ou 'bloqueado'."}), 400

        novo_cpf_raw = dados_seguros.pop("cpf", None)
        if novo_cpf_raw is not None:
            novo_cpf_limpo = limpar_cpf(novo_cpf_raw)
            if not validar_cpf_simples(novo_cpf_limpo):
                return jsonify({"error": "CPF deve ter 11 números"}), 400

            if novo_cpf_limpo != cpf_limpo:
                novo_doc = db.collection("alunos").document(novo_cpf_limpo)
                if novo_doc.get().exists:
                    return jsonify({"error": "O novo CPF já está cadastrado no sistema"}), 409

                aluno_data = aluno_snap.to_dict()
                aluno_data.update(dados_seguros)
                aluno_data["cpf"] = novo_cpf_limpo

                novo_doc.set(aluno_data)
                aluno_ref.delete()

                return jsonify({
                    "message": "Dados atualizados com sucesso e CPF alterado",
                    "cpf_antigo": cpf_limpo,
                    "cpf_novo": novo_cpf_limpo,
                    "atualizados": list(dados_seguros.keys()) + ["cpf"]
                }), 200

        if dados_seguros:
            aluno_ref.update(dados_seguros)

        return jsonify({"message": "Dados atualizados com sucesso", "atualizados": list(dados_seguros.keys())}), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# EXCLUIR ALUNO
@app.route("/alunos/<string:cpf>", methods=["DELETE"])
@token_obrigatorio
def excluir_aluno(cpf):
    if not FIREBASE_CONNECTED or db is None:
        return jsonify({"error": "Sistema funcionando em modo offline - Firebase não configurado"}), 503

    try:
        cpf_limpo = limpar_cpf(cpf)
        aluno_ref = db.collection("alunos").document(cpf_limpo)
        
        if not aluno_ref.get().exists:
            return jsonify({"error": "Aluno não encontrado"}), 404
            
        aluno_ref.delete()
        return jsonify({"message": f"Aluno do CPF {cpf_limpo} removido"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -------------------- ROTA DA CATRACA (VERIFICAR ACESSO) --------------------

@app.route("/acesso/<string:cpf>", methods=["GET"])
def verificar_acesso(cpf):
    if not FIREBASE_CONNECTED or db is None:
        return jsonify({"acesso": False, "mensagem": "Sistema temporariamente indisponível. Procure a secretaria.", "modo": "offline"}), 403
    
    try:
        cpf_limpo = limpar_cpf(cpf)
        
        if not validar_cpf_simples(cpf_limpo):
            return jsonify({"acesso": False, "mensagem": "CPF Inválido"}), 400
            
        doc = db.collection("alunos").document(cpf_limpo).get()
        
        if not doc.exists:
            res = {"acesso": False, "mensagem": "Usuário não está cadastrado", "status": "inexistente"}
        else:
            aluno = doc.to_dict()
            status = aluno.get("status", "bloqueado")
            
            if status == "liberado":
                mensagem = "Liberado para entrar na academia"
                acesso_permitido = True
            else:
                mensagem = "Conta bloqueada. Por favor, dirija-se à secretaria."
                acesso_permitido = False
            
            res = {
                "acesso": acesso_permitido,
                "nome": aluno.get("nome", "Desconhecido"),
                "status": status,
                "mensagem": mensagem
            }
        
        # Tenta salvar log, mas não falha se não conseguir
        try:
            db.collection("logs_acesso").add({
                **res, 
                "cpf": cpf_limpo, 
                "data_hora": firestore.SERVER_TIMESTAMP
            })
        except:
            pass
        
        if res["acesso"]:
            return jsonify(res), 200
        else:
            return jsonify(res), 403

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -------------------- AUTENTICAÇÃO --------------------

@app.route("/login", methods=["POST"])
def login():
    dados = request.get_json()
    if not dados:
        return jsonify({"error": "Dados não fornecidos"}), 400
    
    usuario = dados.get("usuario") or dados.get("username")
    senha = dados.get("senha") or dados.get("password")
    
    # Usuário padrão - configurável via .env
    admin_user = os.getenv("ADMIN_USERNAME", "admin")
    admin_pass = os.getenv("ADMIN_PASSWORD", "adm123")
    
    if usuario == admin_user and senha == admin_pass:
        token = gerar_token(usuario)
        return jsonify({
            "token": token,
            "usuario": usuario,
            "message": "Login realizado com sucesso"
        }), 200
    
    return jsonify({"error": "Login inválido"}), 401

# ==================== INICIALIZAÇÃO ====================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)