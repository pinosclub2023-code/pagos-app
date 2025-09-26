# app.py
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import gspread.exceptions

st.set_page_config(page_title="Pagos Escuela de Fútbol", layout="wide")

# ===============================
# 0️⃣ CONFIG - MESES Y CATEGORÍAS
# ===============================
meses = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
]
categorias = [str(y) for y in range(2011, 2022)]  # 2011..2021

# ===============================
# 1️⃣ CONFIGURACIÓN GOOGLE SHEETS
# ===============================
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/drive.file",
]

creds_dict = st.secrets["gcp"]
creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPE)
client = gspread.authorize(creds)

SPREADSHEET_NAME = "Pagos"

@st.cache_resource
def get_spreadsheet():
    return client.open(SPREADSHEET_NAME)

spreadsheet = get_spreadsheet()

# ===============================
# 2️⃣ CREAR/OBTENER HOJAS SI NO EXISTEN
# ===============================
def get_or_create_worksheet(name, header=None):
    try:
        ws = spreadsheet.worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=name, rows="1000", cols="26")
        if header:
            ws.append_row(header)
    else:
        if header:
            values = ws.get_all_values()
            if not values or len(values) == 0 or (len(values) == 1 and all([c == "" for c in values[0]])):
                ws.clear()
                ws.append_row(header)
    return ws

def ensure_all_sheets_exist():
    jugadores_header = ["Nombres", "Apellidos", "Documento", "Fecha nacimiento", "Categoría",
                        "Nombre acudiente", "Dirección", "Cédula acudiente", "Correo", "Contacto"]
    get_or_create_worksheet("Jugadores", header=jugadores_header)
    cat_header = ["Jugador"] + meses
    for c in categorias:
        get_or_create_worksheet(c, header=cat_header)
    uniformes_header = ["Jugador", "Categoría", "Fecha", "Valor", "Observaciones"]
    get_or_create_worksheet("Uniformes", header=uniformes_header)
    torneos_header = ["Jugador", "Categoría", "Nombre Torneo", "Fecha", "Valor", "Observaciones"]
    get_or_create_worksheet("Torneos", header=torneos_header)

ensure_all_sheets_exist()

# ===============================
# 3️⃣ CARGA GLOBAL (OPTIMIZADA)
# ===============================

# ✅ Cache más alto para evitar bloqueos por exceso de lecturas
@st.cache_data(ttl=600)
def load_sheet(sheet_name):
    ws = spreadsheet.worksheet(sheet_name)
    return pd.DataFrame(ws.get_all_records())

# ✅ Solo cargamos las hojas generales (Jugadores, Uniformes, Torneos)
data = {}
data["Jugadores"] = load_sheet("Jugadores")
data["Uniformes"] = load_sheet("Uniformes")
data["Torneos"] = load_sheet("Torneos")

# ✅ Refrescar una sola hoja
def refresh_sheet(sheet_name):
    return load_sheet(sheet_name)

# ===============================
# 4️⃣ FUNCIONES DE ESCRITURA
# ===============================
def append_row_to_sheet(sheet_name, row_dict, header_order=None):
    ws = spreadsheet.worksheet(sheet_name)
    header = header_order if header_order else ws.row_values(1)
    row = [row_dict.get(col, "") for col in header]
    ws.append_row(row)

def save_df_to_sheet(sheet_name, df):
    ws = spreadsheet.worksheet(sheet_name)
    ws.clear()
    ws.update([df.columns.values.tolist()] + df.values.tolist())

# ===============================
# 5️⃣ GESTIÓN DE JUGADORES
# ===============================
def add_player_record(player_data):
    if not player_data.get("Documento"):
        return False, "El campo Documento es obligatorio."
    df_jug = data["Jugadores"]
    if not df_jug.empty and player_data["Documento"] in df_jug["Documento"].astype(str).values:
        return False, "Ya existe un jugador con ese documento."

    append_row_to_sheet("Jugadores", player_data)
    nombre_completo = f"{player_data.get('Nombres','')} {player_data.get('Apellidos','')}".strip()
    categoria = player_data.get("Categoría")
    if categoria in categorias:
        row = {"Jugador": nombre_completo}
        for mes in meses:
            row[mes] = 0
        append_row_to_sheet(categoria, row, header_order=["Jugador"] + meses)

    data["Jugadores"] = refresh_sheet("Jugadores")
    return True, "✅ Jugador agregado correctamente."

def delete_player_by_document(documento):
    ws = spreadsheet.worksheet("Jugadores")
    df = pd.DataFrame(ws.get_all_records())
    if df.empty:
        return False, "No hay jugadores registrados."
    if str(documento) not in df["Documento"].astype(str).values:
        return False, "Documento no encontrado."
    row_idx = df.index[df["Documento"].astype(str) == str(documento)][0] + 2
    ws.delete_rows(row_idx)
    data["Jugadores"] = refresh_sheet("Jugadores")
    return True, "✅ Jugador eliminado de 'Jugadores'."

# ===============================
# 6️⃣ PAGOS
# ===============================
def update_monthly_payment(categoria, jugador_nombre, mes, monto):
    df = load_sheet(categoria)  # ✅ carga bajo demanda
    if df.empty:
        return False, "Hoja de categoría vacía."
    mask = df["Jugador"].astype(str) == str(jugador_nombre)
    if not mask.any():
        return False, "Jugador no encontrado."
    df.loc[mask, mes] = monto
    save_df_to_sheet(categoria, df)
    return True, "💰 Pago mensual actualizado."

def register_uniform(jugador, categoria, fecha, valor, observaciones=""):
    row = {"Jugador": jugador, "Categoría": categoria, "Fecha": fecha, "Valor": valor, "Observaciones": observaciones}
    append_row_to_sheet("Uniformes", row)
    data["Uniformes"] = refresh_sheet("Uniformes")
    return True, "👕 Registro de uniforme guardado."

def register_torneo(jugador, categoria, nombre_torneo, fecha, valor, observaciones=""):
    row = {"Jugador": jugador, "Categoría": categoria, "Nombre Torneo": nombre_torneo,
           "Fecha": fecha, "Valor": valor, "Observaciones": observaciones}
    append_row_to_sheet("Torneos", row)
    data["Torneos"] = refresh_sheet("Torneos")
    return True, "🏆 Registro de torneo guardado."

# ===============================
# 7️⃣ INTERFAZ STREAMLIT
# ===============================
st.title("⚽ Sistema de pagos - Escuela de Fútbol (Google Sheets)")

menu = st.sidebar.radio("📂 Navegación", ["👥 Gestión de jugadores", "💸 Registrar pago", "📊 Ver datos"])

# ---------- GESTIÓN DE JUGADORES ----------
if menu == "👥 Gestión de jugadores":
    st.header("👥 Gestión de jugadores")
    with st.expander("Agregar nuevo jugador"):
        with st.form("form_add_player"):
            Nombres = st.text_input("Nombres")
            Apellidos = st.text_input("Apellidos")
            Documento = st.text_input("Documento")
            Fecha_nac = st.date_input("Fecha de nacimiento")
            Categoria = st.selectbox("Categoría", categorias)
            Nombre_acudiente = st.text_input("Nombre acudiente")
            Direccion = st.text_input("Dirección")
            Cedula_acudiente = st.text_input("Cédula acudiente")
            Correo = st.text_input("Correo")
            Contacto = st.text_input("Contacto")

            submitted = st.form_submit_button("Agregar jugador")
            if submitted:
                fecha_str = Fecha_nac.isoformat() if Fecha_nac else ""
                player_data = {
                    "Nombres": Nombres.strip(),
                    "Apellidos": Apellidos.strip(),
                    "Documento": Documento.strip(),
                    "Fecha nacimiento": fecha_str,
                    "Categoría": Categoria,
                    "Nombre acudiente": Nombre_acudiente.strip(),
                    "Dirección": Direccion.strip(),
                    "Cédula acudiente": Cedula_acudiente.strip(),
                    "Correo": Correo.strip(),
                    "Contacto": Contacto.strip()
                }
                ok, msg = add_player_record(player_data)
                st.success(msg) if ok else st.error(msg)

    st.markdown("---")
    st.subheader("Buscar / Eliminar jugadores")
    df_jug = data["Jugadores"]
    if df_jug.empty:
        st.info("No hay jugadores registrados.")
    else:
        query = st.text_input("Buscar por nombre o documento")
        result = df_jug[df_jug.apply(lambda row: query.lower() in " ".join(map(str, row.values)).lower(), axis=1)] if query else df_jug
        st.dataframe(result)
        doc_to_delete = st.text_input("Documento a eliminar")
        if st.button("Eliminar jugador"):
            if doc_to_delete:
                ok, msg = delete_player_by_document(doc_to_delete.strip())
                st.success(msg) if ok else st.error(msg)

# ---------- REGISTRAR PAGO ----------
elif menu == "💸 Registrar pago":
    st.header("💸 Registrar pago")
    tipo = st.selectbox("Tipo de pago", ["Mensualidad", "Uniforme", "Torneo"])

    if tipo == "Mensualidad":
        categoria = st.selectbox("Categoría", categorias)
        df_cat = load_sheet(categoria)
        if df_cat.empty:
            st.warning("No hay jugadores en esta categoría.")
        else:
            jugador = st.selectbox("Jugador", df_cat["Jugador"].tolist())
            mes = st.selectbox("Mes", meses)
            monto = st.number_input("Monto", min_value=0.0, step=1000.0)
            if st.button("Guardar mensualidad"):
                ok, msg = update_monthly_payment(categoria, jugador, mes, monto)
                st.success(msg) if ok else st.error(msg)

    elif tipo == "Uniforme":
        df_jug = data["Jugadores"]
        jugadores_list = (df_jug["Nombres"] + " " + df_jug["Apellidos"]).tolist() if not df_jug.empty else []
        jugador = st.selectbox("Jugador", jugadores_list)
        categoria = st.selectbox("Categoría", categorias)
        fecha = st.date_input("Fecha")
        valor = st.number_input("Valor", min_value=0.0, step=1000.0)
        obs = st.text_input("Observaciones")
        if st.button("Registrar uniforme"):
            fecha_str = fecha.isoformat() if fecha else ""
            ok, msg = register_uniform(jugador, categoria, fecha_str, valor, obs)
            st.success(msg) if ok else st.error(msg)

    elif tipo == "Torneo":
        df_jug = data["Jugadores"]
        jugadores_list = (df_jug["Nombres"] + " " + df_jug["Apellidos"]).tolist() if not df_jug.empty else []
        jugador = st.selectbox("Jugador", jugadores_list)
        categoria = st.selectbox("Categoría", categorias)
        nombre_torneo = st.text_input("Nombre Torneo")
        fecha = st.date_input("Fecha del torneo")
        valor = st.number_input("Valor", min_value=0.0, step=1000.0)
        obs = st.text_input("Observaciones")
        if st.button("Registrar torneo"):
            fecha_str = fecha.isoformat() if fecha else ""
            ok, msg = register_torneo(jugador, categoria, nombre_torneo, fecha_str, valor, obs)
            st.success(msg) if ok else st.error(msg)

# ---------- VER DATOS ----------
elif menu == "📊 Ver datos":
    st.header("📊 Ver datos (hojas)")
    hoja = st.selectbox("Selecciona hoja para ver", ["Jugadores"] + ["Uniformes", "Torneos"])
    df = data[hoja]
    st.dataframe(df if not df.empty else pd.DataFrame({"Info": ["No hay datos en esta hoja"]}))


   





