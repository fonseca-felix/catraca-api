import sys
import io
# Garante que o terminal aceite caracteres especiais (acentos)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from flask import Flask, jsonify, request
import firebase_admin
from firebase_admin import credentials, firestore
from auth import token_obrigatorio, gerar_token
from flask_cors import CORS
from werkzeug.security import check_password_hash
import os
from dotenv import load_dotenv
import json
from datetime import datetime, timedelta
import re

load_dotenv()

# ---------------------
#   INICIALIZAÇÃO FIREBASE
# ---------------------
try:
    if os.getenv("VERCEL") == "true":
        firebase_creds = os.getenv("FIREBASE_CREDENTIALS")
        cred = credentials.Certificate(json.loads(firebase_creds))
    else:
        cred = credentials.Certificate("firebase.json")
    
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("[OK] Conectado ao Firebase")
except Exception as e:
    print(f"[ERRO] Falha ao conectar: {e}")
    exit(1)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "minha-chave-secreta")
CORS(app, origins="*")

# ---------------------
#   ROTA RAIZ (STATUS DA API)
# ---------------------
@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "status": "online",
        "api": "API da Catraca",
        "mensagem": "A API está rodando perfeitamente!"
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
    try:
        contador_ref = db.collection("configuracoes").document("contador_alunos").get()
        if contador_ref.exists:
            return jsonify({"ultimo_id": contador_ref.get("ultimo_id")}), 200
        return jsonify({"ultimo_id": 0}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# BUSCAR UM ESPECÍFICO (DIGITA O CPF E APARECE)
@app.route("/alunos/<string:cpf>", methods=["GET"])
@token_obrigatorio
def buscar_aluno_por_cpf(cpf):
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
    dados = request.get_json()
    
    if not dados:
        return jsonify({"error": "Dados inválidos ou corpo da requisição vazio"}), 400
        
    cpf_limpo = limpar_cpf(dados.get("cpf", ""))

    if not validar_cpf_simples(cpf_limpo):
        return jsonify({"error": "CPF deve ter 11 números"}), 400
    
    if db.collection("alunos").document(cpf_limpo).get().exists:
        return jsonify({"error": "CPF já cadastrado no sistema"}), 409

    try:
        novo_id = obter_proximo_id() # Transacionado e seguro
        status = dados.get("status", "liberado")
        
        # Inserção explícita de apenas ID, Nome, CPF e Status
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

# EDITAR NOME DO ALUNO (Opcional, mas mantido para flexibilidade)
@app.route("/alunos/<string:cpf>", methods=["PUT"])
@token_obrigatorio
def editar_aluno(cpf):
    try:
        cpf_limpo = limpar_cpf(cpf)
        dados = request.get_json()
        
        aluno_ref = db.collection("alunos").document(cpf_limpo)
        if not aluno_ref.get().exists:
            return jsonify({"error": "Usuário não está cadastrado"}), 404

        campos_permitidos = ["nome", "status"]
        dados_seguros = {k: v for k, v in dados.items() if k in campos_permitidos}

        if not dados_seguros:
             return jsonify({"error": "Nenhum dado válido fornecido para atualização"}), 400

        aluno_ref.update(dados_seguros)
        return jsonify({"message": "Dados atualizados com sucesso", "atualizados": list(dados_seguros.keys())}), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# EXCLUIR ALUNO
@app.route("/alunos/<string:cpf>", methods=["DELETE"])
@token_obrigatorio
def excluir_aluno(cpf):
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
        
        db.collection("logs_acesso").add({
            **res, 
            "cpf": cpf_limpo, 
            "data_hora": firestore.SERVER_TIMESTAMP
        })
        
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
    usuario = dados.get("usuario")
    senha = dados.get("senha")
    
    # Se ADM_SENHA_HASH estiver no .env, use check_password_hash. Se não, use texto plano (apenas para teste inicial)
    adm_pass = os.getenv("ADM_SENHA", "admin123")
    if usuario == os.getenv("ADM_USUARIO", "admin") and senha == adm_pass:
        return jsonify({"token": gerar_token(usuario)}), 200
    return jsonify({"error": "Login inválido"}), 401

if __name__ == "__main__":
    app.run(debug=True, port=5000)
