import sys
import io
# Garante que o terminal aceite caracteres especiais (acentos)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from flask import Flask, jsonify, request
import firebase_admin
from firebase_admin import credentials, firestore

# CORREÇÃO: Importar auth do mesmo diretório
try:
    from auth import token_obrigatorio, gerar_token
except ImportError:
    # Se falhar, tenta importar do mesmo diretório com caminho relativo
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from auth import token_obrigatorio, gerar_token

from flask_cors import CORS
from werkzeug.security import check_password_hash
import os
from dotenv import load_dotenv
import json
from datetime import datetime, timedelta
import re
from flasgger import Swagger 

load_dotenv()

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
                print("[INFO] O arquivo de credenciais pode estar corrompido ou inválido")
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
                cred = None
        except Exception as init_error:
            print(f"[ERRO] Erro inesperado ao inicializar Firebase: {init_error}")
            cred = None
    else:
        print("[ERRO] Não foi possível conectar ao Firebase - credenciais ausentes ou inválidas")
        print("[INFO] Para corrigir:")
        print("  1. Acesse https://console.firebase.google.com")
        print("  2. Selecione seu projeto")
        print("  3. Vá em Configurações > Contas de serviço")
        print("  4. Gere uma nova chave privada")
        print("  5. Baixe e substitua o arquivo na pasta backend/")
        print("[INFO] O aplicativo continuará funcionando em modo offline para testes")
        
except Exception as e:
    print(f"[ERRO] Falha geral na configuração do Firebase: {e}")
    import traceback
    traceback.print_exc()
    print("[INFO] Aplicativo continuará em modo offline")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "catraca123")
CORS(app, origins="*")

# Versão do OpenAPI
app.config['SWAGGER'] = {
    'openapi': '3.0.3'
}

# Tentar carregar Swagger se o arquivo existir
try:
    openapi_path = os.path.join(os.path.dirname(__file__), "openapi.yaml")
    if os.path.exists(openapi_path):
        swagger = Swagger(app, template_file=openapi_path)
        print("[OK] Swagger carregado")
    else:
        print("[AVISO] Arquivo openapi.yaml não encontrado")
except Exception as e:
    print(f"[AVISO] Erro ao carregar Swagger: {e}")

# ---------------------
#   ROTA RAIZ (STATUS DA API)
# ---------------------
@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "status": "online",
        "api": "API da Catraca",
        "mensagem": "A API está rodando perfeitamente!",
        "firebase_conectado": db is not None
    }), 200

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
        # Mock para testes sem Firebase
        return 1
    
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

# ---------------------
#   ROTAS DE ALUNOS (CRUD)
# ---------------------

# LISTAR TODOS
@app.route("/alunos", methods=["GET"])
@token_obrigatorio
def listar_todos_alunos():
    if not FIREBASE_CONNECTED:
        return jsonify({"error": "Banco de dados não conectado. Configure as credenciais do Firebase primeiro.", "modo": "offline"}), 503
    
    try:
        alunos = []
        for doc in db.collection("alunos").stream():
            d = doc.to_dict()
            if "data_cadastro" in d and d["data_cadastro"]:
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
    if not FIREBASE_CONNECTED:
        return jsonify({"error": "Sistema funcionando em modo offline - Firebase não configurado"}), 503

    try:
        cpf_limpo = limpar_cpf(cpf)
        doc = db.collection("alunos").document(cpf_limpo).get()
        
        if not doc.exists:
            return jsonify({"error": "Usuário não está cadastrado"}), 404
            
        aluno = doc.to_dict()
        if "data_cadastro" in aluno and aluno["data_cadastro"]:
            aluno["data_cadastro"] = aluno["data_cadastro"].isoformat()
                
        return jsonify(aluno), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# CADASTRAR ALUNO
@app.route("/alunos", methods=["POST"])
@token_obrigatorio
def cadastrar_aluno():
    if not FIREBASE_CONNECTED:
        return jsonify({"error": "Sistema funcionando em modo offline - Firebase não configurado"}), 503

    dados = request.get_json()
    
    if not dados:
        return jsonify({"error": "Dados inválidos ou corpo da requisição vazio"}), 400
        
    cpf_limpo = limpar_cpf(dados.get("cpf", ""))

    if not validar_cpf_simples(cpf_limpo):
        return jsonify({"error": "CPF deve ter 11 números"}), 400
    
    if db.collection("alunos").document(cpf_limpo).get().exists:
        return jsonify({"error": "CPF já cadastrado no sistema"}), 409

    try:
        novo_id = obter_proximo_id()
        status = dados.get("status", "liberado")
        
        aluno_data = {
            "id":            novo_id,
            "nome":          dados.get("nome", "Sem Nome").strip(),
            "cpf":           cpf_limpo,
            "status":        status,
            "data_cadastro": firestore.SERVER_TIMESTAMP
        }
        
        db.collection("alunos").document(cpf_limpo).set(aluno_data)
        return jsonify({"message": "Aluno cadastrado com sucesso!", "id": novo_id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ALTERAR STATUS DO ALUNO
@app.route("/alunos/<string:cpf>/status", methods=["PUT", "PATCH"])
@token_obrigatorio
def alterar_status_aluno(cpf):
    if not FIREBASE_CONNECTED:
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
    if not FIREBASE_CONNECTED:
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
    if not FIREBASE_CONNECTED:
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

# ---------------------
#   ROTA DA CATRACA (VERIFICAR ACESSO)
# ---------------------
@app.route("/acesso/<string:cpf>", methods=["GET"])
def verificar_acesso(cpf):
    if not FIREBASE_CONNECTED:
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

# ---------------------
#   AUTENTICAÇÃO
# ---------------------
@app.route("/login", methods=["POST"])
def login():
    dados = request.get_json()
    if not dados:
        return jsonify({"error": "Dados não fornecidos"}), 400
    
    usuario = dados.get("usuario")
    senha = dados.get("senha")
    
    # Usuário: admin | Senha: adm123
    if usuario == "admin" and senha == "adm123":
        return jsonify({"token": gerar_token(usuario)}), 200
    return jsonify({"error": "Login inválido"}), 401

if __name__ == "__main__":
    app.run(debug=True, port=5000)