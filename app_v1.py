import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# ===============================
# 1️⃣  CONFIGURACIÓN GOOGLE SHEETS
# ===============================

SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/drive.file",
]

# Cargar credenciales
creds = Credentials.from_service_account_file(
    "pagosfutbol-f392b5a5fb90.json", scopes=SCOPE
)
client = gspread.authorize(creds)

# Conectar con el archivo "Pagos"
SPREADSHEET_NAME = "Pagos"
spreadsheet = client.open(SPREADSHEET_NAME)

# ===============================
# 2️⃣  FUNCIONES AUXILIARES
# ===============================

def load_category_df(sheet_name):
    """Carga la hoja (categoría) como DataFrame"""
    sheet = spreadsheet.worksheet(sheet_name)
    data = sheet.get_all_records()
    return pd.DataFrame(data) if data else pd.DataFrame(columns=["Jugador"] + meses)


def save_category_df(sheet_name, df):
    """Guarda un DataFrame completo en la hoja"""
    sheet = spreadsheet.worksheet(sheet_name)
    sheet.clear()
    sheet.update([df.columns.values.tolist()] + df.values.tolist())


def add_player(sheet_name, player_name):
    """Agrega un nuevo jugador a la categoría"""
    df = load_category_df(sheet_name)
    if player_name in df["Jugador"].values:
        return False, "⚠️ El jugador ya existe."
    new_row = {"Jugador": player_name}
    for mes in meses:
        new_row[mes] = 0
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    save_category_df(sheet_name, df)
    return True, "✅ Jugador agregado correctamente."


def delete_player(sheet_name, player_name):
    """Elimina un jugador"""
    df = load_category_df(sheet_name)
    df = df[df["Jugador"] != player_name]
    save_category_df(sheet_name, df)
    return True, "🗑️ Jugador eliminado."


def update_payment(sheet_name, player_name, mes, monto):
    """Actualiza el pago de un jugador"""
    df = load_category_df(sheet_name)
    df.loc[df["Jugador"] == player_name, mes] = monto
    save_category_df(sheet_name, df)
    return True, "💰 Pago actualizado correctamente."


# ===============================
# 3️⃣  INTERFAZ STREAMLIT
# ===============================

st.set_page_config(page_title="Pagos Escuela de Fútbol", layout="wide")

st.title("⚽ Sistema de pagos - Escuela de Fútbol (Google Sheets)")

# Lista de meses
meses = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
]

# Selección de categoría
categorias = ["sub11", "sub12", "sub13"]
categoria = st.sidebar.selectbox("📁 Elegir categoría", categorias)

menu = st.sidebar.radio("📂 Navegación", ["👥 Gestión de jugadores", "💸 Registrar pago", "📊 Ver pagos"])

# ===============================
# 4️⃣  GESTIÓN DE JUGADORES
# ===============================
if menu == "👥 Gestión de jugadores":
    st.header("👥 Gestión de jugadores")
    
    # Agregar jugador
    new_player = st.text_input("Nombre del jugador")
    if st.button("Agregar jugador"):
        ok, msg = add_player(categoria, new_player)
        st.success(msg) if ok else st.warning(msg)

    # Eliminar jugador
    df = load_category_df(categoria)
    if not df.empty:
        player_to_delete = st.selectbox("Selecciona jugador a eliminar", df["Jugador"])
        if st.button("Eliminar jugador"):
            ok, msg = delete_player(categoria, player_to_delete)
            st.success(msg)

# ===============================
# 5️⃣  REGISTRAR PAGO
# ===============================
elif menu == "💸 Registrar pago":
    st.header("💸 Registrar pago")
    df = load_category_df(categoria)
    if df.empty:
        st.warning("No hay jugadores registrados.")
    else:
        player = st.selectbox("Jugador", df["Jugador"])
        mes = st.selectbox("Mes", meses)
        monto = st.number_input("Monto del pago", min_value=0)
        if st.button("Registrar pago"):
            ok, msg = update_payment(categoria, player, mes, monto)
            st.success(msg)

# ===============================
# 6️⃣  VER PAGOS
# ===============================
elif menu == "📊 Ver pagos":
    st.header("📊 Ver pagos")
    df = load_category_df(categoria)
    if df.empty:
        st.info("No hay datos para mostrar.")
    else:
        st.dataframe(df)
