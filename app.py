import sys
import io
# Garante que o terminal aceite caracteres especiais (acentos)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from flask import Flask, jsonify, request
import firebase_admin
from firebase_admin import credentials, firestore
import jwt
from datetime import datetime, timedelta
from functools import wraps
from flask_cors import CORS
import os
from dotenv import load_dotenv
import json
import re

load_dotenv()

# ---------------------
#   CONFIGURAÇÃO JWT
# ---------------------
SECRET_KEY = os.getenv("SECRET_KEY", "catraca123")

def gerar_token(usuario):
    """Gera token JWT para autenticação"""
    payload = {
        'usuario': usuario,
        'exp': datetime.utcnow() + timedelta(hours=24)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm='HS256')

def token_obrigatorio(f):
    """Decorator para proteger rotas que precisam de autenticação"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
       
        if not token:
            return jsonify({'error': 'Token não fornecido'}), 401
       
        # Remove 'Bearer ' se presente
        if token.startswith('Bearer '):
            token = token[7:]
       
        try:
            decoded = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
            request.usuario = decoded['usuario']
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expirado'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Token inválido'}), 401
       
        return f(*args, **kwargs)
    return decorated

# ---------------------
#   INICIALIZAÇÃO FIREBASE
# ---------------------
db = None
FIREBASE_CONNECTED = False

print("[INFO] Iniciando configuração do Firebase...")

try:
    if os.getenv("VERCEL") == "true":
        firebase_creds = os.getenv("FIREBASE_CREDENTIALS")
        if firebase_creds:
            cred = credentials.Certificate(json.loads(firebase_creds))
            print("[INFO] Usando credenciais do Vercel")
        else:
            print("[ERRO] FIREBASE_CREDENTIALS não encontrada nas variáveis de ambiente")
            cred = None
    else:
        # Tenta encontrar o arquivo de credenciais Firebase
        firebase_json_path = os.path.join(os.path.dirname(__file__), "teste-catraca-firebase-adminsdk-fbsvc-e8860cef87.json")
        print(f"[INFO] Procurando arquivo de credenciais em: {firebase_json_path}")
       
        if os.path.exists(firebase_json_path):
            print("[INFO] Arquivo encontrado, tentando conectar...")
            try:
                cred = credentials.Certificate(firebase_json_path)
                print("[INFO] Credenciais carregadas com sucesso")
            except Exception as cred_error:
                print(f"[ERRO] Erro ao carregar credenciais: {cred_error}")
                cred = None
        else:
            print(f"[ERRO] Arquivo de credenciais não encontrado: {firebase_json_path}")
            cred = None
   
    if cred:
        try:
            firebase_admin.initialize_app(cred)
            db = firestore.client()
            FIREBASE_CONNECTED = True
            print("[OK] Conectado ao Firebase com sucesso!")
        except ValueError as init_error:
            if "already initialized" in str(init_error).lower():
                print("[INFO] Firebase já estava inicializado")
                db = firestore.client()
                FIREBASE_CONNECTED = True
            else:
                print(f"[ERRO] Erro ao inicializar Firebase: {init_error}")
        except Exception as init_error:
            print(f"[ERRO] Erro inesperado ao inicializar Firebase: {init_error}")
    else:
        print("[ERRO] Não foi possível conectar ao Firebase - credenciais ausentes ou inválidas")
       
except Exception as e:
    print(f"[ERRO] Falha geral na configuração do Firebase: {e}")
    import traceback
    traceback.print_exc()

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY

# CORS configurado corretamente
CORS(app, origins="*", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
     allow_headers=["Content-Type", "Authorization", "Accept"])

# ---------------------
#   FUNÇÕES DE APOIO
# ---------------------
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
        print(f"Erro ao gerar ID: {e}")
        return 1

# ---------------------
#   ROTA DE LOGIN
# ---------------------
@app.route("/login", methods=["POST"])
def login():
    """
    Rota de autenticação para o dashboard admin
    """
    try:
        dados = request.get_json()
       
        if not dados:
            return jsonify({"error": "Dados não fornecidos"}), 400
       
        usuario = dados.get("usuario")
        senha = dados.get("senha")
       
        # Verifica credenciais
        if usuario == "adm" and senha == "catraca-adm":
            # Gera token JWT
            token = gerar_token(usuario)
            return jsonify({
                "token": token,
                "message": "Login realizado com sucesso",
                "usuario": usuario
            }), 200
        else:
            return jsonify({"error": "Credenciais inválidas"}), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------------
#   ROTA RAIZ (STATUS DA API)
# ---------------------
@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "status": "online",
        "api": "API da Catraca",
        "mensagem": "A API está rodando perfeitamente!",
        "firebase_conectado": db is not None,
        "versao": "2.0.0"
    }), 200

# ---------------------
#   ROTAS DE ALUNOS (CRUD)
# ---------------------

# LISTAR TODOS
@app.route("/alunos", methods=["GET"])
@token_obrigatorio
def listar_todos_alunos():
    if not FIREBASE_CONNECTED or db is None:
        return jsonify({"error": "Banco de dados não conectado. Configure as credenciais do Firebase primeiro.", "modo": "offline"}), 503
   
    try:
        alunos = []
        alunos_ref = db.collection("alunos").stream()
       
        for doc in alunos_ref:
            d = doc.to_dict()
            # Converte timestamp para string
            if "data_cadastro" in d and d["data_cadastro"]:
                if hasattr(d["data_cadastro"], 'isoformat'):
                    d["data_cadastro"] = d["data_cadastro"].isoformat()
            alunos.append(d)
       
        # Ordena por ID (ou nome)
        alunos.sort(key=lambda x: x.get('id', 0))
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
        nome = dados.get("nome", "Sem Nome").strip()
       
        aluno_data = {
            "id": novo_id,
            "nome": nome,
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

        # Trata alteração de CPF
        novo_cpf_raw = dados_seguros.pop("cpf", None)
        if novo_cpf_raw is not None:
            novo_cpf_limpo = limpar_cpf(novo_cpf_raw)
            if not validar_cpf_simples(novo_cpf_limpo):
                return jsonify({"error": "CPF deve ter 11 números"}), 400

            if novo_cpf_limpo != cpf_limpo:
                novo_doc = db.collection("alunos").document(novo_cpf_limpo)
                if novo_doc.get().exists:
                    return jsonify({"error": "O novo CPF já está cadastrado no sistema"}), 409

                # Copia dados para o novo documento
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

        # Atualização normal
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
        return jsonify({"message": f"Aluno do CPF {cpf_limpo} removido com sucesso"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------------
#   ROTA DA CATRACA (VERIFICAR ACESSO) - PÚBLICA
# ---------------------
@app.route("/acesso/<string:cpf>", methods=["GET"])
def verificar_acesso(cpf):
    """
    Rota pública para a catraca verificar acesso
    """
    if not FIREBASE_CONNECTED or db is None:
        return jsonify({
            "acesso": False,
            "mensagem": "Sistema temporariamente indisponível. Procure a secretaria.",
            "status": "indisponivel"
        }), 503
   
    try:
        cpf_limpo = limpar_cpf(cpf)
       
        # Validação do CPF
        if not validar_cpf_simples(cpf_limpo):
            return jsonify({
                "acesso": False,
                "mensagem": "CPF inválido. Digite 11 números.",
                "status": "invalido"
            }), 400
           
        # Busca no Firebase
        doc = db.collection("alunos").document(cpf_limpo).get()
       
        if not doc.exists:
            # Tenta salvar log de acesso negado
            try:
                db.collection("logs_acesso").add({
                    "cpf": cpf_limpo,
                    "acesso": False,
                    "status": "nao_cadastrado",
                    "mensagem": "CPF não cadastrado",
                    "data_hora": firestore.SERVER_TIMESTAMP
                })
            except:
                pass
               
            return jsonify({
                "acesso": False,
                "mensagem": "CPF não cadastrado no sistema. Procure a secretaria para se cadastrar.",
                "status": "nao_cadastrado"
            }), 404
       
        aluno = doc.to_dict()
        status = aluno.get("status", "bloqueado")
        nome = aluno.get("nome", "Usuário")
       
        # Tenta salvar log de acesso
        try:
            db.collection("logs_acesso").add({
                "cpf": cpf_limpo,
                "nome": nome,
                "acesso": status == "liberado",
                "status": status,
                "mensagem": "Acesso liberado" if status == "liberado" else "Acesso bloqueado",
                "data_hora": firestore.SERVER_TIMESTAMP
            })
        except:
            pass
       
        if status == "liberado":
            return jsonify({
                "acesso": True,
                "nome": nome,
                "status": "liberado",
                "mensagem": "✅ Acesso liberado! Bem-vindo(a) à academia."
            }), 200
        else:
            return jsonify({
                "acesso": False,
                "nome": nome,
                "status": "bloqueado",
                "mensagem": "⛔ Acesso bloqueado. Entre em contato com a secretaria para regularizar sua situação."
            }), 403

    except Exception as e:
        print(f"Erro na verificação de acesso: {e}")
        return jsonify({
            "acesso": False,
            "mensagem": "Erro interno no servidor. Tente novamente mais tarde.",
            "status": "erro"
        }), 500

# ---------------------
#   ROTA DE LOGS (OPCIONAL)
# ---------------------
@app.route("/logs", methods=["GET"])
@token_obrigatorio
def obter_logs():
    """Rota para visualizar logs de acesso (apenas admin)"""
    if not FIREBASE_CONNECTED or db is None:
        return jsonify({"error": "Sistema offline"}), 503
   
    try:
        logs = []
        logs_ref = db.collection("logs_acesso").order_by("data_hora", direction=firestore.Query.DESCENDING).limit(100)
       
        for doc in logs_ref.stream():
            d = doc.to_dict()
            if "data_hora" in d and d["data_hora"]:
                if hasattr(d["data_hora"], 'isoformat'):
                    d["data_hora"] = d["data_hora"].isoformat()
            logs.append(d)
       
        return jsonify(logs), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------------
#   ROTA DE ESTATÍSTICAS
# ---------------------
@app.route("/estatisticas", methods=["GET"])
@token_obrigatorio
def obter_estatisticas():
    """Rota para obter estatísticas do sistema"""
    if not FIREBASE_CONNECTED or db is None:
        return jsonify({"error": "Sistema offline"}), 503
   
    try:
        alunos = db.collection("alunos").stream()
        total = 0
        liberados = 0
        bloqueados = 0
       
        for doc in alunos:
            total += 1
            dados = doc.to_dict()
            if dados.get("status") == "liberado":
                liberados += 1
            else:
                bloqueados += 1
       
        return jsonify({
            "total_alunos": total,
            "liberados": liberados,
            "bloqueados": bloqueados,
            "percentual_liberados": round((liberados / total * 100) if total > 0 else 0, 2)
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------------
#   HEALTH CHECK PARA O VERCEL
# ---------------------
@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "healthy",
        "firebase": FIREBASE_CONNECTED,
        "timestamp": datetime.now().isoformat()
    }), 200

# ---------------------
#   INICIALIZAÇÃO
# ---------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)