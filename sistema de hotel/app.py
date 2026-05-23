import os
import io
import sqlite3
import pandas as pd
from datetime import datetime
from flask import Flask, render_template, request, redirect, session, flash, send_file

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, template_folder=os.path.join(BASE_DIR, 'templates'))
app.secret_key = "hotel_victor_secret_key"

DB_PATH = os.path.join(BASE_DIR, "hotel.db")

def conectar():
    return sqlite3.connect(DB_PATH)

def criar_ou_atualizar_tabela():
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS hospedes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        cpf TEXT UNIQUE,
        telefone TEXT,
        quarto INTEGER CHECK (quarto BETWEEN 1 AND 50),
        entrada DATE NOT NULL,
        saida DATE NOT NULL,
        diaria REAL DEFAULT 250.0 CHECK (diaria > 0),
        total REAL DEFAULT 0.0 CHECK (total >= 0),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        senha TEXT NOT NULL,
        tipo TEXT DEFAULT 'funcionario' CHECK (tipo IN ('funcionario', 'admin')),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reservas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        email TEXT,
        cpf TEXT,
        telefone TEXT,
        quarto TEXT,
        entrada DATE NOT NULL,
        saida DATE NOT NULL,
        status TEXT DEFAULT 'Agendada' CHECK (status IN ('Agendada', 'Confirmada', 'Cancelada')),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("SELECT id FROM usuarios WHERE email = 'admin@hotel.com'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO usuarios (nome, email, senha, tipo) VALUES (?, ?, ?, ?)", 
                       ("Administrador Master", "admin@hotel.com", "admin123", "admin"))

    conn.commit()
    conn.close()

def calcular_total(entrada_str, saida_str, valor_diaria):
    try:
        formato = "%Y-%m-%d"
        d1 = datetime.strptime(entrada_str, formato)
        d2 = datetime.strptime(saida_str, formato)
        dias = max((d2 - d1).days, 1)
        return round(dias * valor_diaria, 2)
    except:
        return 250.0

def quarto_esta_ocupado(quarto_numero, hospede_id=None):
    conn = conectar()
    cursor = conn.cursor()
    if hospede_id:
        cursor.execute("SELECT id FROM hospedes WHERE quarto = ? AND id != ? AND saida > date('now')", 
                      (quarto_numero, hospede_id))
    else:
        cursor.execute("SELECT id FROM hospedes WHERE quarto = ? AND saida > date('now')", (quarto_numero,))
    resultado = cursor.fetchone()
    conn.close()
    return resultado is not None

criar_ou_atualizar_tabela()

@app.route("/")
def index():
    if not session.get("logado"):
        return redirect("/login")
    return render_template("index.html")

@app.route("/login")
def login():
    if session.get("logado"):
        return redirect("/")
    return render_template("login.html")

@app.route("/logar", methods=["POST"])
def logar():
    email = request.form.get("usuario", "").strip()
    senha = request.form.get("senha", "").strip()
    
    if not email or not senha:
        return "<script>alert('Preencha email e senha!'); window.location='/login';</script>"
    
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nome, tipo FROM usuarios WHERE email = ? AND senha = ?", (email, senha))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        session["logado"] = True
        session["usuario_id"] = user[0]
        session["usuario_nome"] = user[1]
        session["usuario_tipo"] = user[2]
        return redirect("/")
    else:
        return "<script>alert('Credenciais inválidas!'); window.location='/login';</script>"

@app.route("/criar-conta")
def criar_conta():
    if not session.get("logado") or session.get("usuario_tipo") != "admin":
        return redirect("/")
    return render_template("conta.html")

@app.route("/salvar-conta", methods=["POST"])
def salvar_conta():
    if session.get("usuario_tipo") != "admin":
        return redirect("/")
    
    nome = request.form.get("nome", "").strip()
    email = request.form.get("email", "").strip().lower()
    senha = request.form.get("senha", "").strip()
    tipo = request.form.get("tipo", "funcionario")
    
    if len(senha) < 3:
        return "<script>alert('Senha deve ter pelo menos 3 caracteres!'); window.history.back();</script>"
    
    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO usuarios (nome, email, senha, tipo) VALUES (?, ?, ?, ?)", 
                      (nome, email, senha, tipo))
        conn.commit()
        return redirect("/")
    except sqlite3.IntegrityError:
        return "<script>alert('Email já cadastrado!'); window.history.back();</script>"
    finally:
        conn.close()

@app.route("/sair")
def sair():
    session.clear()
    return redirect("/login")

@app.route("/cadastro")
def cadastro():
    if not session.get("logado"):
        return redirect("/login")
    return render_template("cadastro.html")

@app.route("/salvar", methods=["POST"])
def salvar():
    if not session.get("logado"):
        return redirect("/login")
    
    nome = request.form.get("nome", "").strip()
    cpf = request.form.get("cpf", "").strip()
    telefone = request.form.get("telefone", "").strip()
    quarto_str = request.form.get("quarto", "").strip()
    entrada = request.form.get("data_entrada")
    saida = request.form.get("data_saida")
    
    try:
        num_quarto = int(quarto_str)
        if num_quarto < 1 or num_quarto > 50:
            return f"<script>alert('Quarto inválido! Use números de 1 a 50.'); window.history.back();</script>"
    except:
        return "<script>alert('Número de quarto inválido!'); window.history.back();</script>"
    
    if quarto_esta_ocupado(num_quarto):
        return f"<script>alert('Quarto {num_quarto} já ocupado!'); window.history.back();</script>"

    try:
        diaria_str = request.form.get("valor_diaria", "R$ 250,00").replace("R$ ", "").replace(".", "").replace(",", ".")
        diaria = float(diaria_str) or 250.0
    except:
        diaria = 250.0

    total = calcular_total(entrada, saida, diaria)
    
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO hospedes (nome, cpf, telefone, quarto, entrada, saida, diaria, total) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (nome, cpf, telefone, num_quarto, entrada, saida, diaria, total))
    conn.commit()
    conn.close()
    
    return redirect("/lista")

@app.route("/lista")
def lista():
    if not session.get("logado"):
        return redirect("/login")
    
    busca = request.args.get("busca", "").strip()
    conn = conectar()
    cursor = conn.cursor()
    
    if busca:
        cursor.execute("""
            SELECT id, nome, cpf, telefone, quarto, entrada, saida, diaria, total 
            FROM hospedes 
            WHERE nome LIKE ? OR cpf LIKE ? OR telefone LIKE ?
            ORDER BY saida DESC
        """, (f"%{busca}%", f"%{busca}%", f"%{busca}%"))
    else:
        cursor.execute("SELECT id, nome, cpf, telefone, quarto, entrada, saida, diaria, total FROM hospedes ORDER BY saida DESC")
    
    hospedes = cursor.fetchall()
    conn.close()
    return render_template("lista.html", hospedes=hospedes, termo_busca=busca)

@app.route("/excluir/<int:id>")
def excluir(id):
    if not session.get("logado"):
        return redirect("/login")
    
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM hospedes WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect("/lista")

@app.route("/editar/<int:id>")
def editar(id):
    if not session.get("logado") or session.get("usuario_tipo") != "admin":
        return redirect("/lista")
    
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hospedes WHERE id = ?", (id,))
    hospede = cursor.fetchone()
    conn.close()
    
    if not hospede:
        return redirect("/lista")
    
    return render_template("editar.html", hospede=hospede)

@app.route("/atualizar/<int:id>", methods=["POST"])
def atualizar(id):
    if not session.get("logado") or session.get("usuario_tipo") != "admin":
        return redirect("/lista")

    nome = request.form.get("nome", "").strip()
    cpf = request.form.get("cpf", "").strip()
    telefone = request.form.get("telefone", "").strip()
    quarto_str = request.form.get("quarto", "").strip()
    entrada = request.form.get("data_entrada")
    saida = request.form.get("data_saida")
    
    try:
        num_quarto = int(quarto_str)
        if num_quarto < 1 or num_quarto > 50:
            return f"<script>alert('Quarto inválido! 1-50'); window.history.back();</script>"
    except:
        return "<script>alert('Quarto inválido!'); window.history.back();</script>"

    if quarto_esta_ocupado(num_quarto, id):
        return f"<script>alert('Quarto {num_quarto} ocupado!'); window.history.back();</script>"

    try:
        diaria_str = request.form.get("valor_diaria", "250").replace(",", ".")
        diaria = float(diaria_str)
    except:
        diaria = 250.0

    total = calcular_total(entrada, saida, diaria)
    
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE hospedes SET nome=?, cpf=?, telefone=?, quarto=?, entrada=?, saida=?, diaria=?, total=? 
        WHERE id=?
    """, (nome, cpf, telefone, num_quarto, entrada, saida, diaria, total, id))
    conn.commit()
    conn.close()
    
    return redirect("/lista")

@app.route("/dashboard")
def dashboard():
    if not session.get("logado") or session.get("usuario_tipo") != "admin":
        return redirect("/")
    
    conn = conectar()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM hospedes WHERE saida > date('now')")
    total_hospedes = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM hospedes")
    total_registros = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(total) FROM hospedes")
    faturamento = cursor.fetchone()[0] or 0.0
    
    cursor.execute("SELECT COUNT(DISTINCT quarto) FROM hospedes WHERE saida > date('now')")
    ocupados = cursor.fetchone()[0]
    
    total_quartos = 50
    livres = total_quartos - ocupados
    
    conn.close()
    
    return render_template("dashboard.html", 
                         livres=livres,
                         ocupados=ocupados,
                         faturamento=faturamento,
                         total_hospedes=total_hospedes,
                         total_quartos=total_quartos)

@app.route("/quartos")
def visualizar_quartos():
    if not session.get("logado"):
        return redirect("/login")
    
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT h.quarto, h.nome, h.entrada, h.saida 
        FROM hospedes h 
        WHERE h.saida > date('now') 
        ORDER BY h.quarto
    """)
    ocupados = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()

    quartos_info = []
    for i in range(1, 51):
        if i in ocupados:
            quartos_info.append({
                "numero": i, 
                "status": "ocupado", 
                "hospede": ocupados[i]
            })
        else:
            quartos_info.append({
                "numero": i, 
                "status": "livre", 
                "hospede": None
            })

    return render_template("quartos.html", quartos=quartos_info)

@app.route("/reserva")
def pagina_reserva():
    if not session.get("logado"):
        return redirect("/login")
    return render_template("reserva.html")

@app.route("/salvar-reserva", methods=["POST"])
def salvar_reserva():
    if not session.get("logado"):
        return redirect("/login")
    
    nome = request.form.get("nome", "").strip()
    cpf = request.form.get("cpf", "").strip()
    telefone = request.form.get("telefone", "").strip()
    entrada = request.form.get("entrada")
    saida = request.form.get("saida")
    
    if not all([nome, cpf, telefone, entrada, saida]):
        return "<script>alert('Preencha todos os campos!'); window.history.back();</script>"

    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO reservas (nome, cpf, telefone, entrada, saida) 
        VALUES (?, ?, ?, ?, ?)
    """, (nome, cpf, telefone, entrada, saida))
    conn.commit()
    conn.close()
    
    return redirect("/lista_reservas")

@app.route("/lista_reservas")
def lista_reservas():
    if not session.get("logado"):
        return redirect("/login")
    
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reservas ORDER BY created_at DESC")
    reservas = cursor.fetchall()
    conn.close()
    return render_template("lista_reservas.html", reservas=reservas)

@app.route("/relatorio")
def gerar_relatorio():
    if not session.get("logado") or session.get("usuario_tipo") != "admin":
        return redirect("/lista")
    
    conn = conectar()
    df = pd.read_sql_query("""
        SELECT 
            nome, cpf, telefone, quarto, 
            entrada, saida, diaria, total,
            date(entrada, '+1 day') as primeiro_dia,
            julianday(saida) - julianday(entrada) as dias
        FROM hospedes 
        ORDER BY saida DESC
    """, conn)
    conn.close()
    
    if df.empty:
        return "<script>alert('Sem dados para exportar!'); window.location='/lista';</script>"
    
    output = io.BytesIO()
    df.to_csv(output, index=False, encoding='utf-8-sig', sep=';', decimal=',')
    output.seek(0)
    return send_file(output, 
                    mimetype="text/csv", 
                    as_attachment=True, 
                    download_name=f"relatorio_hospedes_{datetime.now().strftime('%Y%m%d')}.csv")

@app.route("/criar_banco")
def criar_banco():
    criar_ou_atualizar_tabela()
    return "✅ Banco criado/atualizado com sucesso!"

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)