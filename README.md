# 🚀 Catraca Academia - Backend API

![Flask](https://img.shields.io/badge/Flask-3.1.0-000000?logo=flask&logoColor=white)
![Firebase](https://img.shields.io/badge/Firebase-Firestore-FFCA28?logo=firebase&logoColor=black)
![Python](https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white)
![JWT](https://img.shields.io/badge/JWT-Authentication-00BFFF?logo=json-web-tokens)
![Swagger](https://img.shields.io/badge/Swagger-Documentation-85EA2D?logo=swagger)
![Vercel](https://img.shields.io/badge/Deploy-Vercel-000000?logo=vercel)

**API robusta para controle de acesso em academias.**  
Gerencia o cadastro de alunos, valida entradas via CPF na catraca e fornece endpoints seguros para aplicações administrativas.

---

## 👥 Desenvolvido por

| Função | Desenvolvedor | GitHub |
|--------|---------------|--------|
| **Back-End** | Fonseca-Felix | [@fonseca-felix](https://github.com/fonseca-felix) |
| **Front-End** | mariajschimidt | [@mariajschimidt](https://github.com/mariajschimidt) |

> 💡 **Front-End:** [projeto-catraca-adm.vercel.app](https://projeto-catraca-adm.vercel.app) (Painel Admin)  
> 📱 **Front-End:** [projeto-catraca-tablet.vercel.app](https://projeto-catraca-tablet.vercel.app) (Catraca Tablet)

---

## 📋 Índice

- [Tecnologias Utilizadas](#-tecnologias-utilizadas)
- [Funcionalidades](#-funcionalidades)
- [Documentação da API](#-documentação-da-api)
- [Aplicações Front-End](#-aplicações-front-end)
- [Como Executar Localmente](#-como-executar-localmente)
- [Variáveis de Ambiente](#-variáveis-de-ambiente)
- [Estrutura do Projeto](#-estrutura-do-projeto)
- [Deploy na Vercel](#-deploy-na-vercel)
- [Licença](#-licença)

---

## 🛠 Tecnologias Utilizadas

| Tecnologia | Ícone | Descrição |
|------------|-------|-------------|
| **Python** | ![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white) | Linguagem principal |
| **Flask** | ![Flask](https://img.shields.io/badge/Flask-000000?logo=flask&logoColor=white) | Framework web minimalista |
| **Firebase Admin SDK** | ![Firebase](https://img.shields.io/badge/Firebase-FFCA28?logo=firebase&logoColor=black) | Conexão com Firestore |
| **PyJWT** | ![JWT](https://img.shields.io/badge/JWT-00BFFF?logo=json-web-tokens) | Autenticação via token |
| **Flask-CORS** | ![CORS](https://img.shields.io/badge/CORS-Enabled-4CAF50) | Compartilhamento de recursos |
| **Flasgger** | ![Swagger](https://img.shields.io/badge/Swagger-85EA2D?logo=swagger) | Documentação OpenAPI |
| **Gunicorn** | ![Gunicorn](https://img.shields.io/badge/Gunicorn-499848?logo=gunicorn) | Servidor WSGI |
| **Vercel** | ![Vercel](https://img.shields.io/badge/Vercel-000000?logo=vercel) | Hospedagem serverless |

---

## ⚙️ Funcionalidades

### 🔐 Autenticação
- Login de administrador com usuário/senha
- Geração de token JWT válido por 24h
- Proteção de rotas via decorator `@token_obrigatorio`

### 👨‍🎓 Gestão de Alunos (CRUD)
- Cadastro com nome, CPF e status inicial (`liberado`/`bloqueado`)
- Busca por CPF (com ou sem formatação)
- Listagem de todos os alunos
- Edição de nome e status
- Exclusão de alunos
- Geração automática de ID sequencial seguro (via transação Firestore)

### 🚪 Controle de Catraca
- Endpoint público `/acesso/<cpf>` → verifica se aluno está liberado
- Retorna acesso permitido/negado com mensagem clara
- Registro automático de logs de acesso no Firestore

### 📊 Logs & Relatórios
- Todos os acessos são armazenados em `logs_acesso`
- Endpoint de relatório geral (total, ativos, bloqueados, etc.)

### 📚 Documentação Interativa
- Swagger UI disponível em `/apidocs` (após configurar Flasgger)

---

## 📖 Documentação da API

A API segue o padrão **REST** e utiliza **Bearer Token** para rotas protegidas.

### 🔗 Base URL
```
https://catraca-api.vercel.app
```

### 🔑 Endpoints Públicos

| Método | Endpoint | Descrição |
|--------|----------|-------------|
| `GET`  | `/` | Status da API |
| `POST` | `/login` | Autenticação do administrador |
| `GET`  | `/acesso/{cpf}` | Validação de acesso na catraca |

### 🛡️ Endpoints Protegidos (Token Obrigatório)

| Método | Endpoint | Descrição |
|--------|----------|-------------|
| `GET`    | `/alunos` | Listar todos os alunos |
| `POST`   | `/alunos` | Cadastrar novo aluno |
| `GET`    | `/alunos/{cpf}` | Buscar aluno por CPF |
| `PUT`    | `/alunos/{cpf}` | Editar dados do aluno |
| `DELETE` | `/alunos/{cpf}` | Excluir aluno |
| `PATCH`  | `/alunos/{cpf}/status` | Alterar status (liberado/bloqueado) |
| `GET`    | `/alunos/ultimo_id` | Consultar último ID gerado |
| `GET`    | `/relatorios/geral` | Relatório estatístico |

### 📥 Exemplos de Requisição

#### Login
```bash
curl -X POST https://catraca-api.vercel.app/login \
  -H "Content-Type: application/json" \
  -d '{"usuario":"admin","senha":"admin123"}'
```

#### Cadastrar Aluno (Requer Token)
```bash
curl -X POST https://catraca-api.vercel.app/alunos \
  -H "Authorization: Bearer SEU_TOKEN_AQUI" \
  -H "Content-Type: application/json" \
  -d '{"nome":"João Silva","cpf":"12345678909","status":"liberado"}'
```

#### Verificar Acesso (Público)
```bash
curl https://catraca-api.vercel.app/acesso/12345678909
```

#### Resposta (Sucesso):
```json
{
  "acesso": true,
  "nome": "João Silva",
  "status": "liberado",
  "mensagem": "Liberado para entrar na academia"
}
```

#### Resposta (Bloqueado):
```json
{
  "acesso": false,
  "nome": "João Silva",
  "status": "bloqueado",
  "mensagem": "Conta bloqueada. Por favor, dirija-se à secretaria."
}
```

#### Resposta (Não Cadastrado):
```json
{
  "acesso": false,
  "mensagem": "Usuário não está cadastrado",
  "status": "inexistente"
}
```

📘 **Documentação completa e interativa:** Após rodar localmente, acesse `http://localhost:5000/apidocs`.  
O arquivo `openapi.yaml` também está disponível no repositório.

---

## 📱 Aplicações Front-End

Estas duas interfaces foram desenvolvidas por **mariajschimidt** e consomem a API para compor o ecossistema completo da Catraca Academia.

### 1. Painel Administrativo (Secretaria)
**Link:** [projeto-catraca-adm.vercel.app](https://projeto-catraca-adm.vercel.app)

**Funcionalidades:**
- 🔐 Login seguro (usuário/senha)
- 📋 Listagem de todos os alunos
- ➕ Cadastro de novos alunos (nome, CPF, status)
- ✏️ Edição de informações (nome, status)
- 🔄 Alteração rápida de status (liberar/bloquear)
- ❌ Exclusão de alunos
- 📊 Relatórios gerenciais

**Tecnologias utilizadas no front-end:**
- React.js
- Tailwind CSS
- Axios para consumo da API
- React Router DOM

### 2. Catraca Tablet (Front-End do Aluno)
**Link:** [projeto-catraca-tablet.vercel.app](https://projeto-catraca-tablet.vercel.app)

**Funcionalidades:**
- 📱 Interface touch otimizada para tablets
- ⌨️ Teclado virtual para digitar CPF
- ✅ Verificação em tempo real com a API
- 🟢 Feedback visual: acesso liberado (verde)
- 🔴 Feedback visual: acesso bloqueado (vermelho)
- 🕒 Registro automático de logs no backend

**Tecnologias utilizadas no front-end:**
- React.js
- CSS Modules
- Axios para consumo da API
- Design responsivo para tablets

---

## 🖥️ Como Executar Localmente

### Pré-requisitos
- Python 3.9+
- Conta no Firebase (Firestore)
- Arquivo de credenciais `firebase.json` ou variável `FIREBASE_CREDENTIALS`

### Passos

#### 1. Clone o repositório
```bash
git clone https://github.com/fonseca-felix/catraca-api.git
cd catraca-api
```

#### 2. Crie um ambiente virtual
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

#### 3. Instale as dependências
```bash
pip install -r requirements.txt
```

#### 4. Configure as variáveis de ambiente (crie um arquivo `.env`)
```env
SECRET_KEY=sua-chave-secreta-jwt
ADM_USUARIO=admin
ADM_SENHA=admin123
FIREBASE_CREDENTIALS={ ... }  # ou use firebase.json local
```

#### 5. Execute a aplicação
```bash
python app.py
```

#### 6. Acesse a aplicação
```
http://localhost:5000
```

---

## 🔐 Variáveis de Ambiente

| Variável | Descrição | Obrigatória |
|----------|-----------|-------------|
| `SECRET_KEY` | Chave para assinar tokens JWT | ✅ Sim |
| `ADM_USUARIO` | Login do administrador | ✅ Sim |
| `ADM_SENHA` | Senha do administrador (texto plano) | ✅ Sim |
| `FIREBASE_CREDENTIALS` | JSON com as credenciais do Firebase (para Vercel) | ❌ (use firebase.json local) |
| `VERCEL` | Definir como "true" quando em produção na Vercel | ❌ |

> ⚠️ **Nota de segurança:** Em produção, recomenda-se usar `ADM_SENHA_HASH` com `werkzeug.security.generate_password_hash` e `check_password_hash`. O código atual aceita texto plano para simplificar.

---

## 📁 Estrutura do Projeto

```
catraca-api/
├── app.py               # Aplicação principal (rotas, Firebase, token)
├── auth.py              # Decorator token_obrigatorio e gerar_token
├── firebase.json        # Credenciais do Firebase (não versionar)
├── openapi.yaml         # Documentação OpenAPI 3.0.3
├── requirements.txt     # Dependências Python
├── .env                 # Variáveis de ambiente (não versionar)
└── README.md            # Este arquivo
```

### auth.py (exemplo do conteúdo esperado)
```python
import jwt
from functools import wraps
from flask import request, jsonify, current_app
from datetime import datetime, timedelta

def gerar_token(usuario):
    payload = {
        'usuario': usuario,
        'exp': datetime.utcnow() + timedelta(hours=24)
    }
    return jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')

def token_obrigatorio(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'error': 'Token ausente'}), 401
        
        try:
            token = token.split(' ')[1]  # Bearer <token>
            jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
        except:
            return jsonify({'error': 'Token inválido ou expirado'}), 401
        
        return f(*args, **kwargs)
    return decorated
```

---

## 🚀 Deploy na Vercel

O projeto está configurado para deploy direto na Vercel:

1. Conecte seu repositório GitHub à Vercel
2. Adicione as variáveis de ambiente no painel da Vercel:
   - `SECRET_KEY`
   - `ADM_USUARIO`
   - `ADM_SENHA`
   - `FIREBASE_CREDENTIALS` (conteúdo do JSON como string)
   - `VERCEL=true`

3. O arquivo `vercel.json` (opcional) pode ser usado para ajustar rotas

### Exemplo de vercel.json:
```json
{
  "version": 2,
  "builds": [
    {
      "src": "app.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    {
      "src": "/(.*)",
      "dest": "app.py"
    }
  ]
}
```

---

## 📄 Licença

Este projeto está sob a licença MIT. Sinta-se livre para usar, modificar e distribuir.

---

## 🙏 Agradecimentos

- Firebase por fornecer a infraestrutura de banco de dados
- Vercel pela hospedagem simples e eficiente
- Comunidade open-source pelas bibliotecas utilizadas

---

## 📞 Contato

| Desenvolvedor | Função | GitHub | Email |
|---------------|--------|--------|-------|
| Fonseca-Felix | Back-End | [@fonseca-felix](https://github.com/fonseca-felix) | [felix.fonseca.senai@gmail.com](mailto:felix.fonseca.senai@gmail.com) |
| mariajschimidt | Front-End | [@mariajschimidt](https://github.com/mariajschimidt) | [maria.prestes.senai@gmail.com](mailto:maria.prestes.senai@gmail.com) |

---

**Feito por Fonseca-Felix 🎭(Back-End) e mariajschimidt ✨(Front-End)**
