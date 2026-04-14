import jwt
import os
from functools import wraps
from flask import request, jsonify
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "minha-chave-secreta-padrao")

def gerar_token(usuario):
    """Gera um token JWT para o usuário"""
    payload = {
        'usuario': usuario,
        'exp': datetime.utcnow() + timedelta(hours=24),
        'iat': datetime.utcnow()
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm='HS256')
    return token

def token_obrigatorio(f):
    """Decorator para proteger rotas que exigem autenticação"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        
        if not token:
            return jsonify({'error': 'Token não fornecido!'}), 401
        
        if token.startswith('Bearer '):
            token = token[7:]
        
        try:
            jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expirado!'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Token inválido!'}), 401
        
        return f(*args, **kwargs)
    return decorated